"""
Dialog Manager for enhanced customer service interactions.
Handles empathy, clarification, quick replies, and CTAs.
"""

from typing import Dict, List, Any, Optional
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Product mapping for loan types
LOAN_PRODUCTS = {
    "car": {"name": "Auto Loan", "url": "/apply?product=auto"},
    "auto": {"name": "Auto Loan", "url": "/apply?product=auto"},
    "vehicle": {"name": "Auto Loan", "url": "/apply?product=auto"},
    "home": {"name": "Home Loan", "url": "/apply?product=home"},
    "mortgage": {"name": "Home Loan", "url": "/apply?product=home"},
    "house": {"name": "Home Loan", "url": "/apply?product=home"},
    "real estate": {"name": "Real Estate Loan", "url": "/apply?product=realestate"},
    "property": {"name": "Real Estate Loan", "url": "/apply?product=realestate"},
    "business": {"name": "Commercial Loan", "url": "/apply?product=commercial"},
    "commercial": {"name": "Commercial Loan", "url": "/apply?product=commercial"},
    "personal": {"name": "Personal Loan", "url": "/apply?product=personal"},
    "refinance": {"name": "Refinancing", "url": "/apply?product=refinance"}
}

QUICK_REPLY_OPTIONS = [
    {"label": "Auto Loan", "value": "car loan"},
    {"label": "Home Loan", "value": "home mortgage"},
    {"label": "Commercial Loan", "value": "business loan"},
    {"label": "Personal Loan", "value": "personal loan"},
    {"label": "Refinancing", "value": "refinance options"}
]


