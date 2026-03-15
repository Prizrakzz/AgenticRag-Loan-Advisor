"""
Principal AI/NLP Architect — Arab Bank Loan Advisor (Single-Agent)
Enhanced with 10-turn memory window, evidence-driven RAG, and freeform LLM reasoning.
"""

import json
import logging
import asyncio
import openai
import os
import re
from typing import Dict, Any, List, Optional
from ..utils.config import settings
from ..utils.logger import get_logger
from .guardrail import guardrail_node, guardrail_out_node, GuardrailError
from ..rag.retriever import search_policy_by_question
from ..api.schemas import QuickReply

logger = get_logger(__name__)

# Intent classification with 10-turn memory context
INTENT_CLASSIFIER_PROMPT = """
Based on the conversation transcript below (last 10 turns), classify the user's latest message into exactly one of these categories:

ACK — phatic/acknowledgment/greeting/ambiguous (e.g., "thanks," "hello," "I need help," "help me") - no specific request
INFO — policy/rates/terms/products questions (specific information about banking/loan features without asking for approval)  
ELIGIBILITY — approval/qualification/decision requests (asking "can I get", "am I eligible", "will you approve", "I want a loan" or stating loan type alone as follow-up)

Consider the full context. Generic follow-ups like "are you sure?" refer to the previous topic unless the user clearly shifts.
If user states just a loan type (like "auto loan", "commercial loan") after previous eligibility discussion, classify as ELIGIBILITY.

Conversation transcript:
{transcript}

Classification:"""

# ACK mode - Warm banker persona (v3 - non-invention guardrails)
# Notes:
# - Sharper brand voice: poised, expert, proactive ("advisor" not "assistant")
# - Subtle momentum: ends with an open, specific invitation; avoids generic "How can I help?"
# - Micro-constraints prevent weak fillers, over-apologies, exclamation overload, or emoji usage
# - Strict non-invention: Never mention specific loan types unless present in conversation
ACK_SYSTEM_PROMPT = """
You are Arabie — a warm, charismatic senior loan advisor at Arab Bank. The user just greeted, thanked you, asked for help, or said something affectionate.

Produce EXACTLY 1–2 short, human sentences that:
• Sound welcoming, kind, and confident (real banker energy; no corporate fluff)
• Stay neutral: do NOT name a specific loan type or amount unless it appears in the last 10 turns
• Invite one next step (pick exactly one): share their goal, loan type, amount, or ask to check eligibility
• No emojis or exclamation points; max 38 words; no bullet lists; avoid "I can help you with…"
• Gentle mirroring of their greeting is OK (one or two words), then move them forward

Tone examples (style only; don't copy verbatim):
- "Hi—glad you're here. Would you like to explore a loan today or see what you qualify for?"
- "Happy to help. Tell me your goal or the amount you have in mind, and I'll guide you."

Conversation history (last turns):
{transcript}

Return ONLY the 1–2 sentences.
"""

# ELIGIBILITY mode - LLM-driven decisions without clarifications
ELIGIBILITY_SYSTEM_PROMPT = """
You are Arabie, Arab Bank's senior loan advisor. Make loan eligibility decisions using ONLY the structured signals provided below.

**STRICT REQUIREMENTS:**
- NO RAG calls, NO policy citations, NO document retrieval
- Use ONLY: risk grade, annual income, requested amount, loan type, market condition
- If loan type or amount missing → COUNTER with simple ask in one sentence
- When enough info present → decide immediately (APPROVE/DECLINE/COUNTER)

**DECISION LOGIC:**
Relate amount ↔ income (capacity), risk grade (credit quality), market (conditions).
Use qualitative LLM reasoning - no hardcoded rules or thresholds.

**CONVERSATION MEMORY (last 10 turns):**
{transcript}

**STRUCTURED SIGNALS:**
- Risk Grade: {risk_grade}
- Annual Income: {annual_income} 
- Requested Amount: {requested_amount}
- Loan Type: {loan_type}
- Market Condition: {market_condition}

**OUTPUT (JSON only):**
{{
  "decision": "APPROVE|COUNTER|DECLINE",
  "rationale": ["2-5 bullets referencing only the structured signals above"]
}}

**TONE:** Confident banker. Reference only signals actually present. No fabricated data.
"""

