import re, pandas as pd, numpy as np
from .config import ROOT
import os

def normalise_phone(p):
    d = re.sub(r"\D", "", str(p))
    if len(d) == 12 and d.startswith("91"): d = d[2:]
    return d

def load(path=None, report=None):
    """Load + clean. Returns labelled orders (DELIVERED/RTO only)."""
    df = pd.read_csv(path or os.path.join(ROOT, "data", "orders_sample.csv"), dtype={"phone": str})
    n0 = len(df)
    df = df.drop_duplicates()
    n_dup = n0 - len(df)
    df = df.drop_duplicates("order_id")
    df["status"] = df["final_status"].str.strip().str.upper()
    n_unlab = int((~df.status.isin(["RTO", "DELIVERED"])).sum())
    df = df[df.status.isin(["RTO", "DELIVERED"])].copy()
    df["rto"] = (df.status == "RTO").astype(int)
    df["dt"] = pd.to_datetime(df.order_datetime)
    df["phone10"] = df.phone.map(normalise_phone)
    df["phone_valid"] = df.phone10.str.fullmatch(r"[6-9]\d{9}").fillna(False)
    df["pincode"] = [str(int(x)) if pd.notna(x) else "" for x in df.pincode]
    df["city"] = df.city.fillna("")
    df = df.sort_values("dt").reset_index(drop=True)
    # products: pipe-separated list; validate against num_items (rule: trust the parsed list if they disagree)
    df["products"] = df["items"].fillna("").map(lambda s: [x.strip() for x in str(s).split("|") if x.strip()])
    n_parsed = df.products.str.len()
    n_mismatch = int((n_parsed != df.num_items).sum())
    df["num_items_reported"] = df.num_items
    df["num_items"] = np.where(n_parsed > 0, n_parsed, df.num_items).astype(int)
    # Rs 0 orders (free replacement / gift / 100% coupon): kept for analysis; engine never nudges or cancels them (see DECISION_LOG)
    df["zero_value"] = df.order_value <= 0
    add_indata_history(df)
    add_history_state(df)
    if report is not None:
        report.update(rows_raw=n0, exact_duplicates_removed=n_dup, unlabelled_removed=n_unlab,
                      rows_clean=len(df), zero_value_orders=int((df.order_value == 0).sum()),
                      missing_pincode=int((df.pincode == "").sum()), missing_city=int((df.city == "").sum()),
                      bad_phone=int((~df.phone_valid).sum()),
                      num_items_mismatch=n_mismatch,
                      prior_rto_gt_prior_orders=int((df.customer_prior_rto > df.customer_prior_orders).sum()))
    return df

OUTCOME_LAG_DAYS = 14   # an order's RTO/delivered outcome is only known ~2 weeks later

def add_indata_history(df):
    """Customer history rebuilt from THIS file (same normalised phone, strictly earlier orders).
    Used to audit the reported customer_prior_* columns. Outcomes count only after a 14-day lag,
    so nothing here could be unknown at decision time."""
    po, pr = np.zeros(len(df), int), np.zeros(len(df), int)
    for _, g in df.groupby("phone10"):
        if len(g) == 1: continue
        t, y, idx = g.dt.values, g.rto.values, g.index.values
        for k in range(len(g)):
            earlier = t < t[k]
            po[idx[k]] = earlier.sum()
            pr[idx[k]] = y[earlier & (t <= t[k] - np.timedelta64(OUTCOME_LAG_DAYS, "D"))].sum()
    df["indata_prior_orders"], df["indata_prior_rto"] = po, pr
    return df

def add_history_state(df):
    """history_state in {REPORTED_FIRST_TIME, REPORTED_RETURNING, UNKNOWN_OR_INCONSISTENT}.
    Inconsistency is judged ONLY against the same phone's EARLIER orders in this file (never later ones),
    so it is knowable at decision time:
      * reported prior_rto > reported prior_orders, or
      * an earlier order from this phone exists but reported prior_orders is lower than (earlier orders seen), or
      * reported prior_orders went DOWN versus the same phone's earlier order.
    Otherwise: 0 reported prior orders -> REPORTED_FIRST_TIME, else REPORTED_RETURNING.
    Phone is a weak customer key (no Shopify customer ID in this file): future work."""
    from .policy import FIRST, RETURNING, UNKNOWN
    st = np.where(df.customer_prior_orders == 0, FIRST, RETURNING).astype(object)
    st[(df.customer_prior_rto > df.customer_prior_orders).values] = UNKNOWN
    pos = {ix: k for k, ix in enumerate(df.index)}
    for _, g in df.groupby("phone10"):
        if len(g) == 1: continue
        t, rep, idx = g.dt.values, g.customer_prior_orders.values, g.index.values
        for k in range(len(g)):
            earlier = t < t[k]
            if not earlier.any(): continue
            if rep[k] < earlier.sum() or rep[k] < rep[earlier].max():
                st[pos[idx[k]]] = UNKNOWN
    df["history_state"] = st
    return df
