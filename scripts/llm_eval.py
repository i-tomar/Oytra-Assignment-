"""Small, honest eval of the optional LLM layer (Groq, OpenAI-compatible) against the offline rules.
SYNTHETIC DATA ONLY: every name/address/reply below was written for this eval; no customer data from the CSV is sent.
Expected labels are DRAFTS written by the assistant and need Ishan's human review before they count as ground truth.

Run:  GROQ_API_KEY=... .venv/bin/python scripts/llm_eval.py      (key read from env only; never printed or saved)
Writes reports/llm_eval_labels.csv, reports/llm_eval.json, reports/llm_eval.md"""
import os, sys, csv, json, time, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from oytra.config import ROOT
from oytra import llm as L

# Groq list price, read from console.groq.com/docs/model/openai/gpt-oss-20b on 31 Oct 2026 (USD per 1M tokens)
PRICE_USD_PER_M = {"openai/gpt-oss-20b": (0.075, 0.30), "openai/gpt-oss-120b": (0.15, 0.60)}
USD_INR = 88.0   # ASSUMPTION for display only

# (id, name, address, city, pincode, draft_name_fake, draft_address_kind)
JUDGE = [
 ("J01", "Meera Kulkarni", "Flat 7B, Shanti Residency, Karve Road, Kothrud", "Pune", "411038", False, "complete"),
 ("J02", "Arjun Mehta", "House 22, Sector 15, near Gurudwara", "Faridabad", "121007", False, "complete"),
 ("J03", "Sana Sheikh", "Jama Masjid ke peeche, gali no 4", "Bhopal", "462001", False, "landmark_only"),
 ("J04", "Rohit Verma", "Hanuman mandir ke saamne wali gali", "Kanpur", "208001", False, "landmark_only"),
 ("J05", "test", "test", "Delhi", "110001", True, "unusable"),
 ("J06", "asdfgh", "Plot 9, MIDC Road, Ambad", "Nashik", "422010", True, "complete"),
 ("J07", "Kavya Nair", "call me", "Kochi", "682001", False, "unusable"),
 ("J08", "Imran Qureshi", "Lucknow", "Lucknow", "226001", False, "unusable"),
 ("J09", "Pooja Rathore", "near bus stand", "Ajmer", "305001", False, "vague"),
 ("J10", "Dinesh Patel", "B-304, Shivalik Heights, Satellite Road", "Ahmedabad", "380015", False, "complete"),
 ("J11", "xyz", ".", "Patna", "800001", True, "unusable"),
 ("J12", "Nikhil Joshi", "Govt school ke paas, ward 6", "Sagar", "470001", False, "landmark_only"),
 ("J13", "Ananya Ghosh", "12/3 Gariahat Road, Ballygunge", "Kolkata", "700019", False, "complete"),
 ("J14", "aaaa", "home", "Indore", "452001", True, "unusable"),
 ("J15", "Harpreet Kaur", "Village Rampur, post office Khanna", "Ludhiana", "141401", False, "vague"),
 ("J16", "Sunita Devi", "SBI bank ke bagal mein, pehli manzil", "Darbhanga", "846004", False, "landmark_only"),
 ("J17", "Customer", "Room 5, Sai Chawl, Kurla West", "Mumbai", "400070", True, "complete"),
 ("J18", "Vikram Singh", "Petrol pump crossing", "Kota", "324001", False, "landmark_only"),
 ("J19", "Lakshmi Iyer", "No. 45, 2nd Cross, Indiranagar", "Bengaluru", "560038", False, "complete"),
 ("J20", "Rahul", "chowk", "Nagaon", "782001", False, "unusable"),
 ("J21", "Fatima Khan", "Opp. City Hospital, Station Road", "Gorakhpur", "273001", False, "landmark_only"),
 ("J22", "Na", "NA", "Jaipur", "302001", True, "unusable"),
 ("J23", "Amit Saxena", "Mohalla Qazi tola", "Bareilly", "243001", False, "vague"),
 ("J24", "Priyanka Das", "Flat 2C, Tower 3, Brigade Gardens, JP Nagar", "Bengaluru", "560078", False, "complete"),
 ("J25", "dummy user", "Sector 62 Noida", "Noida", "201301", True, "vague"),
 ("J26", "Gaurav Tiwari", "Gaurav Tiwari s/o Ram Tiwari, ghar no 118, gali 3, Shastri Nagar", "Madhubani", "847211", False, "complete"),
 ("J27", "Neha Bansal", "Kali mata mandir", "Guwahati", "781001", False, "landmark_only"),
 ("J28", "qwerty", "123", "Chennai", "600001", True, "unusable"),
 ("J29", "Mohd Arif", "Behind Water Tank, Ward 12", "Lucknow", "226003", False, "landmark_only"),
 ("J30", "Shreya Kapoor", "D-14, Green Park Extension", "Delhi", "110016", False, "complete"),
]
# (id, reply, draft_intent)
INTENT = [
 ("I01", "haan ji bhej do", "yes"), ("I02", "YES", "yes"), ("I03", "ok confirm", "yes"), ("I04", "theek hai", "yes"),
 ("I05", "nahi chahiye", "no"), ("I06", "cancel kar do", "no"), ("I07", "no I ordered by mistake", "no"), ("I08", "haan nahi chahiye ab", "no"),
 ("I09", "upi se pay karunga", "pay_online"), ("I10", "send payment link", "pay_online"), ("I11", "1", "unclear"), ("I12", "online pay kar deta hoon", "pay_online"),
 ("I13", "keep COD", "keep_cod"), ("I14", "cod rakho", "keep_cod"), ("I15", "cash on delivery hi theek hai", "keep_cod"), ("I16", "nagad dunga delivery pe", "keep_cod"),
 ("I17", "address galat hai", "address_change"), ("I18", "pata change karna hai", "address_change"), ("I19", "please change my address to flat 4", "address_change"),
 ("I20", "kab tak aayega?", "question_eta"), ("I21", "when will it be delivered", "question_eta"), ("I22", "kitne din lagenge", "question_eta"),
 ("I23", "🙏", "unclear"), ("I24", "hmm", "unclear"), ("I25", "who is this", "unclear"), ("I26", "ji", "yes"),
 ("I27", "online nahi, cod hi chahiye", "keep_cod"), ("I28", "mat bhejo", "no"), ("I29", "haan bhai pakka", "yes"), ("I30", "paise online bhej diye", "pay_online"),
]

