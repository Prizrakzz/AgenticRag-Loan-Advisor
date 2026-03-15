
"""LangGraph nodes for the loan approval workflow."""

import openai
from typing import Dict, Any, List, Union

from .state import State, sanitize_state_for_logging
from .intent import classify_intent
from ..api.schemas import QuickReply
from ..db.database import get_db_session
from ..db.models import Customer, AuditLog
from ..nodes.guardrail import GuardrailError
from ..scrape.store import read_all_metrics, is_metric_stale
from ..rag.retriever import retrieve_policy_snippets
from ..utils.config import settings
from ..utils.logger import get_logger, NodeLogger
from ..utils.iron_clad_filter import filter_content_strict

logger = get_logger(__name__)

# Normalize logger creation with structlog fallback
try:
    import structlog
    log = structlog.get_logger(__name__)
except Exception:
    import logging
    log = logging.getLogger(__name__)

# Diversity filter for RAG results
def _apply_diversity_filter(snippets: List[Dict], max_results: int = 3, similarity_threshold: float = 0.8) -> List[Dict]:
    """Apply simple diversity filter to remove near-duplicate snippets."""
    if len(snippets) <= 1:
        return snippets
    
    unique_snippets = [snippets[0]]  # Always keep the first (highest scored)
    
    for snippet in snippets[1:]:
        if len(unique_snippets) >= max_results:
            break
            
        # Simple text similarity check
        new_content = snippet.get('page_content', '').lower()
        is_unique = True
        
        for existing in unique_snippets:
            existing_content = existing.get('page_content', '').lower()
            
            # Simple overlap check (could be improved with embeddings)
            words_new = set(new_content.split())
            words_existing = set(existing_content.split())
            
            if len(words_new) > 0 and len(words_existing) > 0:
                overlap = len(words_new.intersection(words_existing))
                union = len(words_new.union(words_existing))
                jaccard_sim = overlap / union if union > 0 else 0
                
                if jaccard_sim > similarity_threshold:
                    is_unique = False
                    break
        
        if is_unique:
            unique_snippets.append(snippet)
    
    return unique_snippets

# Initialize OpenAI client with modern approach
try:
    api_key = getattr(settings, 'openai_api_key', None)
    if not api_key:
        log.error("OPENAI_API_KEY not set - explanation generation will fail")
        openai_client = None
    else:
        openai_client = openai.OpenAI(api_key=api_key)
        log.info("OpenAI client initialized successfully for nodes")
except Exception as e:
    log.error("Failed to initialize OpenAI client: %s", str(e))
    openai_client = None


def safe_get_id(obj: Union[int, object]) -> int:
    """
    Safely get ID from either an int or an object with .id attribute.
    
    Args:
        obj: Either an integer ID or an object with .id attribute
        
    Returns:
        Integer ID
        
    Raises:
        ValueError: If object type is not supported
    """
    if isinstance(obj, int):
        return obj
    elif hasattr(obj, 'id'):
        return getattr(obj, 'id')
    else:
        raise ValueError(f"Cannot extract ID from object of type {type(obj)}")


def _log_node_execution(node_name: str, state: State, input_state: State = None):
    """Log node execution and create audit entry."""
    req_id = state.get("req_id", "unknown")
    user_id = state.get("user_id", 0)
    
    node_logger = NodeLogger(node_name, logger)
    
    if input_state:
        node_logger.log_input(sanitize_state_for_logging(input_state))
    
    node_logger.log_output(sanitize_state_for_logging(state))
    
    # Create audit log entry
    try:
        with get_db_session() as db:
            audit_entry = AuditLog.create_entry(
                req_id=req_id,
                username=str(user_id),
                node=node_name,
                state=sanitize_state_for_logging(state)
            )
            db.add(audit_entry)
            db.commit()
    except Exception as e:
        logger.error("audit_log_failed", node=node_name, error=str(e))


