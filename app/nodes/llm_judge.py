import json
import openai
import logging
from typing import Dict, Any, Optional
from ..utils.config import settings
from ..utils.logger import get_logger
from ..utils.prompts import (
    SYSTEM_COMPLIANT, JUDGE_V3, EXPLAINER_V2, REFUSAL_OBJECT, 
    LLM_PARAMS, validate_llm_response, format_context_for_prompt
)

logger = get_logger(__name__)


async def _enforce_judge_v3_rules(data: dict, client, formatted_ctx: dict) -> dict:
    """
    Enforce Judge V3 rules: non-empty answer, proper COUNTER behavior, decision validation.
    
    Args:
        data: Parsed LLM response
        client: OpenAI client for re-asking
        formatted_ctx: Formatted context for re-prompting
        
    Returns:
        Corrected response data
    """
    from ..utils.config import settings
    
    # 1. Assert answer is non-empty
    if not data.get("answer", "").strip():
        logger.warning("Empty answer detected, re-asking model")
        try:
            user_message = f"Your answer was empty. Fill 'answer' with the main text.\n\nOriginal context:\n{JUDGE_V3.format(**formatted_ctx)}"
            
            resp = await client.chat.completions.acreate(
                model=settings.llm.chat_model,
                messages=[
                    {"role": "system", "content": SYSTEM_COMPLIANT},
                    {"role": "user", "content": user_message}
                ],
                **LLM_PARAMS,
                response_format={"type": "json_object"}
            )
            
            retry_data = json.loads(resp.choices[0].message.content.strip())
            if retry_data.get("answer", "").strip():
                data = retry_data
            else:
                data["answer"] = "I'm here to help with your loan inquiry. How can I assist you?"
                
        except Exception as e:
            logger.error(f"Failed to re-ask for empty answer: {e}")
            data["answer"] = "I'm here to help with your loan inquiry. How can I assist you?"
    
    # 2. Validate decision is in allowed set
    valid_decisions = {"INFORM", "APPROVE", "DECLINE", "COUNTER", "REFUSE"}
    if data.get("decision") not in valid_decisions:
        logger.warning(f"Invalid decision '{data.get('decision')}', re-asking model")
        try:
            user_message = f"You chose '{data.get('decision')}' which is invalid. Use only: {', '.join(valid_decisions)}.\n\nOriginal context:\n{JUDGE_V3.format(**formatted_ctx)}"
            
            resp = await client.chat.completions.acreate(
                model=settings.llm.chat_model,
                messages=[
                    {"role": "system", "content": SYSTEM_COMPLIANT},
                    {"role": "user", "content": user_message}
                ],
                **LLM_PARAMS,
                response_format={"type": "json_object"}
            )
            
            retry_data = json.loads(resp.choices[0].message.content.strip())
            if retry_data.get("decision") in valid_decisions:
                data = retry_data
            else:
                data["decision"] = "DECLINE"
                
        except Exception as e:
            logger.error(f"Failed to re-ask for invalid decision: {e}")
            data["decision"] = "DECLINE"
    
    # 3. Enforce COUNTER behavior - must list specific missing items
    if data.get("decision") == "COUNTER":
        answer = data.get("answer", "")
        # Check if answer contains specific bullet points or missing items
        if not ("•" in answer or "?" in answer or "missing" in answer.lower() or "need" in answer.lower()):
            logger.warning("COUNTER decision without specific missing items, re-asking model")
            try:
                user_message = f"You chose COUNTER; include exactly 1–2 missing items as bullets.\n\nOriginal context:\n{JUDGE_V3.format(**formatted_ctx)}"
                
                resp = await client.chat.completions.acreate(
                    model=settings.llm.chat_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_COMPLIANT},
                        {"role": "user", "content": user_message}
                    ],
                    **LLM_PARAMS,
                    response_format={"type": "json_object"}
                )
                
                retry_data = json.loads(resp.choices[0].message.content.strip())
                if retry_data.get("decision") == "COUNTER" and ("•" in retry_data.get("answer", "") or "missing" in retry_data.get("answer", "").lower()):
                    data = retry_data
                else:
                    # Flip to DECLINE if COUNTER can't be justified
                    data["decision"] = "DECLINE"
                    data["answer"] = "Based on current information, we cannot approve this loan application at this time."
                    
            except Exception as e:
                logger.error(f"Failed to re-ask for COUNTER specifics: {e}")
                data["decision"] = "DECLINE"
                data["answer"] = "Based on current information, we cannot approve this loan application at this time."
    
    # 4. Cap references to ≤3
    if isinstance(data.get("references"), list):
        data["references"] = data["references"][:3]
    else:
        data["references"] = []
    
    # 5. Coerce quick_replies to list of dicts
    if not isinstance(data.get("quick_replies"), list):
        data["quick_replies"] = []
    else:
        # Ensure each item is a dict with label
        fixed_replies = []
        for item in data["quick_replies"]:
            if isinstance(item, dict) and "label" in item:
                fixed_replies.append(item)
            elif isinstance(item, str):
                fixed_replies.append({"label": item})
        data["quick_replies"] = fixed_replies
    
    return data


