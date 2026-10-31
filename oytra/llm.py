"""Text judgement layer: is the NAME real, is the ADDRESS deliverable?

This is the ONLY place an LLM is used. It returns features (flags + a 0-1 address score);
it never makes the ship/cancel decision. Backends:
  * RuleJudge  - default, offline, deterministic (used for backtests & tests)
  * LLMJudge   - Groq (OpenAI-compatible) when GROQ_API_KEY is set, base https://api.groq.com/openai/v1,
                 JSON mode, default model openai/gpt-oss-20b (OYTRA_LLM_MODEL overrides). OPENAI_API_KEY also works.
                 OPT-IN: only used when OYTRA_USE_LLM=1. Falls back to rules on any error.
The key is read from the environment only; it is never written to disk, logs or the cache.
Backtests ALWAYS use RuleJudge, whatever keys are set.
"""
import json, os, re, hashlib, urllib.request

FAKE_NAMES = {"test", "test order", "asdf", "qwerty", "aaa", "abc", "xyz", "xyz xyz", "na", "n/a",
              "dummy", "fake", "sample", "customer", "user"}
JUNK_ADDR = {".", "..", "-", "xyz", "na", "home", "call me", "near station", "address", "abc"}
HINGLISH = re.compile(r"\b(ke|ka|ki|wala|wali|krke|karke|se|saamne|samne|paas|peeche|ghar|gali|naam|aana)\b", re.I)
LANDMARK = re.compile(r"(mandir|masjid|school|bank|tank|petrol pump|crossing|bazaar|chowk|station|hospital)", re.I)
CITIES = {"delhi", "mumbai", "pune", "chennai", "kolkata", "bengaluru", "hyderabad", "jaipur", "indore",
          "lucknow", "patna", "sagar", "kota", "guwahati", "nagaon", "darbhanga", "bareilly", "gorakhpur", "madhubani"}

class RuleJudge:
    name = "rules"
    def judge(self, name, address, city="", pincode=""):
        n = str(name or "").strip().lower()
        a = str(address or "").strip()
        al = a.lower()
        issues = []
        fake = n in FAKE_NAMES or len(n) < 3 or bool(re.fullmatch(r"(.)\1+", n.replace(" ", ""))) \
            or "test" in n.split()
        if fake: issues.append(f"name '{name}' looks fake")
        hinglish = bool(HINGLISH.search(a))
        has_number = bool(re.search(r"\d", a))
        if al in JUNK_ADDR or len(a) < 6 or al in CITIES:
            score, kind = 0.0, "unusable"
            issues.append(f"address '{a}' is not deliverable")
        elif has_number and len(a.split(",")) >= 2:
            score, kind = 1.0, "complete"
        elif LANDMARK.search(a):
            score, kind = 0.6, "landmark_only"
            issues.append("address has only a landmark, no house/flat number")
        else:
            score, kind = 0.3, "vague"
            issues.append("address is vague")
        if not pincode: issues.append("pincode missing"); score = min(score, 0.6)
        return {"name_fake": fake, "address_score": score, "address_kind": kind,
                "hinglish": hinglish, "issues": issues, "backend": self.name}

PROMPT = """You check Indian e-commerce COD orders for delivery problems. Addresses may be in
Hinglish (Hindi in Latin script), e.g. "Hanuman Mandir ke saamne" = opposite Hanuman temple.
Landmark-style Indian addresses are normal and can be deliverable; judge only whether a courier
could find the house. Reply with JSON only:
{"name_fake": bool, "address_kind": "complete"|"landmark_only"|"vague"|"unusable",
 "hinglish": bool, "issues": [short strings in plain English]}
Name: %s
Address: %s
City: %s  Pincode: %s"""
KIND_SCORE = {"complete": 1.0, "landmark_only": 0.6, "vague": 0.3, "unusable": 0.0}

PROMPT_VERSION = "judge-v2"
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"

def api_config():
    """(key, base_url, model) from the environment, or None. Never logged."""
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"], GROQ_BASE, os.environ.get("OYTRA_LLM_MODEL", GROQ_DEFAULT_MODEL)
    if os.environ.get("OPENAI_API_KEY"):
        return (os.environ["OPENAI_API_KEY"], os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
                os.environ.get("OYTRA_LLM_MODEL", "gpt-4o-mini"))
    return None