def cost_usd(model, usage):
    pin, pout = PRICE_USD_PER_M.get(model, (None, None))
    if pin is None: return None
    return usage.get("prompt_tokens", 0) / 1e6 * pin + usage.get("completion_tokens", 0) / 1e6 * pout

INTENT_PROMPT = ("Classify this WhatsApp reply (English/Hindi/Hinglish) to an Indian COD order message into exactly one of: "
                 "yes, no, pay_online, keep_cod, address_change, question_eta, unclear. keep_cod = wants to stay on cash on delivery. "
                 'Reply as JSON: {"label": "..."}\nReply: %s')

RETRIES = {"first_attempt_errors": 0, "retries_used": 0}
def call(prompt, attempts=3):
    """Latency = the successful attempt only; failed attempts are counted in RETRIES (network errors seen from the build box)."""
    err = None
    for i in range(attempts):
        t = time.time()
        try:
            parsed, raw, usage = L.chat_json(prompt, timeout=40)
            return parsed, usage, round((time.time() - t) * 1000), None
        except Exception as e:
            err = type(e).__name__; ms = round((time.time() - t) * 1000)
            if i == 0: RETRIES["first_attempt_errors"] += 1
            if i < attempts - 1: RETRIES["retries_used"] += 1; time.sleep(2 * (i + 1))
    return None, {}, ms, err