# INFO mode - Evidence-driven RAG with visible references
INFO_SYSTEM_PROMPT = """
You are Arabie, Arab Bank's policy specialist. Answer using retrieved policy evidence with visible references.

**EVIDENCE GATE:** Only assert specific policy/terms if retrieved chunks clear relevance threshold. If nothing relevant, give softened response.

**CONVERSATION MEMORY (last 10 turns):**  
{transcript}

**RETRIEVED EVIDENCE:**
{evidence}

**OUTPUT REQUIREMENTS:**
- Short, precise, user-friendly answer (no paragraph dumps)
- Quote/paraphrase only what's needed
- End with visible references in exact format:

References:
S1: <heading_path> (p.<page>)
S2: <heading_path> (p.<page>)

**ANSWER STYLE:** ≤80 words, banking professional tone. If no relevant evidence, acknowledge limitation softly.
"""

# Amount & type parsing with LLM extraction
async def extract_cross_turn_slots(memory: List[Dict], openai_client) -> Dict[str, Any]:
    """Extract and assemble loan_type and requested_amount across conversation turns"""
    
    # Build conversation context from last 10 turns
    transcript_lines = []
    for msg in memory[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        speaker = "User" if role == "user" else "Arabie"
        transcript_lines.append(f"{speaker}: {content}")
    
    transcript = "\n".join(transcript_lines)
    
    extraction_prompt = f"""Extract loan information from this conversation history. Look across ALL turns to assemble complete loan context.

**CONVERSATION:**
{transcript}

**SLOT ASSEMBLY RULES:**
- loan_type: Look for auto/car/vehicle → "auto", home/house/mortgage → "home", business/commercial → "commercial" 
- requested_amount: Extract any dollar amounts mentioned ($25k, 100000, "one hundred thousand", etc.)
- Combine information from multiple turns (e.g., "car" in turn 1 + "$100k" in turn 3)
- If user says just "car" or "commercial" without amount, still capture the type
- Prioritize most recent/complete information if conflicting

**OUTPUT (JSON only):**
{{
  "loan_type": "auto|home|commercial|null",
  "requested_amount": "numeric_value_or_null",
  "confidence": "high|medium|low",
  "assembled_from_turns": "description of which turns provided info"
}}

**EXAMPLES:**
- Turn 1: "can I get a loan?" Turn 2: "car" Turn 3: "100k car loan" → loan_type="auto", requested_amount="100000"
- Turn 1: "100k" Turn 2: "commercial loan" → loan_type="commercial", requested_amount="100000"
- Turn 1: "what are car loan rates?" → loan_type="auto", requested_amount=null (info request, not eligibility)"""

    try:
        response = await openai_client.chat.completions.create(
            model=settings.llm.chat_model,
            messages=[{"role": "user", "content": extraction_prompt}],
            max_tokens=150,
            temperature=0.1
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        # Clean up response - remove markdown formatting if present
        if raw_response.startswith("```json"):
            raw_response = raw_response.replace("```json", "").replace("```", "").strip()
        
        parsed = json.loads(raw_response)
        
        # Normalize null strings to None
        loan_type = parsed.get("loan_type")
        if loan_type in ["null", "None", ""]:
            loan_type = None
            
        requested_amount = parsed.get("requested_amount") 
        if requested_amount in ["null", "None", ""]:
            requested_amount = None
            
        return {
            "loan_type": loan_type,
            "requested_amount": requested_amount,
            "confidence": parsed.get("confidence", "medium"),
            "assembled_from_turns": parsed.get("assembled_from_turns", ""),
            "has_both_slots": bool(loan_type and requested_amount)
        }
        
    except Exception as e:
        logger.warning("cross_turn_extraction_failed", error=str(e))
        # Fallback to simple regex extraction
        return regex_extract_amount_type(memory)

async def parse_amount_and_type(memory: List[Dict], openai_client) -> Dict[str, Any]:
    """Extract amount and loan type from conversation using LLM"""
    
    # Build conversation context
    transcript_lines = []
    for msg in memory[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        speaker = "User" if role == "user" else "Arabie"
        transcript_lines.append(f"{speaker}: {content}")
    
    transcript = "\n".join(transcript_lines)
    
    extraction_prompt = f"""Extract loan amount and type from this conversation.

**CONVERSATION:**
{transcript}

**OUTPUT (JSON only):**
{{
  "amount": "numeric value or null",
  "currency": "USD",
  "type_inferred": "auto|home|mortgage|commercial|null",
  "confidence": "high|medium|low"
}}

**EXTRACTION RULES:**
- Look for amounts: $25,000, 25k, twenty-five thousand, etc.
- Types: auto/car/vehicle → "auto", home/house/mortgage → "home", business/commercial → "commercial"
- If multiple amounts, use the most recent
- If unclear, set to null"""

    try:
        response = await openai_client.chat.completions.create(
            model=settings.llm.chat_model,
            messages=[{"role": "user", "content": extraction_prompt}],
            max_tokens=100,
            temperature=0.1
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        # Clean up response - remove markdown formatting if present
        if raw_response.startswith("```json"):
            raw_response = raw_response.replace("```json", "").replace("```", "").strip()
        
        parsed = json.loads(raw_response)
        
        return {
            "amount": parsed.get("amount"),
            "type": parsed.get("type_inferred"),
            "confidence": parsed.get("confidence", "medium")
        }
        
    except Exception as e:
        logger.warning("llm_extraction_failed", error=str(e))
        # Fallback to regex
        return regex_extract_amount_type(memory)

def regex_extract_amount_type(memory: List[Dict]) -> Dict[str, Any]:
    """Regex fallback for amount/type extraction"""
    
    # Get last user message
    last_user_msg = ""
    for msg in reversed(memory):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "").lower()
            break

    # Improved scalable amount parsing (k, thousand, m, million, b, billion)
    amount_val = _to_int_amount(last_user_msg)
    amount = str(amount_val) if amount_val is not None else None
    
    # Extract type with keywords
    loan_type = None
    if any(word in last_user_msg for word in ["auto", "car", "vehicle"]):
        loan_type = "auto"
    elif any(word in last_user_msg for word in ["home", "house", "mortgage"]):
        loan_type = "home"
    elif any(word in last_user_msg for word in ["business", "commercial"]):
        loan_type = "commercial"
    
    return {
        "amount": amount,
        "type": loan_type,
        "confidence": "medium" if amount or loan_type else "low"
    }

# --- Scalable amount parsing helpers (added) ---
_AMOUNT_RE = re.compile(
    r'(?i)\b(?:usd|jod|\$)?\s*'                               # optional currency
    r'(\d{1,3}(?:[,\s]\d{3})*|\d+(?:\.\d+)?)\s*'              # 25,000 | 25000 | 1.25
    r'(k|thousand|m|mn|mm|million|b|bn|billion)?\b'           # optional scale
)
_SCALE = {
    None: 1,
    "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "mn": 1_000_000, "mm": 1_000_000, "million": 1_000_000,
    "b": 1_000_000_000, "bn": 1_000_000_000, "billion": 1_000_000_000,
}
def _to_int_amount(text: str) -> Optional[int]:
    if not text:
        return None
    s = text.replace("\u00A0", " ")  # NBSP → space
    m = _AMOUNT_RE.search(s)
    if not m:
        return None
    num, scale = m.group(1), (m.group(2) or "").lower()
    num = num.replace(",", "").replace(" ", "")
    try:
        val = float(num)  # supports decimals like 1.2m
    except ValueError:
        return None
    return int(val * _SCALE.get(scale, 1))

# Model parameters
LLM_PARAMS = {
    "temperature": 0.4,
    "top_p": 0.9,
    "max_tokens": 500
}

async def classify_intent_with_memory(memory: List[Dict], assembled_slots: Dict[str, Any], openai_client) -> str:
    """Classify intent using 10-turn conversation memory and assembled slot context."""
    
    # Build transcript from memory
    transcript_lines = []
    for i, msg in enumerate(memory[-10:]):  # Last 10 turns
        role = msg.get("role", "user")
        content = msg.get("content", "")
        speaker = "User" if role == "user" else "Arabie"
        transcript_lines.append(f"{speaker}: {content}")
    
    transcript = "\n".join(transcript_lines)
    
    # Enhanced prompt with slot assembly context
    enhanced_prompt = f"""
Based on the conversation transcript below (last 10 turns), classify the user's latest message into exactly one of these categories:

ACK — phatic/acknowledgment/greeting/ambiguous (e.g., "thanks," "hello," "I need help," "help me") - no specific request
INFO — policy/rates/terms/products questions (specific information about banking/loan features without asking for approval)  
ELIGIBILITY — approval/qualification/decision requests (asking "can I get", "am I eligible", "will you approve", "I want a loan" or providing loan details for qualification)

**ASSEMBLED CONTEXT FROM CONVERSATION:**
- Loan Type: {assembled_slots.get('loan_type', 'Not specified')}
- Requested Amount: {assembled_slots.get('requested_amount', 'Not specified')}
- Has Both Slots: {assembled_slots.get('has_both_slots', False)}

**ROUTING PRECEDENCE RULES:**
1. If the assembled context contains BOTH loan_type AND requested_amount, and the user intent involves getting/qualifying/applying/wanting for a loan, classify as ELIGIBILITY
2. If user is asking about rates/terms/policies/rules without seeking approval, classify as INFO
3. If user is giving greetings/thanks/ambiguous requests, classify as ACK

Consider the full context. Generic follow-ups like "are you sure?" refer to the previous topic unless the user clearly shifts.
If user states just a loan type (like "auto loan", "commercial loan") after previous eligibility discussion, classify as ELIGIBILITY.

Conversation transcript:
{transcript}

Classification:"""

    try:
        response = await openai_client.chat.completions.create(
            model=settings.llm.chat_model,
            messages=[{"role": "user", "content": enhanced_prompt}],
            max_tokens=10,
            temperature=0.1
        )
        
        intent = response.choices[0].message.content.strip().upper()
        
        # Validate and apply tie-breaker
        if intent in ["ACK", "INFO", "ELIGIBILITY"]:
            # Tie-breaker: if we have both slots and judge is ambiguous between INFO/ELIGIBILITY, choose ELIGIBILITY
            if assembled_slots.get('has_both_slots') and intent == "INFO":
                # Check if this might be an eligibility request disguised as info
                latest_user_msg = ""
                for msg in reversed(memory):
                    if msg.get("role") == "user":
                        latest_user_msg = msg.get("content", "").lower()
                        break
                
                # If user mentions getting/qualifying with complete slots, flip to ELIGIBILITY
                eligibility_indicators = ["can i get", "am i eligible", "qualify", "approve", "application"]
                if any(indicator in latest_user_msg for indicator in eligibility_indicators):
                    logger.info("router_tie_breaker", original_intent="INFO", final_intent="ELIGIBILITY", reason="has_both_slots_with_eligibility_intent")
                    return "ELIGIBILITY"
            
            return intent
        else:
            logger.warning("invalid_intent_returned", intent=intent)
            # Apply fallback tie-breaker - default to ACK on classifier error
            if assembled_slots.get('has_both_slots'):
                return "ELIGIBILITY"
            return "ACK"  # Safe default for ambiguous cases
            
    except Exception as e:
        logger.warning("intent_classification_failed", error=str(e))
        # Apply fallback tie-breaker - default to ACK on error
        if assembled_slots.get('has_both_slots'):
            return "ELIGIBILITY"
        return "ACK"  # Default fallback

def sanitize_ack_response(response: str, conversation_history: str, assembled_slots: Dict[str, Any]) -> str:
    """
    Sanitize ACK response to prevent loan type invention.
    Replace specific loan types with 'loan' unless they appear in conversation or slots.
    """
    # Extract all text for checking
    check_text = (conversation_history + " " + str(assembled_slots.get('loan_type', ''))).lower()
    
    # Specific loan type words to check
    specific_types = [
        'car', 'auto', 'vehicle', 'automotive',
        'home', 'house', 'mortgage', 'property',
        'business', 'commercial', 'corporate',
        'personal', 'student', 'education'
    ]
    
    response_lower = response.lower()
    for loan_type in specific_types:
        # If loan type appears in response but not in conversation/slots, replace with 'loan'
        if loan_type in response_lower and loan_type not in check_text:
            # Replace with case-preserved generic term
            response = re.sub(r'\b' + re.escape(loan_type) + r'\b', 'loan', response, flags=re.IGNORECASE)
            response = re.sub(r'\b' + re.escape(loan_type) + r' loan\b', 'loan', response, flags=re.IGNORECASE)
    
    return response

async def handle_ack_mode(memory: List[Dict], openai_client) -> Dict[str, Any]:
    """Handle ACK mode - warm banker greeting with no tools."""
    
    # Build transcript
    transcript_lines = []
    for msg in memory[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        speaker = "User" if role == "user" else "Arabie"
        transcript_lines.append(f"{speaker}: {content}")
    
    transcript = "\n".join(transcript_lines)
    
    prompt = ACK_SYSTEM_PROMPT.format(transcript=transcript)
    
    try:
        response = await openai_client.chat.completions.create(
            model=settings.llm.chat_model,
            messages=[{"role": "system", "content": prompt}],
            temperature=0,
            top_p=1.0,
            max_tokens=60
        )
        
        answer = response.choices[0].message.content.strip()
        
        # Sanitize response to prevent loan type invention
        answer = sanitize_ack_response(answer, transcript, {})
        
        return {
            "answer": answer,
            "decision": "ACK",
            "references": [],
            "quick_replies": [
                {"label": "Check eligibility"},
                {"label": "Loan rates"},
                {"label": "Apply now"}
            ],
            "cta": None,
            "rag_called": False  # ACK mode does not call RAG
        }
        
    except Exception as e:
        logger.error("ack_mode_failed", error=str(e))
        return {
            "answer": "Hello! I'm here to help with your banking needs. What can I assist you with today?",
            "decision": "ACK",
            "references": [],
            "quick_replies": [],
            "cta": None,
            "rag_called": False  # Error case, no RAG called
        }

async def handle_eligibility_mode(
    memory: List[Dict], 
    client_id: str,
    openai_client
) -> Dict[str, Any]:
    """Handle ELIGIBILITY mode with simplified logic - no clarifications"""
    
    # Extract structured signals from data sources
    structured_signals = await extract_structured_signals(client_id, memory)
    
    # Parse amount and type from conversation
    parsed_data = await parse_amount_and_type(memory, openai_client)
    
    # Update structured signals with parsed data
    if parsed_data.get("amount"):
        structured_signals["requested_amount"] = parsed_data["amount"]
    if parsed_data.get("type"):
        structured_signals["loan_type"] = parsed_data["type"]
    
    # Check if we have enough info - if not, return simple COUNTER with ask
    loan_type = structured_signals.get("loan_type")
    requested_amount = structured_signals.get("requested_amount")
    
    # Handle null strings returned by LLM
    if loan_type in [None, "null", "Not specified"]:
        loan_type = None
    if requested_amount in [None, "null", "Not specified"]:
        requested_amount = None
    
    logger.info("eligibility_check", 
                loan_type=loan_type, 
                requested_amount=requested_amount, 
                parsed_type=parsed_data.get("type"),
                parsed_amount=parsed_data.get("amount"))
    
    if not loan_type and not requested_amount:
        return {
            "answer": "Please tell me the loan type and amount so I can help with your eligibility.",
            "decision": "COUNTER",
            "references": [],
            "quick_replies": [],
            "cta": None
        }
    elif not loan_type:
        return {
            "answer": "Please tell me the loan type so I can help with your eligibility.",
            "decision": "COUNTER",
            "references": [],
            "quick_replies": [],
            "cta": None
        }
    elif not requested_amount:
        return {
            "answer": "Please tell me the amount so I can help with your eligibility.",
            "decision": "COUNTER",
            "references": [],
            "quick_replies": [],
            "cta": None
        }
    
    # Build transcript
    transcript_lines = []
    for msg in memory[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        speaker = "User" if role == "user" else "Arabie"
        transcript_lines.append(f"{speaker}: {content}")
    
    transcript = "\n".join(transcript_lines)
    
    # Make eligibility decision using LLM
    prompt = ELIGIBILITY_SYSTEM_PROMPT.format(
        transcript=transcript,
        risk_grade=structured_signals.get("risk_grade", "Not available"),
        annual_income=structured_signals.get("annual_income", "Not available"),
        requested_amount=structured_signals.get("requested_amount", "Not specified"),
        loan_type=structured_signals.get("loan_type", "Not specified"),
        market_condition=structured_signals.get("market_condition", "Not available")
    )
    
    try:
        response = await openai_client.chat.completions.create(
            model=settings.llm.chat_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        # Clean up response - remove markdown formatting if present  
        if raw_response.startswith("```json"):
            raw_response = raw_response.replace("```json", "").replace("```", "").strip()
        
        decision_result = json.loads(raw_response)
        
    except Exception as e:
        logger.error("eligibility_decision_failed", error=str(e))
        # Safe fallback
        decision_result = {
            "decision": "COUNTER",
            "rationale": ["Unable to process request due to system error"]
        }
    
    # Build final answer from decision
    decision = decision_result.get("decision", "COUNTER")
    rationale = decision_result.get("rationale", ["Unable to process request"])
    
    answer_parts = [f"**{decision}**"]
    answer_parts.extend([f"• {bullet}" for bullet in rationale])
    
    final_answer = "\n".join(answer_parts)
    
    # Determine quick replies and CTA based on decision
    quick_replies = []
    cta = None
    
    if decision == "COUNTER":
        quick_replies = [
            {"label": "Adjust amount"},
            {"label": "Check eligibility"},
            {"label": "Contact officer"}
        ]
        cta = {"text": "Contact Officer", "action": "contact_officer"}
    elif decision == "DECLINE":
        quick_replies = [
            {"label": "Loan options"},
            {"label": "Improve credit"},
            {"label": "Contact officer"}
        ]
        cta = {"text": "Contact Officer", "action": "contact_officer"}
    else:  # APPROVE
        quick_replies = [
            {"label": "Apply now"},
            {"label": "Learn more"},
            {"label": "Contact officer"}
        ]
        cta = {"text": "Start Application", "action": "apply_now"}
    
    return {
        "answer": final_answer,
        "decision": decision,
        "references": [],
        "quick_replies": quick_replies,
        "cta": cta,
        "rag_called": False  # ELIGIBILITY does not call RAG
    }

async def handle_info_mode(memory: List[Dict], openai_client) -> Dict[str, Any]:
    """Handle INFO mode - Evidence-driven RAG with visible references."""
    
    # Get the latest user question
    user_question = ""
    for msg in reversed(memory):
        if msg.get("role") == "user":
            user_question = msg.get("content", "")
            break
    
    if not user_question:
        return {
            "answer": "I didn't catch your question. Could you please ask about specific loan policies or rates?",
            "decision": "INFORM",
            "references": [],
            "quick_replies": [],
            "cta": None,
            "rag_called": False  # No RAG for empty questions
        }
    
    # Retrieve evidence from Qdrant
    try:
        raw_snippets = search_policy_by_question(
            question=user_question,
            top_k=8
        )
        
        # Filter and build evidence with governance filtering
        evidence = []
        user_question_lower = user_question.lower()
        user_asked_governance = any(word in user_question_lower for word in 
                                   ["insider", "committee", "board", "governance", "minutes"])
        
        governance_pattern = re.compile(r'(Insider|Committee|Board|Minutes)', re.IGNORECASE)
        
        for snippet in raw_snippets:
            # Check minimum relevance
            if snippet.get("score", 0) < 0.1:
                continue
                
            snippet_text = snippet.get("page_content", str(snippet))
            metadata = snippet.get("metadata", {})
            
            heading_path = metadata.get("heading_path", "")
            section_title = metadata.get("section_title", heading_path)
            
            # Drop governance unless explicitly asked
            if not user_asked_governance and governance_pattern.search(f"{snippet_text} {section_title}"):
                continue
                
            evidence.append({
                "text": snippet_text,
                "metadata": metadata
            })
            
            # Keep top 3 most relevant
            if len(evidence) >= 3:
                break
        
        # Build evidence context for LLM
        evidence_lines = []
        for i, item in enumerate(evidence):
            source_id = f"S{i+1}"
            text = item["text"][:400]  # Truncate for context
            metadata = item["metadata"]
            heading = metadata.get("heading_path", "Unknown section")
            page = metadata.get("page_start", "?")
            # Omit PDF filename for cleaner display
            evidence_lines.append(f"{source_id}: {text}...")
            evidence_lines.append(f"   [Source: {heading} (p.{page})]")
        
        evidence_context = "\n\n".join(evidence_lines) if evidence_lines else "No relevant policy information found."
        
        # Build transcript
        transcript_lines = []
        for msg in memory[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            speaker = "User" if role == "user" else "Arabie"
            transcript_lines.append(f"{speaker}: {content}")
        
        transcript = "\n".join(transcript_lines)
        
        # Generate response with evidence
        prompt = INFO_SYSTEM_PROMPT.format(
            transcript=transcript,
            evidence=evidence_context
        )
        
        response = await openai_client.chat.completions.create(
            model=settings.llm.chat_model,
            messages=[{"role": "user", "content": prompt}],
            **LLM_PARAMS
        )
        
        answer = response.choices[0].message.content.strip()
        
        # Build references for API response
        references = []
        for i, item in enumerate(evidence):
            metadata = item["metadata"]
            references.append({
                "source": f"S{i+1}",
                "section": metadata.get("heading_path", "Unknown section"),
                "page": metadata.get("page_start", "?")
            })
        
        return {
            "answer": answer,
            "decision": "INFORM",
            "references": references,
            "quick_replies": [
                {"label": "More details"},
                {"label": "Check eligibility"}
            ],
            "cta": None,
            "rag_called": True  # INFO mode calls RAG
        }
        
    except Exception as e:
        logger.error("info_mode_failed", error=str(e))
        return {
            "answer": "I'm having trouble accessing our policy information right now. Please try again or contact our support team.",
            "decision": "INFORM",
            "references": [],
            "quick_replies": [],
            "cta": {"text": "Contact Support", "action": "contact_officer"},
            "rag_called": False  # Error case, no RAG called
        }

async def extract_structured_signals(client_id: str, memory: List[Dict]) -> Dict[str, Any]:
    """Extract structured signals for eligibility decisions."""
    
    signals = {}
    
    # Extract customer data from database
    try:
        customer_data = await fetch_customer_data(client_id)
        if customer_data:
            signals["risk_grade"] = customer_data.get("risk_grade")
            signals["annual_income"] = customer_data.get("annual_income")
    except Exception as e:
        logger.warning("customer_data_fetch_failed", error=str(e))
    
    # Extract market conditions
    try:
        market_data = await fetch_market_data()
        if market_data:
            signals["market_condition"] = market_data.get("risk_level", "moderate_risk")
    except Exception as e:
        logger.warning("market_data_fetch_failed", error=str(e))
    
    # Parse requested amount and loan type from conversation
    for msg in memory:
        if msg.get("role") == "user":
            content = msg.get("content", "").lower()
            
            # Extract loan amount
            amt_val = _to_int_amount(content)
            if amt_val is not None and not signals.get("requested_amount"):
                signals["requested_amount"] = str(amt_val)
            
            # Extract loan type
            if any(word in content for word in ["auto", "car", "vehicle"]):
                signals["loan_type"] = "auto"
            elif any(word in content for word in ["home", "house", "mortgage"]):
                signals["loan_type"] = "home"
            elif any(word in content for word in ["business", "commercial"]):
                signals["loan_type"] = "commercial"
    
    return signals

async def fetch_customer_data(client_id: str) -> Optional[Dict[str, Any]]:
    """Fetch customer data from database."""
    try:
        import sqlite3
        
        # Use synchronous database access
        conn = sqlite3.connect('data/app.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT risk_grade, annual_income, risk_score, employment_status
            FROM customers 
            WHERE client_id = ?
        """, (client_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "risk_grade": result[0],
                "annual_income": result[1], 
                "risk_score": result[2],
                "employment_status": result[3]
            }
        
        return None
        
    except Exception as e:
        logger.error("customer_data_fetch_error", client_id=client_id, error=str(e))
        return None

async def fetch_market_data(region: str = "OK") -> Optional[Dict[str, Any]]:
    """Fetch current market conditions."""
    try:
        # Simulate market data - in real implementation would fetch from market store
        return {
            "risk_level": "moderate_risk",
            "prime_rate": 7.5,
            "market_trend": "stable"
        }
        
    except Exception as e:
        logger.error("market_data_fetch_error", region=region, error=str(e))
        return None

async def single_agent_controller(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Principal AI/NLP Architect controller with 10-turn memory and evidence-driven decisions.
    """
    
    user_message = state.get("user_message", "") or state.get("question", "")
    client_id = state.get("client_id") 
    memory = state.get("memory", [])
    req_id = state.get("req_id")
    
    # Input guardrail check
    state["question"] = user_message  # Set for guardrail compatibility
    state = guardrail_node(state)
    
    # If guardrail violation detected, return early
    if state.get("guardrail_violation"):
        logger.warning("Input guardrail violation detected", req_id=req_id)
        return state
    
    # Memory management: append incoming message and truncate to last 10
    memory.append({"role": "user", "content": user_message})
    memory = memory[-10:]  # Keep last 10 messages
    state["memory"] = memory
    
    logger.info("single_agent_start", req_id=req_id, question_length=len(user_message))
    
    # Initialize OpenAI client
    try:
        api_key = getattr(settings, 'openai_api_key', None) or os.getenv('OPENAI_API_KEY')
        if api_key:
            openai_client = openai.AsyncOpenAI(api_key=api_key)
            logger.info("Created async OpenAI client for single agent")
        else:
            raise Exception("OpenAI API key not found")
    except Exception as e:
        raise Exception(f"OpenAI client not configured: {e}")
    
    # Extract cross-turn slot assembly for enhanced routing
    assembled_slots = await extract_cross_turn_slots(memory, openai_client)
    logger.info("cross_turn_slots_assembled", req_id=req_id, slots=assembled_slots)
    
    # Classify intent with 10-turn memory context and assembled slots
    agent_mode = await classify_intent_with_memory(memory, assembled_slots, openai_client)
    state["agent_mode"] = agent_mode
    
    logger.info("agent_mode", req_id=req_id, mode=agent_mode)
    
    # Route to appropriate handler
    if agent_mode == "ACK":
        result = await handle_ack_mode(memory, openai_client)
    elif agent_mode == "ELIGIBILITY":
        result = await handle_eligibility_mode(memory, client_id, openai_client)
    else:  # INFO mode
        result = await handle_info_mode(memory, openai_client)
    
    # Add assistant response to memory
    memory.append({"role": "assistant", "content": result["answer"]})
    state["memory"] = memory[-10:]  # Keep last 10
    
    # Update state with results including debugging info
    state.update({
        "answer": result["answer"],
        "decision": result["decision"], 
        "references": result["references"],
        "quick_replies": result["quick_replies"],
        "cta": result["cta"],
        "path_chosen": agent_mode,  # Add this for testing/debugging
        "assembled_slots": assembled_slots,  # Add this for testing/debugging
        "rag_called": result.get("rag_called", False),  # Add this for testing/debugging
        "final_answer": result["answer"],  # Set for guardrail compatibility
        "explanation": f"Agent mode: {agent_mode}"  # Set for guardrail compatibility
    })
    
    # Output guardrail check
    state = guardrail_out_node(state)
    
    # Update answer if guardrail modified it
    if state.get("output_guardrail_triggered"):
        logger.warning("Output guardrail triggered", req_id=req_id)
        state["answer"] = state["final_answer"]
    
    # Enhanced observability logging
    logger.info("final_observability",
               req_id=req_id,
               mode=agent_mode,
               decision=result["decision"],
               refs=len(result["references"]),
               answer_tokens=len(result["answer"].split()),
               memory_turns=len(memory))
    
    return state

# Export the main entry point
async def process_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a request using the single agent controller.
    This is a wrapper for API compatibility.
    """
    state = {
        "user_message": request.get("question", ""),
        "client_id": request.get("client_id"),
        "memory": request.get("memory", []),
        "req_id": request.get("req_id")
    }
    
    result = await single_agent_controller(state)
    
    return {
        "answer": result.get("answer", ""),
        "decision": result.get("decision", "INFORM"),
        "references": result.get("references", []),
        "quick_replies": result.get("quick_replies", []),
        "cta": result.get("cta"),
        "request_id": request.get("req_id", ""),
        "metadata": result.get("metadata", {}),
        "path_chosen": result.get("path_chosen"),  # Add for testing
        "assembled_slots": result.get("assembled_slots", {}),  # Add for testing
        "rag_called": result.get("rag_called", False)  # Add for testing
    }

__all__ = ["single_agent_controller", "process_request"]