def auth_node(state: State) -> State:
    """
    Authentication node - ensures client data is loaded.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with client data
    """
    from .patches import StatePatch
    
    input_state = state.copy()
    patch = StatePatch().from_node("customer_node")
    
    try:
        user_id = state["user_id"]
        
        # Load client data from database
        with get_db_session() as db:
            customer = db.query(Customer).filter(Customer.client_id == user_id).first()
            
            if not customer:
                logger.error("customer_not_found", user_id=user_id)
                patch.set("client", None)
            else:
                patch.set("client", customer.to_dict())
                logger.info("customer_loaded", user_id=user_id, risk_grade=customer.risk_grade)
        
        # Apply patch to state for return
        state.update(patch.sets)
        _log_node_execution("auth_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("auth_node_failed", error=str(e))
        patch.set("client", None)
        state.update(patch.sets)
        _log_node_execution("auth_node", state, input_state)
        return state


def risk_gate_node(state: State) -> State:
    """
    Risk gate node - early decline for high-risk customers.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with decision if high risk
    """
    input_state = state.copy()
    
    try:
        client = state.get("client")
        if not client:
            logger.warning("risk_gate_no_client")
            _log_node_execution("risk_gate_node", state, input_state)
            return state
        
        grade = client.get("risk_grade")
        if not grade:
            logger.warning("risk_gate_no_risk_grade")
            _log_node_execution("risk_gate_node", state, input_state)
            return state
        
        if grade == "A":
            state["decision"] = "DECLINE"
            state["reason_codes"] = ["GRADE_A_HIGH_RISK"]
            logger.info("risk_gate_declined", risk_grade=grade, reason="Grade A high risk")
            _log_node_execution("risk_gate_node", state, input_state)
            return state
        
        if grade == "D":
            state["decision"] = "APPROVE"
            state["reason_codes"] = ["GRADE_D_LOW_RISK"]
            logger.info("risk_gate_approved", risk_grade=grade, reason="Grade D low risk")
            _log_node_execution("risk_gate_node", state, input_state)
            return state
        
        # B/C fall through to market analysis
        state["reason_codes"] = [f"GRADE_{grade}"]
        logger.info("risk_gate_passed", risk_grade=grade, reason="Grade B/C requires full analysis")
        
        _log_node_execution("risk_gate_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("risk_gate_node_failed", error=str(e))
        _log_node_execution("risk_gate_node", state, input_state)
        return state


def market_node(state: State) -> State:
    """
    Market data node - loads market metrics and staleness.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with market data
    """
    from .patches import StatePatch
    
    input_state = state.copy()
    patch = StatePatch().from_node("market_node")
    
    try:
        # Read all market metrics
        metrics = read_all_metrics()
        
        if not metrics:
            logger.warning("no_market_metrics_found")
            patch.set("market", {})
            patch.set("market_stale", True)
        else:
            patch.set("market", metrics)
            
            # Check for stale data
            stale_threshold_hours = settings.scrape.stale_threshold_hours
            stale_metrics = []
            
            key_metrics = ["cbj_rate", "cpi_yoy", "re_price_index", "market_risk_score"]
            for metric_key in key_metrics:
                if metric_key in metrics and is_metric_stale(metric_key, stale_threshold_hours):
                    stale_metrics.append(metric_key)
            
            patch.set("market_stale", len(stale_metrics) > 0)
            
            logger.info(
                "market_data_loaded",
                metrics_count=len(metrics),
                stale_metrics=stale_metrics,
                market_stale=patch.sets["market_stale"]
            )
        
        # Apply patch to state for return
        state.update(patch.sets)
        _log_node_execution("market_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("market_node_failed", error=str(e))
        patch.set("market", {})
        patch.set("market_stale", True)
        state.update(patch.sets)
        _log_node_execution("market_node", state, input_state)
        return state


def score_node(state: State) -> State:
    """
    Scoring node - calculates composite risk score.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with composite score
    """
    input_state = state.copy()
    
    try:
        client = state.get("client", {})
        market = state.get("market", {})
        
        # Extract risk scores from grade
        risk_grade = client.get("risk_grade", "C")  # Default to medium risk
        # Convert grade to numeric score (A=riskiest=0.8, B=0.6, C=0.4, D=safest=0.2)
        grade_to_score = {"A": 0.8, "B": 0.6, "C": 0.4, "D": 0.2}
        client_risk_score = grade_to_score.get(risk_grade, 0.5)
        
        market_risk_data = market.get("market_risk_score", {})
        market_risk_score = market_risk_data.get("value", 0.5)  # Default to medium risk
        
        # Default weights (configurable)
        weights = {
            "client": 0.6,
            "market": 0.3,
            "bank": 0.1
        }
        
        # Override with config if available
        if hasattr(settings, 'risk') and hasattr(settings.risk, 'weights'):
            weights.update(settings.risk.weights)
        
        # Calculate composite score (higher = less risky = better)
        bank_health = settings.bank.health_constant
        
        composite_score = (
            weights["client"] * (1 - client_risk_score) +
            weights["market"] * (1 - market_risk_score) +
            weights["bank"] * bank_health
        )
        
        # Ensure score is in valid range
        composite_score = max(0.0, min(1.0, composite_score))
        
        state["score"] = composite_score
        
        logger.info(
            "score_calculated",
            composite_score=composite_score,
            risk_grade=risk_grade,
            client_risk_score=client_risk_score,
            market_risk=market_risk_score,
            bank_health=bank_health,
            weights=weights
        )
        
        _log_node_execution("score_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("score_node_failed", error=str(e))
        state["score"] = 0.0  # Default to lowest score on error
        _log_node_execution("score_node", state, input_state)
        return state


def decision_node(state: State) -> State:
    """
    Decision node - maps score to approval decision.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with decision and reason codes
    """
    input_state = state.copy()
    
    try:
        score = state.get("score", 0.0)
        client = state.get("client", {})
        market = state.get("market", {})
        
        # Thresholds from config
        approve_threshold = settings.risk.approve_threshold
        counter_threshold = settings.risk.counter_threshold
        
        # Make decision based on score
        if score >= approve_threshold:
            decision = "APPROVE"
        elif score >= counter_threshold:
            decision = "COUNTER"
        else:
            decision = "DECLINE"
        
        state["decision"] = decision
        
        # Generate human-readable reason codes
        reason_codes = []
        
        # Client-based reasons
        risk_grade = client.get("risk_grade", "C")
        if risk_grade == "A":
            reason_codes.append("High individual risk profile")
        elif risk_grade in ["B", "C"]:
            reason_codes.append("Moderate risk factors")
        
        # Market-based reasons
        market_data = market.get("market_risk_score", {}).get("extra", {})
        components = market_data.get("components", {})
        
        if components.get("cbj_risk", 0) > 0.6:
            reason_codes.append("High interest rate environment")
        if components.get("cpi_risk", 0) > 0.6:
            reason_codes.append("High inflation conditions")
        if components.get("re_risk", 0) > 0.6:
            reason_codes.append("Volatile real estate market")
        
        # Income/affordability reasons
        annual_income = client.get("annual_income", 0)
        if annual_income and annual_income < 30:  # Less than 30K
            reason_codes.append("Low annual income")
        
        # Family size vs income
        family_size = client.get("family_size", 1)
        if annual_income and family_size > 1:
            income_per_person = annual_income / family_size
            if income_per_person < 15:  # Less than 15K per person
                reason_codes.append("Low income per family member")
        
        # Credit/banking relationship
        if not client.get("credit_card_with_bank"):
            reason_codes.append("No existing banking relationship")
        
        # Default reasons if none found
        if not reason_codes:
            if decision == "APPROVE":
                reason_codes = ["Strong financial profile", "Favorable market conditions"]
            elif decision == "COUNTER":
                reason_codes = ["Acceptable risk with conditions"]
            else:
                reason_codes = ["Risk factors exceed policy limits"]
        
        state["reason_codes"] = reason_codes
        
        logger.info(
            "decision_made",
            decision=decision,
            score=score,
            approve_threshold=approve_threshold,
            counter_threshold=counter_threshold,
            reason_codes=reason_codes
        )
        
        _log_node_execution("decision_node", state, input_state)
        return state
        
    except Exception as e:
        logger.error("decision_node_failed", error=str(e))
        state["decision"] = "DECLINE"
        state["reason_codes"] = ["System error during evaluation"]
        _log_node_execution("decision_node", state, input_state)
        return state


def policy_rag_node(state: State) -> State:
    """
    Policy RAG node - retrieves relevant policy snippets.
    
    Args:
        state: Current workflow state
    
    Returns:
        Updated state with policy snippets
    """
    from .patches import StatePatch
    
    input_state = state.copy()
    patch = StatePatch().from_node("policy_rag_node")
    
    try:
        decision = state.get("decision")
        reason_codes = state.get("reason_codes", [])
        question = state.get("question", "")
        autonomous_mode = state.get("autonomous_mode", False)
        req_id = state.get("req_id", "unknown")
        
        # INSTRUMENTATION: Track RAG node entry
        log.info(
            "policy_rag_entry",
            req_id=req_id,
            question_length=len(question),
            decision=decision,
            autonomous_mode=autonomous_mode,
            reason_codes_count=len(reason_codes)
        )
        
        log.info("🔍 RAG node processing: decision=%s, question=%r, autonomous=%s", decision, question, autonomous_mode)
        
        # NOTE: Removed decision setting - this should be done by judge_and_explain node
        # Decision setting in data gathering phase causes concurrency conflicts
        
        # First try to search based on the user's question directly
        snippets = []
        if question:
            from ..rag.retriever import search_policy_by_question
            # Hard cap at k=3 for focused, relevant results
            question_snippets = search_policy_by_question(question, top_k=3)
            snippets.extend(question_snippets)
            
            log.info("📚 Retrieved %d chunks from user question", len(question_snippets))
            for i, snippet in enumerate(question_snippets[:3]):
                content = snippet.get('page_content', str(snippet))
                log.debug("  question_chunk[%d]=%r", i, content[:100])
        
        # Apply diversity filter to avoid near-duplicates (simple cosine similarity check)
        if len(snippets) > 1:
            unique_snippets = _apply_diversity_filter(snippets, max_results=3)
            snippets = unique_snippets
        
        # Convert to clean text chunks with labels for friendly citations
        clean_snippet_texts = []
        snippet_metadata = []
        for i, snippet in enumerate(snippets[:3]):  # Hard cap at 3
            content = snippet.get('page_content', str(snippet))
            if content and content.strip():
                clean_snippet_texts.append(content.strip())
                
                # Build enhanced metadata for citations (S1, S2, S3)
                label = f"S{i+1}"
                section_ref = ""
                
                # Extract enhanced metadata if available from enriched chunks
                metadata_dict = {}
                if isinstance(snippet, dict):
                    snippet_meta = snippet.get('metadata', {})
                    
                    # Build section reference from enriched metadata
                    section_title = snippet_meta.get('section_title')
                    section_id = snippet_meta.get('section_id')
                    if section_title:
                        section_ref = f"Section {section_id}: {section_title}" if section_id else section_title
                    elif section_id:
                        section_ref = f"Policy §{section_id}"
                    
                    # Preserve all enriched metadata for reference building
                    metadata_dict.update({
                        "reference": snippet_meta.get("reference"),
                        "section_id": section_id,
                        "section_title": section_title,
                        "section_type": snippet_meta.get("section_type"),
                        "page_start": snippet_meta.get("page_start"),
                        "page_end": snippet_meta.get("page_end"),
                        "source_file": snippet_meta.get("source_file"),
                        "heading_path": snippet_meta.get("heading_path"),
                        "tags": snippet_meta.get("tags", []),
                        "effective_date": snippet_meta.get("effective_date")
                    })
                
                snippet_metadata.append({
                    "label": label,
                    "section_ref": section_ref,
                    "full_citation": f"({label}{f'—{section_ref}' if section_ref else ''})",
                    **metadata_dict  # Include all enriched metadata
                })
        
        # Log final retrieval results
        scores = [snippet.get('score', 0.0) for snippet in snippets[:3]]
        log.info("retrieval_complete", k=len(clean_snippet_texts), scores=scores)
        
        log.info("📚 Total retrieved chunks: %d", len(clean_snippet_texts))
        
        state["policy_snippets"] = snippets[:3]  # Keep original format for compatibility
        state["snippet_metadata"] = snippet_metadata  # For friendly citations
        
        # Set snippets as clean text array for response
        state["snippets"] = clean_snippet_texts
        
        # Apply patches to state
        patch.set("policy_snippets", snippets[:3])
        patch.set("snippet_metadata", snippet_metadata) 
        patch.set("snippets", clean_snippet_texts)
        state.update(patch.sets)
        
        # INSTRUMENTATION: Track RAG retrieval results
        log.info(
            "policy_rag_completion",
            req_id=req_id,
            snippets_retrieved=len(snippets),
            snippet_texts_count=len(clean_snippet_texts),
            question_based_snippets=len([s for s in snippets if s.get('from_question', True)]),
            decision_based_snippets=len([s for s in snippets if not s.get('from_question', True)])
        )
        
        log.info(
            "policy_snippets_retrieved",
            question_snippets=len([s for s in snippets if s.get('from_question', True)]),
            decision_snippets=len([s for s in snippets if not s.get('from_question', True)]),
            total_snippets=len(snippets)
        )
        
        # _log_node_execution("policy_rag_node", state, input_state)  # Skip problematic logging
        return state
        
    except Exception as e:
        log.exception("policy_rag_node_failed", error=str(e))
        patch.set("policy_snippets", [])
        patch.set("snippets", [])
        state.update(patch.sets)
        # _log_node_execution("policy_rag_node", state, input_state)  # Skip problematic logging
        return state


def explain_node(state: State) -> State:
    """
    Generate conversational, human-like explanations with enhanced dialogue management.
    Always produces natural paragraph responses ≤120 words with inline citations.
    """
    input_state = state.copy()
    req_id = state.get("req_id", "unknown")
    
    try:
        from .dialog_manager import process_dialogue
        from ..utils.dialog import build_bullet_requirements, echo_prior_answers, extract_product_from_memory, format_cta_in_response
        
        log.info(
            "explain_node_dialogue_imports_success",
            req_id=req_id
        )
        
        decision = state.get("decision", "UNKNOWN")
        snippets = state.get("snippets", [])
        snippet_metadata = state.get("snippet_metadata", [])
        question = state.get("question", "")
        memory = state.get("memory", [])
        
        # Extract product context from memory if not set
        product_context = extract_product_from_memory(memory)
        
        # Process dialogue for enhanced customer service
        dialog_context = {
            "question": question,
            "memory": memory,
            "intent_confidence": 0.8,  # TODO: Get from intent classifier
            "product_context": product_context
        }
        
        log.info(
            "explain_node_dialogue_context",
            req_id=req_id,
            question_length=len(question),
            memory_count=len(memory),
            product_context=product_context
        )
        
        dm_result = process_dialogue(dialog_context)
        
        log.info(
            "explain_node_dialogue_result",
            req_id=req_id,
            empathy_length=len(dm_result.get("empathy", "")),
            clarification_needed=dm_result.get("clarification_needed", False),
            quick_replies_count=len(dm_result.get("quick_replies", [])),
            has_cta=bool(dm_result.get("cta"))
        )
        
        # Build conversational human-like prompt with dialogue enhancements
        prompt_data = _build_friendly_explanation_prompt_enhanced(state, dm_result)
        
        # TEMPORARY LOGGING - snippet count and labels for debugging
        log.info(
            "explain_snippet_count",
            req_id=req_id,
            explain_snippet_count=len(snippets),
            decision=decision,
            model=settings.llm.chat_model,
            clarification_needed=dm_result.get("clarification_needed", False),
            has_cta=bool(dm_result.get("cta"))
        )
        
        if openai_client is None:
            log.error("OpenAI client not available")
            raise Exception("LLM service unavailable")
        
        # Import content filter utilities
        from ..utils.content_filter import get_system_message, get_filtered_response
        
        # Generate conversational explanation with enhanced dialogue
        completion = openai_client.chat.completions.create(
            model=settings.llm.chat_model,
            messages=[
                get_system_message(),  # Add content guardrail system message
                {"role": "system", "content": prompt_data["system"]},
                {"role": "user", "content": prompt_data["user"]}
            ],
            temperature=0.3,  # Natural but consistent
            max_tokens=300,   # Increased for enhanced responses
            top_p=0.9
        )
        
        # Apply content filtering to the response
        raw_answer = get_filtered_response(completion.choices[0].message.content.strip())
        
        # Add empathy hook from dialogue manager
        if dm_result.get("empathy"):
            raw_answer = f"{dm_result['empathy']}\n\n{raw_answer}"
        
        # Apply word limit clamp (≤120 words server-side)
        final_answer = _clamp_explanation_length(raw_answer, max_words=120)
        
        # Build references array from snippets metadata
        references = []
        if state.get("data_sources", {}).get("rag", {}).get("snippets"):
            rag_snippets = state["data_sources"]["rag"]["snippets"]
            references = [
                {
                    "source": f"S{i+1}",
                    "id": snippet.get("id"),
                    "section": snippet.get("section"),
                    "page": snippet.get("source_page")
                }
                for i, snippet in enumerate(rag_snippets[:3])  # Limit to top 3
                if snippet.get("id") or snippet.get("section") or snippet.get("source_page")
            ]
        
        # Add References section if we have enriched metadata with reference information
        references_section = _build_references_section(snippets, snippet_metadata)
        if references_section:
            final_answer += f"\n\n**References:**\n{references_section}"
        elif references:
            # Build concise references summary from our new references array
            ref_lines = []
            for ref in references:
                parts = []
                if ref.get("section"):
                    parts.append(f'Section "{ref["section"]}"')
                if ref.get("page"):
                    parts.append(f"Page {ref['page']}")
                if parts:
                    ref_lines.append(f"{ref['source']}: {' - '.join(parts)}")
            
            if ref_lines:
                final_answer += f"\n\nReferences:\n" + "\n".join(ref_lines)
        
        # Format CTA into response if present
        if dm_result.get("cta"):
            final_answer = format_cta_in_response(dm_result["cta"], final_answer)
        
        state["final_answer"] = final_answer
        state["explanation"] = final_answer
        state["references"] = references  # Store references in state for API response
        
        # Store dialogue manager results for API response
        state["quick_replies"] = dm_result.get("quick_replies", [])
        state["cta"] = dm_result.get("cta")
        state["product_context"] = dm_result.get("product_context")
        
        # DEBUG: Log what we're setting in state
        log.info(
            "explain_node_dialogue_state",
            req_id=req_id,
            quick_replies_set=state["quick_replies"],
            cta_set=state["cta"],
            product_context_set=state["product_context"]
        )
        
        # TEMPORARY LOGGING - labels used and word count for debugging
        labels_used = _extract_labels_from_text(final_answer)
        word_count = len(final_answer.split())
        log.info(
            "explain_node_completion",
            req_id=req_id,
            labels_used=labels_used,
            final_explain_word_count=word_count,
            decision=decision,
            quick_replies_count=len(dm_result.get("quick_replies", [])),
            has_product_context=bool(dm_result.get("product_context"))
        )
        
        return state
        
    except Exception as e:
        log.exception("explain_node_failed", error=str(e))
        
        # Always generate something conversational - never fall back to structured text
        decision = state.get("decision", "UNKNOWN")
        if decision == "COUNTER":
            emergency_explanation = "I'd be happy to help with a loan, though we'd need to adjust the terms or amount based on your profile. Let me know if you'd like to discuss the details."
        elif decision == "DECLINE":
            emergency_explanation = "Unfortunately, we can't approve the loan as requested, but there might be alternative options available. I'd be glad to explore what might work better."
        elif decision == "APPROVE":
            emergency_explanation = "Good news—this looks like something we can work with! I can walk you through the next steps to get things moving."
        else:
            emergency_explanation = "I'd be happy to help with your question. Let me connect you with someone who can provide the specific details you need."
        
        state["final_answer"] = emergency_explanation
        state["explanation"] = emergency_explanation
        
        return state


def _extract_labels_from_text(text: str) -> list:
    """Extract S1, S2, S3 labels used in the text for logging."""
    import re
    labels = re.findall(r'\(S[1-3]\)', text)
    return list(set(labels))


def _clamp_explanation_length(text: str, max_words: int = 120) -> str:
    """Clamp explanation to maximum word count while preserving conversational flow."""
    words = text.split()
    if len(words) <= max_words:
        return text
    
    # For conversational responses, try to end at a natural sentence boundary
    sentences = text.split('. ')
    result_sentences = []
    current_words = 0
    
    for sentence in sentences:
        sentence_words = len(sentence.split())
        if current_words + sentence_words <= max_words:
            result_sentences.append(sentence)
            current_words += sentence_words
        else:
            # If we can't fit the whole sentence, truncate at word boundary
            remaining_words = max_words - current_words
            if remaining_words > 5:  # Only if we have meaningful space left
                truncated_sentence = ' '.join(sentence.split()[:remaining_words]) + "..."
                result_sentences.append(truncated_sentence)
            break
    
    result = '. '.join(result_sentences)
    
    # Clean up any double periods from rejoining
    if result.endswith('..'):
        result = result[:-1]
    elif not result.endswith('.') and not result.endswith('...'):
        result += '.'
    
    return result


def _build_references_section(snippets: List[str], snippet_metadata: List[Dict[str, Any]]) -> str:
    """
    Build a References section from enriched snippet metadata.
    
    Args:
        snippets: List of snippet texts
        snippet_metadata: List of metadata dictionaries with reference information
        
    Returns:
        Formatted references string or empty string if no valid references
    """
    if not snippet_metadata:
        return ""
    
    references = []
    seen_references = set()  # Avoid duplicates
    
    for i, meta in enumerate(snippet_metadata[:3]):  # Limit to top 3 references
        # Try to get reference from metadata or build one
        reference = meta.get("reference")
        if not reference:
            # Build reference from individual metadata fields
            reference_parts = []
            
            if meta.get("section_title"):
                section_ref = meta["section_title"]
                if meta.get("section_id"):
                    section_ref = f"Section {meta['section_id']}: {section_ref}"
                reference_parts.append(section_ref)
            elif meta.get("section_id"):
                reference_parts.append(f"Section {meta['section_id']}")
            
            # Add page reference
            page_start = meta.get("page_start")
            page_end = meta.get("page_end")
            if page_start:
                if page_end and page_end != page_start:
                    reference_parts.append(f"Pages {page_start}-{page_end}")
                else:
                    reference_parts.append(f"Page {page_start}")
            
            # Omit source file (PDF name) from displayed reference for cleaner UI
            # source_file = meta.get("source_file")
            # if source_file:
            #     filename = source_file.replace(".pdf", "").replace("-", " ").title()
            #     reference_parts.append(filename)
            
            reference = " | ".join(reference_parts) if reference_parts else None
        
        if reference and reference not in seen_references:
            label = meta.get("label", f"S{i+1}")
            references.append(f"- {label}: {reference}")
            seen_references.add(reference)
    
    return "\n".join(references) if references else ""


def _build_friendly_explanation_prompt_enhanced(state: State, dm_result: Dict[str, Any]) -> Dict[str, str]:
    """Build enhanced conversational prompt with dialogue manager context."""
    
    decision = state.get("decision", "UNKNOWN")
    score = state.get("score", 0.0)
    client = state.get("client", {})
    question = state.get("question", "")
    snippets = state.get("snippets", [])
    snippet_metadata = state.get("snippet_metadata", [])
    reason_codes = state.get("reason_codes", [])
    memory = state.get("memory", [])
    
    from ..utils.dialog import build_bullet_requirements, echo_prior_answers
    
    # Enhanced system prompt with dialogue awareness
    system_prompt = """You are Arab Bank's customer service assistant. Sound like a friendly, professional human.
Answer in 2–4 short sentences, plain language, ≤120 words.
Do not use headings or labels (no "DECISION:", no "Why:", no "Next step:").
Use only provided snippets; cite inline as (S1), (S2), (S3). Never invent facts.

DIALOGUE CONTEXT:
- If clarification is needed, ask a confirming question naturally
- Include bullet-point requirements when discussing loan details
- Echo prior conversation context when relevant
- Be empathetic and solution-focused
- Guide toward next steps when appropriate

Respond as a single conversational paragraph with natural flow."""

    # Build enhanced user prompt
    user_prompt = f"Question: {question}\n"
    
    # Add dialogue manager context
    if dm_result.get("clarification_needed"):
        user_prompt += "INSTRUCTION: This question needs clarification. Ask a confirming question.\n"
    
    if dm_result.get("main_answer_prompt"):
        user_prompt += f"GUIDANCE: {dm_result['main_answer_prompt']}\n"
    
    # Add decision context for eligibility questions with enhanced market context
    if decision and decision != "INFORM":
        user_prompt += f"Decision context: {decision}\n"
        
        # Add market conditions if available for richer context
        market_data = state.get("market_data", {})
        if market_data:
            condition = market_data.get("condition", "")
            prime_rate = market_data.get("prime_rate")
            if condition:
                user_prompt += f"Market environment: {condition}"
                if prime_rate:
                    user_prompt += f" (Prime rate: {prime_rate}%)"
                user_prompt += "\n"
    
    # Add conversation context
    context_echo = echo_prior_answers(memory)
    if context_echo:
        user_prompt += f"{context_echo}\n"
    
    # Add product-specific requirements
    if dm_result.get("product_context"):
        requirements = build_bullet_requirements(dm_result["product_context"])
        if requirements:
            user_prompt += f"{requirements}\n\n"
    
    # Use only top K chunks to prevent repetition (max 3)
    top_snippets = snippets[:3] if len(snippets) > 3 else snippets
    
    # Add essential context
    if reason_codes:
        user_prompt += f"Key factors: {', '.join(reason_codes[:3])}\n"
    
    if score is not None and score > 0:
        # Translate score to plain English
        risk_level = "low risk" if score >= 0.7 else "moderate risk" if score >= 0.5 else "higher risk"
        user_prompt += f"Risk assessment: {risk_level}\n"
    
    # Add labeled snippets with enhanced metadata for richer citations
    if top_snippets and snippet_metadata:
        user_prompt += "\nPolicy snippets to reference:\n"
        for i, (snippet, meta) in enumerate(zip(top_snippets, snippet_metadata[:3])):
            label = meta.get("label", f"S{i+1}")
            confidence_tier = meta.get("confidence_tier", "")
            document_type = meta.get("document_type", "")
            section_ref = meta.get("section_ref", "")
            
            # Enhanced citation with metadata context
            citation_context = f"{label}"
            if confidence_tier and confidence_tier != "UNKNOWN":
                citation_context += f" ({confidence_tier} confidence)"
            if section_ref:
                citation_context += f" - {section_ref}"
            
            user_prompt += f"{citation_context}: {snippet[:200]}...\n"
    elif top_snippets:
        user_prompt += "\nPolicy snippets to reference:\n"
        for i, snippet in enumerate(top_snippets):
            user_prompt += f"S{i+1}: {snippet[:200]}...\n"
    
    return {
        "system": system_prompt,
        "user": user_prompt
    }


def _build_friendly_explanation_prompt(state: State) -> Dict[str, str]:
    """Build conversational Oklahoma Bank help-center prompt for human-like responses."""
    
    decision = state.get("decision", "UNKNOWN")
    score = state.get("score", 0.0)
    client = state.get("client", {})
    question = state.get("question", "")
    snippets = state.get("snippets", [])
    snippet_metadata = state.get("snippet_metadata", [])
    reason_codes = state.get("reason_codes", [])
    
    # Get chat history from context if available
    context = state.get("context", {})
    chat_history = context.get("history", [])
    
    # Oklahoma Bank conversational system prompt
    system_prompt = """You are Oklahoma Bank's help-center assistant. Sound like a friendly human.
Answer in 2–4 short sentences, plain language, ≤120 words.
Do not use headings or labels (no "DECISION:", no "Why:", no "Next step:").
Use only provided snippets; cite inline as (S1), (S2), (S3). Never invent facts.
If the decision is COUNTER or DECLINE, naturally mention conditions or alternatives in one sentence.

Respond as a single conversational paragraph. Examples:

Policy: "Most commercial loans land around WSJ Prime +2% up to ~16% depending on your profile (S1). If your credit is stronger, you'll likely be toward the lower end; weaker files price higher (S2). If you'd like, I can give you a quick estimate based on a few details."

Eligibility: "Based on what I see, we'd be open to a conditional approval if we tighten the amount and verify income/collateral (S1). I can walk you through the documents that help lower the rate and make this smoother."

Keep it conversational and human—no bullet points, no section headings."""

    # Build user prompt with question, decision context, and labeled snippets
    user_prompt = f"Question: {question}\n"
    
    # Add decision context for eligibility questions with enhanced market context
    if decision and decision != "INFORM":
        user_prompt += f"Decision context: {decision}\n"
        
        # Add market conditions if available for richer context
        market_data = state.get("market_data", {})
        if market_data:
            condition = market_data.get("condition", "")
            prime_rate = market_data.get("prime_rate")
            if condition:
                user_prompt += f"Market environment: {condition}"
                if prime_rate:
                    user_prompt += f" (Prime rate: {prime_rate}%)"
                user_prompt += "\n"
    
    # Add memory/chat history if available (for context)
    memory = state.get("memory", [])
    if memory:
        user_prompt += "\nPrior context (most recent first):\n"
        for turn in memory[-4:]:  # Only include last 4 turns to avoid prompt bloat
            role = turn.get("role", "")
            content = turn.get("content", "")[:100]  # Truncate long messages
            user_prompt += f"- {role.title()}: {content}...\n"
        user_prompt += "\n"
    
    # Use only top K chunks to prevent repetition (max 3)
    top_snippets = snippets[:3] if len(snippets) > 3 else snippets
    
    # Add essential context
    if reason_codes:
        user_prompt += f"Key factors: {', '.join(reason_codes[:3])}\n"
    
    if score is not None and score > 0:
        # Translate score to plain English
        risk_level = "low risk" if score >= 0.7 else "moderate risk" if score >= 0.5 else "higher risk"
        user_prompt += f"Risk assessment: {risk_level}\n"
    
    # Add labeled snippets with enhanced metadata for richer citations
    if top_snippets and snippet_metadata:
        user_prompt += "\nPolicy snippets to reference:\n"
        for i, (snippet, meta) in enumerate(zip(top_snippets, snippet_metadata[:3])):
            label = meta.get("label", f"S{i+1}")
            confidence_tier = meta.get("confidence_tier", "")
            document_type = meta.get("document_type", "")
            section_ref = meta.get("section_ref", "")
            
            # Enhanced citation with metadata context
            citation_context = f"{label}"
            if confidence_tier and confidence_tier != "UNKNOWN":
                citation_context += f" ({confidence_tier} confidence)"
            if section_ref:
                citation_context += f" - {section_ref}"
            
            user_prompt += f"{citation_context}: {snippet[:200]}...\n"
    elif top_snippets:
        # Fallback if metadata missing
        user_prompt += "\nPolicy snippets to reference:\n"
        for i, snippet in enumerate(top_snippets):
            user_prompt += f"S{i+1}: {snippet[:200]}...\n"
    
    user_prompt += "\nRespond as a friendly human agent in a single conversational paragraph (2–4 sentences). No headings or labels."

    return {
        "system": system_prompt,
        "user": user_prompt
    }


def end_node(state: State) -> State:
    """
    End node - final cleanup and logging.
    
    Args:
        state: Current workflow state
    
    Returns:
        Final state
    """
    input_state = state.copy()
    
    # Log workflow completion
    logger.info(
        "workflow_completed",
        req_id=state.get("req_id"),
        decision=state.get("decision"),
        score=state.get("score"),
        has_final_answer=bool(state.get("final_answer"))
    )
    
    _log_node_execution("end_node", state, input_state)
    return state 