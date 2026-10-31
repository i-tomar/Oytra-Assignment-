import os, pytest
os.environ.pop("OPENAI_API_KEY", None); os.environ.pop("GROQ_API_KEY", None); os.environ["OYTRA_USE_LLM"] = "0"
from oytra.config import load_rules, load_econ
from oytra.economics import value, breakdown
from oytra.llm import RuleJudge, classify_intent_rules
from oytra.whatsapp import Conversation, DEMO_ORDER, DEMO_ORDER_EN
from oytra.data import load
from oytra import backtest

E, R = load_econ(), load_rules()

def test_rto_loss_matches_brief():
    assert E["rto_loss"] == pytest.approx(65 + 65 + 25 + 0.08 * 180)

def test_cancel_only_pays_at_very_high_risk():
    assert value("SHIP", 0.5, 649, True, E, R) > value("HOLD", 0.5, 649, True, E, R)
    assert value("SHIP", 0.95, 649, False, E, R) < 0

def test_breakdown_hold_on_genuine_loses_margin():
    b = breakdown("HOLD", 0, 649, False, E, R)
    assert b.rto_cost_avoided == 0 and b.genuine_lost == pytest.approx(0.62 * 649 - 90)

@pytest.mark.parametrize("name,addr,fake,kind", [
    ("asdf", "call me", True, "unusable"), ("Test Order", ".", True, "unusable"),
    ("Priya Iyer", "Flat 12, Lotus Apartments, Anna Nagar", False, "complete"),
    ("Ravi Kumar", "Hanuman Mandir ke saamne", False, "landmark_only"), ("Ravi Kumar", "Patna", False, "unusable")])
def test_rule_judge(name, addr, fake, kind):
    j = RuleJudge().judge(name, addr, "", "800001")
    assert j["name_fake"] == fake and j["address_kind"] == kind

@pytest.mark.parametrize("text,intent", [("haan ji", "yes"), ("YES", "yes"), ("nahi chahiye", "no"), ("haan nahi chahiye", "no"),
    ("upi se pay karunga", "pay_online"), ("kab aayega", "question_eta"), ("🙏", "unclear")])
def test_intent(text, intent):
    assert classify_intent_rules(text) == intent

def test_whatsapp_branches():
    c = Conversation(dict(DEMO_ORDER), "confirm"); assert c.lang == "hi"; c.receive("haan"); assert c.state == "CONFIRMED"
    c = Conversation(dict(DEMO_ORDER_EN), "confirm"); assert c.lang == "en"; c.receive("no"); assert c.state == "CANCELLED"
    c = Conversation(dict(DEMO_ORDER), "confirm"); c.receive("??"); c.receive("hmm"); assert c.state == "HANDOFF"
    c = Conversation(dict(DEMO_ORDER), "confirm"); c.wait(12); assert c.reminded and c.state == "AWAITING"; c.wait(12); assert c.state == "MANUAL_OPS_REVIEW"; assert c.ops_review("ship") == "ship" and c.state == "CONFIRMED" and c.released == 1
    c = Conversation(dict(DEMO_ORDER), "nudge"); c.receive("1"); assert c.state == "PAYMENT_PENDING" and c.payment_status == "pending"
    c = Conversation(dict(DEMO_ORDER), "nudge"); c.wait(24); assert c.flow == "confirm" and c.state == "AWAITING"

def test_data_cleaning():
    rep = {}; d = load(report=rep)
    assert rep["exact_duplicates_removed"] == 30 and d.order_id.is_unique and set(d.status) == {"RTO", "DELIVERED"}

def test_backtest_and_engine():
    res = backtest.main()
    assert res["train"]["to"] < res["test"]["from"]           # no time leakage
    assert res["model"]["test_auc"] > 0.65
    assert res["september"]["our_rules"]["net"] > res["september"]["ops_cancel_risky (Operations)"]["net"]
    from oytra.engine import Engine
    from oytra.decide import EXAMPLES
    eng = Engine.load(judge=RuleJudge())
    for o in EXAMPLES:
        r = eng.decide(o)
        assert r["action"] in {"SHIP", "CONFIRM", "NUDGE", "HOLD"} and len(r["reason"]) > 20

# ---- added after the brief review ----
import json, csv, numpy as np
from oytra.whatsapp import LanguageStore, write_event_log
from oytra.data import add_indata_history
from oytra.features import FEATURES, PRODUCT_FEATURES
from oytra.variants import history_audit
import pandas as pd

