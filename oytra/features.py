"""Deterministic features. Pure code/statistics - no LLM here except the judge() output."""
import numpy as np, pandas as pd
from .llm import RuleJudge

class HistoryStats:
    """Empirical-Bayes smoothed RTO rates: pincode shrinks to its state, state shrinks to global.
    With median 1 order per pincode, raw pincode rates are noise; smoothing fixes that."""
    def __init__(self, k_state=30, k_pin=8):
        self.k_state, self.k_pin = k_state, k_pin
    def fit(self, df):
        self.g = df.rto.mean()
        s = df.groupby("state").rto.agg(["sum", "count"])
        self.state = ((s["sum"] + self.k_state * self.g) / (s["count"] + self.k_state)).to_dict()
        p = df[df.pincode != ""].groupby(["pincode", "state"]).rto.agg(["sum", "count"]).reset_index()
        self.pin = {(r.pincode): ((r["sum"] + self.k_pin * self.state.get(r.state, self.g)) / (r["count"] + self.k_pin), r["count"])
                    for _, r in p.iterrows()}
        return self
    def state_rate(self, state): return self.state.get(state, self.g)
    def pin_rate(self, pincode, state):
        v = self.pin.get(pincode)
        return v[0] if v else self.state_rate(state)
    def pin_count(self, pincode):
        v = self.pin.get(pincode); return v[1] if v else 0

def logit(p): p = np.clip(p, 1e-3, 1 - 1e-3); return np.log(p / (1 - p))

FEATURES = ["pin_logit", "first_time", "prior_rto", "prior_rto_rate", "meta_first_time",
            "single_item", "address_score", "name_fake", "phone_invalid", "value_k", "night"]

# Used only by the model-variant experiments (oytra/variants.py), NOT by the production model.
# Products are never a decision input: see DECISION_LOG ("never cancel because of a product").
PRODUCTS = ["Claw Clip Set", "Heatless Curling Set", "Satin Pillowcase", "Satin Bonnet", "Microfiber Hair Towel",
            "Scrunchies 6pk", "Hair Oil 100ml", "Rice Water Shampoo Bar"]
PRODUCT_FEATURES = ["p_" + p.lower().replace(" ", "_") for p in PRODUCTS]
HISTORY_FEATURES = ["first_time", "prior_rto", "prior_rto_rate", "meta_first_time"]          # from reported customer_prior_* columns
NON_HISTORY = [f for f in FEATURES if f not in HISTORY_FEATURES]
QUALITY_FEATURES = [f + "_q" for f in HISTORY_FEATURES] + ["hist_unknown"]   # history zeroed when UNKNOWN_OR_INCONSISTENT + flag
# The three history models compared by oytra/history_variants.py (chronological validation inside Apr-Aug)
HISTORY_MODELS = {"no_history": NON_HISTORY, "reported_history": FEATURES, "history_quality_flag": NON_HISTORY + QUALITY_FEATURES}
SIMPLICITY_ORDER = ["no_history", "reported_history", "history_quality_flag"]   # simplest first
INDATA_HISTORY_FEATURES = ["indata_first_time", "indata_prior_rto", "indata_prior_orders"]  # rebuilt from this file

def _missing(v):
    """True when reported history is absent, None, NaN or non-numeric."""
    if v is None or isinstance(v, bool): return v is None
    try: return bool(pd.isna(float(v)))
    except (TypeError, ValueError): return True

def _num(v):
    """Reported history value, or 0 when missing (missing rows are UNKNOWN_OR_INCONSISTENT)."""
    return 0 if _missing(v) else v

def _reported_state(r):
    if _missing(r.customer_prior_orders) or _missing(r.customer_prior_rto): return "UNKNOWN_OR_INCONSISTENT"
    if r.customer_prior_rto > r.customer_prior_orders: return "UNKNOWN_OR_INCONSISTENT"
    return "REPORTED_FIRST_TIME" if r.customer_prior_orders == 0 else "REPORTED_RETURNING"

def build(df, stats, judge=None, judged=None):
    judge = judge or RuleJudge()
    rows = []
    for i, r in enumerate(df.itertuples()):
        j = judged[i] if judged is not None else judge.judge(r.customer_name, r.address, r.city, r.pincode)
        hs = getattr(r, "history_state", None) or _reported_state(r)
        po, pr = _num(r.customer_prior_orders), _num(r.customer_prior_rto)
        first = int(po == 0)
        unk = int(hs == "UNKNOWN_OR_INCONSISTENT")
        rows.append({
            "pin_logit": logit(stats.pin_rate(r.pincode, r.state)),
            "first_time": first,
            "prior_rto": min(pr, 2),
            "prior_rto_rate": pr / max(po, 1),
            "meta_first_time": int(first and r.utm_source == "meta_ads"),
            "single_item": int(r.num_items == 1),
            "address_score": j["address_score"],
            "name_fake": int(j["name_fake"]),
            "phone_invalid": int(not r.phone_valid),
            "value_k": r.order_value / 1000.0,
            "night": int(pd.Timestamp(r.dt).hour < 6),
            "hist_unknown": unk,
            "_judge": j, "_history_state": hs,
        })
        for f in HISTORY_FEATURES: rows[-1][f + "_q"] = 0 if unk else rows[-1][f]
        if hasattr(r, "products"):
            for p, f in zip(PRODUCTS, PRODUCT_FEATURES): rows[-1][f] = int(p in r.products)
        if hasattr(r, "indata_prior_orders"):
            rows[-1].update(indata_first_time=int(r.indata_prior_orders == 0), indata_prior_rto=min(r.indata_prior_rto, 2),
                            indata_prior_orders=min(r.indata_prior_orders, 3))
    return pd.DataFrame(rows, index=df.index)

assert not set(FEATURES) & set(PRODUCT_FEATURES), "products must never drive the production decision"

def chrono_pin_logit(df, k_state=30, k_pin=8, freq="7D"):
    """Chronological expanding-window pincode feature for TRAINING rows (replaces the random OOF):
    each weekly block is encoded with stats fitted only on orders placed BEFORE that block starts.
    The first block has no earlier data and gets logit(0.5)=0 ("no information").
    Limitation: earlier orders' outcomes are used without the 14-day outcome lag (same as at test time)."""
    out = pd.Series(0.0, index=df.index)
    t0 = df.dt.min().normalize()
    blk = ((df.dt - t0) // pd.Timedelta(freq)).values
    for b in np.unique(blk):
        m = blk == b
        start = t0 + b * pd.Timedelta(freq)
        prev = df[df.dt < start]
        if len(prev) == 0: continue
        st = HistoryStats(k_state, k_pin).fit(prev)
        out[m] = [logit(st.pin_rate(p, s)) for p, s in zip(df.pincode[m], df.state[m])]
    return out

def oof_pin_logit(df, k_state=30, k_pin=8, folds=5, seed=0):
    """OLD (kept only for leakage_audit comparison). Random out-of-fold pincode feature for training rows so the model can't memorise its own labels."""
    out = pd.Series(0.0, index=df.index)
    f = np.random.RandomState(seed).randint(0, folds, len(df))
    for k in range(folds):
        st = HistoryStats(k_state, k_pin).fit(df[f != k])
        out[f == k] = [logit(st.pin_rate(p, s)) for p, s in zip(df.pincode[f == k], df.state[f == k])]
    return out
