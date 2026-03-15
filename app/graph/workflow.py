"""LangGraph workflow for loan approval decision making.

This module defines the workflow graph that can operate in two modes:
1. Rule-based mode (original): Fixed DAG with deterministic nodes
2. Autonomous mode (new): Dynamic agent that plans and executes actions
"""

import logging
import os
from langgraph.graph import StateGraph, END
from typing import Dict, Any

from .state import State, Context
from .nodes import (
    auth_node, market_node, risk_gate_node, 
    score_node, decision_node, policy_rag_node, explain_node
)
from .agent_nodes import (
    agent_init_node, agent_plan_node, agent_execute_node,
    agent_decision_node, agent_should_continue, 
    agent_compatibility_node, agent_metrics_node
)
from ..nodes.guardrail import guardrail_node, guardrail_out_node
from ..nodes.llm_judge import judge_and_explain_node
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Global cached workflow instance
_workflow = None


def create_workflow() -> StateGraph:
    """
    Create the loan approval workflow graph with guardrails and LLM judge.
    
    Returns:
        StateGraph configured with guardrails and judge flow
    """
    # Initialize the graph
    workflow = StateGraph(State)
    
    # === GUARDRAIL AND JUDGE NODES ===
    workflow.add_node("guardrail_in", guardrail_node)
    workflow.add_node("intent_classifier", _intent_classifier_node)
    workflow.add_node("customer_node", auth_node)
    workflow.add_node("market_node", market_node)
    workflow.add_node("policy_rag_node", policy_rag_node)
    workflow.add_node("score_node", score_node)
    workflow.add_node("judge_and_explain", judge_and_explain_node)
    workflow.add_node("guardrail_out", guardrail_out_node)
    workflow.add_node("serializer", _serializer_node)
    
    # === LEGACY NODES (for fallback) ===
    workflow.add_node("decision", decision_node)
    workflow.add_node("explain", explain_node)
    
    # === ROUTING LOGIC ===
    
    # Entry point: Start with input guardrail
    workflow.set_entry_point("guardrail_in")
    
    # === NEW GUARDRAIL + JUDGE FLOW ===
    
    # Conditional routing function for guardrail results
    def route_after_guardrail(state):
        """Route based on guardrail result."""
        if state.get("guardrail_violation"):
            return "serializer"  # Skip to end if guardrail violation
        return "intent_classifier"  # Continue normal flow
    
    # guardrail_in -> conditional routing
    workflow.add_conditional_edges(
        "guardrail_in",
        route_after_guardrail,
        {
            "serializer": "serializer",
            "intent_classifier": "intent_classifier"
        }
    )
    
    # intent_classifier -> sequential data gathering (TEMP FIX for concurrency)
    workflow.add_edge("intent_classifier", "customer_node")
    workflow.add_edge("customer_node", "market_node") 
    workflow.add_edge("market_node", "policy_rag_node")
    
    # Sequential nodes -> score_node 
    workflow.add_edge("policy_rag_node", "score_node")
    
    # score_node -> judge_and_explain
    workflow.add_edge("score_node", "judge_and_explain")
    
    # judge_and_explain -> guardrail_out
    workflow.add_edge("judge_and_explain", "guardrail_out")
    
    # guardrail_out -> serializer
    workflow.add_edge("guardrail_out", "serializer")
    
    # serializer -> END
    workflow.add_edge("serializer", END)
    
    return workflow


def _intent_classifier_node(state):
    """Simple intent classifier node."""
    question = state.get("question", "")
    
    # Simple classification based on keywords
    decision_keywords = ["loan", "approve", "apply", "credit", "borrow", "finance"]
    policy_keywords = ["policy", "rate", "requirement", "term", "condition", "documentation"]
    
    question_lower = question.lower()
    
    if any(word in question_lower for word in decision_keywords):
        state["intent"] = "decision"
    elif any(word in question_lower for word in policy_keywords):
        state["intent"] = "policy"
    else:
        state["intent"] = "general"
    
    logger.info("intent_classified", req_id=state.get("req_id"), intent=state["intent"])
    return state


def _serializer_node(state):
    """Serializer node to format final response."""
    # Ensure all required fields are present
    state.setdefault("decision", "INFORM")
    state.setdefault("final_answer", "I'd be happy to help with your question.")
    state.setdefault("references", [])
    state.setdefault("quick_replies", [])
    state.setdefault("cta", None)
    
    logger.info("response_serialized", req_id=state.get("req_id"), decision=state["decision"])
    return state
    
    # explain -> agent_metrics (collect performance data)
    workflow.add_edge("explain", "agent_metrics")
    
    # agent_metrics -> END
    workflow.add_edge("agent_metrics", END)
    
    # === RULE-BASED FLOW (ORIGINAL) - DISABLED TO PREVENT STATE CONFLICTS ===
    # Legacy nodes are preserved for potential dynamic invocation by the agent,
    # but their direct edges are removed to avoid "market already being used" errors
    # when the autonomous flow writes to the same state keys.
    
    # REMOVED: auth -> market -> risk_gate -> score/decision flow
    # The agent can still invoke these nodes individually via modules.py
    
    return workflow


