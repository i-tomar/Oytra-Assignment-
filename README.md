# OYTRA COD Risk Engine (take-home)

Decides for every new COD order: **Ship as-is / Ship after confirmation / Nudge to prepaid / Hold-cancel**, with a plain-English reason. It also includes a WhatsApp confirmation mock, a morning dashboard and a business memo.

**Start here:** [`memo.pdf`](memo.pdf) (founder memo) · [`docs/CHANGES_AUDIT_FIXES.md`](docs/CHANGES_AUDIT_FIXES.md) (what the audit changed) · [`dashboard/index.html`](dashboard/index.html) · [`DECISION_LOG.md`](DECISION_LOG.md) · [`AI_USAGE_LOG.md`](AI_USAGE_LOG.md) · [`reports/findings.md`](reports/findings.md) · [`docs/WHATSAPP_FLOW.md`](docs/WHATSAPP_FLOW.md) · [`docs/DESIGN.md`](docs/DESIGN.md)

## Run it (≈2 minutes)
Needs Python 3.10+. No API key required.
```bash
./run_all.sh          # venv + install, findings, train/backtest, example decisions, WhatsApp demo, dashboard, tests
```
Or step by step:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m oytra.variants        # history-leakage + product checks -> reports/model_variants.json
.venv/bin/python -m oytra.analysis        # data findings  -> reports/findings.md
.venv/bin/python -m oytra.history_variants # choose the history model on Apr–Aug only -> reports/history_model_selection.md
.venv/bin/python -m oytra.backtest        # train Apr–Aug, test Sep -> reports/backtest.json, september_decisions.csv, calibration.png, artifacts/engine.pkl
.venv/bin/python -m oytra.walkforward     # Jun–Sep month by month -> reports/walkforward.md
.venv/bin/python -m oytra.leakage_audit   # target-encoding leakage checks -> reports/leakage_audit.json
.venv/bin/python -m oytra.history_rootcause # why reported customer history disagrees with the file -> reports/history_rootcause.json
.venv/bin/python -m oytra.ablation        # drop each feature group -> reports/ablation.md
PYTHONPATH=. .venv/bin/python scripts/check_threshold_maths.py  # every number in docs/THRESHOLD_MATHS.md recomputed
.venv/bin/python -m oytra.decide          # score 4 example orders (or pass one order as JSON)
.venv/bin/python -m oytra.whatsapp        # chat simulator (/wait N, /paid, /payfail); --demo runs every branch -> reports/whatsapp_events.jsonl/.csv
.venv/bin/python -m oytra.dashboard       # -> dashboard/index.html (open in a browser)
.venv/bin/python scripts/build_memo.py    # memo/memo.md -> memo.pdf (needs Chrome/Chromium)
.venv/bin/python scripts/check_consistency.py  # every headline number agrees across reports, dashboard, memo, README
.venv/bin/python scripts/llm_eval.py      # optional, needs GROQ_API_KEY: 60 synthetic cases -> reports/llm_eval.md
.venv/bin/python -m pytest -q             # 79 tests
```

**Dashboard:** one static `dashboard/index.html` (inline CSS/JS, works offline). Day / Night / Auto toggle in the header; the choice is remembered in the browser and Auto follows the device setting. Sections: latest day in data (30 Sep 2026, 9 orders), ₹ saved/lost, orders per action, September backtest vs the Ops rule, model quality, and a searchable, filterable, sortable order table with reasons. Design spec (tokens, layout, accessibility): [`docs/DESIGN.md`](docs/DESIGN.md). Screenshots: `screenshots/dashboard_light.png`, `screenshots/dashboard_dark.png`.

Optional LLM (off by default): copy `.env.example`, set `GROQ_API_KEY` in your environment and `OYTRA_USE_LLM=1` (default model `openai/gpt-oss-20b`, JSON mode; `OPENAI_API_KEY`/`OPENAI_BASE_URL` also work). The key is read from the environment only and never written to the repo, cache or logs. Without it, or if the API fails, the rule-based judge is used. Backtests always use the rule judge. Eval on 60 synthetic cases: `reports/llm_eval.md` (labels are drafts awaiting human review).

## Changing the rules (no code)
Open **`config/rules.csv`** in Excel or Google Sheets: risk thresholds, first-time-buyer protection, what to do with fake names or bad addresses, discount ₹, no-reply actions, and the assumptions (confirmation and prepaid take-up rates). Each row has a plain-English explanation. To run straight off a Google Sheet, publish it as CSV and `export RULES_CSV_URL=<link>`. Cost inputs from the brief are in `config/economics.yaml`. After changing rules, re-run `python -m oytra.backtest` to see the ₹ effect on September.

## How it works
| Layer | What | Why this tool |
|---|---|---|
| Data cleaning (`data.py`) | dedupe, normalise status labels, fix phones/pincodes, parse products and validate `num_items`, flag ₹0 orders, rebuild in-file customer history | code |
| Area history (`features.py`) | pincode RTO rate shrunk toward the state rate, state toward the overall rate (empirical Bayes) | median pincode has 1 order, so raw rates are noise |
| Name/address judge (`llm.py`) | fake name? address complete / landmark-only / vague / unusable? Hinglish-aware | **only place an LLM helps**: messy free text. Rule fallback built in |
| Risk model (`model.py`) | 11-feature logistic regression in numpy, weights inspectable | arithmetic beats an LLM: calibrated, deterministic, cheap, testable |
| Decision (`engine.py`) | risk % → action via `rules.csv` bands, + overrides, + reason from the top drivers | |
| Money (`economics.py`) | expected ₹ for each action per order | thresholds chosen by ₹, not by accuracy |

Labels: **[M]** measured from the CSV · **model** · **HYPOTHETICAL** (depends on assumed WhatsApp/prepaid rates in `rules.csv`).

Backtest (`oytra/backtest.py`): time split (train 1 Apr–31 Aug, 1,658 orders; September 329 orders = retrospective holdout used during development, not an untouched test set). Pincode encoding is chronological (earlier orders only). History model chosen on Apr–Aug by out-of-time folds (`reports/history_model_selection.md`): `reported_history`. September AUC **0.738**, PR-AUC 0.534, Brier 0.164, ECE 0.042 (model).

**Measured (September):** 57 orders flagged (17%); 30 of them were RTO out of 86, carrying ₹5,082 of ₹14,568 RTO cost. Precision 0.53, recall 0.35. Flagged, not prevented.

**HYPOTHETICAL**, net vs ship-everything (no CAC counted as value):

| Scenario | Our rules | Ops' cancel rule |
|---|---|---|
| Conservative | −₹117 | −₹16,595 |
| Base | **₹1,387** | −₹16,595 |
| Optimistic | ₹2,728 | −₹16,595 |

**Walk-forward (`reports/walkforward.md`)**, fixed 40/60/87.5, base ₹ (HYPOTHETICAL): Jun −₹556, Jul ₹1,200, Aug ₹2,642, Sep ₹1,387; conservative negative in Jun, Jul and Sep. Jun–Aug also informed the thresholds, so they are a stability check; table B re-chooses model and thresholds using only earlier months. Argmax-EV is reported only as a comparison (table C); the bands are kept.

**Robustness:** without customer-history fields September AUC is 0.689 and base ₹1,452 (higher ₹ despite lower AUC; the model was chosen on Apr–Aug, not September).

**Rules that never depend on the score** (precedence: `docs/RULE_PRECEDENCE.md`):
- First-time-labelled buyers and orders with unknown/inconsistent history are never auto-cancelled on score.
- Products never trigger a hold.
- ₹0 orders are always confirmed.

See memo §2–3.

## Layout
```
config/      rules.csv (editable), economics.yaml
oytra/       data, features, llm, model, metrics, economics, policy, engine, backtest, history_variants, walkforward, variants, leakage_audit, history_rootcause, ablation, analysis, decide, whatsapp, dashboard
reports/     findings.md, backtest.json, model_variants.json, leakage_audit.json, history_rootcause.json, ablation.json/.md,
             calibration.svg/.png, september_decisions.csv, whatsapp_events.jsonl/.csv
docs/        THRESHOLD_MATHS.md (checked by scripts/check_threshold_maths.py), RULE_PRECEDENCE.md, WHATSAPP_FLOW.md, DESIGN.md, CHANGES_AUDIT_FIXES.md
dashboard/   index.html, summary.json     memo/  memo.md (+ memo.pdf at root)
tests/       pytest suite                data/  orders_sample.csv
```
