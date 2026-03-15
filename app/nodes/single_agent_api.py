"""
API Integration for Single Agent Orchestration.
Replaces the existing LangGraph-based loan.py endpoints with single-agent controller.
"""

from fastapi import HTTPException
from typing import Dict, Any
import logging

from .single_agent import process_request
from ..utils.logger import get_logger

logger = get_logger(__name__)


async def decision_endpoint_single_agent(request_data: dict, user_id: str) -> dict:
    """
    Single agent decision endpoint.
    Replaces the complex graph orchestration with tool-calling agent.
    """
    question = request_data.get("question", "").strip()
    
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty")
    
    # Build request for single agent
    agent_request = {
        "req_id": f"req_{user_id}_{hash(question) % 10000}",
        "question": question,
        "client_id": user_id,
        "memory": []  # TODO: Load from conversation history
    }
    
    try:
        # Process with single agent
        response = await process_request(agent_request)
        
        # Map to existing API response format for backward compatibility
        api_response = {
            "decision": response["decision"],
            "answer": response["answer"],
            "explanation": response["answer"],  # Unified field
            "references": response["references"],
            "quick_replies": response["quick_replies"],
            "cta": response["cta"],
            "score": get_confidence_score(response["decision"]),
            "reason_codes": get_reason_codes(response["decision"])
        }
        
        logger.info("decision_completed", 
                   user_id=user_id,
                   decision=response["decision"],
                   answer_length=len(response["answer"]))
        
        return api_response
        
    except Exception as e:
        logger.error("decision_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


def get_confidence_score(decision: str) -> float:
    """Map decision to confidence score for backward compatibility."""
    score_map = {
        "APPROVE": 0.9,
        "DECLINE": 0.8, 
        "INFORM": 0.95,
        "COUNTER": 0.7,
        "REFUSE": 1.0
    }
    return score_map.get(decision, 0.5)


def get_reason_codes(decision: str) -> list:
    """Generate reason codes for backward compatibility."""
    if decision == "REFUSE":
        return ["Content violates usage policy"]
    elif decision == "DECLINE":
        return ["Risk assessment", "Policy constraints"]
    elif decision == "COUNTER":
        return ["Additional information required"]
    else:
        return []


# Integration instructions for existing loan.py
INTEGRATION_GUIDE = """
# Single Agent Integration Steps

## 1. Replace existing decision endpoint in app/api/loan.py

```python
# OLD: Complex graph orchestration
async def decision_endpoint(request_data, user_id):
    # ... complex graph execution ...
    
# NEW: Single agent orchestration  
from .nodes.single_agent_api import decision_endpoint_single_agent

async def decision_endpoint(request_data, user_id):
    return await decision_endpoint_single_agent(request_data, user_id)
```

## 2. Update imports

```python
# Remove old imports
# from .graph.workflow import execute_workflow
# from .nodes.llm_judge import judge_decision

# Add new import
from .nodes.single_agent_api import decision_endpoint_single_agent
```

## 3. Feature flag for gradual rollout

```python
import os

SINGLE_AGENT_ENABLED = os.getenv("SINGLE_AGENT_ENABLED", "false").lower() == "true"

async def decision_endpoint(request_data, user_id):
    if SINGLE_AGENT_ENABLED:
        return await decision_endpoint_single_agent(request_data, user_id)
    else:
        return await legacy_decision_endpoint(request_data, user_id)
```

## 4. Integration with existing data sources

Update the tool functions in single_agent.py to use existing data sources:

```python
async def fetch_customer_data(client_id: str) -> Dict[str, Any]:
    # Replace mock with actual customer service
    from ..db.customer import get_customer_profile
    customer = await get_customer_profile(client_id)
    return {"customer": customer}

async def fetch_market_data(region: str = "OK") -> Dict[str, Any]:
    # Replace mock with actual market service  
    from ..services.market import get_market_conditions
    market = await get_market_conditions(region)
    return {"market": market}

async def policy_retrieval(query: str, k: int = 3, min_score: float = 0.1) -> Dict[str, Any]:
    # Replace mock with existing RAG system
    from ..rag.retriever import search_policies
    snippets = await search_policies(query, top_k=k, min_score=min_score)
    return {"snippets": snippets}
```

## 5. Memory integration

```python
async def load_conversation_memory(user_id: str) -> list:
    # Load last 10 conversation turns
    from ..db.conversations import get_recent_history
    return await get_recent_history(user_id, limit=10)

# Update agent_request in decision_endpoint_single_agent:
agent_request = {
    # ...
    "memory": await load_conversation_memory(user_id)
}
```

## 6. Testing migration

```python
# A/B test both systems
async def test_migration():
    test_questions = [
        "What are car loan requirements?",
        "Can I get a $25k loan?", 
        "What documents do I need?"
    ]
    
    for question in test_questions:
        legacy_response = await legacy_decision_endpoint({"question": question}, "test_user")
        new_response = await decision_endpoint_single_agent({"question": question}, "test_user")
        
        # Compare responses
        assert legacy_response["decision"] == new_response["decision"]
        # Validate semantic similarity, etc.
```

## 7. Monitoring and rollback

```python
# Monitor key metrics
import time

async def decision_endpoint_with_monitoring(request_data, user_id):
    start_time = time.time()
    
    try:
        response = await decision_endpoint_single_agent(request_data, user_id)
        
        # Log success metrics
        duration = time.time() - start_time
        logger.info("decision_success", duration_ms=duration*1000, decision=response["decision"])
        
        return response
        
    except Exception as e:
        # Log failure and fallback
        logger.error("single_agent_failed", error=str(e))
        
        # Circuit breaker: fallback to legacy if too many failures
        if should_fallback_to_legacy():
            return await legacy_decision_endpoint(request_data, user_id)
        else:
            raise
```

## Benefits of Migration

### Simplified Architecture
- **No graph orchestration** - Simple linear flow with tool calls
- **No intent classification step** - Agent decides internally  
- **No parallel coordination complexity** - Sequential tool usage
- **No state merge conflicts** - Single agent owns decisions

### Better LLM Control
- **Evidence-based decisions** - Agent sees all data before deciding
- **Natural tool usage** - Agent chooses what data to fetch
- **Contextual reasoning** - Full conversation awareness
- **Adaptive behavior** - Can adjust strategy based on tool responses

### Operational Benefits  
- **Easier debugging** - Single prompt, clear tool trace
- **Better observability** - Tool calls are explicit 
- **Simpler testing** - Mock tools, test agent responses
- **Faster iteration** - Change prompt, not graph structure

## Rollback Plan

1. **Environment variable**: `SINGLE_AGENT_ENABLED=false`
2. **Circuit breaker**: Auto-fallback on high error rate
3. **Manual override**: Admin endpoint to disable single agent
4. **Gradual rollout**: 10% → 50% → 100% over 3 days
"""
