#!/usr/bin/env bash
# One command: install, analyse, train+backtest, walk-forward, demo, dashboard, consistency check, tests.
# Offline: no API key needed. The LLM eval (scripts/llm_eval.py) is separate and needs GROQ_API_KEY.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
PY=.venv/bin/python
echo "== 1a. History + product checks =="; $PY -m oytra.variants > /dev/null && echo "reports/model_variants.json"
echo "== 1b. History model selection (Apr-Aug only) =="; $PY -m oytra.history_variants > /dev/null && echo "reports/history_model_selection.json, .md"
echo "== 2. Train + backtest ==";         $PY -m oytra.backtest | head -1 && echo "reports/backtest.json, reports/september_decisions.csv, reports/calibration.png"
echo "== 2a. Walk-forward (Jun-Sep) ==";   $PY -m oytra.walkforward > /dev/null && echo "reports/walkforward.json, reports/walkforward.md"
echo "== 2b. Leakage audit ==";           $PY -m oytra.leakage_audit > /dev/null && echo "reports/leakage_audit.json"
echo "== 2c. History root cause ==";      $PY -m oytra.history_rootcause > /dev/null && echo "reports/history_rootcause.json"
echo "== 2d. Feature ablation ==";        $PY -m oytra.ablation > /dev/null && echo "reports/ablation.json, reports/ablation.md"
echo "== 2e. Data findings ==";           $PY -m oytra.analysis > /dev/null && echo "reports/findings.md"
echo "== 2f. Threshold maths check ==";   PYTHONPATH=. $PY scripts/check_threshold_maths.py | tail -1
echo "== 3. Score example orders ==";     $PY -m oytra.decide --examples
echo "== 4. WhatsApp flow demo ==";       $PY -m oytra.whatsapp --demo | tail -1
echo "== 5. Dashboard ==";                $PY -m oytra.dashboard | head -1
echo "== 5b. Consistency check ==";      $PY scripts/check_consistency.py | tail -1
echo "== 6. Tests ==";                    $PY -m pytest -q
