import re
import json
import openai
from typing import Literal, Tuple, Dict, Any
from ..utils.config import settings
from ..utils.prompts import SYSTEM_COMPLIANT, INTENT_CLASSIFIER, LLM_PARAMS
from ..utils.logger import get_logger

logger = get_logger(__name__)

Intent = Literal["eligibility", "policy", "forbidden"]

# Enhanced loan mention pattern (priority rule)
LOAN_MENTION = r'\b(loan|loans|mortgage|mortgages|debt|debts|borrow|financ(e|ing))\b'

_ELIG_PATTERNS = [
    r"\b(can i|get|qualify|eligible|approve|approve me|pre-?approve|decline)\b",
    r"\b(loan)\b.*\b(for me|for client|my|i)\b",
    r"\b(\$?\d{4,}|\d{2,}\s*(k|thousand|usd|usd\.?))\b",  # amounts
    r"\b(credit score|risk grade|dti|income)\b",
]
_POLICY_PATTERNS = [
    r"\b(terms?|policy|requirements?|ltv|apr|fee|grace|tenor|max|min|rate|penalty)\b",
    r"\b(what|how|when|where|which)\b.*\b(loan|policy|term|rate|ltv|apr|fees?)\b",
]

def classify_intent_llm(question: str) -> Tuple[Intent, float, Dict[str, Any]]:
    """
    LLM-based intent classification with forbidden content detection.
    
    Args:
        question: User question text
    
    Returns:
        Tuple of (intent, confidence, features)
    """
    if not question or not question.strip():
        return "policy", 0.5, {"fallback": True}
    
    try:
        # Get OpenAI client
        openai_client = getattr(settings, 'openai_client', None)
        if not openai_client:
            logger.warning("OpenAI client not available, falling back to heuristic")
            return classify_intent(question)
        
        # Format prompt
        user_message = INTENT_CLASSIFIER.format(question=question)
        
        # Call LLM
        response = openai_client.chat.completions.create(
            model=settings.llm.chat_model,
            messages=[
                {"role": "system", "content": SYSTEM_COMPLIANT},
                {"role": "user", "content": user_message}
            ],
            **LLM_PARAMS
        )
        
        # Parse response
        content = response.choices[0].message.content.strip()
        result = json.loads(content)
        
        intent = result.get("intent", "policy")
        
        # Map to our Intent type and set confidence
        if intent == "forbidden":
            return "forbidden", 0.95, {"llm_classified": True, "forbidden_detected": True}
        elif intent == "eligibility":
            return "eligibility", 0.85, {"llm_classified": True}
        else:  # informational
            return "policy", 0.80, {"llm_classified": True}
            
    except Exception as e:
        logger.warning("LLM intent classification failed, falling back to heuristic", error=str(e))
        return classify_intent(question)


def classify_intent(question: str | None, last_active_intent: Intent = None) -> Tuple[Intent, float, Dict[str, Any]]:
    """
    Classify user intent with enhanced loan mention detection and forbidden content detection.
    
    Args:
        question: User question text
        last_active_intent: Previous intent for context (optional)
    
    Returns:
        Tuple of (intent, confidence, features)
    """
    if not question:
        return "policy", 0.5, {"has_loan_mention": False, "fallback": True}
    
    q = question.lower()
    
    # Check for forbidden content first
    forbidden_patterns = [
        r'\b(politic|election|vote|republican|democrat|conservative|liberal)\b',
        r'\b(religion|religious|islam|christian|jewish|muslim|jew|christian|church|mosque|temple)\b',
        r'\b(hitler|nazi|extremist|terrorist|bomb|violence|kill|murder|hate)\b',
        r'\b(fuck|shit|bitch|nigger|faggot|cunt)\b'
    ]
    
    for pattern in forbidden_patterns:
        if re.search(pattern, q):
            return "forbidden", 0.95, {
                "forbidden_detected": True,
                "pattern_matched": True,
                "heuristic_classified": True
            }
    
    # Priority rule: any loan mention → eligibility
    has_loan_mention = bool(re.search(LOAN_MENTION, q))
    if has_loan_mention:
        return "eligibility", 0.88, {
            "has_loan_mention": True, 
            "loan_mention_priority": True,
            "last_active_intent": last_active_intent
        }
    
    # Existing pattern matching
    elig_matches = sum(1 for p in _ELIG_PATTERNS if re.search(p, q))
    policy_matches = sum(1 for p in _POLICY_PATTERNS if re.search(p, q))
    
    features = {
        "has_loan_mention": has_loan_mention,
        "elig_pattern_matches": elig_matches,
        "policy_pattern_matches": policy_matches,
        "last_active_intent": last_active_intent
    }
    
    if elig_matches > 0:
        confidence = min(0.85, 0.6 + (elig_matches * 0.1))
        return "eligibility", confidence, features
    
    if policy_matches > 0:
        confidence = min(0.85, 0.6 + (policy_matches * 0.1))
        return "policy", confidence, features
    
    # fallback: if it's clearly personal ("I", "my") lean eligibility
    if re.search(r"\b(i|my|me|client\s*\d+)\b", q):
        return "eligibility", 0.65, {**features, "personal_pronoun_fallback": True}
    
    return "policy", 0.5, {**features, "default_fallback": True}
