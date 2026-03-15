"""LLM-driven planning and reasoning layer for autonomous agent.

This module contains the pl    "final_decision": {"enum": ["APPROVE", "COUNTER", "DECLINE", "INFORM", null]},nner that analyzes the current context and generates
a plan of actions to take. It uses GPT-4 with structured output to ensure
reliable plan generation.
"""

import json
import openai
from typing import Dict, Any, List, Optional
from datetime import datetime

from .state import State, Context, AgentPlan, PlanStep
from .modules import get_available_modules
from ..utils.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Initialize OpenAI client with modern approach
try:
    api_key = getattr(settings, 'openai_api_key', None)
    if not api_key:
        logger.error("OPENAI_API_KEY not set - planning will fail")
        client = None
    else:
        client = openai.OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error("Failed to initialize OpenAI client: %s", str(e))
    client = None


def _build_enhanced_context_summary(state: State) -> str:
    """Build enhanced context summary with rich metadata for agent planning."""
    context = state["context"]
    data_sources = context.get("data_sources", {})
    
    summary_parts = []
    
    # Market conditions analysis
    market_data = data_sources.get("market_data", {})
    if market_data and isinstance(market_data, dict) and "error" not in market_data:
        summary_parts.append("=== MARKET CONDITIONS ===")
        condition = market_data.get("condition", "unknown")
        prime_rate = market_data.get("prime_rate")
        econ = market_data.get("economic_indicators", {})
        
        summary_parts.append(f"Market Environment: {condition.upper()}")
        if prime_rate:
            summary_parts.append(f"Prime Rate: {prime_rate}% ({'FAVORABLE' if prime_rate < 5.0 else 'ELEVATED' if prime_rate > 6.5 else 'NORMAL'})")
        
        if econ:
            gdp = econ.get("gdp_growth")
            unemployment = econ.get("unemployment")
            if gdp: summary_parts.append(f"GDP Growth: {gdp}%")
            if unemployment: summary_parts.append(f"Unemployment: {unemployment}%")
            
        summary_parts.append("💡 IMPACT: Market conditions should significantly influence loan decisions!")
    
    # Customer profile analysis  
    customer_data = data_sources.get("customer", {})
    if customer_data and isinstance(customer_data, dict) and "error" not in customer_data:
        summary_parts.append("\n=== CUSTOMER PROFILE ===")
        risk_grade = customer_data.get("risk_grade", "unknown")
        summary_parts.append(f"Risk Grade: {risk_grade}")
        
        if "income" in customer_data:
            summary_parts.append(f"Income: ${customer_data['income']:,}")
        if "credit_score" in customer_data:
            summary_parts.append(f"Credit Score: {customer_data['credit_score']}")
    
    # RAG knowledge analysis
    rag_data = data_sources.get("rag", {})
    if rag_data and isinstance(rag_data, dict) and "snippets" in rag_data:
        snippets = rag_data["snippets"]
        summary_parts.append("\n=== POLICY KNOWLEDGE ===")
        summary_parts.append(f"Retrieved: {len(snippets)} policy documents")
        
        if rag_data.get("metadata_enhanced"):
            high_conf = rag_data.get("high_confidence_count", 0)
            avg_score = rag_data.get("avg_relevance_score", 0)
            summary_parts.append(f"High Confidence Sources: {high_conf}")
            summary_parts.append(f"Average Relevance: {avg_score:.2f}")
            
            # Show document types available
            doc_types = set()
            for snippet in snippets[:3]:  # Top 3
                if isinstance(snippet, dict):
                    doc_type = snippet.get("document_type", "Unknown")
                    section = snippet.get("section_summary", "")
                    doc_types.add(doc_type)
                    
            if doc_types:
                summary_parts.append(f"Document Types: {', '.join(doc_types)}")
                
        summary_parts.append("💡 USE: Reference specific policy sections (P1, P2, P3) in your reasoning!")
    
    # Decision guidance
    summary_parts.append("\n=== DECISION GUIDANCE ===")
    summary_parts.append("• Factor market conditions heavily (±25 pts impact)")
    summary_parts.append("• Reference specific policy sections when available")  
    summary_parts.append("• Consider economic indicators for risk assessment")
    summary_parts.append("• Use enhanced metadata for transparent explanations")
    
    return "\n".join(summary_parts)


