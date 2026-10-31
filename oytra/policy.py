"""THE single decision-precedence function (docs/RULE_PRECEDENCE.md). Used by engine._decide and backtest.policy.
Order: 1 risk band -> 2 first-time protection -> 3 unknown-history protection -> 4 hard data-quality rules
(override the band, incl. HOLD) -> 5 Rs 0 orders never nudged/held."""
import numpy as np

FIRST, RETURNING, UNKNOWN = "REPORTED_FIRST_TIME", "REPORTED_RETURNING", "UNKNOWN_OR_INCONSISTENT"
HISTORY_STATES = (FIRST, RETURNING, UNKNOWN)

def band(p, R):
    p = np.asarray(p, float)
    return np.where(p < R["ship_below_risk"], "SHIP", np.where(p < R["confirm_below_risk"], "CONFIRM",
                    np.where(p < R["nudge_below_risk"], "NUDGE", "HOLD"))).astype(object)

def apply_policy(p, hist, fake, unusable, zero, R, explain=False):
    """Vectorised. Returns actions (and, if explain, a list of the steps that changed each order)."""
    n = len(np.atleast_1d(p))
    hist = np.asarray(hist, object); fake = np.asarray(fake, bool); unusable = np.asarray(unusable, bool)
    zero = np.zeros(n, bool) if zero is None else np.asarray(zero, bool)
    a = band(np.atleast_1d(p), R); steps = [[] for _ in range(n)]
    def mark(m, tag):
        for i in np.where(m)[0]: steps[i].append(tag)
    if R["protect_first_time_customers"]:
        m = (a == "HOLD") & (hist == FIRST); a[m] = "NUDGE"; mark(m, "first_time_protect")
    if R.get("protect_unknown_history", True):
        m = (a == "HOLD") & (hist == UNKNOWN); a[m] = "NUDGE"; mark(m, "unknown_history_protect")
    hard = fake | unusable
    holdm = (fake & (R["fake_name_action"] == "hold")) | (unusable & (R["unusable_address_action"] == "hold"))
    m = hard & ~holdm; a[m] = "CONFIRM"; mark(m, "hard_rule_confirm")
    a[holdm] = "HOLD"; mark(holdm, "hard_rule_hold")
    m = zero & np.isin(a, ["NUDGE", "HOLD"]); a[m] = R.get("zero_value_order_action", "confirm").upper(); mark(m, "zero_value")
    return (a, steps) if explain else a
