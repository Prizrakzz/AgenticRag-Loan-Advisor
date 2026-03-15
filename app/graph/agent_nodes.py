"""Autonomous agent nodes for dynamic loan approval workflow.

These nodes implement the autonomous reasoning loop where the agent plans,
executes, and iterates until a decision is reached.
"""

from typing import Dict, Any
from datetime import datetime

from .state import State, sanitize_state_for_logging
from .planner import generate_plan, should_continue_planning, update_context_from_plan
from .executor import (
    execute_plan, validate_execution_readiness, get_execution_summary,
    should_retry_execution, create_emergency_fallback_decision
)
from ..db.database import get_db_session
from ..db.models import AuditLog
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Normalize logger creation with structlog fallback
try:
    import structlog
    log = structlog.get_logger(__name__)
except Exception:
    import logging
    log = logging.getLogger(__name__)


def _log_agent_node_execution(node_name: str, state: State, input_state: State = None):
    """Log agent node execution and create audit entry."""
    req_id = state.get("req_id", "unknown")
    user_id = state.get("user_id", 0)
    
    if input_state:
        logger.debug("agent_node_input", node=node_name, req_id=req_id)
    
    logger.info("agent_node_output", node=node_name, req_id=req_id)
    
    # Create audit log entry with enhanced context for agent nodes
    try:
        with get_db_session() as db:
            # Include agent-specific state information
            audit_state = sanitize_state_for_logging(state)
            
            # Add agent-specific audit info
            context = state.get("context", {})
            audit_state["agent_audit"] = {
                "iteration_count": context.get("iteration_count", 0),
                "confidence": context.get("confidence"),
                "risk_tier": context.get("risk_tier"),
                "available_data_sources": list(context.get("data_sources", {}).keys()),
                "autonomous_mode": state.get("autonomous_mode", False)
            }
            
            audit_entry = AuditLog.create_entry(
                req_id=req_id,
                username=str(user_id),
                node=node_name,
                state=audit_state
            )
            db.add(audit_entry)
            db.commit()
    except Exception as e:
        logger.error("agent_audit_log_failed", node=node_name, error=str(e))