def build_planner_prompt(state: State) -> List[Dict[str, str]]:
    """
    Build the prompt for the LLM planner based on current state.
    
    Args:
        state: Current workflow state with context
    
    Returns:
        List of message dicts for OpenAI chat completion
    """
    context = state["context"]
    
    # Build context summary
    data_status = {}
    for source, data in context["data_sources"].items():
        if data is None:
            data_status[source] = "not_fetched"
        elif isinstance(data, dict) and "error" in data:
            data_status[source] = "error"
        elif isinstance(data, list) and len(data) == 0:
            data_status[source] = "empty"
        else:
            data_status[source] = "available"
    
    # Add DEBUG log for planner input
    logger.debug("planner_input_context", req_id=state.get("req_id"), data_status=data_status)
    
    # Build history summary
    recent_actions = [action["action"] for action in context["history"][-5:]]
    failed_actions = [action["action"] for action in context["history"] if not action.get("success", True)]
    
    system_prompt = f"""You are an autonomous loan approval agent that plans data gathering and decision-making steps.

AVAILABLE ACTIONS:
- fetch_customer: Load customer profile, risk grade, income data from database
  Parameters: {{"client_id": int}} (optional, will use current user if not provided)
- fetch_market: Get current market conditions, interest rates, economic indicators
  Parameters: {{}} (no parameters needed)
- rag_search: Search policy documents for relevant loan criteria and guidelines
  Parameters: {{"query": str, "k": int}} (k defaults to 8 if not provided)
- compute_decision: Calculate final loan decision using available data
  Parameters: {{}} (no parameters needed)

JSON SCHEMA (STRICT):
{{
  "type": "object",
  "properties": {{
    "reasoning": {{"type": "string", "minLength": 10}},
    "steps": {{
      "type": "array",
      "minItems": 1,
      "maxItems": 5,
      "items": {{
        "type": "object",
        "properties": {{
          "action": {{"enum": ["fetch_customer", "fetch_market", "rag_search", "compute_decision"]}},
          "params": {{"type": "object"}}
        }},
        "required": ["action", "params"],
        "additionalProperties": false
      }}
    }},
    "final_decision": {{"enum": ["APPROVE", "COUNTER", "DECLINE", null]}},
    "confidence": {{"type": "number", "minimum": 0.0, "maximum": 1.0}}
  }},
  "required": ["reasoning", "steps", "final_decision", "confidence"],
  "additionalProperties": false
}}

EXAMPLES:
Good: {{"reasoning": "Need customer data first", "steps": [{{"action": "fetch_customer", "params": {{}}}}], "final_decision": null, "confidence": 0.5}}
Good: {{"reasoning": "Policy question requires search", "steps": [{{"action": "rag_search", "params": {{"query": "loan terms Oklahoma", "k": 8}}}}], "final_decision": null, "confidence": 0.7}}
Bad: {{"reasoning": "Need data", "steps": [{{"action": "fetch_customer", "params": null}}], "final_decision": null, "confidence": 0.5}}

CRITICAL RULES:
- Never return null for params. Use empty object {{}} when no arguments needed.
- All actions must be from the allowed list.
- Confidence must be between 0.0 and 1.0.
- Steps array must have 1-5 items.
- Reasoning must be descriptive (10+ characters).

Current context:
- Query: "{context['query']}"
- Risk tier: {context.get('risk_tier', 'unknown')}
- Iteration: {context['iteration_count']}
- Data status: {data_status}
- Recent actions: {recent_actions}
- Failed actions: {failed_actions}
- Confidence: {context.get('confidence', 'unknown')}

ENHANCED CONTEXT AWARENESS:
{_build_enhanced_context_summary(state)}"""
    
    user_prompt = f"""Plan the next steps for this loan application:

Query: "{context['query']}"
Current situation: {data_status}
Iteration: {context['iteration_count']}

Return ONLY valid JSON matching the schema. No additional text."""
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]


