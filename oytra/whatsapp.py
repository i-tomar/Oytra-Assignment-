"""Mock WhatsApp confirmation / prepaid-nudge flow with a simulated clock.

  python -m oytra.whatsapp            # interactive chat simulator (type replies, or /wait 12 to jump hours)
  python -m oytra.whatsapp --demo     # scripted run of every branch (yes / no / random / silence / payment ok / fail / timeout)
Every message and state change is written to an event log (reports/whatsapp_events.jsonl + .csv) with the
model version, risk score and action that started the conversation.
"""
import sys, re, os, json, csv, datetime as _dt
from dataclasses import dataclass, field
from .llm import classify_intent
from .config import load_rules, ROOT

IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))

HINDI_STATES = {"Uttar Pradesh", "Bihar", "Madhya Pradesh", "Rajasthan", "Delhi", "Haryana", "Jharkhand", "Chhattisgarh", "Uttarakhand", "Himachal Pradesh"}

T = {
 "confirm": {
  "en": "Hi {name}! Thanks for ordering {items} (₹{value}, Cash on Delivery) from OYTRA. Please reply YES to confirm and we'll ship today, or NO to cancel.",
  "hi": "Namaste {name} ji! Aapne OYTRA se {items} (₹{value}, Cash on Delivery) order kiya hai. Order confirm karne ke liye HAAN likhein, cancel ke liye NAHI."},
 "nudge": {
  "en": "Hi {name}! Your OYTRA order {items} is ₹{value} COD. Pay online now and get ₹{d} off (you pay ₹{pv}) + priority dispatch: {link}\nReply 1 to pay online, 2 to keep Cash on Delivery.",
  "hi": "Namaste {name} ji! Aapka OYTRA order {items} ₹{value} COD hai. Abhi online pay karein aur ₹{d} ki chhoot paayein (sirf ₹{pv}) + jaldi dispatch: {link}\nOnline pay ke liye 1, COD rakhne ke liye 2 likhein."},
 "address": {
  "en": "Hi {name}! We want to deliver your OYTRA order but the address/name looks incomplete: \"{address}\". Please reply with your full name, house/flat no., street and landmark.",
  "hi": "Namaste! Aapka OYTRA order deliver karne ke liye pura pata chahiye. Abhi likha hai: \"{address}\". Kripya apna naam, ghar/flat number, gali aur landmark bhejein."},
 "reminder": {
  "en": "Reminder: your OYTRA order is waiting. Reply YES to confirm so we can ship it, or NO to cancel.",
  "hi": "Yaad dilaana: aapka OYTRA order intezaar mein hai. Ship karne ke liye HAAN likhein, cancel ke liye NAHI."},
 "reminder_nudge": {
  "en": "Reminder: your ₹{d} online-payment discount expires in 12 hours. Reply 1 to pay online or 2 to keep Cash on Delivery.",
  "hi": "Yaad dilaana: ₹{d} ki online-payment chhoot 12 ghante mein khatam ho jayegi. Online pay ke liye 1, COD ke liye 2 likhein."},
 "confirmed": {"en": "Thank you! Your order is confirmed and ships today. 🚚", "hi": "Dhanyavaad! Aapka order confirm ho gaya, aaj ship hoga. 🚚"},
 "cancelled": {"en": "Okay, we've cancelled your order. You can reorder any time.", "hi": "Theek hai, aapka order cancel kar diya gaya hai. Kabhi bhi dobara order kar sakte hain."},
 "paylink": {"en": "Here is your secure payment link for ₹{pv}: {link}. Order ships as soon as payment is done.", "hi": "Yeh raha payment link (₹{pv}): {link}. Payment hote hi order ship hoga."},
 "eta": {"en": "Delivery usually takes 3–5 days after confirmation. Reply YES to confirm your order.", "hi": "Confirm hone ke 3-5 din mein delivery ho jaati hai. Order confirm karne ke liye HAAN likhein."},
 "addr_ok": {"en": "Thanks, address updated! Your order will ship today.", "hi": "Dhanyavaad, pata update ho gaya! Order aaj ship hoga."},
 "unclear": {"en": "Sorry, didn't get that. Please reply YES to confirm or NO to cancel.", "hi": "Maaf kijiye, samajh nahi aaya. Confirm ke liye HAAN, cancel ke liye NAHI likhein."},
 "paid": {"en": "Payment of ₹{pv} received, thank you! Your order ships today. 🚚", "hi": "₹{pv} ka payment mil gaya, dhanyavaad! Order aaj ship hoga. 🚚"},
 "payfail": {"en": "Your payment didn't go through. Try again here: {link}\nOr reply 2 to keep Cash on Delivery.", "hi": "Payment nahi ho paaya. Dobara try karein: {link}\nYa COD rakhne ke liye 2 likhein."},
 "paytimeout": {"en": "We didn't receive the online payment, no problem, we'll keep your order as Cash on Delivery.", "hi": "Online payment nahi mila, koi baat nahi, aapka order Cash on Delivery rahega."},
 "lang_ask": {"en": "\n(Hindi mein message chahiye? Reply HINDI)", "hi": "\n(Prefer English? Reply ENGLISH)"},
 "handoff": {"en": "Connecting you to our team, they'll reply shortly.", "hi": "Hamari team aapse jaldi baat karegi."},
}

