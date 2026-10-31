"""Regression: missing/None/NaN customer history must be UNKNOWN_OR_INCONSISTENT, never first-time."""
import os, math, pytest
os.environ.pop("OPENAI_API_KEY", None); os.environ.pop("GROQ_API_KEY", None); os.environ["OYTRA_USE_LLM"] = "0"
from oytra.engine import Engine
from oytra.llm import RuleJudge

BASE = {"order_id": "MH1", "order_datetime": "2026-09-10 10:00", "customer_name": "Asha Rao", "phone": "9876543210",
        "address": "Flat 12, Shanti Apartments, MG Road", "city": "Patna", "state": "Bihar", "pincode": 800001,
        "order_value": 649, "items": "Satin Bonnet", "num_items": 1, "utm_source": "meta_ads"}
ACTIONS = {"SHIP", "CONFIRM", "NUDGE", "HOLD"}

@pytest.fixture(scope="module")
def eng():
    return Engine.load(judge=RuleJudge())


@pytest.mark.parametrize("hist", [{}, {"customer_prior_orders": None, "customer_prior_rto": None},
                                  {"customer_prior_orders": math.nan, "customer_prior_rto": math.nan},
                                  {"customer_prior_orders": 2, "customer_prior_rto": None}])
def test_missing_history_is_unknown(eng, hist):
    import pandas as pd
    from oytra.features import _reported_state
    o = {**BASE, **hist}
    row = pd.Series({"customer_prior_orders": o.get("customer_prior_orders"), "customer_prior_rto": o.get("customer_prior_rto")})
    assert _reported_state(row) == "UNKNOWN_OR_INCONSISTENT"
    r = eng.decide(o)
    assert r["action"] in ACTIONS and 0 <= r["risk"] <= 1

@pytest.mark.parametrize("po,pr,state", [(0, 0, "REPORTED_FIRST_TIME"), (3, 0, "REPORTED_RETURNING"), (1, 2, "UNKNOWN_OR_INCONSISTENT")])
def test_explicit_history_unchanged(po, pr, state):
    import pandas as pd
    from oytra.features import _reported_state
    assert _reported_state(pd.Series({"customer_prior_orders": po, "customer_prior_rto": pr})) == state
