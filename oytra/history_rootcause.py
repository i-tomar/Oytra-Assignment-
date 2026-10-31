"""Root cause of the customer-history inconsistency -> reports/history_rootcause.json
Tests four explanations: (a) our datetime parse / sort, (b) one phone shared by different people,
(c) a counter that resets, (d) the source field itself does not follow the customer's sequence.
Run: python -m oytra.history_rootcause"""
import os, json, numpy as np, pandas as pd
from .config import ROOT
from .data import load

def ndec(frame, col):
    return int(frame.groupby("phone10")[col].apply(lambda x: (x.diff() < 0).any()).sum())

def main(n_shuffle=200):
    raw = pd.read_csv(os.path.join(ROOT, "data", "orders_sample.csv"), dtype={"phone": str})
    d = load(); d["oid"] = d.order_id.str[2:].astype(int)
    s = d.sort_values(["dt", "oid"], kind="mergesort")
    m = s[s.phone10.map(s.phone10.value_counts()) > 1]
    out = {}
    # (a) parse + sort
    fmt = raw.order_datetime.astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
    ties = m[m.duplicated(["phone10", "dt"], keep=False)]
    tie_phones = set(ties.phone10)
    po_dec = m.groupby("phone10").customer_prior_orders.apply(lambda x: (x.diff() < 0).any())
    pr_dec = m.groupby("phone10").customer_prior_rto.apply(lambda x: (x.diff() < 0).any())
    out["a_parse_and_sort"] = {
        "rows_matching_single_format_YYYY-MM-DD_HH:MM": f"{int(fmt.sum())}/{len(raw)}",
        "parse_failures": int(pd.to_datetime(raw.order_datetime, errors="coerce").isna().sum()),
        "order_id_vs_time_rank_correlation": round(float(d.oid.rank().corr(d.dt.rank())), 3),
        "phones_prior_orders_decreasing_time_sorted": int(po_dec.sum()),
        "phones_prior_orders_decreasing_if_sorted_by_order_id": ndec(d.sort_values("oid"), "customer_prior_orders"),
        "phones_prior_rto_decreasing_time_sorted": int(pr_dec.sum()),
        "phones_prior_rto_decreasing_excluding_same_minute_ties": int(pr_dec[[p not in tie_phones for p in pr_dec.index]].sum()),
        "phones_prior_rto_decreasing_grouped_by_raw_phone_string": int(d.sort_values(["dt", "oid"], kind="mergesort").groupby("phone")
                                                                      .customer_prior_rto.apply(lambda x: (x.diff() < 0).any()).sum()),
        "same_phone_same_minute_order_pairs": int(s.duplicated(["phone10", "dt"]).sum()),
        "reading": "Every timestamp parses in one format; sorting is by the parsed time with order_id as a stable tie-break. "
                   "Order IDs are not in time order, so sorting by ID would be wrong, not right. Not our bug."}
    g = m.groupby("phone10")
    out["b_shared_phone"] = {"phones_with_2plus_orders": int(g.ngroups),
        "with_more_than_one_name": int((g.customer_name.nunique() > 1).sum()), "with_more_than_one_city": int((g.city.nunique() > 1).sum()),
        "with_more_than_one_pincode": int((g.pincode.nunique() > 1).sum()),
        "name_city_pairs_seen_on_more_than_one_phone": int((d.groupby(["customer_name", "city"]).phone10.nunique() > 1).sum()),
        "reading": "Same phone almost always carries the same name and city, so these are the same person; the address/pincode varies. "
                   "Name+city pairs on several phones are mostly common names (e.g. 'Priya Sharma'), so name is not a usable key."}
    diff = m.groupby("phone10").customer_prior_orders.diff()
    drops = diff < 0
    out["c_counter_reset"] = {"drops_in_prior_orders": int(drops.sum()), "drops_to_zero": int((drops & (m.customer_prior_orders == 0)).sum()),
        "drops_to_nonzero": int((drops & (m.customer_prior_orders > 0)).sum()),
        "reading": "Most drops land on 0, but 0 is also 75% of all values, so a 'reset' can't be told apart from a random draw; drops between non-zero values also occur."}
    rng = np.random.RandomState(0); bp, br = [], []
    for _ in range(n_shuffle):
        t = m.copy(); t["customer_prior_orders"] = rng.permutation(t.customer_prior_orders.values)
        t["customer_prior_rto"] = rng.permutation(t.customer_prior_rto.values)
        bp.append(ndec(t, "customer_prior_orders")); br.append(ndec(t, "customer_prior_rto"))
    first_app = m.groupby("phone10").cumcount() == 0
    single = d[d.phone10.map(d.phone10.value_counts()) == 1]
    out["d_source_field"] = {
        "prior_orders_values_when_above_0": {int(k): int(v) for k, v in d.customer_prior_orders[d.customer_prior_orders > 0].value_counts().sort_index().items()},
        "phones_decreasing_observed_vs_if_values_were_shuffled_randomly": {
            "prior_orders": [int(po_dec.sum()), round(float(np.mean(bp)), 1), [float(x) for x in np.percentile(bp, [2.5, 97.5])]],
            "prior_rto": [int(pr_dec.sum()), round(float(np.mean(br)), 1), [float(x) for x in np.percentile(br, [2.5, 97.5])]]},
        "reported_first_time_share": {"single_order_phones": round(float((single.customer_prior_orders == 0).mean()), 3),
            "repeat_phones_first_appearance": round(float((m[first_app].customer_prior_orders == 0).mean()), 3),
            "repeat_phones_later_appearances": round(float((m[~first_app].customer_prior_orders == 0).mean()), 3)},
        "reading": "The non-zero counts are flat across 1–5 (~100 each), and the ordering within a phone is about as inconsistent as random shuffling. "
                   "Yet single-order phones say 'first-time' 99.6% of the time. So the field knows *whether* someone is a repeat customer but not their sequence: "
                   "it is produced per order by the source (sample generator or export), not accumulated per customer."}
    # (e) does the counter follow order_id instead of time?
    steps = {}
    for key in ["oid", "dt"]:
        ss = m.sort_values([key, "oid"], kind="mergesort"); gg = ss.groupby("phone10")
        st = gg.customer_prior_orders.diff().dropna()
        steps[key] = {"steps": int(len(st)), "negative_steps": int((st < 0).sum()),
                      "reported_count_at_least_position": round(float((ss.customer_prior_orders >= gg.cumcount()).mean()), 3)}
    within = m.sort_values(["dt", "oid"], kind="mergesort").groupby("phone10").oid.diff().dropna()
    from .backtest import TEST_START
    te = d[d.dt >= TEST_START]
    later = 0
    for ph, grp in te.groupby("phone10"):
        allp = d[d.phone10 == ph]
        for _, r in grp.iterrows():
            later += bool(((allp["oid"] < r["oid"]) & (allp["dt"] > r["dt"])).any())
    out["e_order_id_sequence"] = {"by_order_id": steps["oid"], "by_timestamp": steps["dt"],
        "same_phone_order_id_increases_with_time_share": round(float((within > 0).mean()), 3),
        "september_orders_whose_phone_has_a_lower_id_order_timestamped_later": int(later), "september_orders": int(len(te)),
        "reading": "Sorted by order_id the counts mostly go up; sorted by timestamp they go up and down at random. Within a phone, a later timestamp has a "
                   "higher order_id only about half the time. So the source built the history in order_id order, and the timestamps do not follow that order."}
    out["verdict"] = ("Source-data issue. Not our parsing or sorting (one timestamp format, 0 parse failures, stable time sort), not one phone shared by different people "
                      "(same name/city on almost every repeat phone), and not a counter reset. The counts were accumulated in order_id order, but order_id and "
                      "order_datetime disagree, so in time order they look scrambled. We keep time order (the backtest must be time-based) and treat the fields "
                      "as reported signals, not exact counts. Because the order_id sequence may include orders dated later, the no-history model stays the worst case.")
    out["how_to_identify_first_time_customers"] = [
        "At order time, look up the Shopify customer ID (customer.id / orders_count) from the order webhook; it is maintained by Shopify, not re-typed.",
        "Fallback key: normalised phone (last 10 digits) + email, matched against OYTRA's own order table including orders still in transit.",
        "Count prior RTOs from courier final statuses already received, never from the order payload.",
        "Log the key used and the counts with each decision so they can be audited later."]
    json.dump(out, open(os.path.join(ROOT, "reports", "history_rootcause.json"), "w"), indent=1)
    print(json.dumps(out, indent=1)); return out

if __name__ == "__main__":
    main()
