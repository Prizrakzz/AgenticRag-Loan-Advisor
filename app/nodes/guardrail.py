import re
import openai
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class GuardrailError(Exception):
    """Raised when content violates guardrails."""
    pass


# Forbidden content patterns (kept generic — no slurs in source code)
_FORBIDDEN_TERMS = [
    "politic", "election", "hitler",
]
FORBIDDEN_REGEX = re.compile(
    r"(" + "|".join(re.escape(t) for t in _FORBIDDEN_TERMS) + r")",
    re.I | re.U,
)


async def check_content(text: str) -> None:
    """
    Check content against guardrails using OpenAI moderation API with regex fallback.
    
    Args:
        text: Content to check
        
    Raises:
        GuardrailError: If content violates guardrails
    """
    if not text or not text.strip():
        return
    
    try:
        # Primary check: OpenAI moderation API  
        from ..utils.config import settings
        api_key = getattr(settings, 'openai_api_key', None) or os.getenv('OPENAI_API_KEY')
        client = openai.AsyncOpenAI(api_key=api_key)
        
        resp = await client.moderations.create(
            model="omni-moderation-latest", 
            input=text
        )
        
        if resp.results[0].flagged:
            logger.warning("OpenAI moderation flagged content")
            raise GuardrailError("OpenAI moderation flagged content")
            
    except Exception as api_err:
        # Fallback: regex-based filtering
        logger.warning("Moderation API failed → fallback regex: %s", api_err)
        
        if FORBIDDEN_REGEX.search(text):
            logger.warning("Regex flagged forbidden content")
            raise GuardrailError("Regex flagged content")
    
    logger.debug("Content passed guardrail checks")


def guardrail_node(state):
    """
    Input guardrail node - checks user question.
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with guardrail response if violation detected
    """
    question = state.get("question", "")
    
    logger.info(f"guardrail_input_check req_id={state.get('req_id')} question_length={len(question)}")
    
    # Check for forbidden content
    if FORBIDDEN_REGEX.search(question):
        logger.warning(f"Input guardrail violation detected question={question[:50]}")
        
        # Set REFUSE response and stop workflow
        state.update({
            "decision": "REFUSE",
            "reason_codes": ["Content violates usage policy"],
            "final_answer": "I cannot assist with that request as it violates our usage policy. Please rephrase your question in a respectful manner.",
            "score": 0.0,
            "explanation": "Input content blocked by content guardrails",
            "guardrail_violation": True
        })
        return state
    
    logger.debug("Input passed guardrail checks")
    return state


def guardrail_out_node(state):
    """
    Output guardrail node - checks generated response.
    
    Args:
        state: Current workflow state
        
    Returns:
        Updated state with sanitized response if violation detected
    """
    final_answer = state.get("final_answer", "")
    explanation = state.get("explanation", "")
    
    # Check both final answer and explanation
    content_to_check = f"{final_answer} {explanation}".strip()
    
    logger.info(f"guardrail_output_check req_id={state.get('req_id')} content_length={len(content_to_check)}")
    
    # Check for forbidden content in response
    if FORBIDDEN_REGEX.search(content_to_check):
        logger.warning(f"Output guardrail violation detected content_length={len(content_to_check)}")
        
        # Replace with safe generic response
        state.update({
            "final_answer": "I'm here to help with your loan inquiry. Please let me know how I can assist you with Arab Bank's loan products and services.",
            "explanation": "Response sanitized due to content policy violation",
            "output_guardrail_triggered": True
        })
    
    logger.debug("Output guardrail check completed")
    return state
