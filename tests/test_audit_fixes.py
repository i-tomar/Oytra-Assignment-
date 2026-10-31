"""Regression tests for the audit fixes (C1-C6 and fixes 1-10)."""
import os, itertools, json, pytest, numpy as np, pandas as pd
os.environ.pop("OPENAI_API_KEY", None); os.environ.pop("GROQ_API_KEY", None); os.environ["OYTRA_USE_LLM"] = "0"
from oytra.config import load_rules, load_econ, RulesError, ROOT
from oytra.economics import value, breakdown, outcome, ACTIONS
from oytra.policy import apply_policy, FIRST, RETURNING, UNKNOWN
from oytra.llm import classify_intent_rules, RuleJudge
from oytra.whatsapp import Conversation, DEMO_ORDER, DEMO_ORDER_EN
from oytra import backtest

E, R = load_econ(), load_rules()
RULES_TXT = open(os.path.join(ROOT, "config", "rules.csv")).read()

# ---------- Fix 1: one NUDGE formula ----------
@pytest.mark.parametrize("a", ACTIONS)
def test_value_equals_breakdown_weighted_over_grid(a):
    for p, v, first, sc in itertools.product(np.linspace(0, 1, 11), [0, 199, 649, 1499], [True, False],
                                            ["conservative", "base", "optimistic"]):
        from oytra.economics import SCENARIOS
        r = {**R, **SCENARIOS[sc]}
        lhs = value(a, p, v, first, E, r) - value("SHIP", p, v, first, E, r)
        rhs = p * breakdown(a, 1, v, first, E, r).net + (1 - p) * breakdown(a, 0, v, first, E, r).net
        assert lhs == pytest.approx(rhs, abs=1e-9)
        assert value(a, p, v, first, E, r) == pytest.approx(p * outcome(a, 1, v, first, E, r) + (1 - p) * outcome(a, 0, v, first, E, r))

def test_nudge_costs_counted_once_and_components_separate():
    b1, b0 = breakdown("NUDGE", 1, 649, False, E, R), breakdown("NUDGE", 0, 649, False, E, R)
    t1, t0, q = R["prepaid_takeup_if_baseline_rto"], R["prepaid_takeup_if_baseline_delivered"], E["prepaid_rto_rate"]
    fee = E["payment_gateway_fee"] * 649
    assert b1.flow_costs == pytest.approx(E["whatsapp_msg_cost"] * (2 - t1) + t1 * (1 - q) * (R["prepaid_discount_rupees"] + fee))
    assert b0.flow_costs == pytest.approx(E["whatsapp_msg_cost"] * (2 - t0) + t0 * (1 - q) * (R["prepaid_discount_rupees"] + fee))
    assert b1.prepaid_delivered_contribution > 0 and b0.prepaid_delivered_contribution == 0

def test_no_cac_in_base_value():
    assert R["assumed_future_contribution_first_time_rupees"] == 0
    assert value("HOLD", 0.5, 649, True, E, R) == value("HOLD", 0.5, 649, False, E, R)

# ---------- Fix 3: precedence table (docs/RULE_PRECEDENCE.md) ----------
def _pol(p, hist, fake=False, unus=False, zero=False, r=None):
    return apply_policy(np.array([p]), [hist], [fake], [unus], [zero], r or R)[0]

def test_precedence_fake_name_first_time():            # row 1
    assert _pol(0.88, FIRST, fake=True) == "CONFIRM"
    assert _pol(0.88, FIRST, fake=True, r={**R, "fake_name_action": "hold"}) == "HOLD"   # row 1b

def test_precedence_unusable_address_very_high_risk():  # row 2 (KT100327 pattern)
    assert _pol(0.943, RETURNING, unus=True) == "CONFIRM"
    assert _pol(0.10, RETURNING, unus=True) == "CONFIRM"

def test_precedence_unknown_history_very_high_risk():   # row 3
    assert _pol(0.93, UNKNOWN) == "NUDGE"
    assert _pol(0.93, RETURNING) == "HOLD"

def test_unknown_history_never_moves_towards_hold():
    for p in np.linspace(0, 0.999, 60):
        order = ACTIONS.index
        assert order(_pol(p, UNKNOWN)) <= order(_pol(p, RETURNING))
        assert _pol(p, UNKNOWN) != "HOLD"

def test_precedence_zero_value():                       # rows 4, 4b
    assert _pol(0.10, RETURNING, zero=True) == "SHIP"
    assert _pol(0.95, RETURNING, zero=True) == "CONFIRM"
    assert _pol(0.70, FIRST, zero=True) == "CONFIRM"

def test_precedence_hard_rule_beats_every_band():       # row 5
    for p in [0.1, 0.5, 0.7, 0.95]:
        assert _pol(p, RETURNING, fake=True) == "CONFIRM"
        assert _pol(p, RETURNING, unus=True, r={**R, "unusable_address_action": "hold"}) == "HOLD"