def _route_entry_point(state: State) -> str:
    """
    Route the workflow entry based on autonomous mode setting.
    
    Args:
        state: Initial workflow state
    
    Returns:
        Entry node name
    """
    autonomous_mode = state.get("autonomous_mode", False)
    
    logger.info(
        "workflow_entry_routing",
        req_id=state.get("req_id"),
        autonomous_mode=autonomous_mode
    )
    
    if autonomous_mode:
        return "autonomous"
    else:
        return "policy"


def _route_after_explain(state: State) -> str:
    """
    Route after explain node based on autonomous mode.
    
    Args:
        state: Current workflow state
    
    Returns:
        Next node name
    """
    autonomous_mode = state.get("autonomous_mode", False)
    
    if autonomous_mode:
        return "metrics"
    else:
        return "end"


def _route_after_risk_gate(state: State) -> str:
    """
    Route after risk gate based on client risk profile.
    
    Args:
        state: Current workflow state
    
    Returns:
        Next node name
    """
    client = state.get("client", {})
    if not client:
        logger.warning("no_client_data_in_risk_gate", req_id=state.get("req_id"))
        return "decline"
    
    risk_grade = client.get("risk_grade", "C")
    
    # High risk (A) gets declined immediately and explained
    if risk_grade == "A":
        logger.info("high_risk_client_declined", req_id=state.get("req_id"), risk_grade=risk_grade)
        # Set decision for policy RAG
        state["decision"] = "DECLINE"
        state["reason_codes"] = ["High risk grade"]
        state["score"] = 0.2
        return "decline"
    else:
        logger.info("client_proceeding_to_scoring", req_id=state.get("req_id"), risk_grade=risk_grade)
        return "continue"


def run_decision(req_id: str, user_id: int, question: str, autonomous: bool = True, memory: list = None) -> Dict[str, Any]:
    """
    Run the loan approval decision workflow with guardrails.
    
    Args:
        req_id: Request ID for tracking
        user_id: Authenticated user ID  
        question: User's loan question
        autonomous: Whether to use autonomous agent mode (default: True)
        memory: Recent conversation memory for context (optional)
    
    Returns:
        Final workflow state as dict
    """
    from .state import new_state, Message
    
    logger.info(
        "workflow_starting",
        req_id=req_id,
        user_id=user_id,
        autonomous=autonomous,
        question_length=len(question),
        memory_count=len(memory) if memory else 0
    )
    
    try:
        # Create initial state
        initial_state = new_state(req_id, user_id, question, autonomous, memory)
        
        # Add memory to context if provided
        if memory:
            if "context" not in initial_state:
                initial_state["context"] = {}
            initial_state["context"]["history"] = memory
        
        # Run through the new guardrail-enabled workflow
        workflow = get_workflow()  # This gets our new workflow with guardrails
        
        # TEMP: Add state write instrumentation
        original_state = initial_state.copy()
        def log_state_changes(current_state, step_name="unknown"):
            for key in current_state:
                if key not in original_state or current_state[key] != original_state[key]:
                    logger.info(f"[state_write] req_id={req_id} node={step_name} key={key} op=set")
        
        final_state = workflow.invoke(initial_state)
        
        # Check for guardrail violations (REFUSE decision indicates guardrail block)
        if final_state.get("decision") == "REFUSE":
            logger.warning("guardrail_violation_detected", req_id=req_id)
        
        # ensure explanation & snippets always set (defensive)
        if not final_state.get("explanation"):
            final_state["explanation"] = final_state.get("final_answer", "A concise explanation is provided based on available policy.")
        if final_state.get("snippets") is None:
            final_state["snippets"] = []
        
        # INSTRUMENTATION: Log flow completion
        logger.info(
            "workflow_completion",
            req_id=req_id,
            decision=final_state.get("decision"),
            autonomous=autonomous,
            final_answer_length=len(final_state.get("final_answer", "")),
            explanation_length=len(final_state.get("explanation", "")),
            snippet_count=len(final_state.get("snippets", [])),
            guardrail_triggered=final_state.get("guardrail_violation", False)
        )
        
        return final_state
        
    except Exception as e:
        logger.error("workflow_execution_failed", req_id=req_id, error=str(e), error_type=type(e).__name__)
        
        # Return a safe fallback response
        return {
            "req_id": req_id,
            "decision": "DECLINE",
            "reason_codes": ["Workflow execution error"],
            "final_answer": "I'm sorry, but I'm unable to process your request at this time. Please try again later.",
            "explanation": f"Workflow error: {str(e)}",
            "score": 0.0,
            "snippets": [],
            "autonomous_mode": autonomous,
            "workflow_error": True
        }


