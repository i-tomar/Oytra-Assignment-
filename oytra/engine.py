"""Decision engine: order -> one of 4 actions + plain-English reason."""
import os, pickle, hashlib, json
import pandas as pd
from .config import load_rules, load_econ, ROOT
from .features import HistoryStats, build
from .model import RiskModel
from .llm import get_judge
from .economics import LABEL, ACTIONS, value
from .policy import apply_policy, FIRST, UNKNOWN

MODEL_PATH = os.path.join(ROOT, "artifacts", "engine.pkl")

def model_version():
    """Short fingerprint of the trained model + current rules, logged with every decision."""
    m = hashlib.sha256(open(MODEL_PATH, "rb").read()).hexdigest()[:8] if os.path.exists(MODEL_PATH) else "untrained"
    r = hashlib.sha256(json.dumps(load_rules(), sort_keys=True, default=str).encode()).hexdigest()[:6]
    return f"model-{m}/rules-{r}"

REASONS = {
    "pin_logit": lambda o, e: f"{'high' if e['pin_rate'] > 0.3 else 'low'}-RTO area ({e['pin_rate']:.0%} past RTO in {o['pincode'] or o['state']})",
    "first_time": lambda o, e: "first order from this customer",
    "prior_rto": lambda o, e: f"refused {o['customer_prior_rto']} earlier order(s)",
    "prior_rto_rate": lambda o, e: f"refused {o['customer_prior_rto']} of {o['customer_prior_orders']} past orders",
    "meta_first_time": lambda o, e: "first-time buyer from a Meta ad",
    "single_item": lambda o, e: "single low-commitment item",
    "address_score": lambda o, e: "address is incomplete" if e["judge"]["address_score"] < 1 else "full address with house number",
    "name_fake": lambda o, e: "name looks fake",
    "phone_invalid": lambda o, e: "phone number is not a valid 10-digit mobile",
    "value_k": lambda o, e: f"order value ₹{o['order_value']}",
    "night": lambda o, e: "placed late at night",
    "hist_unknown": lambda o, e: "customer-history records are inconsistent, so history is not used",
}

LOW_REASONS = {
    "pin_logit": lambda o, e: f"low-RTO area ({e['pin_rate']:.0%} past RTO in {o['pincode'] or o['state']})",
    "first_time": lambda o, e: f"returning customer ({o['customer_prior_orders']} past orders)",
    "prior_rto": lambda o, e: "no past refusals",
    "prior_rto_rate": lambda o, e: "good past delivery record",
    "meta_first_time": lambda o, e: "not a first-time Meta-ad buyer",
    "single_item": lambda o, e: f"{o['num_items']} items in the order",
    "address_score": lambda o, e: "full address with house number",
    "name_fake": lambda o, e: "real-looking name",
    "phone_invalid": lambda o, e: "valid mobile number",
    "value_k": lambda o, e: f"order value ₹{o['order_value']}",
    "night": lambda o, e: "placed in daytime",
    "hist_unknown": lambda o, e: "consistent customer-history records",
}

