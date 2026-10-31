# LLM eval (synthetic, 60 cases) — DRAFT labels, need Ishan's human review

Model `openai/gpt-oss-20b` via `https://api.groq.com/openai/v1` · prompt `judge-v2` · run 2026-10-30 22:14 IST · temperature 0, JSON mode.

Agreement is against **draft** expected labels written by the assistant, not verified ground truth.

| Task | LLM agrees | Rules agree | Cases |
|---|---|---|---|
| Name + address (both fields) | 23 | 25 | 30 |
| — fake name | 28 | 28 | 30 |
| — address kind | 24 | 27 | 30 |
| Reply intent | 29 | 30 | 30 |

Valid JSON: 60/60 · API errors after 3 attempts: 0 · invalid outputs: 0 · first-attempt network errors: 44 (retried).
Latency median 491 ms, p90 633 ms, max 862 ms.
Tokens 12,033 in / 13,332 out · cost this run $0.004902 (≈ ₹7.19 per 1,000 calls at an assumed ₹88/$). Groq list price for the model, console.groq.com, read 31 Oct 2026; USD->INR 88 is an assumption.

**Caveat:** the draft labels and the offline rules were written by the same assistant, so rules-vs-draft agreement is optimistic (circular). Treat the rules column as a self-consistency check, not accuracy.

**Decision impact:** none. Backtests always use RuleJudge; the LLM is opt-in and only produces features/intent.

## Cases where the LLM or the rules differ from the draft label

| ID | Input | Draft | Rules | LLM |
|---|---|---|---|---|
| J03 | Sana Sheikh | Jama Masjid ke peeche, gali no 4 | Bhopal 462001 | fake=False;landmark_only | fake=False;complete | fake=False;landmark_only |
| J06 | asdfgh | Plot 9, MIDC Road, Ambad | Nashik 422010 | fake=True;complete | fake=False;complete | fake=True;complete |
| J08 | Imran Qureshi | Lucknow | Lucknow 226001 | fake=False;unusable | fake=False;unusable | fake=False;vague |
| J09 | Pooja Rathore | near bus stand | Ajmer 305001 | fake=False;vague | fake=False;vague | fake=False;landmark_only |
| J12 | Nikhil Joshi | Govt school ke paas, ward 6 | Sagar 470001 | fake=False;landmark_only | fake=False;complete | fake=False;landmark_only |
| J14 | aaaa | home | Indore 452001 | fake=True;unusable | fake=True;unusable | fake=True;vague |
| J17 | Customer | Room 5, Sai Chawl, Kurla West | Mumbai 400070 | fake=True;complete | fake=True;complete | fake=False;complete |
| J20 | Rahul | chowk | Nagaon 782001 | fake=False;unusable | fake=False;unusable | fake=False;vague |
| J25 | dummy user | Sector 62 Noida | Noida 201301 | fake=True;vague | fake=False;vague | fake=False;complete |
| J28 | qwerty | 123 | Chennai 600001 | fake=True;unusable | fake=True;unusable | fake=True;vague |
| J29 | Mohd Arif | Behind Water Tank, Ward 12 | Lucknow 226003 | fake=False;landmark_only | fake=False;complete | fake=False;landmark_only |
| I06 | cancel kar do | no | no | unclear |