def test_KT100327_engine_and_backtest_agree():
    from oytra.data import load
    from oytra.engine import Engine
    df = load(); o = df[df.order_id == "KT100327"]
    assert len(o) == 1
    eng = Engine.load(judge=RuleJudge())
    d = eng.decide_frame(o).iloc[0]
    j = RuleJudge().judge(o.customer_name.iloc[0], o.address.iloc[0], o.city.iloc[0], o.pincode.iloc[0])
    assert j["address_score"] == 0 and d.action == "CONFIRM"
    assert backtest.policy(np.array([d.risk]), None, [j["name_fake"]], [True], R, zero=[False], hist=o.history_state.values)[0] == "CONFIRM"

def test_engine_actions_equal_backtest_policy_on_september():
    p = os.path.join(ROOT, "reports", "september_decisions.csv")
    d = pd.read_csv(p)
    from oytra.data import load
    te = load().set_index("order_id").loc[d.order_id]
    J = RuleJudge(); jj = [J.judge(r.customer_name, r.address, r.city, r.pincode) for r in te.itertuples()]
    a = backtest.policy(d.risk.values, None, [j["name_fake"] for j in jj], [j["address_score"] == 0 for j in jj], R,
                        zero=te.zero_value.values, hist=te.history_state.values)
    # risk is rounded to 3dp in the CSV; allow disagreement only exactly at a threshold
    near = np.isclose(d.risk.values[:, None], [R["ship_below_risk"], R["confirm_below_risk"], R["nudge_below_risk"]], atol=6e-4).any(1)
    assert ((a == d.action.values) | near).all()

# ---------- Fix 2: shown rupees ----------
def test_reason_states_disagreement_with_best_ev():
    d = pd.read_csv(os.path.join(ROOT, "reports", "september_decisions.csv"))
    dis = d[d.action != d.best_ev_action]
    assert all("per-order ₹ estimate favours" in r for r in dis.reason)
    assert not any("per-order ₹ estimate favours" in r for r in d[d.action == d.best_ev_action].reason)

# ---------- Fix 4: WhatsApp ----------
@pytest.mark.parametrize("text", ["keep COD", "cod rakho", "COD hi rakho", "Cash on delivery", "cash pe dena", "COD hi theek hai, online nahi"])
def test_keep_cod_phrases(text):
    assert classify_intent_rules(text) == "keep_cod"

def _nudge(): return Conversation({**DEMO_ORDER_EN, "order_id": "T9", "phone": "9000000009"}, "nudge",
                                  decision={"action": "NUDGE", "risk": 0.7, "model_version": "test"})

@pytest.mark.parametrize("reply", ["2", "keep COD", "cod rakho"])
def test_confirmed_cod_is_released(reply):
    c = _nudge(); c.receive(reply); assert c.state == "CONFIRMED" and c.released == 1 and c.payment_status == "cod"
    c = _nudge(); c.receive("1"); c.receive(reply); assert c.state == "CONFIRMED" and c.released == 1

def test_yes_and_address_fix_release():
    c = Conversation(dict(DEMO_ORDER), "confirm"); c.receive("haan"); assert c.released == 1
    c = Conversation({**DEMO_ORDER_EN, "address": "call me"}, "address"); c.receive("Flat 4, Rose Apts, MG Road, Pune"); assert c.released == 1

def test_late_payment_after_cod_fallback_flagged():
    c = _nudge(); c.receive("1"); c.wait(R["payment_timeout_hours"]); c.receive("yes")
    assert c.state == "CONFIRMED" and c.released == 1
    c.payment_result(True, "late1")
    assert c.released == 1 and len(c.ops_flags) == 1 and c.ops_flags[0]["flag"] == "late_payment_after_cod_fallback" and c.ops_flags[0]["ts"]
    ev = [e for e in c.events if e["event"] == "late_payment_refund_review"]
    assert len(ev) == 1 and ev[0]["ts"]
    c.payment_result(True, "late1")                     # duplicate webhook stays idempotent
    assert len(c.ops_flags) == 1 and c.released == 1

def test_duplicate_payment_idempotent():
    c = _nudge(); c.receive("1"); c.payment_result(True, "e1"); c.payment_result(True, "e1"); c.payment_result(True, "e2")
    assert c.state == "PAID" and c.released == 1 and c.ops_flags == []