def _nudge(**kw): return Conversation({**DEMO_ORDER_EN, "order_id": "T1", "phone": "9000000001"}, "nudge",
                                     decision={"action": "NUDGE", "risk": 0.7, "model_version": "test"}, **kw)

def test_payment_success_only_from_gateway():
    c = _nudge(); c.receive("1"); c.receive("I paid")          # customer's word is not proof
    assert c.state == "PAYMENT_PENDING" and c.payment_status == "pending"
    c.payment_result(True); assert c.state == "PAID" and c.payment_status == "paid"

def test_payment_fail_twice_falls_back_to_cod_confirmation():
    c = _nudge(); c.receive("1"); c.payment_result(False)
    assert c.state == "PAYMENT_PENDING"
    c.payment_result(False); assert c.state == "AWAITING" and c.flow == "confirm" and c.payment_status == "cod"
    c.receive("yes"); assert c.state == "CONFIRMED"

def test_payment_timeout_falls_back_to_cod():
    c = _nudge(); c.receive("1"); c.wait(R["payment_timeout_hours"] - 0.5); assert c.state == "PAYMENT_PENDING"
    c.wait(0.5); assert c.flow == "confirm" and c.state == "AWAITING"

def test_event_log_has_model_version_score_action(tmp_path):
    c = _nudge(); c.receive("1"); c.payment_result(True)
    rows = write_event_log([c], str(tmp_path / "ev"))
    assert {"payment_success", "message:paid"} <= {r["event"] for r in rows}
    assert all(r["model_version"] == "test" and r["risk"] == 0.7 and r["action"] == "NUDGE" and r["ts"] for r in rows)
    assert len(open(tmp_path / "ev.jsonl").readlines()) == len(rows) == len(list(csv.DictReader(open(tmp_path / "ev.csv"))))

def test_language_asked_once_then_remembered(tmp_path):
    st = LanguageStore(str(tmp_path / "lang.json"))
    c = Conversation({**DEMO_ORDER, "phone": "9000000002"}, "confirm", store=st)
    assert c.lang == "hi" and "ENGLISH" in c.log[0][2]
    c.receive("English"); assert c.lang == "en"
    c2 = Conversation({**DEMO_ORDER, "phone": "9000000002"}, "confirm", store=LanguageStore(str(tmp_path / "lang.json")))
    assert c2.lang == "en" and "HINDI" not in c2.log[0][2] and "ENGLISH" not in c2.log[0][2]

def test_zero_value_orders_never_nudged_or_held():
    p = np.array([0.95, 0.7, 0.95]); z = np.array([True, True, False]); f = np.zeros(3, bool)
    a = backtest.policy(p, f, f, f, R, zero=z)
    assert list(a[:2]) == ["CONFIRM", "CONFIRM"] and a[2] in ("HOLD", "NUDGE")

def test_products_not_in_production_model():
    assert not set(FEATURES) & set(PRODUCT_FEATURES)

def test_num_items_validated_and_indata_history():
    d = load(); assert (d.num_items == d.products.apply(len)).all()
    t = pd.DataFrame({"phone10": ["1", "1", "1"], "dt": pd.to_datetime(["2026-04-01", "2026-04-05", "2026-05-01"]), "rto": [1, 0, 0]})
    t = add_indata_history(t)
    assert list(t.indata_prior_orders) == [0, 1, 2]
    assert list(t.indata_prior_rto) == [0, 0, 1]   # the 1 Apr RTO is only 'known' after 14 days

def test_history_audit_runs():
    h = history_audit(load()); assert h["phones_with_more_than_one_order"] > 0

# --- review round 3 ---
def test_duplicate_paid_webhook_releases_once():
    c = _nudge(); c.receive("1")
    c.payment_result(True, "evt_1"); assert c.state == "PAID" and c.released == 1
    assert c.payment_result(True, "evt_1") is None          # same id retried
    assert c.payment_result(True, "evt_2") is None          # different id, but already PAID (state guard)
    assert c.payment_result(False, "evt_3") is None and c.state == "PAID"
    assert c.released == 1 and sum(e["event"] == "order_released" for e in c.events) == 1
    assert sum(e["event"] == "payment_duplicate_ignored" for e in c.events) == 3

def test_failed_webhook_retry_not_counted_twice():
    c = _nudge(); c.receive("1"); c.payment_result(False, "f1"); c.payment_result(False, "f1")
    assert c.pay_attempts == 1 and c.state == "PAYMENT_PENDING"