class LanguageStore:
    """Remembers each customer's language (keyed by phone). We ask once in the first message;
    the answer (or silent acceptance of our first guess) is stored and reused next time."""
    def __init__(self, path=None):
        self.path = path or os.path.join(ROOT, "state", "language_prefs.json")
        self.prefs = json.load(open(self.path)) if os.path.exists(self.path) else {}
    def get(self, phone): return self.prefs.get(str(phone), {}).get("lang")
    def set(self, phone, lang, source):
        if not phone: return
        self.prefs[str(phone)] = {"lang": lang, "source": source}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        json.dump(self.prefs, open(self.path, "w"), indent=1)

LANG_WORDS = {"hindi": "hi", "hinglish": "hi", "हिंदी": "hi", "english": "en", "angrezi": "en"}

def pick_language(order):
    """First guess only, used until the customer tells us (we ask in the first message)."""
    a = str(order.get("address", ""))
    if order.get("state") in HINDI_STATES or re.search(r"\b(ke|ka|wala|krke|saamne|paas|ghar)\b", a, re.I): return "hi"
    return "en"

@dataclass
class Conversation:
    order: dict
    flow: str                 # "confirm" | "nudge" | "address"
    rules: dict = field(default_factory=load_rules)
    lang: str = ""
    hour: float = 0.0
    start: float = 0.0
    state: str = "AWAITING"   # -> CONFIRMED / PAYMENT_PENDING / PAID / CANCELLED / SHIPPED_UNCONFIRMED / HANDOFF / MANUAL_OPS_REVIEW
    reminded: bool = False
    unclear_count: int = 0
    log: list = field(default_factory=list)
    decision: dict = field(default_factory=dict)   # {"action","risk","model_version"} from the engine
    store: object = None                           # LanguageStore; None = don't remember
    payment_status: str = "cod"                    # cod -> pending -> paid | failed
    pay_attempts: int = 0
    pay_started: float = 0.0
    events: list = field(default_factory=list)
    seen_payment_events: set = field(default_factory=set)   # webhook ids already processed (idempotency)
    released: int = 0                                       # times the order was released to the warehouse; must stay <= 1
    had_payment_link: bool = False                          # a payment link was sent at some point
    ops_flags: list = field(default_factory=list)          # e.g. late payment after COD fallback -> refund/ops review

    def __post_init__(self):
        o, R = self.order, self.rules
        self.phone = str(o.get("phone", ""))
        stored = self.store.get(self.phone) if self.store else None
        self.lang_source = "customer_choice/stored" if stored else ("set_by_caller" if self.lang else "first_guess")
        self.lang = self.lang or stored or pick_language(o)
        self.ask_lang = self.lang_source == "first_guess"
        try: self.t0 = _dt.datetime.fromisoformat(str(o.get("order_datetime"))).replace(tzinfo=IST)
        except ValueError: self.t0 = _dt.datetime(2026, 10, 1, 10, 0, tzinfo=IST)
        self.vars = dict(name=str(o.get("customer_name", "")).split()[0] if o.get("customer_name") else "", items=o.get("items", "your order"),
                         value=o.get("order_value"), d=R["prepaid_discount_rupees"], pv=o.get("order_value", 0) - R["prepaid_discount_rupees"],
                         link=f"https://pay.oytra.in/{o.get('order_id', 'X')}", address=o.get("address", ""))
        self.send(self.flow)

    def event(self, actor, kind, text=""):
        self.events.append({"ts": (self.t0 + _dt.timedelta(hours=self.hour)).isoformat(timespec="minutes"),
            "order_id": self.order.get("order_id", ""), "actor": actor, "event": kind, "text": text, "flow": self.flow,
            "state": self.state, "payment_status": self.payment_status, "lang": self.lang,
            "action": self.decision.get("action", ""), "risk": self.decision.get("risk", ""),
            "model_version": self.decision.get("model_version", "")})

    def system(self, text, kind="system"):
        self.log.append((self.hour, "SYSTEM", text)); self.event("system", kind, text)

    def send(self, key):
        msg = T[key][self.lang].format(**self.vars)
        if self.ask_lang and key in ("confirm", "nudge", "address"): msg += T["lang_ask"][self.lang]
        self.log.append((self.hour, "OYTRA", msg)); self.event("oytra", "message:" + key, msg); return msg

    def _remember_lang(self, source):
        if self.ask_lang:
            self.ask_lang = False
            if self.store: self.store.set(self.phone, self.lang, source)

    def payment_result(self, ok, event_id=None):
        """Mock payment-gateway webhook. Payment status changes ONLY here, never on the customer's word.
        Idempotent: a webhook id seen before is ignored, and a 'paid' event when we are not waiting for payment is ignored,
        so a retried/duplicated 'paid' webhook can never release the order twice."""
        if event_id is not None:
            if event_id in self.seen_payment_events:
                self.system(f"Gateway event {event_id} already processed -> ignored", "payment_duplicate_ignored"); return None
            self.seen_payment_events.add(event_id)
        if self.state != "PAYMENT_PENDING" and ok and self.had_payment_link and self.payment_status == "cod":
            # money arrived AFTER we fell back to COD (or the customer chose COD): never silently keep it, never release twice
            ts = (self.t0 + _dt.timedelta(hours=self.hour)).isoformat(timespec="minutes")
            flag = {"flag": "late_payment_after_cod_fallback", "event_id": event_id, "ts": ts, "state": self.state,
                    "action": "refund or convert to prepaid - ops review"}
            self.ops_flags.append(flag)
            self.system(f"Gateway: payment {event_id or ''} received at {ts} AFTER COD fallback (order {self.state}) -> flagged for refund/ops review", "late_payment_refund_review")
            return None
        if self.state != "PAYMENT_PENDING":
            self.system(f"Gateway event {event_id or ''} ignored: order is {self.state}, not waiting for payment".replace("  ", " "), "payment_duplicate_ignored")
            return None
        if ok:
            self.payment_status, self.state = "paid", "PAID"; self.system("Gateway: payment verified", "payment_success")
            self._release("paid online")
            return self.send("paid")
        self.pay_attempts += 1; self.payment_status = "failed"
        self.system(f"Gateway: payment failed (attempt {self.pay_attempts})", "payment_failed")
        if self.pay_attempts >= 2: return self._to_cod("2 failed payments -> keep COD, send COD confirmation")
        self.payment_status = "pending"; return self.send("payfail")

    def _release(self, why):
        if self.released: self.system(f"Release requested again ({why}) -> ignored, already released", "release_duplicate_ignored"); return
        self.released += 1; self.system(f"Order released to warehouse ({why})", "order_released")

    def _confirm_cod(self, why, kind="confirmed"):
        self.payment_status, self.state = "cod", "CONFIRMED"; self.system(why, kind); self._release(why)

    def ops_review(self, outcome, address=None):
        """Ops outcome after a call for an order in MANUAL_OPS_REVIEW: 'ship' or 'cancel'."""
        if self.state != "MANUAL_OPS_REVIEW": return None
        if outcome == "ship":
            if self.flow == "address":
                if not address: self.system("Ops: can't ship without a full address", "ops_review_blocked"); return None
                self.order["address"] = address
            self.state = "CONFIRMED"; self.system("Ops called the customer -> ship", "ops_review_ship"); self._release("ops review"); return "ship"
        self.state = "CANCELLED"; self.system("Ops could not confirm -> cancel", "ops_review_cancel"); return "cancel"

    def _to_cod(self, why):
        self.system(why, "fallback_to_cod")
        self.payment_status, self.state, self.flow, self.reminded, self.start = "cod", "AWAITING", "confirm", False, self.hour
        return self.send("confirm")

    def _no_reply_action(self):
        if self.flow == "nudge": return self.rules["no_reply_action_nudge"]
        if self.flow == "address": return self.rules.get("no_reply_action_address", "manual_review")
        return self.rules["no_reply_action_confirm"]

    def receive(self, text):
        self.log.append((self.hour, "Customer", text)); self.event("customer", "reply", text)
        t = text.strip()
        if t.lower() in LANG_WORDS:
            self.lang = LANG_WORDS[t.lower()]; self.ask_lang = True; self._remember_lang("customer_choice")
            self.system(f"Language set to {self.lang} by customer", "language_set")
            return self.send(self.flow if self.state == "AWAITING" else "handoff")
        self._remember_lang("accepted_first_guess")
        if self.state == "PAYMENT_PENDING":
            if t == "2" or classify_intent(text) == "keep_cod":
                self._confirm_cod("Customer kept COD (confirmed)", "keep_cod")
                return self.send("confirmed")
            return self.send("paylink")
        if self.state != "AWAITING": return self.send("handoff")
        if self.flow == "address":
            if len(text) > 15 and re.search(r"\d", text):
                self.order["address"] = text; self._confirm_cod("Address received -> confirmed COD", "address_updated"); return self.send("addr_ok")
        if self.flow == "nudge" and t in ("1", "2"): intent = "pay_online" if t == "1" else "keep_cod"
        else: intent = classify_intent(text)
        if intent == "pay_online":
            self.state, self.payment_status, self.pay_started, self.had_payment_link = "PAYMENT_PENDING", "pending", self.hour, True
            return self.send("paylink")
        if intent == "keep_cod":   # "keep COD" / "cod rakho" / "cash on delivery" -> confirmed COD, released
            self._confirm_cod("Customer chose to keep COD (confirmed)", "keep_cod"); return self.send("confirmed")
        if intent == "yes": self._confirm_cod("Customer confirmed", "confirmed"); return self.send("confirmed")
        if intent == "no": self.state = "CANCELLED"; self.event("system", "cancelled_by_customer"); return self.send("cancelled")
        if intent == "question_eta": return self.send("eta")
        self.unclear_count += 1
        if self.unclear_count >= 2: self.state = "HANDOFF"; self.event("system", "handoff_to_human"); return self.send("handoff")
        return self.send("unclear")

    def wait(self, hours):
        """Advance the simulated clock and fire reminder / 24h fallback."""
        out = []
        self.hour += hours
        el = self.hour - self.start
        if self.state == "PAYMENT_PENDING" and self.hour - self.pay_started >= self.rules.get("payment_timeout_hours", 2):
            self.send("paytimeout")
            out.append(self._to_cod(f"No verified payment within {self.rules.get('payment_timeout_hours', 2)}h -> COD confirmation")); return out
        if self.state == "AWAITING" and not self.reminded and el >= self.rules["reminder_after_hours"]:
            self.reminded = True; out.append(self.send("reminder_nudge" if self.flow == "nudge" else "reminder"))
        if self.state == "AWAITING" and el >= 24:
            act = self._no_reply_action()
            if act == "manual_review" or (self.flow == "address" and act == "ship"):   # never ship an unusable address blind
                self.state = "MANUAL_OPS_REVIEW"; self.system("No reply in 24h -> manual ops review (call, then ship or cancel)", "timeout_manual_review")
            elif act == "cancel":
                self.state = "CANCELLED"; self.system("No reply in 24h -> order cancelled (fallback)", "timeout_cancel")
            elif act == "confirm":
                out.append(self._to_cod("No reply to prepaid nudge in 24h -> switch to COD confirmation"))
            else:
                self.state = "SHIPPED_UNCONFIRMED"; self.system("No reply in 24h -> shipped anyway (fallback)", "timeout_ship")
        return out

