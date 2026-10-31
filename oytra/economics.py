"""Rupee maths. ONE formula per action (audit fix C1).

breakdown(action, y, ...) = what the action changes vs shipping as COD, for an order whose outcome under
the ORIGINAL COD process would have been y (1 = RTO, 0 = delivered). 'Baseline RTO / delivered' is a
counterfactual category known only in hindsight, not an observable customer identity.
value(action, p, ...) = p * outcome(action, 1) + (1 - p) * outcome(action, 0)   (exactly; tested)

All intervention rates (confirm catch/loss, prepaid take-up) are HYPOTHETICAL until a pilot measures them.
prepaid_rto_rate (4%) is an ASSIGNMENT-PROVIDED assumption. Each cost is counted exactly once:
  * WhatsApp: 1 message for CONFIRM; for NUDGE 1 offer message + 1 confirmation message for those who don't switch
  * discount + payment-gateway fee: only on prepaid orders that are actually delivered
"""
from collections import namedtuple
from .config import scenarios as _scenarios, load_rules

ACTIONS = ["SHIP", "CONFIRM", "NUDGE", "HOLD"]
LABEL = {"SHIP": "Ship as-is", "CONFIRM": "Ship after confirmation", "NUDGE": "Nudge to prepaid", "HOLD": "Hold / cancel"}
SCENARIOS = _scenarios(load_rules())   # read from config/rules.csv (conservative / base / optimistic)

Breakdown = namedtuple("Breakdown", ["rto_cost_avoided", "prepaid_delivered_contribution", "genuine_lost", "flow_costs"])
Breakdown.net = property(lambda b: b.rto_cost_avoided + b.prepaid_delivered_contribution - b.genuine_lost - b.flow_costs)

def delivered_value(v, econ, rules=None):
    """Contribution of a delivered COD order: 62% gross margin minus forward shipping and packing.
    No customer-lifetime / CAC credit (base = 0; see assumed_future_contribution_first_time_rupees)."""
    return econ["gross_margin"] * v - econ["forward_shipping"] - econ["packaging_handling"]

def _V(v, first_time, econ, rules):
    return delivered_value(v, econ) + (rules.get("assumed_future_contribution_first_time_rupees", 0) if first_time else 0)

def breakdown(action, y, v, first_time, econ, rules):
    """Components vs ship-as-COD, given the baseline outcome y."""
    V, L = _V(v, first_time, econ, rules), econ["rto_loss"]
    c, g = rules["confirm_catches_rto_share"], rules["confirm_genuine_loss_share"]
    msg, q = econ["whatsapp_msg_cost"], econ["prepaid_rto_rate"]
    if action == "SHIP": return Breakdown(0.0, 0.0, 0.0, 0.0)
    if action == "HOLD": return Breakdown(L, 0.0, 0.0, 0.0) if y else Breakdown(0.0, 0.0, V, 0.0)
    if action == "CONFIRM": return Breakdown(c * L, 0.0, 0.0, msg) if y else Breakdown(0.0, 0.0, g * V, msg)
    if action != "NUDGE": raise ValueError(action)
    D, fee = rules["prepaid_discount_rupees"], econ["payment_gateway_fee"] * v
    if y:   # would have been RTO as COD
        t = rules["prepaid_takeup_if_baseline_rto"]
        # switchers: prepaid, delivered with prob 1-q (RTO cost avoided AND a delivered margin earned); rest -> confirmation
        return Breakdown(rto_cost_avoided=t * (1 - q) * L + (1 - t) * c * L,
                         prepaid_delivered_contribution=t * (1 - q) * V,
                         genuine_lost=0.0,
                         flow_costs=msg + (1 - t) * msg + t * (1 - q) * (D + fee))
    t = rules["prepaid_takeup_if_baseline_delivered"]
    # switchers: delivered with prob 1-q (pay discount + fee); prob q they RTO as prepaid (lose V and pay L); rest -> confirmation
    return Breakdown(0.0, 0.0, genuine_lost=t * q * (V + L) + (1 - t) * g * V,
                     flow_costs=msg + (1 - t) * msg + t * (1 - q) * (D + fee))

def outcome(action, y, v, first_time, econ, rules):
    """Absolute contribution of the order (ship-as-COD outcome + the action's change)."""
    base = -econ["rto_loss"] if y else _V(v, first_time, econ, rules)
    return base + breakdown(action, y, v, first_time, econ, rules).net

def value(action, p, v, first_time, econ, rules):
    """Expected rupees for one order given RTO probability p. Same formula as breakdown(), by construction."""
    return p * outcome(action, 1, v, first_time, econ, rules) + (1 - p) * outcome(action, 0, v, first_time, econ, rules)

def all_values(p, v, first_time, econ, rules):
    return {a: value(a, p, v, first_time, econ, rules) for a in ACTIONS}