def process_dialogue(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main dialogue processing function.
    
    Args:
        context: Dict containing question, memory, intent, product context
        
    Returns:
        Dict with empathy, clarification_needed, quick_replies, main_answer_prompt, cta
    """
    question = context.get("question", "").lower()
    memory = context.get("memory", [])
    intent_confidence = context.get("intent_confidence", 0.0)
    product_context = context.get("product_context")
    
    # Detect product from question if not already set
    if not product_context:
        product_context = _detect_product_from_question(question)
    
    # Generate empathy hook
    empathy = _generate_empathy_hook(product_context, question)
    
    # Determine if clarification is needed
    clarification_needed = (
        intent_confidence < 0.75 or 
        not product_context or
        _is_ambiguous_query(question)
    )
    
    # Generate quick replies if clarification needed
    quick_replies = []
    if clarification_needed:
        quick_replies = _get_relevant_quick_replies(question, product_context)
    
    # Generate main answer prompt
    main_answer_prompt = _build_main_answer_prompt(
        question, product_context, clarification_needed, memory
    )
    
    # Generate CTA if product is known
    cta = None
    if product_context and not clarification_needed:
        cta = _generate_cta(product_context)
    
    # Handle "did you mean" flows
    if _is_did_you_mean_query(question) and product_context:
        return _handle_did_you_mean(product_context, question)
    
    result = {
        "empathy": empathy,
        "clarification_needed": clarification_needed,
        "quick_replies": quick_replies,
        "main_answer_prompt": main_answer_prompt,
        "cta": cta,
        "product_context": product_context
    }
    
    logger.debug(
        "dialog_manager_processed",
        question_preview=question[:50],
        product_context=product_context,
        clarification_needed=clarification_needed,
        has_cta=bool(cta),
        quick_replies_count=len(quick_replies)
    )
    
    return result


def _detect_product_from_question(question: str) -> Optional[str]:
    """Detect loan product from user question."""
    question_lower = question.lower()
    
    # Direct product matches
    for product_key in LOAN_PRODUCTS:
        if product_key in question_lower:
            return product_key
    
    # Contextual clues
    if any(word in question_lower for word in ["buying", "purchase", "buy"]):
        if any(word in question_lower for word in ["car", "vehicle", "auto"]):
            return "car"
        elif any(word in question_lower for word in ["home", "house"]):
            return "home"
    
    return None


def _generate_empathy_hook(product_context: Optional[str], question: str) -> str:
    """Generate empathetic opening based on context."""
    if product_context:
        product_name = LOAN_PRODUCTS.get(product_context, {}).get("name", product_context)
        return f"I understand you're interested in a {product_name}—let's get you the details you need."
    
    if "help" in question.lower():
        return "I'm here to help you find the right loan solution for your needs."
    
    return "Thank you for reaching out to Arab Bank. I'm here to assist you with your loan inquiry."


def _is_ambiguous_query(question: str) -> bool:
    """Check if the query is too ambiguous to provide specific help."""
    ambiguous_patterns = [
        "what can you help",
        "what do you offer",
        "tell me about",
        "i need help",
        "what are my options",
        "what loans",
        "help me"
    ]
    
    question_lower = question.lower()
    return any(pattern in question_lower for pattern in ambiguous_patterns)


def _get_relevant_quick_replies(question: str, product_context: Optional[str]) -> List[Dict[str, str]]:
    """Get relevant quick reply options based on context."""
    if product_context:
        # If we have some context, offer related options
        related_products = _get_related_products(product_context)
        return [{"label": LOAN_PRODUCTS[p]["name"], "value": f"{p} loan"} 
                for p in related_products if p in LOAN_PRODUCTS]
    
    # Default quick replies for ambiguous queries
    return QUICK_REPLY_OPTIONS


def _get_related_products(product: str) -> List[str]:
    """Get related loan products for cross-selling."""
    related_map = {
        "car": ["auto", "personal"],
        "auto": ["car", "personal"],
        "home": ["mortgage", "refinance"],
        "mortgage": ["home", "refinance"],
        "business": ["commercial"],
        "commercial": ["business"],
        "personal": ["car", "home"]
    }
    
    return related_map.get(product, [product])


def _build_main_answer_prompt(
    question: str, 
    product_context: Optional[str], 
    clarification_needed: bool,
    memory: List[Dict[str, str]]
) -> str:
    """Build the main prompt for the answer generation."""
    
    if clarification_needed:
        return f"""
The user's question seems to need clarification about loan type or requirements.
Please respond with: "Just to confirm, are you looking for information about [loan type]—is that correct?"
Offer to help them explore their options.

Original question: {question}
"""
    
    prompt = f"""
Provide a helpful, detailed response about {product_context or 'loan'} options.
Include specific requirements, benefits, and next steps.
Be conversational and professional.

Question: {question}
"""
    
    if product_context:
        prompt += f"\nFocus specifically on {LOAN_PRODUCTS.get(product_context, {}).get('name', product_context)} products."
    
    return prompt


def _generate_cta(product_context: str) -> Dict[str, str]:
    """Generate call-to-action for known products."""
    if product_context in LOAN_PRODUCTS:
        product_info = LOAN_PRODUCTS[product_context]
        return {
            "label": f"Start {product_info['name']} Application",
            "url": product_info["url"]
        }
    
    return {
        "label": "Start Application",
        "url": "/apply"
    }


def _is_did_you_mean_query(question: str) -> bool:
    """Check if user is asking for clarification about what they meant."""
    patterns = [
        "what loan do you think",
        "what do you think i'm talking about",
        "what am i talking about",
        "do you know what i mean",
        "what product am i asking about"
    ]
    
    question_lower = question.lower()
    return any(pattern in question_lower for pattern in patterns)


def _handle_did_you_mean(product_context: str, question: str) -> Dict[str, Any]:
    """Handle 'did you mean' clarification flows."""
    product_name = LOAN_PRODUCTS.get(product_context, {}).get("name", product_context)
    
    return {
        "empathy": f"Based on our conversation, it sounds like we've been discussing {product_name} options.",
        "clarification_needed": True,
        "quick_replies": [
            {"label": "Yes, that's right", "value": f"yes {product_context} loan"},
            {"label": "No, something else", "value": "no let me clarify"},
            {"label": "Show all options", "value": "show me all loan types"}
        ],
        "main_answer_prompt": f"Confirm if the user is asking about {product_name} and offer to help clarify if not.",
        "cta": None,
        "product_context": product_context
    }