def _run_policy_flow(req_id: str, user_id: int, question: str, autonomous: bool, memory: list = None) -> Dict[str, Any]:
    """
    Run policy-based information flow for loan questions.
    
    Args:
        req_id: Request ID for tracking
        user_id: User ID  
        question: User's question
        autonomous: Whether autonomous mode was requested
        memory: Chat history for context
        
    Returns:
        Final state dict
    """
    # This is a simple policy flow implementation
    # For now, just create a basic response
    from .state import new_state
    
    try:
        # Create initial state for policy flow
        initial_state = new_state(req_id, user_id, question, autonomous, memory)
        
        # Set basic response for policy questions
        initial_state.update({
            "decision": "INFORM",
            "final_answer": "I'm here to help with your Arab Bank loan inquiry. How can I assist you?",
            "explanation": "Policy information is available for loan products.",
            "score": 0.0,
            "reason_codes": [],
            "snippets": []
        })
        
        return initial_state
        
    except Exception as e:
        logger.error("policy_flow_error", req_id=req_id, error=str(e))
        return {
            "req_id": req_id,
            "decision": "DECLINE", 
            "final_answer": "I'm sorry, there was an error processing your request.",
            "explanation": "System error in policy flow",
            "score": 0.0,
            "reason_codes": ["System error"],
            "snippets": []
        }


def _run_autonomous_flow(state: State) -> Dict[str, Any]:
    """Entry point for autonomous agent workflow"""
    print("🟢 AUTONOMOUS FLOW: Starting autonomous agent workflow")
    print(f"🟢 AUTONOMOUS FLOW: Initial state keys: {list(state.keys())}")
    
    # Create context for autonomous agent
    context = state.get("context", {})
    if not context:
        context = Context(
            step_history=[],
            data_sources={},
            validation_results={}
        )
    
    # Initialize state for autonomous flow
    new_state = {
        **state,
        "context": context,
        "workflow_type": "autonomous"
    }
    
    print(f"🟢 AUTONOMOUS FLOW: Initialized context, proceeding to agent_init")
    return {"workflow_type": "autonomous", "context": context}


def _run_policy_flow(req_id: str, user_id: int, question: str, autonomous: bool, memory: list = None) -> Dict[str, Any]:
    """Run the enhanced policy flow with optional LLM judge."""
    from .state import new_state
    from .nodes import policy_rag_node, explain_node, auth_node, market_node, score_node
    from ..nodes.llm_judge import judge_and_explain_node
    from ..utils.config import settings
    
    logger.info("starting_policy_flow", req_id=req_id, question_length=len(question or ""))
    
    try:
        # Create initial state
        initial_state = new_state(req_id, user_id, question, autonomous, memory)
        
        # Add memory to context if provided (memory is already in state but also in context for compatibility)
        if memory:
            if "context" not in initial_state:
                initial_state["context"] = {}
            initial_state["context"]["history"] = memory
        
        # Check if we should use LLM judge (for questions that might benefit from decision logic)
        use_judge = _should_use_judge(question)
        
        if use_judge:
            logger.info("using_llm_judge_for_policy", req_id=req_id)
            
            # Load customer and market data for context
            state_with_customer = auth_node(initial_state)
            state_with_market = market_node(state_with_customer)
            state_with_score = score_node(state_with_market)
            
            # Run RAG search to get policy snippets
            state_with_rag = policy_rag_node(state_with_score)
            
            # Use LLM judge for enhanced response
            final_state = judge_and_explain_node(state_with_rag)
            
        else:
            logger.info("using_traditional_policy_flow", req_id=req_id)
            
            # Run RAG search to get policy snippets
            rag_state = policy_rag_node(initial_state)
            
            # Generate LLM explanation
            final_state = explain_node(rag_state)
        
        # Ensure decision is INFORM for policy questions (unless judge set it)
        if not final_state.get("decision"):
            final_state["decision"] = "INFORM"
            logger.info("set_decision_to_inform", req_id=req_id)
        
        # Ensure snippets field for frontend display
        snippets = final_state.get("policy_snippets", [])
        snippet_texts = []
        for snippet in snippets[:3]:
            content = snippet.get('page_content', str(snippet))
            if content:
                snippet_texts.append(content[:200])  # Truncate for display
        
        final_state["snippets"] = snippet_texts
        
        # Ensure enhanced response fields are present
        final_state.setdefault("references", [])
        final_state.setdefault("quick_replies", [])
        final_state.setdefault("cta", None)
        
        logger.info("policy_flow_completed", req_id=req_id, 
                   decision=final_state.get("decision"),
                   snippets_count=len(snippet_texts),
                   has_explanation=bool(final_state.get("explanation")),
                   used_judge=use_judge)
        
        return final_state
        
    except Exception as e:
        logger.error("policy_flow_failed", req_id=req_id, error=str(e))
        # Create minimal fallback for policy flow
        from .state import new_state
        fallback_state = new_state(req_id, user_id, question, autonomous, memory)
        fallback_state["decision"] = "INFORM"
        fallback_state["explanation"] = "I can provide general loan policy information, but detailed analysis is temporarily unavailable."
        fallback_state["final_answer"] = fallback_state["explanation"]
        fallback_state["snippets"] = []
        fallback_state["policy_snippets"] = []
        fallback_state["references"] = []
        fallback_state["quick_replies"] = []
        fallback_state["cta"] = None
        return fallback_state