def llm_enabled(): return os.environ.get("OYTRA_USE_LLM", "0") == "1" and api_config() is not None

def chat_json(prompt, timeout=30):
    """One JSON-mode call. Returns (parsed_json_or_None, raw_text, usage_dict). Raises on HTTP errors."""
    key, base, model = api_config()
    req = urllib.request.Request(base + "/chat/completions", method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "oytra-cod-engine"},
        data=json.dumps({"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                         "messages": [{"role": "user", "content": prompt}]}).encode())
    resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    raw = resp["choices"][0]["message"]["content"]
    try: parsed = json.loads(raw)
    except Exception: parsed = None
    return parsed, raw, resp.get("usage", {})

class LLMJudge:
    name = "llm"
    def __init__(self, cache_dir=None):
        self.key, self.base, self.model = api_config()
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(__file__), "..", ".llm_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.fallback = RuleJudge()
    def judge(self, name, address, city="", pincode=""):
        prompt = PROMPT % (name, address, city, pincode)
        f = os.path.join(self.cache_dir, hashlib.sha1((self.model + prompt).encode()).hexdigest() + ".json")
        if os.path.exists(f): return json.load(open(f))
        try:
            out, _, _ = chat_json(prompt)
            res = {"name_fake": bool(out["name_fake"]), "address_kind": out["address_kind"],
                   "address_score": KIND_SCORE.get(out["address_kind"], 0.3),
                   "hinglish": bool(out.get("hinglish")), "issues": list(out.get("issues", [])), "backend": self.name}
            json.dump(res, open(f, "w"))
            return res
        except Exception as e:  # never block shipping on an API outage
            r = self.fallback.judge(name, address, city, pincode); r["backend"] = f"rules (llm error: {type(e).__name__})"
            return r

def get_judge(prefer_llm=None):
    use = prefer_llm if prefer_llm is not None else os.environ.get("OYTRA_USE_LLM", "0") == "1"
    return LLMJudge() if (use and api_config()) else RuleJudge()

INTENTS = {"yes", "no", "pay_online", "keep_cod", "address_change", "question_eta", "unclear"}
COD_WORDS = {"cod", "cash", "nagad", "nakad", "कैश"}

def classify_intent_rules(text):
    raw = str(text).lower()
    t = re.sub(r"[^\w\s\u0900-\u097F]", " ", raw).split()
    s = set(t)
    yes = {"yes", "y", "haan", "ha", "han", "haa", "ok", "okay", "confirm", "confirmed", "theek", "thik", "sure", "ji", "हाँ", "हां"}
    no = {"no", "n", "nahi", "nhi", "nahin", "cancel", "mat", "नहीं"}
    pay = {"pay", "prepaid", "upi", "online", "link"}
    # keep COD: "keep COD", "cod rakho", "cash on delivery", "cash pe", "COD hi theek hai", "online nahi, cod"
    if (s & COD_WORDS or "cash on delivery" in raw) and "cancel" not in s: return "keep_cod"
    if s & no: return "no"           # 'no' wins: "haan nahi chahiye" = no
    if s & pay: return "pay_online"
    if s & yes: return "yes"
    if s & {"address", "pata", "change", "galat"}: return "address_change"
    if s & {"kab", "when", "delivery", "kitne", "din"}: return "question_eta"
    return "unclear"

def classify_intent(text):
    if llm_enabled():
        try:
            p = ("Classify this WhatsApp reply (English/Hindi/Hinglish) to a COD order message into one of: "
                 "yes, no, pay_online, keep_cod, address_change, question_eta, unclear. keep_cod = wants to stay on cash on delivery. "
                 'Reply as JSON: {"label": "..."}\nReply: ' + str(text))
            out, _, _ = chat_json(p, timeout=15)
            lab = str((out or {}).get("label", "")).strip().lower()
            if lab in INTENTS: return lab
        except Exception:
            pass
    return classify_intent_rules(text)
