from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class CustomerLookupInput(BaseModel):
    client_id: int = Field(..., description="Customer numeric client_id")

class CustomerLookupOutput(BaseModel):
    client_id: int
    risk_grade: Optional[str]
    annual_income: Optional[float]
    risk_score: Optional[float]
    employment_status: Optional[str]
    found: bool

class MarketMetricsInput(BaseModel):
    pass

class MarketMetricsOutput(BaseModel):
    market_risk_score: Optional[float]
    stale: bool
    components: Dict[str, Any] = {}

class PolicySearchInput(BaseModel):
    query: str
    top_k: int = 3

class PolicySnippet(BaseModel):
    id: str
    content: str
    score: float

class PolicySearchOutput(BaseModel):
    snippets: List[PolicySnippet]

class ComputeScoreInput(BaseModel):
    risk_grade: str
    annual_income: float
    market_risk_score: Optional[float]

class ComputeScoreOutput(BaseModel):
    approval_score: float
    decision: str
    components: Dict[str, Any]

ToolSpec = Dict[str, Any]

def get_tool_specs() -> List[ToolSpec]:
    return [
        {
            "name": "customer.lookup",
            "description": "Fetch customer profile by client_id.",
            "input_schema": CustomerLookupInput.model_json_schema(),
            "output_schema": CustomerLookupOutput.model_json_schema(),
        },
        {
            "name": "market.read_composite",
            "description": "Get composite market_risk_score and staleness.",
            "input_schema": MarketMetricsInput.model_json_schema(),
            "output_schema": MarketMetricsOutput.model_json_schema(),
        },
        {
            "name": "policy.search",
            "description": "Retrieve top policy snippets relevant to a query.",
            "input_schema": PolicySearchInput.model_json_schema(),
            "output_schema": PolicySearchOutput.model_json_schema(),
        },
        {
            "name": "score.compute",
            "description": "Compute approval score from signals.",
            "input_schema": ComputeScoreInput.model_json_schema(),
            "output_schema": ComputeScoreOutput.model_json_schema(),
        },
    ]