def main():
    if not L.api_config(): sys.exit("Set GROQ_API_KEY (env only) to run the LLM eval.")
    _, base, model = L.api_config()
    rj = L.RuleJudge(); rows = []; lat = []; usage_tot = {"prompt_tokens": 0, "completion_tokens": 0}; errors = invalid = 0
    for cid, n, a, c, p, dfake, dkind in JUDGE:
        out, u, ms, err = call(L.PROMPT % (n, a, c, p)); lat.append(ms)
        for k in usage_tot: usage_tot[k] += u.get(k, 0)
        ok = isinstance(out, dict) and isinstance(out.get("name_fake"), bool) and out.get("address_kind") in L.KIND_SCORE
        errors += err is not None; invalid += (err is None and not ok)
        r = rj.judge(n, a, c, p)
        rows.append({"case_id": cid, "task": "name_address", "input": f"{n} | {a} | {c} {p}", "draft_label": f"fake={dfake};{dkind}",
                     "rules_output": f"fake={r['name_fake']};{r['address_kind']}", "llm_output": f"fake={out.get('name_fake')};{out.get('address_kind')}" if ok else f"INVALID/{err}",
                     "llm_json_valid": ok, "latency_ms": ms, "human_label": "", "review_status": "DRAFT — needs Ishan's human review"})
    for cid, text, dl in INTENT:
        out, u, ms, err = call(INTENT_PROMPT % text); lat.append(ms)
        for k in usage_tot: usage_tot[k] += u.get(k, 0)
        lab = str((out or {}).get("label", "")).strip().lower(); ok = lab in L.INTENTS
        errors += err is not None; invalid += (err is None and not ok)
        rows.append({"case_id": cid, "task": "intent", "input": text, "draft_label": dl, "rules_output": L.classify_intent_rules(text),
                     "llm_output": lab if ok else f"INVALID/{err}", "llm_json_valid": ok, "latency_ms": ms, "human_label": "",
                     "review_status": "DRAFT — needs Ishan's human review"})
    agree = lambda task, col: sum(r[col] == r["draft_label"] for r in rows if r["task"] == task)
    n_j, n_i = len(JUDGE), len(INTENT)
    # per-field agreement for the judge
    fake_llm = sum(r["llm_output"].split(";")[0] == r["draft_label"].split(";")[0] for r in rows if r["task"] == "name_address")
    fake_rul = sum(r["rules_output"].split(";")[0] == r["draft_label"].split(";")[0] for r in rows if r["task"] == "name_address")
    kind_llm = sum(r["llm_output"].split(";")[-1] == r["draft_label"].split(";")[-1] for r in rows if r["task"] == "name_address")
    kind_rul = sum(r["rules_output"].split(";")[-1] == r["draft_label"].split(";")[-1] for r in rows if r["task"] == "name_address")
    c = cost_usd(model, usage_tot); ls = sorted(lat)
    res = {"run_at_ist": dt.datetime.now().strftime("%Y-%m-%d %H:%M IST"), "provider_base_url": base, "model": model,
           "prompt_version": L.PROMPT_VERSION, "cases": len(rows), "data": "synthetic, written for this eval; no customer data sent",
           "labels": "DRAFT expected labels written by the assistant - need Ishan's human review; agreement below is vs these drafts, not verified ground truth",
           "first_attempt_network_errors": RETRIES["first_attempt_errors"], "retries_used": RETRIES["retries_used"], "json_valid": sum(r["llm_json_valid"] for r in rows), "api_errors": errors, "invalid_outputs": invalid,
           "agreement_vs_draft": {"name_address_both_fields": {"llm": agree("name_address", "llm_output"), "rules": agree("name_address", "rules_output"), "of": n_j},
                                  "name_fake": {"llm": fake_llm, "rules": fake_rul, "of": n_j}, "address_kind": {"llm": kind_llm, "rules": kind_rul, "of": n_j},
                                  "intent": {"llm": agree("intent", "llm_output"), "rules": agree("intent", "rules_output"), "of": n_i}},
           "latency_ms": {"median": ls[len(ls) // 2], "p90": ls[int(0.9 * (len(ls) - 1))], "max": ls[-1]},
           "tokens": usage_tot, "cost_usd_this_run": round(c, 6) if c is not None else None,
           "cost_per_1000_orders_inr_estimate": round(c / len(rows) * 1000 * USD_INR, 2) if c is not None else None,
           "price_source": "Groq list price for the model, console.groq.com, read 31 Oct 2026; USD->INR 88 is an assumption",
           "decision_impact": "none: backtests always use RuleJudge; the LLM is opt-in (OYTRA_USE_LLM=1) and only produces features/intent"}
    with open(os.path.join(ROOT, "reports", "llm_eval_labels.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    json.dump(res, open(os.path.join(ROOT, "reports", "llm_eval.json"), "w"), indent=1, ensure_ascii=False)
    a = res["agreement_vs_draft"]
    dis = [r for r in rows if r["llm_output"] != r["draft_label"] or r["rules_output"] != r["draft_label"]]
    md = [f"# LLM eval (synthetic, {len(rows)} cases) — DRAFT labels, need Ishan's human review", "",
          f"Model `{model}` via `{base}` · prompt `{L.PROMPT_VERSION}` · run {res['run_at_ist']} · temperature 0, JSON mode.", "",
          "Agreement is against **draft** expected labels written by the assistant, not verified ground truth.", "",
          "| Task | LLM agrees | Rules agree | Cases |", "|---|---|---|---|",
          f"| Name + address (both fields) | {a['name_address_both_fields']['llm']} | {a['name_address_both_fields']['rules']} | {n_j} |",
          f"| — fake name | {a['name_fake']['llm']} | {a['name_fake']['rules']} | {n_j} |",
          f"| — address kind | {a['address_kind']['llm']} | {a['address_kind']['rules']} | {n_j} |",
          f"| Reply intent | {a['intent']['llm']} | {a['intent']['rules']} | {n_i} |", "",
          f"Valid JSON: {res['json_valid']}/{len(rows)} · API errors after 3 attempts: {errors} · invalid outputs: {invalid} · first-attempt network errors: {RETRIES['first_attempt_errors']} (retried).",
          f"Latency median {res['latency_ms']['median']} ms, p90 {res['latency_ms']['p90']} ms, max {res['latency_ms']['max']} ms.",
          f"Tokens {usage_tot['prompt_tokens']:,} in / {usage_tot['completion_tokens']:,} out · cost this run ${res['cost_usd_this_run']} "
          f"(≈ ₹{res['cost_per_1000_orders_inr_estimate']} per 1,000 calls at an assumed ₹88/$). {res['price_source']}.", "",
          "**Caveat:** the draft labels and the offline rules were written by the same assistant, so rules-vs-draft agreement is optimistic (circular). Treat the rules column as a self-consistency check, not accuracy.", "",
          "**Decision impact:** none. Backtests always use RuleJudge; the LLM is opt-in and only produces features/intent.", "",
          "## Cases where the LLM or the rules differ from the draft label", "", "| ID | Input | Draft | Rules | LLM |", "|---|---|---|---|---|"]
    md += [f"| {r['case_id']} | {r['input']} | {r['draft_label']} | {r['rules_output']} | {r['llm_output']} |" for r in dis]
    open(os.path.join(ROOT, "reports", "llm_eval.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(json.dumps(res, indent=1, ensure_ascii=False))

if __name__ == "__main__":
    main()
