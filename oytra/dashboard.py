"""Founder's morning dashboard -> dashboard/index.html (static, open in any browser).
'Latest day in data' = the latest day in the data (30 Sep 2026); the model was trained only on Apr-Aug.
Run: python -m oytra.dashboard"""
import os, json, html, datetime as dt
import pandas as pd
from .config import load_rules, load_econ, ROOT
from .data import load
from .engine import Engine
from .llm import RuleJudge
from .economics import breakdown, LABEL
from .policy import FIRST
from .dashboard_template import render

ORDER = ["SHIP", "CONFIRM", "NUDGE", "HOLD"]

def expected(dec, df, econ, R, hindsight=False):
    """Same breakdown() as the backtest: RTO cost avoided + prepaid delivered contribution - genuine lost - flow costs."""
    s = pdc = l = c = 0.0
    for a, p, y, v, h in zip(dec.action, dec.risk, df.rto, df.order_value, df.history_state):
        f = h == FIRST
        if hindsight: b = breakdown(a, y, v, f, econ, R)
        else:
            b1, b0 = breakdown(a, 1, v, f, econ, R), breakdown(a, 0, v, f, econ, R)
            b = [p * x + (1 - p) * z for x, z in zip(b1, b0)]
        s += b[0]; pdc += b[1]; l += b[2]; c += b[3]
    return {"saved": s, "prepaid": pdc, "lost": l, "costs": c, "net": s + pdc - l - c}

def rs(x): return ("−" if x < 0 else "") + "₹" + f"{abs(x):,.0f}"

def main():
    econ, R = load_econ(), load_rules()
    df = load(); eng = Engine.load(rules=R, econ=econ, judge=RuleJudge())
    day = df.dt.dt.normalize().max()
    sep = df[df.dt >= "2026-09-01"]
    dec_all = eng.decide_frame(sep)
    y_mask = sep.dt.dt.normalize() == day
    yd, ydec = sep[y_mask], dec_all[y_mask.values]
    est, hs = expected(ydec, yd, econ, R), expected(ydec, yd, econ, R, hindsight=True)
    w_mask = sep.dt >= day - pd.Timedelta(days=6)
    west = expected(dec_all[w_mask.values], sep[w_mask], econ, R)
    m_est, m_hs = expected(dec_all, sep, econ, R), expected(dec_all, sep, econ, R, hindsight=True)
    flag, y = dec_all.action.values != "SHIP", sep.rto.values
    meas = {"flagged": int(flag.sum()), "rto_flagged": int(y[flag].sum()), "rto_all": int(y.sum()),
            "flagged_delivered": int((flag & (y == 0)).sum()), "rto_rs_flagged": y[flag].sum() * econ["rto_loss"],
            "yflag": int((ydec.action != "SHIP").sum()), "yrto_flag": int(yd.rto.values[(ydec.action != "SHIP").values].sum())}
    counts = ydec.action.value_counts().reindex(ORDER, fill_value=0)
    trend = []
    for d, g in sep.assign(day=sep.dt.dt.normalize()).groupby("day"):
        dd = dec_all[(sep.dt.dt.normalize() == d).values]
        trend.append((d, expected(dd, g, econ, R)["net"], len(g)))
    bt = json.load(open(os.path.join(ROOT, "reports", "backtest.json")))
    wf = json.load(open(os.path.join(ROOT, "reports", "walkforward.json")))
    scen = {k: v["our_rules_net"] for k, v in bt["september_estimated_scenarios"].items()}   # ONE source: backtest.json
    hs_month = expected(dec_all, sep, econ, R, hindsight=True)
    assert round(hs_month["net"]) == scen["base"], (hs_month["net"], scen["base"])         # dashboard engine == backtest
    sm, rb = bt["model"]["september_metrics"], bt["september_risk_buckets"]
    page = render(day=day, yd=yd, ydec=ydec, sep=sep, R=R, econ=econ, counts=counts, meas=meas, est=est,
                  west=west, m_est=m_est, scen=scen, wf=wf, trend=trend, bt=bt, sm=sm, rb=rb)
    os.makedirs(os.path.join(ROOT, "dashboard"), exist_ok=True)
    path = os.path.join(ROOT, "dashboard", "index.html"); open(path, "w").write(page)
    summary = {"latest_day_in_data": str(day.date()), "orders_latest_day": int(len(yd)), "counts": {LABEL[k]: int(v) for k, v in counts.items()},
               "measured": {k: round(float(v)) for k, v in meas.items()},
               "estimated_latest_day_from_scores": {k: round(v) for k, v in est.items()},
               "estimated_latest_day_actual_outcomes_base": {k: round(v) for k, v in hs.items()},
               "september_estimated_net_from_scores": round(m_est["net"]),
               "september_estimated_net_actual_outcomes": {k: round(v) for k, v in scen.items()},
               "september_model_quality": {"roc_auc": bt["model"]["test_auc"], **{k: v for k, v in sm.items() if k != "majority_class_note"}}}
    json.dump(summary, open(os.path.join(ROOT, "dashboard", "summary.json"), "w"), indent=1)
    print(path); print(json.dumps(summary, indent=1))

if __name__ == "__main__":
    main()
