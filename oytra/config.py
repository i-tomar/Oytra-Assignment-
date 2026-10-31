import csv, os, io, yaml
from urllib.parse import urlparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class RulesError(ValueError):
    """A problem in config/rules.csv, explained in plain English."""

def _coerce(v):
    v = str(v).strip()
    if v.lower() in ("yes", "true"): return True
    if v.lower() in ("no", "false"): return False
    try: return float(v) if ("." in v or "e" in v.lower()) else int(v)
    except ValueError: return v

THRESHOLDS = ["ship_below_risk", "confirm_below_risk", "nudge_below_risk"]
SCENARIO_KEYS = ["confirm_catches_rto_share", "confirm_genuine_loss_share",
                 "prepaid_takeup_if_baseline_delivered", "prepaid_takeup_if_baseline_rto"]
SHARES = THRESHOLDS + SCENARIO_KEYS + [k + s for k in SCENARIO_KEYS for s in ("_conservative", "_optimistic")] + ["ops_max_friction_share"]
NON_NEG = ["prepaid_discount_rupees", "assumed_future_contribution_first_time_rupees", "reminder_after_hours", "payment_timeout_hours"]
BOOLS = ["protect_first_time_customers", "protect_unknown_history"]
CHOICES = {"fake_name_action": {"confirm", "hold"}, "unusable_address_action": {"confirm", "hold"},
           "no_reply_action_confirm": {"manual_review", "cancel", "ship"}, "no_reply_action_address": {"manual_review", "cancel"},
           "no_reply_action_nudge": {"confirm", "ship"}, "zero_value_order_action": {"confirm", "ship"}}
REQUIRED = SHARES + NON_NEG + BOOLS + list(CHOICES)

def validate_rules(r):
    """Raise RulesError with a plain-English message if any setting is missing or out of range."""
    errs = []
    missing = [k for k in REQUIRED if k not in r]
    if missing: errs.append("missing setting(s): " + ", ".join(missing))
    num = lambda k: isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)
    for k in SHARES:
        if k in r and not (num(k) and 0 <= r[k] <= 1):
            errs.append(f"{k} must be a number between 0 and 1 (it is '{r[k]}')")
    for k in NON_NEG:
        if k in r and not (num(k) and r[k] >= 0):
            errs.append(f"{k} must be a number of 0 or more (it is '{r[k]}')")
    for k in BOOLS:
        if k in r and not isinstance(r[k], bool): errs.append(f"{k} must be yes or no (it is '{r[k]}')")
    for k, ok in CHOICES.items():
        if k in r and str(r[k]).lower() not in ok: errs.append(f"{k} must be one of {sorted(ok)} (it is '{r[k]}')")
        elif k in r: r[k] = str(r[k]).lower()
    if all(num(k) for k in THRESHOLDS if k in r) and all(k in r for k in THRESHOLDS):
        a, b, c = (r[k] for k in THRESHOLDS)
        if not (0 < a < b < c < 1):
            errs.append(f"thresholds must go strictly up between 0 and 1: ship_below_risk ({a}) < confirm_below_risk ({b}) < nudge_below_risk ({c})")
    if errs: raise RulesError("config/rules.csv has a problem:\n  - " + "\n  - ".join(errs))
    return r

def _check_url(url):
    u = urlparse(url)
    if u.scheme != "https" or not u.netloc:
        raise RulesError(f"RULES_CSV_URL must be an https:// link to a published CSV (got '{url}')")
    return url

def load_rules(path=None):
    """Rules live in a plain CSV (open in Excel / Google Sheets). Set RULES_CSV_URL to a
    published Google-Sheet CSV link (https only) to read straight from a sheet. Always validated."""
    url = os.environ.get("RULES_CSV_URL")
    if url and path is None:
        import urllib.request
        text = urllib.request.urlopen(_check_url(url), timeout=10).read().decode()
    else:
        text = open(path or os.path.join(ROOT, "config", "rules.csv"), encoding="utf-8").read()
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or not {"setting", "value"} <= set(rows[0]):
        raise RulesError("config/rules.csv must have the columns: setting, value, what_it_means")
    seen = [row["setting"] for row in rows]
    dup = sorted({s for s in seen if seen.count(s) > 1})
    if dup: raise RulesError("config/rules.csv lists a setting twice: " + ", ".join(dup))
    return validate_rules({row["setting"].strip(): _coerce(row["value"]) for row in rows})

def scenarios(r):
    """Conservative / base / optimistic HYPOTHETICAL intervention assumptions, all read from rules.csv."""
    return {"conservative": {k: r[k + "_conservative"] for k in SCENARIO_KEYS},
            "base": {k: r[k] for k in SCENARIO_KEYS},
            "optimistic": {k: r[k + "_optimistic"] for k in SCENARIO_KEYS}}

def load_econ(path=None):
    e = yaml.safe_load(open(path or os.path.join(ROOT, "config", "economics.yaml")))
    e["rto_loss"] = e["forward_shipping"] + e["return_shipping"] + e["packaging_handling"] \
        + e["damage_rate"] * e["avg_product_cost"]
    return e