def _should_use_judge(question: str) -> bool:
    """Determine if question should use LLM judge instead of basic explain."""
    if not question:
        return False
    
    # Use judge for questions that might benefit from decision logic
    judge_keywords = [
        "approve", "loan", "credit", "borrow", "apply", "qualify", 
        "eligible", "get", "amount", "how much", "can i"
    ]
    
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in judge_keywords)


def _add_agent_debug_metadata(state: State) -> None:
    """
    Add agent debug metadata to the state for debugging purposes.
    
    Args:
        state: Final workflow state to add metadata to
    """
    try:
        context = state.get("context", {})
        plan = state.get("plan")
        
        # Collect actions taken from history
        actions_taken = []
        for action in context.get("history", []):
            actions_taken.append({
                "action": action.get("action"),
                "success": action.get("success", False),
                "error": action.get("error"),
                "timestamp": action.get("timestamp")
            })
        
        # Build agent metadata
        agent_meta = {
            "iterations": context.get("iteration_count", 0),
            "actions_taken": actions_taken,
            "final_confidence": context.get("confidence"),
            "data_sources_available": [
                k for k, v in context.get("data_sources", {}).items() 
                if v is not None and (not isinstance(v, dict) or "error" not in v)
            ],
            "data_sources_errors": [
                k for k, v in context.get("data_sources", {}).items() 
                if isinstance(v, dict) and "error" in v
            ]
        }
        
        # Add plan information if available
        if plan:
            # Mask sensitive data in plan
            plan_debug = {
                "reasoning": plan.get("reasoning", ""),
                "steps": [
                    {
                        "action": step.get("action"),
                        "params_keys": list(step.get("params", {}).keys()) if isinstance(step.get("params"), dict) else []
                    }
                    for step in plan.get("steps", [])
                ],
                "final_decision": plan.get("final_decision"),
                "confidence": plan.get("confidence")
            }
            agent_meta["plan"] = plan_debug
        
        # Add to state metadata (create if doesn't exist)
        if "metadata" not in state:
            state["metadata"] = {}
        
        state["metadata"]["agent_meta"] = agent_meta
        
        logger.debug("agent_debug_metadata_added", req_id=state.get("req_id"), 
                    iterations=agent_meta["iterations"], 
                    actions_count=len(actions_taken))
        
    except Exception as e:
        logger.warning("failed_to_add_agent_debug_metadata", error=str(e))


def get_workflow():
    """Return the cached compiled workflow instance."""
    global _workflow
    if _workflow is None:
        wf = create_workflow()
        _workflow = wf.compile()
        logger.info("workflow_compiled")
    return _workflow


def get_compiled_workflow():
    """Back-compat shim. Prefer get_workflow()."""
    return get_workflow()


__all__ = ["get_workflow", "get_compiled_workflow", "run_decision", "get_workflow_info"]


def get_workflow_info() -> Dict[str, Any]:
    """
    Get information about the available workflow modes and capabilities.
    
    Returns:
        Workflow information dict
    """
    from .modules import get_available_modules
    
    return {
        "modes": {
            "rule_based": {
                "description": "Original deterministic workflow with fixed node sequence",
                "nodes": ["auth", "market_fetch", "risk_gate", "risk_score", "decision_node", "policy_rag", "explain"],
                "features": ["Fast execution", "Predictable behavior", "Rule-based decisions"]
            },
            "autonomous": {
                "description": "AI-driven agent that dynamically plans and executes actions",
                "nodes": ["agent_init", "agent_plan", "agent_execute", "agent_decision", 
                         "agent_compatibility", "explain", "agent_metrics"],
                "features": ["Dynamic planning", "Context-aware decisions", "Iterative refinement", 
                           "Performance tracking"]
            }
        },
        "available_modules": get_available_modules(),
        "routing": {
            "entry_point": "autonomous_mode flag determines workflow path",
            "autonomous_loop": "agent_execute -> agent_should_continue -> [plan|decision]",
            "fallback": "Emergency decision creation on failures"
        }
    }