def generate_plan(state: State) -> AgentPlan:
    """
    Generate an action plan using the LLM planner with strict validation.
    
    Args:
        state: Current workflow state
    
    Returns:
        AgentPlan with steps and reasoning
    
    Raises:
        Exception: If planning fails after retries
    """
    context = state["context"]
    req_id = state.get("req_id", "unknown")
    
    # Increment iteration counter
    context["iteration_count"] += 1
    
    logger.info(
        "generating_plan",
        req_id=req_id,
        iteration=context["iteration_count"],
        risk_tier=context.get("risk_tier"),
        query_length=len(context["query"])
    )
    
    # Check for maximum iterations to prevent infinite loops
    max_iterations = 5
    if context["iteration_count"] > max_iterations:
        logger.warning("max_iterations_reached", req_id=req_id)
        return _create_fallback_plan(context)
    
    # Build prompt
    messages = build_planner_prompt(state)
    
    # Try planning with validation retries (up to 2 retries)
    for attempt in range(3):
        try:
            if not client:
                raise Exception("OpenAI client not initialized - check OPENAI_API_KEY")
                
            response = client.chat.completions.create(
                model=settings.llm.chat_model,
                messages=messages,
                max_tokens=settings.llm.max_tokens,
                temperature=0.2,  # Low temperature for consistent planning
                response_format={"type": "json_object"}
            )
            
            plan_json = response.choices[0].message.content
            
            # Add DEBUG log for raw LLM output (preview)
            logger.debug("planner_raw_llm_output_preview", req_id=req_id, 
                        plan_preview=plan_json[:200] + "..." if len(plan_json) > 200 else plan_json)
            
            plan_dict = json.loads(plan_json)
            
            # Strict validation with detailed error reporting
            validated_plan = _validate_plan_strict(plan_dict, req_id)
            
            logger.info(
                "plan_generated",
                req_id=req_id,
                iteration=context["iteration_count"],
                steps_count=len(validated_plan["steps"]),
                has_final_decision=bool(validated_plan.get("final_decision")),
                confidence=validated_plan.get("confidence")
            )
            
            # Add DEBUG log for the final plan
            logger.debug("planner_final_plan_json", req_id=req_id, plan=json.dumps(validated_plan))

            return AgentPlan(
                reasoning=validated_plan["reasoning"],
                steps=validated_plan["steps"],
                final_decision=validated_plan.get("final_decision"),
                confidence=validated_plan["confidence"]
            )
            
        except PlanValidationError as e:
            logger.warning("planner_validation_errors", req_id=req_id, attempt=attempt + 1, errors=str(e))
            
            if attempt < 2:  # Retry with repair prompt
                repair_prompt = f"""Your last output failed validation: {str(e)}

Return a corrected JSON only. Follow the schema exactly:
- reasoning: string (10+ chars)
- steps: array of 1-5 objects with action (from allowed list) and params (object, never null)
- final_decision: "APPROVE"/"COUNTER"/"DECLINE"/"INFORM"/null
- confidence: number 0.0-1.0

Query: "{context['query']}"
Data status: {dict((k, v) for k, v in context["data_sources"].items() if v is not None)}"""
                
                messages = [{"role": "user", "content": repair_prompt}]
                continue
            else:
                return _create_fallback_plan(context)
            
        except json.JSONDecodeError as e:
            logger.warning("plan_json_decode_error", req_id=req_id, attempt=attempt + 1, error=str(e))
            if attempt == 2:
                return _create_fallback_plan(context)
            
        except Exception as e:
            logger.error("plan_generation_error", req_id=req_id, attempt=attempt + 1, error=str(e))
            if attempt == 2:
                return _create_fallback_plan(context)
    
    # Should not reach here, but safety fallback
    return _create_fallback_plan(context)


class PlanValidationError(Exception):
    """Raised when plan validation fails."""
    pass


def _validate_plan_strict(plan_dict: Dict[str, Any], req_id: str) -> Dict[str, Any]:
    """
    Strictly validate the plan generated by LLM.
    
    Args:
        plan_dict: Raw plan from LLM
        req_id: Request ID for logging
    
    Returns:
        Validated plan
    
    Raises:
        PlanValidationError: If plan is invalid
    """
    errors = []
    
    # Check required fields
    required_fields = ["reasoning", "steps", "final_decision", "confidence"]
    for field in required_fields:
        if field not in plan_dict:
            errors.append(f"Missing required field: {field}")
    
    if errors:
        raise PlanValidationError("; ".join(errors))
    
    # Validate reasoning
    reasoning = plan_dict["reasoning"]
    if not isinstance(reasoning, str) or len(reasoning.strip()) < 10:
        errors.append("reasoning must be string with 10+ characters")
    
    # Validate steps
    steps = plan_dict["steps"]
    if not isinstance(steps, list):
        errors.append("steps must be a list")
    elif len(steps) == 0:
        errors.append("steps array must have at least 1 item")
    elif len(steps) > 5:
        errors.append("steps array must have at most 5 items")
    else:
        # Validate each step
        allowed_actions = ["fetch_customer", "fetch_market", "rag_search", "compute_decision"]
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"step[{i}] must be an object")
                continue
            
            if "action" not in step:
                errors.append(f"step[{i}] missing 'action' field")
            elif step["action"] not in allowed_actions:
                errors.append(f"step[{i}] action '{step['action']}' not in allowed list")
            
            if "params" not in step:
                errors.append(f"step[{i}] missing 'params' field")
            elif step["params"] is None:
                errors.append(f"step[{i}] params cannot be null (use empty object {{}})")
            elif not isinstance(step["params"], dict):
                errors.append(f"step[{i}] params must be an object")
    
    # Validate final_decision
    final_decision = plan_dict["final_decision"]
    if final_decision is not None and final_decision not in ["APPROVE", "COUNTER", "DECLINE", "INFORM"]:
        errors.append(f"final_decision must be null or one of: APPROVE, COUNTER, DECLINE")
    
    # Validate confidence
    confidence = plan_dict["confidence"]
    if not isinstance(confidence, (int, float)):
        errors.append("confidence must be a number")
    elif not (0.0 <= confidence <= 1.0):
        errors.append("confidence must be between 0.0 and 1.0")
    
    if errors:
        raise PlanValidationError("; ".join(errors))
    
    # Return validated plan (no cleaning, strict validation)
    return {
        "reasoning": reasoning.strip(),
        "steps": steps,
        "final_decision": final_decision,
        "confidence": float(confidence)
    }