class Engine:
    def __init__(self, stats, model, rules=None, econ=None, judge=None):
        self.stats, self.model = stats, model
        self.rules, self.econ = rules or load_rules(), econ or load_econ()
        self.judge = judge or get_judge()

    @classmethod
    def load(cls, **kw):
        stats, model = pickle.load(open(MODEL_PATH, "rb"))
        return cls(stats, model, **kw)

    def score(self, df, judged=None):
        X = build(df, self.stats, self.judge, judged)
        return X, self.model.predict(X)

    def decide_frame(self, df, judged=None):
        X, p = self.score(df, judged)
        out = [self._decide(o, X.loc[i], pi) for (i, o), pi in zip(df.iterrows(), p)]
        return pd.DataFrame(out, index=df.index)

    def decide(self, order: dict):
        o = {"pincode": "", "city": "", "customer_prior_orders": None, "customer_prior_rto": None, "num_items": 1,
             "utm_source": "direct", "courier": "", "order_datetime": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), **order}
        df = pd.DataFrame([o])
        from .data import normalise_phone
        df["dt"] = pd.to_datetime(df.order_datetime)
        df["phone10"] = df.phone.map(normalise_phone)
        df["phone_valid"] = df.phone10.str.fullmatch(r"[6-9]\d{9}").fillna(False)
        df["pincode"] = df.pincode.astype(str)
        return self.decide_frame(df).iloc[0].to_dict()

    def _decide(self, o, x, p):
        """Action comes ONLY from policy.apply_policy (same function as the backtest)."""
        R = self.rules
        j = x["_judge"]; hs = x["_history_state"]
        first = hs == FIRST
        unusable = j["address_score"] == 0
        ev = {"pin_rate": self.stats.pin_rate(o["pincode"], o["state"]), "judge": j}
        acts, steps = apply_policy([p], [hs], [j["name_fake"]], [unusable], [o.get("order_value", 1) <= 0], R, explain=True)
        a, steps = acts[0], steps[0]
        hard = []
        if j["name_fake"]: hard.append(f"name '{o['customer_name']}' looks fake")
        if unusable: hard.append(f"address '{o['address']}' is not deliverable")
        if hard:
            why = [f"RTO risk {p:.0%}"] + hard
        else:
            contrib = {k[:-2] if k.endswith("_q") else k: v for k, v in self.model.contributions(x).items()}
            top = sorted([(k, v) for k, v in contrib.items() if v > 0.05], key=lambda kv: -kv[1])[:3] if a != "SHIP" \
                else sorted([(k, v) for k, v in contrib.items() if v < -0.05], key=lambda kv: kv[1])[:2]
            drivers = [(LOW_REASONS if a == "SHIP" else REASONS)[k](o, ev) for k, _ in top]
            why = ([f"low risk ({p:.0%})"] if a == "SHIP" else [f"RTO risk {p:.0%}"]) + drivers
        txt = {"first_time_protect": "first-time-labelled buyer, so offered prepaid instead of cancelling",
               "unknown_history_protect": "customer history is inconsistent/unknown, which is never a reason to cancel, so offered prepaid then ops review",
               "hard_rule_confirm": "WhatsApp asks for the correct details before we ship (data-quality rule overrides the risk band)",
               "hard_rule_hold": "hold; cancel if customer does not fix it in 24h (data-quality rule)",
               "zero_value": "₹0 order (free replacement/gift): nothing to discount and nothing gained by cancelling, so confirm on WhatsApp"}
        why += [txt[s_] for s_ in steps if not (s_ == "first_time_protect" and a != "NUDGE") and not (s_ == "unknown_history_protect" and a != "NUDGE")]
        if o.get("order_value", 1) <= 0 and "zero_value" not in steps: why.append(txt["zero_value"])
        if hs == UNKNOWN and "unknown_history_protect" not in steps: why.append("customer history inconsistent (not used as evidence)")
        V = {k: round(value(k, p, o["order_value"], first, self.econ, R)) for k in ACTIONS}
        best = max(ACTIONS, key=lambda k: V[k])
        note = "" if V[best] <= V[a] or o.get("order_value", 1) <= 0 else f" Policy band chose {LABEL[a]}; per-order ₹ estimate favours {LABEL[best]} (₹{V[best]} vs ₹{V[a]}, base-case HYPOTHETICAL assumptions)."
        return {"order_id": o.get("order_id", ""), "action": a, "action_label": LABEL[a], "risk": round(float(p), 3),
                "history_state": hs,
                "reason": f"{LABEL[a]}: " + "; ".join(dict.fromkeys(why)) + "." + note,
                "expected_rupees": V, "best_ev_action": best, "judge_backend": j["backend"], "address_issues": "; ".join(j["issues"])}
