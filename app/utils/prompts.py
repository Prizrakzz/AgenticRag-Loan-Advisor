"""
Shared prompts and constants for LLM interactions.
Implements strict guardrails, natural tone, and structured outputs.
"""

SYSTEM_COMPLIANT = """
You are Arabie, Arab Bank's professional loan advisor.

STRICT GUARDRAILS:
• Do not discuss religion, politics, elections, hate, violence, extremist content, self-harm, or protected-class topics.
• If asked about any forbidden topic, respond with the REFUSAL object (see Output Schema) and stop.
• Keep answers short, factual, and grounded in provided policy snippets (max 3). Paraphrase policy language.

TONE:
• Warm, concise, natural. Use natural, varied openers. Avoid repeating the same sentence starter across turns, and avoid 'Sure—' or 'I understand'.
• Use bullets for requirements. Offer a single next step only when helpful.
"""

INTENT_CLASSIFIER = """
Classify the user message into one of:
- "informational" (policy info, requirements, terms),
- "eligibility" (can I get X, am I approved),
- "forbidden" (religion, politics, elections, hate, extremist, protected-class).

Return ONLY:
{"intent":"<informational|eligibility|forbidden>"}

User: {question}
"""

JUDGE_V3 = """
ROLE: Decide the appropriate outcome for the user's request using policy snippets, customer profile, and market context.

TOPIC GATE: If the message involves religion, politics, hate, extremist, or protected classes, return the REFUSAL object and stop.

ROUTING:
• If asking for terms/requirements → decision="INFORM".
• If asking eligibility/approval → decide among APPROVE/DECLINE; use COUNTER only if essential info is missing.

DECISION POLICY (qualitative, NOT keyword rules):
• Use policy_snippets to check hard constraints (e.g., DTI, min income, collateral).
• Use customer risk & market conditions to tilt decision:
  – Favor APPROVE when risk is low and market stable/positive and constraints appear met from profile/history.
  – Favor DECLINE when risk is high or constraints likely unmet.
  – Use COUNTER only if you truly need 1–2 specific documents or numbers (e.g., proof of income, DTI %, collateral details). List exactly what's missing.

STYLE:
• Natural, concise, varied; no boilerplate. Keep replies to 4–7 sentences.
• Use bullets for requirements. One clear next step if helpful.

OUTPUT SCHEMA (return ONLY this JSON, in this exact order):
{{
"answer": "<concise conversational text; never empty; bullets allowed>",
"decision": "INFORM | APPROVE | DECLINE | COUNTER | REFUSE",
"references": [ {{"source":"S1","section":"<str>","page":<int>}} ],
"quick_replies": [ {{"label":"<str>"}} ],
"cta": {{ "label":"<str>","url":"<str>"}} | null
}}

REFERENCE RULES:
• Up to 3, derived from the given snippets; else [].

CTA RULES:
• Only include a CTA for APPROVE or COUNTER.

INPUTS:

customer_profile: {customer_json}

risk_grade: {risk_grade}

market_metrics: {market_json}

policy_snippets (≤3): {snippets_json}

memory (last 10 Q/A pairs): {memory_json}

user_request: {question}
"""

EXPLAINER_V2 = """
Produce a short, helpful explanation grounded in provided snippets and context.
Apply the same guardrails, tone, and OUTPUT SCHEMA as JUDGE_V2.

Natural, concise, varied; no boilerplate.

Inputs:
- snippets: {snippets_json}
- memory: {memory_json}
- risk_grade: {risk_grade}
- market_metrics: {market_json}

User: {question}
"""

REFUSAL_OBJECT = {
    "answer": "I'm sorry, but I can't help with that.",
    "decision": "REFUSE",
    "references": [],
    "quick_replies": [],
    "cta": None
}

# Standardized LLM parameters for consistent behavior
LLM_PARAMS = {
    "temperature": 0.4,
    "top_p": 0.9,
    "frequency_penalty": 0.4,
    "presence_penalty": 0.0,
    "max_tokens": 300
}

# Validation schemas
VALID_DECISIONS = {"INFORM", "APPROVE", "COUNTER", "DECLINE", "REFUSE"}

def validate_llm_response(response_data: dict) -> tuple[bool, str]:
    """
    Validate LLM response structure and content.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    required_fields = ["answer", "decision", "references", "quick_replies", "cta"]
    for field in required_fields:
        if field not in response_data:
            return False, f"Missing required field: {field}"
    
    # Validate decision
    if response_data["decision"] not in VALID_DECISIONS:
        return False, f"Invalid decision: {response_data['decision']}"
    
    # Validate references structure and count
    references = response_data["references"]
    if not isinstance(references, list) or len(references) > 3:
        return False, f"References must be a list of max 3 items, got {len(references)}"
    
    for ref in references:
        if not isinstance(ref, dict) or not all(k in ref for k in ["source", "section", "page"]):
            return False, "Each reference must have source, section, and page"
    
    # Validate quick_replies structure
    quick_replies = response_data["quick_replies"]
    if not isinstance(quick_replies, list):
        return False, "quick_replies must be a list"
    
    for qr in quick_replies:
        if not isinstance(qr, dict) or "label" not in qr:
            return False, "Each quick_reply must have a label"
    
    return True, ""

def format_context_for_prompt(
    customer_profile: dict,
    risk_grade: str,
    market_metrics: dict,
    snippets: list,
    memory: list,
    question: str
) -> dict:
    """
    Format context data for prompt templates.
    
    Returns:
        Dictionary with formatted context strings
    """
    import json
    
    try:
        # Format snippets (cap at 3)
        formatted_snippets = []
        for i, snippet in enumerate(snippets[:3]):
            if snippet is None:
                continue
            if isinstance(snippet, dict):
                formatted_snippets.append({
                    "source": f"S{i+1}",
                    "section": snippet.get("section", "General"),
                    "page": snippet.get("source_page", 1),
                    "content": snippet.get("page_content", "")
                })
            else:
                # Handle non-dict snippet
                formatted_snippets.append({
                    "source": f"S{i+1}",
                    "section": "General",
                    "page": 1,
                    "content": str(snippet)
                })
        
        # Format memory (last 10 pairs)
        formatted_memory = []
        for msg in memory[-10:]:
            if msg is None:
                continue
            if isinstance(msg, dict):
                formatted_memory.append({
                    "question": msg.get("question", ""),
                    "answer": msg.get("answer", "")
                })
        
        result = {
            "customer_json": json.dumps(customer_profile, indent=2),
            "risk_grade": risk_grade,
            "market_json": json.dumps(market_metrics, indent=2),
            "snippets_json": json.dumps(formatted_snippets, indent=2),
            "memory_json": json.dumps(formatted_memory, indent=2),
            "question": question
        }
        
        return result
        
    except Exception as e:
        # Log error and return minimal context
        print(f"Error in format_context_for_prompt: {e}")
        return {
            "customer_json": json.dumps(customer_profile or {}, indent=2),
            "risk_grade": risk_grade or "C",
            "market_json": json.dumps(market_metrics or {}, indent=2),
            "snippets_json": json.dumps([], indent=2),
            "memory_json": json.dumps([], indent=2),
            "question": question or ""
        }