def _create_fallback_plan(context: Context) -> AgentPlan:
    """
    Create a fallback plan when LLM planning fails.
    
    Args:
        context: Current agent context
    
    Returns:
        Simple fallback plan with strict schema compliance
    """
    logger.info("creating_fallback_plan")
    
    query = context.get("query", "").lower()
    steps = []
    
    # Deterministic fallback based on question type
    if "policy" in query or "terms" in query or "rate" in query or "oklahoma" in query:
        # Policy question
        steps.append({"action": "rag_search", "params": {"query": context.get("query", "loan policy"), "k": 8}})
    elif "eligible" in query or "qualify" in query or context["data_sources"].get("customer"):
        # Customer eligibility question
        if not context["data_sources"].get("customer"):
            steps.append({"action": "fetch_customer", "params": {}})
        else:
            steps.append({"action": "compute_decision", "params": {}})
    elif "market" in query or "today" in query or "current" in query:
        # Market data question
        steps.append({"action": "fetch_market", "params": {}})
    else:
        # Default: start with customer data
        if not context["data_sources"].get("customer"):
            steps.append({"action": "fetch_customer", "params": {}})
        else:
            steps.append({"action": "rag_search", "params": {"query": context.get("query", "loan"), "k": 8}})
    
    # Ensure we have at least one step
    if not steps:
        steps.append({"action": "fetch_customer", "params": {}})
    
    return AgentPlan(
        reasoning="Fallback plan due to LLM planning failure - using deterministic logic based on question type",
        steps=steps,
        final_decision=None,
        confidence=0.3  # Low confidence for fallback
    )


def should_continue_planning(state: State) -> bool:
    """
    Determine if the agent should continue planning or finalize decision.
    
    Args:
        state: Current workflow state
    
    Returns:
        True if should continue planning, False if ready to finalize
    """
    context = state["context"]
    plan = state.get("plan")
    
    # Stop if we have a final decision
    if plan and plan.get("final_decision"):
        return False
    
    # Stop if we've exceeded max iterations
    if context["iteration_count"] >= 5:
        logger.warning("max_iterations_reached_stopping", req_id=state.get("req_id"))
        return False
    
    # Stop if we have computed a decision
    decision_data = context["data_sources"].get("decision")
    if decision_data and isinstance(decision_data, dict) and "decision" in decision_data:
        return False
    
    # Continue if we have steps to execute
    if plan and plan.get("steps"):
        return True
    
    # Continue if we don't have basic data yet
    if not context["data_sources"].get("customer"):
        return True
    
    # Default to stopping to avoid infinite loops
    return False


def update_context_from_plan(state: State) -> State:
    """
    Update context and state fields from the completed plan.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with decision fields populated from context
    """
    context = state["context"]
    plan = state.get("plan")
    
    # Move decision from context.data_sources to state fields
    decision_data = context["data_sources"].get("decision")
    if decision_data and isinstance(decision_data, dict) and "decision" in decision_data:
        state["decision"] = decision_data["decision"]
        state["score"] = decision_data.get("score", 0.0)
        state["reason_codes"] = decision_data.get("reasons", [])
    
    # If plan has final decision, use that
    if plan and plan.get("final_decision"):
        state["decision"] = plan["final_decision"]
    
    # Move customer data to legacy field for compatibility
    customer_data = context["data_sources"].get("customer")
    if customer_data and isinstance(customer_data, dict) and "error" not in customer_data:
        state["client"] = customer_data
    
    # Move market data to legacy field for compatibility
    market_data = context["data_sources"].get("market_data")
    if market_data and isinstance(market_data, dict) and "error" not in market_data:
        state["market_data"] = market_data.get("metrics", {})
        state["market_stale"] = market_data.get("stale", False)
    
    # Move RAG results to legacy field for compatibility
    rag_data = context["data_sources"].get("rag")
    if rag_data and isinstance(rag_data, dict) and "snippets" in rag_data:
        state["policy_snippets"] = rag_data["snippets"]
    
    logger.info(
        "context_updated_from_plan",
        req_id=state.get("req_id"),
        decision=state.get("decision"),
        has_customer=bool(state.get("client")),
        has_market=bool(state.get("market_data")),
        snippets_count=len(state.get("policy_snippets", []))
    )
    
    return state
