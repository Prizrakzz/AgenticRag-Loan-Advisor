from typing import Optional, List, Dict, Any
from .schemas import (
    CustomerLookupInput, CustomerLookupOutput,
    MarketMetricsInput, MarketMetricsOutput,
    PolicySearchInput, PolicySearchOutput, PolicySnippet,
    ComputeScoreInput, ComputeScoreOutput
)

# Reuse existing internal utilities where possible
from ..nodes.single_agent import fetch_customer_data
from ..scrape.store import read_all_metrics
from ..rag.retriever import retrieve_policy_snippets


def tool_customer_lookup(inp: CustomerLookupInput) -> CustomerLookupOutput:
    data = None
    try:
        # single_agent fetch expects string id
        data = run_async(fetch_customer_data(str(inp.client_id)))
    except Exception:
        data = None
    if not data:
        return CustomerLookupOutput(client_id=inp.client_id, found=False, risk_grade=None, annual_income=None, risk_score=None, employment_status=None)
    return CustomerLookupOutput(
        client_id=inp.client_id,
        found=True,
        risk_grade=data.get("risk_grade"),
        annual_income=data.get("annual_income"),
        risk_score=data.get("risk_score"),
        employment_status=data.get("employment_status")
    )


def tool_market_read(inp: MarketMetricsInput) -> MarketMetricsOutput:
    metrics = read_all_metrics()
    m = metrics.get("market_risk_score")
    if not m:
        return MarketMetricsOutput(market_risk_score=None, stale=True, components={})
    extra = m.get("extra_json", {}) if isinstance(m, dict) else {}
    components = extra.get("components", {})
    stale = extra.get("market_stale", False)
    return MarketMetricsOutput(market_risk_score=m.get("value"), stale=stale, components=components)


def tool_policy_search(inp: PolicySearchInput) -> PolicySearchOutput:
    try:
        snippets = retrieve_policy_snippets(inp.query, top_k=inp.top_k)
        wrapped = [PolicySnippet(id=s.get("id", str(i)), content=s.get("content", ""), score=s.get("score", 0.0)) for i, s in enumerate(snippets)]
    except Exception:
        wrapped = []
    return PolicySearchOutput(snippets=wrapped)


def tool_score_compute(inp: ComputeScoreInput) -> ComputeScoreOutput:
    grade_map = {"A": 0.8, "B": 0.65, "C": 0.45, "D": 0.3}
    base = grade_map.get(inp.risk_grade, 0.5)
    income_component = min(1.0, inp.annual_income / 150.0)  # assuming income in thousands
    # Market risk lowers approval: convert risk (0=low risk => high approval) to contribution
    if inp.market_risk_score is not None:
        market_component = 1 - inp.market_risk_score
    else:
        market_component = 0.5  # neutral if unknown
    weights = {"grade": 0.5, "income": 0.3, "market": 0.2}
    raw = (weights["grade"] * base +
           weights["income"] * income_component +
           weights["market"] * market_component)
    approval = round(max(0.0, min(1.0, raw)), 3)
    if approval >= 0.7:
        decision = "APPROVE"
    elif approval >= 0.5:
        decision = "COUNTER"
    else:
        decision = "DECLINE"
    components = {
        "base_from_grade": base,
        "income_component": income_component,
        "market_component": market_component,
        "weights": weights
    }
    return ComputeScoreOutput(approval_score=approval, decision=decision, components=components)

# Helper to run async function from sync context
import asyncio

def run_async(awaitable):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # In an already-running loop; schedule a new task
        return asyncio.create_task(awaitable)  # caller must handle task
    else:
        return asyncio.run(awaitable)