def test_no_reply_goes_to_manual_review_configurable():
    for flow, order in (("confirm", DEMO_ORDER), ("address", {**DEMO_ORDER_EN, "address": "call me"})):
        c = Conversation(dict(order), flow); c.wait(12); c.wait(12); assert c.state == "MANUAL_OPS_REVIEW"
    c = Conversation({**DEMO_ORDER_EN, "address": "call me"}, "address"); c.wait(24)
    assert c.ops_review("ship") is None and c.state == "MANUAL_OPS_REVIEW"     # no address -> can't ship
    assert c.ops_review("ship", address="Flat 3, MG Road, near SBI") == "ship"
    c = Conversation(dict(DEMO_ORDER), "confirm", rules={**R, "no_reply_action_confirm": "cancel"}); c.wait(24); assert c.state == "CANCELLED"
    c = Conversation(dict(DEMO_ORDER), "confirm"); c.wait(24); c.ops_review("cancel"); assert c.state == "CANCELLED" and c.released == 0

def test_bad_rules_value_rejected(tmp_path):
    p = tmp_path / "r.csv"; txt = open(os.path.join(os.path.dirname(__file__), "..", "config", "rules.csv")).read()
    p.write_text(txt.replace("no_reply_action_confirm,manual_review", "no_reply_action_confirm,maybe"))
    from oytra.config import RulesError
    with pytest.raises(RulesError, match="no_reply_action_confirm"): load_rules(str(p))

def test_zero_value_bad_address_has_one_consistent_reason():
    from oytra.engine import Engine
    e = Engine.load(judge=RuleJudge())
    o = {"order_id": "Z1", "order_datetime": "2026-09-10 10:00", "customer_name": "Asha Rao", "phone": "9876543210",
         "address": "call me", "city": "Patna", "state": "Bihar", "pincode": 800001, "order_value": 0, "items": "Satin Bonnet",
         "num_items": 1, "customer_prior_orders": 0, "customer_prior_rto": 0, "utm_source": "meta_ads"}
    r = e.decide(o)
    assert r["action"] == "CONFIRM" and "cancel if customer" not in r["reason"] and "payment link" not in r["reason"]
    assert "₹0 order" in r["reason"] and "correct details" in r["reason"]


def test_metrics_match_hand_computed_values():
    from oytra.metrics import average_precision, brier, majority_accuracy, risk_buckets
    y, p = [1, 0, 1, 0], [0.9, 0.8, 0.7, 0.1]
    assert abs(average_precision(y, p) - (1 + 2 / 3) / 2) < 1e-9      # precision 1/1 and 2/3 at the two positives
    assert abs(brier(y, p) - (0.01 + 0.64 + 0.09 + 0.01) / 4) < 1e-9
    assert majority_accuracy([1, 0, 0, 0]) == 0.75
    b = risk_buckets(y, p)
    assert sum(r["orders"] for r in b) == 4 and sum(r["rto"] for r in b) == 2


def test_threshold_maths_doc_reproduces_from_code():
    import importlib.util, os
    spec = importlib.util.spec_from_file_location("ctm", os.path.join(os.path.dirname(__file__), "..", "scripts", "check_threshold_maths.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    _, missing = m.main()
    assert missing == []


def test_leakage_audit_and_history_rootcause_reports():
    import json, os
    from oytra.config import ROOT
    from oytra import leakage_audit
    leakage_audit.main()  # deterministic; history_rootcause is run by run_all.sh (200 shuffles) and only read here
    la = json.load(open(os.path.join(ROOT, "reports", "leakage_audit.json")))
    hr = json.load(open(os.path.join(ROOT, "reports", "history_rootcause.json")))
    assert "verdict" in la and "verdict" in hr
    assert hr["a_parse_and_sort"]["phones_prior_rto_decreasing_grouped_by_raw_phone_string"] == 74


def test_dashboard_has_both_themes_and_toggle():
    import subprocess, sys, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run([sys.executable, "-m", "oytra.dashboard"], cwd=root, check=True, capture_output=True)
    page = open(os.path.join(root, "dashboard", "index.html"), encoding="utf-8").read()
    assert "[data-theme=light]" in page and "[data-theme=dark]" in page
    assert 'data-set-theme="light"' in page and 'data-set-theme="dark"' in page
    assert "prefers-color-scheme" in page and "localStorage" in page
    assert "http://" not in page.replace('xmlns="http://www.w3.org/2000/svg"', "") and "https://" not in page
    for label in ["Ship as-is", "Ship after confirmation", "Nudge to prepaid", "Hold / cancel"]:
        assert label in page