async def judge_decision(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use LLM to judge loan decision and generate response with new prompt system.
    
    Args:
        ctx: Context containing customer, market, snippets, etc.
        
    Returns:
        Dictionary with decision, answer, references, quick_replies, cta
    """
    try:
        # Get OpenAI client
        openai_client = getattr(settings, 'openai_client', None)
        if not openai_client:
            raise Exception("OpenAI client not configured")
        
        # Get memory for context
        memory = ctx.get("memory", [])
        
        # Format context for prompt
        formatted_ctx = format_context_for_prompt(
            customer_profile=ctx.get("customer", {}),
            risk_grade=ctx.get("customer", {}).get("risk_grade", "C"),
            market_metrics=ctx.get("market", {}),
            snippets=ctx.get("snippets", [])[:3],  # Cap at 3
            memory=memory,
            question=ctx.get("question", "")
        )
        
        # Build user message with context
        user_message = JUDGE_V3.format(**formatted_ctx)
        
        resp = await openai_client.chat.completions.acreate(
            model=settings.llm.chat_model,
            messages=[
                {"role": "system", "content": SYSTEM_COMPLIANT},
                {"role": "user", "content": user_message}
            ],
            **LLM_PARAMS,
            response_format={"type": "json_object"}
        )
        
        content = resp.choices[0].message.content.strip()
        data = json.loads(content)
        
        # Post-parse enforcement for Judge V3
        data = await _enforce_judge_v3_rules(data, openai_client, formatted_ctx)
        
        # Validate response structure
        is_valid, error_msg = validate_llm_response(data)
        if not is_valid:
            logger.error("llm_judge_validation_error", error=error_msg)
            raise ValueError(f"Invalid LLM response: {error_msg}")
        
        logger.info("llm_judge_success", decision=data["decision"], answer_length=len(data["answer"]))
        return data
        
    except json.JSONDecodeError as e:
        logger.error("llm_judge_json_error", error=str(e))
        raise Exception("Failed to parse LLM response as JSON")
    except Exception as e:
        logger.error("llm_judge_error", error=str(e))
        raise Exception(f"LLM judge failed: {str(e)}")
        logger.error("llm_judge_error: %s", str(e))
        raise Exception(f"LLM judge failed: {str(e)}")


def build_prompt(ctx: Dict[str, Any]) -> str:
    """
    Build prompt for LLM judge from context.
    
    Args:
        ctx: Context dictionary with customer, market, snippets, etc.
        
    Returns:
        Formatted prompt string
    """
    question = ctx.get("question", "")
    customer = ctx.get("customer", {})
    market = ctx.get("market", {})
    snippets = ctx.get("snippets", [])
    score = ctx.get("score", 0.0)
    
    prompt_parts = [
        f"QUESTION: {question}",
        "",
        "CONTEXT:"
    ]
    
    # Customer context
    if customer:
        risk_grade = customer.get("risk_grade", "C")
        annual_income = customer.get("annual_income", 0)
        family_size = customer.get("family_size", 1)
        credit_card = customer.get("credit_card_with_bank", False)
        
        prompt_parts.extend([
            f"Customer Risk Grade: {risk_grade}",
            f"Annual Income: ${annual_income}K",
            f"Family Size: {family_size}",
            f"Banking Relationship: {'Yes' if credit_card else 'No'}"
        ])
    
    # Composite score
    if score > 0:
        risk_level = "Low Risk" if score >= 0.7 else "Moderate Risk" if score >= 0.4 else "High Risk"
        prompt_parts.append(f"Composite Score: {score:.2f} ({risk_level})")
    
    # Market conditions
    if market:
        market_risk = market.get("market_risk_score", {}).get("value", 0.5)
        prompt_parts.append(f"Market Risk: {market_risk:.2f}")
    
    prompt_parts.append("")
    
    # Policy snippets
    if snippets:
        prompt_parts.append("POLICY SNIPPETS:")
        for i, snippet in enumerate(snippets[:3]):
            content = snippet if isinstance(snippet, str) else snippet.get("page_content", str(snippet))
            prompt_parts.append(f"S{i+1}: {content[:200]}...")
    
    prompt_parts.extend([
        "",
        "Return valid JSON with decision, answer, references, quick_replies, and cta."
    ])
    
    return "\n".join(prompt_parts)


def judge_and_explain_node(state):
    """
    Combined judge and explain node using LLM with intent-based routing.
    Falls back to legacy decision engine on error.
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with decision and explanation
    """
    req_id = state.get("req_id", "unknown")
    question = state.get("question", "")
    
    try:
        # Step 1: Classify intent with LLM
        from ..graph.intent import classify_intent_llm
        
        logger.info("classify_intent_start", req_id=req_id, question=question)
        result = classify_intent_llm(question)
        logger.info("classify_intent_result", req_id=req_id, result=result, result_type=type(result))
        
        if result is None:
            logger.error("classify_intent_returned_none", req_id=req_id)
            raise ValueError("classify_intent_llm returned None")
            
        if not isinstance(result, tuple) or len(result) != 3:
            logger.error("classify_intent_bad_format", req_id=req_id, result=result)
            raise ValueError(f"classify_intent_llm returned unexpected format: {result}")
        
        intent, confidence, features = result
        
        logger.info("intent_classified_llm", req_id=req_id, intent=intent, confidence=confidence)
        
        # Step 2: Route based on intent
        if intent == "forbidden":
            # Immediately return REFUSAL for forbidden content
            logger.warning("forbidden_content_detected", req_id=req_id)
            
            state["decision"] = "REFUSE"
            state["final_answer"] = REFUSAL_OBJECT["answer"]
            state["explanation"] = REFUSAL_OBJECT["answer"]
            state["references"] = REFUSAL_OBJECT["references"]
            state["quick_replies"] = REFUSAL_OBJECT["quick_replies"]
            state["cta"] = REFUSAL_OBJECT["cta"]
            
            return state
        
        # Step 3: Build context for LLM judge/explainer
        logger.info("state_keys_check", req_id=req_id, available_keys=list(state.keys()))
        
        client_data = state.get("client", {})
        market_data = state.get("market", {})
        snippets_data = state.get("policy_snippets", [])
        
        logger.info("data_check", req_id=req_id, 
                   client_type=type(client_data), client_value=client_data,
                   market_type=type(market_data), 
                   snippets_type=type(snippets_data), snippets_count=len(snippets_data))
        
        ctx = {
            "question": question,
            "customer": client_data if client_data is not None else {},
            "market": market_data if market_data is not None else {},
            "snippets": snippets_data[:3] if snippets_data else [],
            "score": state.get("score", 0.0),
            "reason_codes": state.get("reason_codes", []),
            "memory": state.get("memory", []),
            "intent": intent
        }
        
        logger.info("judge_and_explain_llm_attempt", req_id=req_id, intent=intent)
        logger.info("context_check", req_id=req_id, ctx_keys=list(ctx.keys()), ctx_customer_type=type(ctx.get("customer")), ctx_snippets_count=len(ctx.get("snippets", [])))
        
        # Step 4: Use appropriate LLM based on intent
        if intent == "informational":
            # Use explainer for policy questions
            try:
                logger.info("calling_sync_judge_informational", req_id=req_id)
                result = _judge_decision_sync(ctx)
                # Force decision to INFORM for informational queries
                if result:
                    result["decision"] = "INFORM"
                else:
                    raise ValueError("_judge_decision_sync returned None")
            except Exception as e:
                logger.error("informational_llm_failed", req_id=req_id, error=str(e))
                result = {
                    "decision": "INFORM",
                    "answer": "I can help you with information about Arab Bank's loan products and services.",
                    "references": [],
                    "quick_replies": [],
                    "cta": None
                }
        else:
            # Use judge for eligibility questions
            try:
                logger.info("calling_sync_judge_eligibility", req_id=req_id)
                result = _judge_decision_sync(ctx)
                if not result:
                    raise ValueError("_judge_decision_sync returned None")
            except Exception as e:
                logger.error("eligibility_llm_failed", req_id=req_id, error=str(e))
                # Create a fallback response for eligibility questions
                result = {
                    "decision": "DECLINE", 
                    "answer": "I need more information to assess your loan eligibility. Please contact an Arab Bank representative for personalized assistance.",
                    "references": [],
                    "quick_replies": [],
                    "cta": None
                }
        
        # Step 5: Update state with LLM results
        state["decision"] = result["decision"]
        state["final_answer"] = result["answer"]
        state["explanation"] = result["answer"]
        state["references"] = result.get("references", [])
        state["quick_replies"] = result.get("quick_replies", [])
        state["cta"] = result.get("cta")
        
        logger.info("judge_and_explain_llm_success", req_id=req_id, decision=result["decision"])
        
    except Exception as e:
        logger.warning("judge_and_explain_llm_failed, falling back to legacy: %s", str(e))
        
        # Fall back to legacy decision logic
        from app.graph.nodes import decision_node, explain_node
        
        # Run legacy decision node
        state = decision_node(state)
        
        # Run legacy explain node  
        state = explain_node(state)
        
        logger.info("judge_and_explain_legacy_fallback", req_id=req_id, decision=state.get("decision"))
    
    return state


def _enforce_judge_v3_rules_sync(data: dict, client, formatted_ctx: dict) -> dict:
    """
    Synchronous version of Judge V3 rules enforcement.
    """
    from ..utils.config import settings
    
    # 1. Assert answer is non-empty
    if not data.get("answer", "").strip():
        logger.warning("Empty answer detected, re-asking model")
        try:
            user_message = f"Your answer was empty. Fill 'answer' with the main text.\n\nOriginal context:\n{JUDGE_V3.format(**formatted_ctx)}"
            
            resp = client.chat.completions.create(
                model=settings.llm.chat_model,
                messages=[
                    {"role": "system", "content": SYSTEM_COMPLIANT},
                    {"role": "user", "content": user_message}
                ],
                **LLM_PARAMS,
                response_format={"type": "json_object"}
            )
            
            retry_data = json.loads(resp.choices[0].message.content.strip())
            if retry_data.get("answer", "").strip():
                data = retry_data
            else:
                data["answer"] = "I'm here to help with your loan inquiry. How can I assist you?"
                
        except Exception as e:
            logger.error(f"Failed to re-ask for empty answer: {e}")
            data["answer"] = "I'm here to help with your loan inquiry. How can I assist you?"
    
    # 2. Validate decision is in allowed set
    valid_decisions = {"INFORM", "APPROVE", "DECLINE", "COUNTER", "REFUSE"}
    if data.get("decision") not in valid_decisions:
        logger.warning(f"Invalid decision '{data.get('decision')}', re-asking model")
        try:
            user_message = f"You chose '{data.get('decision')}' which is invalid. Use only: {', '.join(valid_decisions)}.\n\nOriginal context:\n{JUDGE_V3.format(**formatted_ctx)}"
            
            resp = client.chat.completions.create(
                model=settings.llm.chat_model,
                messages=[
                    {"role": "system", "content": SYSTEM_COMPLIANT},
                    {"role": "user", "content": user_message}
                ],
                **LLM_PARAMS,
                response_format={"type": "json_object"}
            )
            
            retry_data = json.loads(resp.choices[0].message.content.strip())
            if retry_data.get("decision") in valid_decisions:
                data = retry_data
            else:
                data["decision"] = "DECLINE"
                
        except Exception as e:
            logger.error(f"Failed to re-ask for invalid decision: {e}")
            data["decision"] = "DECLINE"
    
    # 3. Enforce COUNTER behavior
    if data.get("decision") == "COUNTER":
        answer = data.get("answer", "")
        if not ("•" in answer or "?" in answer or "missing" in answer.lower() or "need" in answer.lower()):
            logger.warning("COUNTER decision without specific missing items, re-asking model")
            try:
                user_message = f"You chose COUNTER; include exactly 1–2 missing items as bullets.\n\nOriginal context:\n{JUDGE_V3.format(**formatted_ctx)}"
                
                resp = client.chat.completions.create(
                    model=settings.llm.chat_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_COMPLIANT},
                        {"role": "user", "content": user_message}
                    ],
                    **LLM_PARAMS,
                    response_format={"type": "json_object"}
                )
                
                retry_data = json.loads(resp.choices[0].message.content.strip())
                if retry_data.get("decision") == "COUNTER" and ("•" in retry_data.get("answer", "") or "missing" in retry_data.get("answer", "").lower()):
                    data = retry_data
                else:
                    data["decision"] = "DECLINE"
                    data["answer"] = "Based on current information, we cannot approve this loan application at this time."
                    
            except Exception as e:
                logger.error(f"Failed to re-ask for COUNTER specifics: {e}")
                data["decision"] = "DECLINE"
                data["answer"] = "Based on current information, we cannot approve this loan application at this time."
    
    # 4. Cap references and fix quick_replies
    if isinstance(data.get("references"), list):
        data["references"] = data["references"][:3]
    else:
        data["references"] = []
    
    if not isinstance(data.get("quick_replies"), list):
        data["quick_replies"] = []
    else:
        fixed_replies = []
        for item in data["quick_replies"]:
            if isinstance(item, dict) and "label" in item:
                fixed_replies.append(item)
            elif isinstance(item, str):
                fixed_replies.append({"label": item})
        data["quick_replies"] = fixed_replies
    
    return data


def _judge_decision_sync(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synchronous version of judge_decision using new prompt system.
    
    Args:
        ctx: Context dictionary
        
    Returns:
        Decision dictionary
    """
    try:
        logger.info("sync_judge_start", ctx_keys=list(ctx.keys()))
        
        # Get OpenAI client
        api_key = getattr(settings, 'openai_api_key', None)
        if not api_key:
            logger.error("sync_judge_no_api_key")
            raise Exception("OpenAI API key not configured")
        
        logger.info("sync_judge_api_key_found")
        
        client = openai.OpenAI(api_key=api_key)
        logger.info("sync_judge_client_created")
        
        # Get memory for context
        memory = ctx.get("memory", [])
        logger.info("sync_judge_memory_processed", memory_count=len(memory))
        
        # Format context for prompt
        snippets = ctx.get("snippets", [])
        logger.info("sync_judge_snippets_check", snippet_count=len(snippets), snippet_types=[type(s) for s in snippets[:3]])
        
        # Ensure snippets are properly formatted
        clean_snippets = []
        for snippet in snippets[:3]:
            if snippet is not None:
                if isinstance(snippet, dict):
                    clean_snippets.append(snippet)
                else:
                    # Convert string snippet to dict
                    clean_snippets.append({"page_content": str(snippet)})
        
        logger.info("sync_judge_clean_snippets", clean_count=len(clean_snippets))
        
        formatted_ctx = format_context_for_prompt(
            customer_profile=ctx.get("customer", {}),
            risk_grade=ctx.get("customer", {}).get("risk_grade", "C"),
            market_metrics=ctx.get("market", {}),
            snippets=clean_snippets,
            memory=memory,
            question=ctx.get("question", "")
        )
        
        if formatted_ctx is None:
            logger.error("sync_judge_format_failed", ctx_keys=list(ctx.keys()))
            raise Exception("format_context_for_prompt returned None")
        
        logger.info("sync_judge_context_formatted")
        
        # Choose prompt based on intent
        intent = ctx.get("intent", "eligibility")
        if intent == "informational":
            user_message = EXPLAINER_V2.format(**formatted_ctx)
        else:
            user_message = JUDGE_V3.format(**formatted_ctx)
        
        resp = client.chat.completions.create(
            model=settings.llm.chat_model,
            messages=[
                {"role": "system", "content": SYSTEM_COMPLIANT},
                {"role": "user", "content": user_message}
            ],
            **LLM_PARAMS,
            response_format={"type": "json_object"}
        )
        
        content = resp.choices[0].message.content.strip()
        
        # Parse and validate JSON response
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError("No valid JSON found in response")
        
        # Post-parse enforcement for Judge V3
        data = _enforce_judge_v3_rules_sync(data, client, formatted_ctx)
        
        # Validate response structure
        is_valid, error_msg = validate_llm_response(data)
        if not is_valid:
            logger.error("sync_judge_validation_error", error=error_msg)
            raise ValueError(f"Invalid LLM response: {error_msg}")
        
        return data
        
    except Exception as e:
        logger.error("sync_judge_error", error=str(e))
        raise Exception(f"Sync LLM judge failed: {str(e)}")