def agent_init_node(state: State) -> State:
    """
    Initialize autonomous agent mode and prepare context.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with agent context initialized
    """
    input_state = state.copy()
    
    try:
        # Ensure we're in autonomous mode
        state["autonomous_mode"] = True
        
        # Initialize context if not already done
        if "context" not in state:
            from .state import Context
            state["context"] = Context(
                query=state["question"],
                risk_tier=None,
                data_sources={"customer": None, "market": None, "rag": []},
                history=[],
                confidence=None,
                iteration_count=0
            )
        
        # Add user_id to context for easy access
        state["context"]["user_id"] = state["user_id"]
        
        logger.info(
            "agent_initialized",
            req_id=state.get("req_id"),
            user_id=state.get("user_id"),
            query_length=len(state["question"])
        )
        
        _log_agent_node_execution("agent_init_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("agent_init_failed", error=str(e))
        # Fall back to non-autonomous mode
        state["autonomous_mode"] = False
        _log_agent_node_execution("agent_init_node", state, input_state)
        return state


def agent_plan_node(state: State) -> State:
    """
    Generate or update the agent's plan based on current context.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with new plan
    """
    input_state = state.copy()
    
    try:
        req_id = state.get("req_id", "unknown")
        context = state["context"]
        
        logger.info(
            "generating_agent_plan",
            req_id=req_id,
            iteration=context["iteration_count"],
            risk_tier=context.get("risk_tier")
        )
        
        # Generate new plan
        plan = generate_plan(state)
        state["plan"] = plan
        
        logger.info(
            "agent_plan_generated",
            req_id=req_id,
            steps_count=len(plan["steps"]),
            has_final_decision=bool(plan.get("final_decision")),
            confidence=plan.get("confidence"),
            reasoning_preview=plan.get("reasoning", "")[:100]
        )
        
        _log_agent_node_execution("agent_plan_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("agent_planning_failed", error=str(e))
        
        # Create emergency fallback plan
        from .planner import _create_fallback_plan
        fallback_plan = _create_fallback_plan(state["context"])
        state["plan"] = fallback_plan
        
        _log_agent_node_execution("agent_plan_node", state, input_state)
        return state


def agent_execute_node(state: State) -> State:
    
    """
    Execute the current plan.
    
    Args:
        state: Current workflow state with plan to execute
    
    Returns:
        Updated state with execution results
    """

    input_state = state.copy()
    
    try:
        req_id = state.get("req_id", "unknown")
        
        # Validate execution readiness
        if not validate_execution_readiness(state):
            logger.error("execution_not_ready", req_id=req_id)
            _log_agent_node_execution("agent_execute_node", state, input_state)
            return state
        
        logger.info("executing_agent_plan", req_id=req_id)
        
        # Execute the plan
        state = execute_plan(state)
        
        # Get execution summary for logging
        summary = get_execution_summary(state)
        
        logger.info(
            "agent_execution_completed",
            req_id=req_id,
            **summary
        )
        
        _log_agent_node_execution("agent_execute_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("agent_execution_failed", error=str(e))
        _log_agent_node_execution("agent_execute_node", state, input_state)
        return state


def agent_decision_node(state: State) -> State:
    """
    Finalize the agent's decision and prepare for explanation.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with finalized decision
    """
    input_state = state.copy()
    
    try:
        req_id = state.get("req_id", "unknown")
        
        # Update state fields from context
        state = update_context_from_plan(state)
        
        # If we don't have a decision yet, create emergency fallback
        if not state.get("decision"):
            logger.warning("no_decision_creating_fallback", req_id=req_id)
            state = create_emergency_fallback_decision(state)
        
        # Ensure we have reason codes
        if not state.get("reason_codes"):
            context = state.get("context", {})
            decision_data = context.get("data_sources", {}).get("decision", {})
            state["reason_codes"] = decision_data.get("reasons", ["Decision analysis completed"])
        
        logger.info(
            "agent_decision_finalized",
            req_id=req_id,
            decision=state.get("decision"),
            score=state.get("score"),
            confidence=state.get("context", {}).get("confidence"),
            reason_count=len(state.get("reason_codes", []))
        )
        
        _log_agent_node_execution("agent_decision_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("agent_decision_failed", error=str(e))
        
        # Emergency fallback
        state = create_emergency_fallback_decision(state)
        _log_agent_node_execution("agent_decision_node", state, input_state)
        return state


def agent_should_continue(state: State) -> str:
    """
    Routing function to determine if agent should continue planning/executing.
    
    Args:
        state: Current workflow state
    
    Returns:
        Next node name ("plan" to continue, "decision" to finalize)
    """
    req_id = state.get("req_id", "unknown")
    
    # Check if we should continue planning
    if should_continue_planning(state):
        # Check if we should retry execution
        summary = get_execution_summary(state)
        if should_retry_execution(state, summary):
            logger.info("agent_continuing_iteration", req_id=req_id)
            return "plan"
        else:
            logger.info("agent_finalizing_no_retry", req_id=req_id)
            return "decision"
    else:
        logger.info("agent_finalizing_no_continue", req_id=req_id)
        return "decision"


def agent_compatibility_node(state: State) -> State:
    """
    Compatibility node to bridge autonomous agent output to legacy explain node.
    
    This node ensures that the state is properly formatted for the existing
    explain_node to generate the final answer.
    
    Args:
        state: Current workflow state from agent
    
    Returns:
        Updated state compatible with legacy nodes
    """
    input_state = state.copy()
    
    try:
        req_id = state.get("req_id", "unknown")
        context = state.get("context", {})
        
        # Ensure legacy fields are populated from context
        
        # Client data
        customer_data = context.get("data_sources", {}).get("customer")
        if customer_data and isinstance(customer_data, dict) and "error" not in customer_data:
            state["client"] = customer_data
        
        # Market data
        market_data = context.get("data_sources", {}).get("market")
        if market_data and isinstance(market_data, dict) and "error" not in market_data:
            state["market"] = market_data.get("metrics", {})
            state["market_stale"] = market_data.get("stale", False)
        
        # RAG snippets
        rag_data = context.get("data_sources", {}).get("rag")
        if rag_data and isinstance(rag_data, dict) and "snippets" in rag_data:
            state["policy_snippets"] = rag_data["snippets"]
        elif not state.get("policy_snippets"):
            # Provide empty list for explain node
            state["policy_snippets"] = []
        
        # Ensure score is set
        if not state.get("score"):
            decision_data = context.get("data_sources", {}).get("decision", {})
            state["score"] = decision_data.get("score", 0.0)
        
        logger.info(
            "agent_compatibility_prepared",
            req_id=req_id,
            has_client=bool(state.get("client")),
            has_market=bool(state.get("market")),
            snippets_count=len(state.get("policy_snippets", [])),
            decision=state.get("decision"),
            score=state.get("score")
        )
        
        _log_agent_node_execution("agent_compatibility_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("agent_compatibility_failed", error=str(e))
        _log_agent_node_execution("agent_compatibility_node", state, input_state)
        return state


def agent_metrics_node(state: State) -> State:
    """
    Collect and log metrics about the autonomous agent's performance.
    
    Args:
        state: Final workflow state
    
    Returns:
        State with metrics logged (unchanged otherwise)
    """
    input_state = state.copy()
    
    try:
        req_id = state.get("req_id", "unknown")
        context = state.get("context", {})
        
        # Collect performance metrics
        metrics = {
            "req_id": req_id,
            "user_id": state.get("user_id"),
            "autonomous_mode": state.get("autonomous_mode", False),
            "iterations": context.get("iteration_count", 0),
            "final_confidence": context.get("confidence"),
            "final_decision": state.get("decision"),
            "final_score": state.get("score"),
            "total_actions": len(context.get("history", [])),
            "successful_actions": sum(1 for a in context.get("history", []) if a.get("success", False)),
            "data_sources_used": [k for k, v in context.get("data_sources", {}).items() 
                                if v and (not isinstance(v, dict) or "error" not in v)],
            "error_sources": [k for k, v in context.get("data_sources", {}).items() 
                            if isinstance(v, dict) and "error" in v],
            "has_final_answer": bool(state.get("final_answer")),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # Log metrics for analysis
        logger.info("agent_performance_metrics", **metrics)
        
        # Could store metrics in database for analysis
        # This would be useful for the feedback loop implementation
        
        _log_agent_node_execution("agent_metrics_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("agent_metrics_failed", error=str(e))
        _log_agent_node_execution("agent_metrics_node", state, input_state)
        return state 