def transcript(c):
    return "\n".join(f"[t+{h:>4.0f}h] {who:>8}: {msg}" for h, who, msg in c.log) + f"\n=> final state: {c.state}\n"

DEMO_ORDER = {"order_id": "KT999001", "customer_name": "Pooja Yadav", "items": "Rice Water Shampoo Bar", "order_value": 649,
              "address": "Hanuman Mandir ke saamne, Station Road", "state": "Uttar Pradesh"}
DEMO_ORDER_EN = {**DEMO_ORDER, "customer_name": "Ananya Iyer", "address": "Flat 12, Lotus Apts, Anna Nagar", "state": "Tamil Nadu"}

DEMO_DECISION = {"confirm": {"action": "CONFIRM", "risk": 0.47}, "nudge": {"action": "NUDGE", "risk": 0.68}, "address": {"action": "CONFIRM", "risk": 0.52}}

def write_event_log(convs, prefix=None):
    """One row per message / state change -> <prefix>.jsonl and <prefix>.csv"""
    prefix = prefix or os.path.join(ROOT, "reports", "whatsapp_events")
    rows = [e for c in convs for e in c.events]
    with open(prefix + ".jsonl", "w") as f:
        for e in rows: f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(prefix + ".csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return rows

def demo(store_path=None, log_prefix=None):
    from .engine import model_version
    mv = model_version()
    store = LanguageStore(store_path or os.path.join(ROOT, "state", "demo_language_prefs.json")); store.prefs = {}
    def C(order, flow, i, **kw):
        o = {**order, "order_id": f"KT9990{i:02d}", "phone": order.get("phone", f"98765430{i:02d}")}
        return Conversation(o, flow, decision={**DEMO_DECISION[flow], "model_version": mv}, store=store, **kw)
    runs = []
    c = C(DEMO_ORDER, "confirm", 1); c.wait(1); c.receive("haan ji bhej do"); runs.append(("Confirm, Hinglish, YES", c))
    c = C(DEMO_ORDER_EN, "confirm", 2); c.receive("no I ordered by mistake"); runs.append(("Confirm, English, NO", c))
    c = C(DEMO_ORDER_EN, "confirm", 3); c.receive("kab tak aayega?"); c.receive("ok yes"); runs.append(("Confirm, question then YES", c))
    c = C(DEMO_ORDER, "confirm", 4); c.receive("🙏🙏"); c.receive("hmm"); runs.append(("Confirm, random replies -> human handoff", c))
    c = C(DEMO_ORDER, "confirm", 5); c.wait(12); c.wait(12); c.ops_review("ship"); runs.append(("Confirm, no reply -> reminder -> manual ops review -> ops call -> ship", c))
    c = C(DEMO_ORDER_EN, "nudge", 6); c.receive("1"); c.wait(0.2); c.payment_result(True, "pay_evt_001"); c.payment_result(True, "pay_evt_001"); runs.append(("Nudge, pays online -> gateway verifies -> PAID (duplicate webhook ignored, released once)", c))
    c = C(DEMO_ORDER_EN, "nudge", 7); c.receive("1"); c.payment_result(False); c.payment_result(False); c.receive("yes"); runs.append(("Nudge, payment fails twice -> COD confirmation -> YES", c))
    c = C(DEMO_ORDER, "nudge", 8); c.receive("1"); c.wait(2); c.receive("haan"); runs.append(("Nudge, link opened but no payment in 2h -> COD confirmation -> YES", c))
    c = C(DEMO_ORDER, "nudge", 9); c.wait(12); c.wait(12); c.receive("haan"); runs.append(("Nudge, silent 24h -> COD confirmation -> YES", c))
    c = C(DEMO_ORDER, "nudge", 13); c.receive("1"); c.receive("cod rakho"); runs.append(("Nudge, link sent, customer says 'cod rakho' -> confirmed COD, released", c))
    c = C(DEMO_ORDER_EN, "nudge", 14); c.receive("1"); c.wait(2); c.receive("yes"); c.payment_result(True, "pay_evt_late"); c.payment_result(True, "pay_evt_late")
    runs.append(("Nudge, timeout -> COD confirmed, THEN payment arrives -> flagged for refund/ops review (released once)", c))
    c = C({**DEMO_ORDER_EN, "address": "call me"}, "address", 10); c.receive("Flat 304, Sai Krupa Apartments, Station Road, near SBI Bank"); runs.append(("Bad address, fixed", c))
    c = C({**DEMO_ORDER, "phone": "9876543011"}, "confirm", 11); c.receive("English"); c.receive("yes"); runs.append(("Language: guessed Hinglish, customer asks for English", c))
    c = C({**DEMO_ORDER, "phone": "9876543011"}, "confirm", 12); c.receive("yes"); runs.append(("Language: same customer next order -> English remembered, not asked again", c))
    out = "".join(f"\n=== {name} ===\n{transcript(c)}" for name, c in runs)
    rows = write_event_log([c for _, c in runs], log_prefix)
    print(out); print(f"Event log: {len(rows)} events -> reports/whatsapp_events.jsonl / .csv (model {mv})"); return runs

def interactive():
    flow = input("Flow? [confirm/nudge/address] (confirm): ").strip() or "confirm"
    lang = input("Language? [en/hi/auto] (auto): ").strip()
    c = Conversation(dict(DEMO_ORDER if lang != "en" else DEMO_ORDER_EN), flow, lang="" if lang in ("", "auto") else lang)
    print(transcript(c)); print("Type a customer reply, '/wait N' to skip N hours, '/quit' to exit.")
    print("Also: '/paid' or '/payfail' to simulate the payment gateway.")
    while c.state in ("AWAITING", "PAYMENT_PENDING"):
        t = input("Customer> ").strip()
        if t == "/quit": break
        if t in ("/paid", "/payfail"): print("OYTRA:", c.payment_result(t == "/paid")); continue
        if t.startswith("/wait"): [print("OYTRA:", m) for m in c.wait(float(t.split()[1]) if len(t.split()) > 1 else 24)]
        else: print("OYTRA:", c.receive(t))
    print(transcript(c))

if __name__ == "__main__":
    demo() if "--demo" in sys.argv else interactive()
