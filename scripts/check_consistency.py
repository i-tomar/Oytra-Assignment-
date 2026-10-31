"""Cross-artifact consistency check: every headline number must agree across reports/*.json, the dashboard,
the memo and the docs, and retired/misleading wording must not reappear. Exit 1 on any mismatch.
Run: .venv/bin/python scripts/check_consistency.py   (also run by run_all.sh and the tests)"""
import os, sys, json, re, glob
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda *p: json.load(open(os.path.join(ROOT, *p)))
T = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, *p)) else ""
def rs(v): return ("−" if v < 0 else "") + f"₹{abs(v):,}"

problems = []
def check(ok, msg):
    if not ok: problems.append(msg)

bt, wf, hs = J("reports", "backtest.json"), J("reports", "walkforward.json"), J("reports", "history_model_selection.json")
dash, html = J("dashboard", "summary.json"), T("dashboard", "index.html")
sep = bt["september"]; ours = sep["our_rules"]; ops = sep["ops_cancel_risky (Operations)"]
scen = {k: v["our_rules_net"] for k, v in bt["september_estimated_scenarios"].items()}

# 1. backtest internal
check(scen["base"] == ours["net"], "base scenario != our_rules net")
c = ours
check(abs(c["rto_cost_avoided"] + c["prepaid_delivered_contribution"] - c["lost_genuine"] - c["flow_costs"] - c["net"]) <= 2, "our_rules components do not add up to net")
check(ops["marketing_metric_acquisition_spend_on_held_first_time_rupees"] == ops["first_time_labelled_held_or_cancelled"] * 300, "Marketing metric != held first-time x 300")
# 2. september_decisions.csv == backtest counts
d = pd.read_csv(os.path.join(ROOT, "reports", "september_decisions.csv"))
LABEL = {"SHIP": "Ship as-is", "CONFIRM": "Ship after confirmation", "NUDGE": "Nudge to prepaid", "HOLD": "Hold / cancel"}
for a, n in d.action.value_counts().items():
    check(ours["counts"].get(LABEL[a], 0) == n, f"september_decisions.csv {a}={n} != backtest {ours['counts'].get(LABEL[a])}")
check(len(d) == bt["test"]["orders"], "september_decisions.csv row count")
# 3. walk-forward Sep row (fixed policy) == backtest
s = [r for r in wf["A_fixed_policy_stability"] if r["month"] == "Sep"][0]
check(s["net_HYPOTHETICAL"] == scen, f"walkforward Sep {s['net_HYPOTHETICAL']} != backtest scenarios {scen}")
check(s["roc_auc"] == bt["model"]["test_auc"], "walkforward Sep AUC != backtest AUC")
check(hs["selected_model"] == wf["production_history_model"], "history model in walkforward != selection")
hsel = hs["september_retrospective_holdout"]["selected"]; sm = bt["model"]["september_metrics"]
check(hsel["roc_auc"] == bt["model"]["test_auc"], "history selection Sep AUC != backtest AUC")
check(hsel["brier"] == sm["brier"] and hsel["ece"] == sm["ece_10bin"] and hsel["pr_auc"] == round(sm["pr_auc_average_precision"], 3), "history selection Sep Brier/ECE/PR-AUC != backtest")
check(hsel["net_rupees_base_HYPOTHETICAL"] == ours["net"], "history selection Sep net != backtest")
# 4. dashboard
check(dash["september_estimated_net_actual_outcomes"] == scen, "dashboard scenarios != backtest")
check(dash["measured"]["flagged"] == sum(v for k, v in ours["counts"].items() if k != "Ship as-is"), "dashboard flagged != backtest")
for k, v in scen.items(): check(rs(v) in html, f"dashboard html missing scenario {k} {rs(v)}")
for r in wf["A_fixed_policy_stability"]:
    for k, v in r["net_HYPOTHETICAL"].items(): check(rs(v) in html, f"dashboard html missing walk-forward {r['month']} {k} {rs(v)}")
check(f"Latest day in data ({pd.Timestamp(dash['latest_day_in_data']):%d %b %Y})" in html, "dashboard latest-day label")
check(f"latest day in data has {dash['orders_latest_day']} orders" in html, "dashboard latest-day order count")
# 5. memo / README / docs quote the same headline numbers
memo, readme = T("memo", "memo.md"), T("README.md")
for name, txt in (("memo/memo.md", memo), ("README.md", readme)):
    if not txt: problems.append(f"{name} missing"); continue
    for k in ("conservative", "base", "optimistic"): check(rs(scen[k]) in txt, f"{name} missing {k} {rs(scen[k])}")
    check(rs(ops["net"]) in txt, f"{name} missing Ops net {rs(ops['net'])}")
    check(f"{bt['model']['test_auc']:.3f}" in txt, f"{name} missing AUC")
# 6. retired / misleading wording
BANNED = [(r"\bprevented\b", "simulated avoided RTOs must not be called prevented"), (r"Yesterday'?s? COD", "use 'Latest day in data'"),
          (r"~10 orders", "latest day has a measured count"), (r"prepaid_takeup_rate\b", "retired rules.csv key"),
          (r"new_customer_future_value_rupees", "retired rules.csv key"), (r"₹612\.38", "old CAC-inflated value"), (r"gsk_[A-Za-z0-9]{8,}", "API key")]
files = [os.path.join(ROOT, p) for p in ("README.md", "memo/memo.md", "dashboard/index.html", "DECISION_LOG.md")] + glob.glob(os.path.join(ROOT, "docs", "*.md")) \
        + glob.glob(os.path.join(ROOT, "oytra", "*.py")) + glob.glob(os.path.join(ROOT, "reports", "*.md")) + glob.glob(os.path.join(ROOT, "config", "*"))
for f in files:
    txt = open(f, encoding="utf-8").read()
    for pat, why in BANNED:
        for m in re.finditer(pat, txt):
            line = txt[:m.start()].count("\n") + 1; ctx = txt.splitlines()[line - 1]
            if pat == r"\bprevented\b" and re.search(r"not (be called )?prevented|never .*prevented|not .{0,40}prevented|NOT prevented", ctx, re.I): continue
            if f.endswith("DECISION_LOG.md") and "retired" in ctx.lower(): continue
            problems.append(f"{os.path.relpath(f, ROOT)}:{line}: '{m.group(0)}' ({why})")

if problems:
    print("CONSISTENCY PROBLEMS:"); [print(" -", p) for p in problems]; sys.exit(1)
print("Consistency check passed: backtest, walk-forward, history selection, dashboard, memo and README agree.")