# ---------- Fix 5: rules validation ----------
@pytest.mark.parametrize("old,new,msg", [
    ("confirm_catches_rto_share,0.5,", "confirm_catches_rto_share,1.5,", "between 0 and 1"),
    ("prepaid_takeup_if_baseline_rto,0.1,", "prepaid_takeup_if_baseline_rto,-0.1,", "between 0 and 1"),
    ("confirm_below_risk,0.6,", "confirm_below_risk,0.3,", "strictly up"),
    ("nudge_below_risk,0.875,", "nudge_below_risk,0.6,", "strictly up"),
    ("fake_name_action,confirm,", "fake_name_action,delete,", "fake_name_action must be one of"),
    ("prepaid_discount_rupees,50,", "prepaid_discount_rupees,fifty,", "number of 0 or more"),
    ("protect_first_time_customers,yes,", "protect_first_time_customers,maybe,", "yes or no"),
])
def test_rules_validation(tmp_path, old, new, msg):
    assert old in RULES_TXT
    f = tmp_path / "r.csv"; f.write_text(RULES_TXT.replace(old, new))
    with pytest.raises(RulesError, match=msg): load_rules(str(f))

def test_rules_missing_row(tmp_path):
    f = tmp_path / "r.csv"; f.write_text("\n".join(l for l in RULES_TXT.splitlines() if not l.startswith("ops_max_friction_share")))
    with pytest.raises(RulesError, match="missing setting"): load_rules(str(f))

def test_rules_url_must_be_https(monkeypatch):
    monkeypatch.setenv("RULES_CSV_URL", "http://example.com/rules.csv")
    with pytest.raises(RulesError, match="https"): load_rules()

# ---------- Fix 6: history state ----------
def test_history_state_uses_only_earlier_orders():
    from oytra.data import add_history_state
    t = pd.DataFrame({"phone10": ["1", "1", "2"], "dt": pd.to_datetime(["2026-04-01", "2026-04-05", "2026-04-01"]),
                      "customer_prior_orders": [3, 0, 0], "customer_prior_rto": [0, 0, 1]})
    add_history_state(t)
    # row 0 says 3 prior orders; a LATER row saying 0 must not make row 0 inconsistent
    assert list(t.history_state) == [RETURNING, UNKNOWN, UNKNOWN]

def test_history_model_selected_without_september():
    h = json.load(open(os.path.join(ROOT, "reports", "history_model_selection.json")))
    assert all(f["fold"].split("test ")[1] < "2026-09" for m in h["results"].values() for f in m["folds"])
    assert "not an untouched test set" in h["september_retrospective_holdout"]["label"]

# ---------- Fix 7 / 8 / 9 ----------
def test_marketing_metric_not_in_net():
    b = json.load(open(os.path.join(ROOT, "reports", "backtest.json")))
    ops = b["september"]["ops_cancel_risky (Operations)"]
    assert ops["marketing_metric_acquisition_spend_on_held_first_time_rupees"] == ops["first_time_labelled_held_or_cancelled"] * E["cac"]
    assert "NOT profit" in b["marketing_metric_note"]

def test_chrono_pin_encoding_uses_only_earlier_orders():
    from oytra.data import load
    from oytra.features import chrono_pin_logit
    d = load(); d = d[d.dt < "2026-06-01"]
    base = chrono_pin_logit(d)
    i = len(d) - 5; d2 = d.copy(); d2.iloc[i:, d2.columns.get_loc("rto")] = 1 - d2.rto.iloc[i:]
    assert np.allclose(chrono_pin_logit(d2).iloc[:i - 200], base.iloc[:i - 200])   # later labels never reach earlier rows
    assert np.isclose(chrono_pin_logit(d2).iloc[i], base.iloc[i])                   # a row's own label never moves it

def test_walkforward_shows_negative_months_and_cap():
    w = json.load(open(os.path.join(ROOT, "reports", "walkforward.json")))
    assert [r["month"] for r in w["A_fixed_policy_stability"]] == ["Jun", "Jul", "Aug", "Sep"]
    assert all(c["argmax_friction_share"] <= w["C_ops_max_friction_share"] + 1e-9 for c in w["C_argmax_vs_bands"])
    md = open(os.path.join(ROOT, "reports", "walkforward.md")).read()
    neg = [r for r in w["A_fixed_policy_stability"] if min(r["net_HYPOTHETICAL"].values()) < 0]
    assert all(f"{min(r['net_HYPOTHETICAL'].values()):,}" in md for r in neg)

# ---------- Fix 10: LLM config hygiene ----------
def test_backtest_forces_rule_judge_and_no_key_in_repo():
    src = open(os.path.join(ROOT, "oytra", "backtest.py")).read()
    assert "judge = RuleJudge()" in src
    assert open(os.path.join(ROOT, ".env.example")).read().strip().endswith("GROQ_API_KEY=")
    gi = open(os.path.join(ROOT, ".gitignore")).read()
    assert ".llm_cache" in gi and "state/" in gi and ".env" in gi

def test_consistency_script_passes():
    import subprocess, sys
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_consistency.py")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
