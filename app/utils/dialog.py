"""
Dialog utility functions for enhanced customer service.
"""

from typing import List, Dict, Any, Optional

# Loan requirement templates
LOAN_REQUIREMENTS = {
    "car": [
        "Valid driver's license",
        "Proof of income (last 2 pay stubs)",
        "Vehicle information (make, model, year)",
        "Down payment (typically 10-20%)",
        "Auto insurance quote"
    ],
    "auto": [
        "Valid driver's license",
        "Proof of income (last 2 pay stubs)",
        "Vehicle information (make, model, year)",
        "Down payment (typically 10-20%)",
        "Auto insurance quote"
    ],
    "home": [
        "Credit score of 620+ (varies by program)",
        "Proof of income (2 years tax returns, pay stubs)",
        "Employment verification",
        "Down payment (3-20% depending on loan type)",
        "Home appraisal",
        "Property inspection",
        "Homeowner's insurance"
    ],
    "mortgage": [
        "Credit score of 620+ (varies by program)",
        "Proof of income (2 years tax returns, pay stubs)",
        "Employment verification", 
        "Down payment (3-20% depending on loan type)",
        "Home appraisal",
        "Property inspection",
        "Homeowner's insurance"
    ],
    "business": [
        "Business plan and financial projections",
        "3 years of business tax returns",
        "Personal and business credit reports",
        "Bank statements (6-12 months)",
        "Collateral documentation",
        "Business license and registration"
    ],
    "commercial": [
        "Business plan and financial projections",
        "3 years of business tax returns", 
        "Personal and business credit reports",
        "Bank statements (6-12 months)",
        "Collateral documentation",
        "Business license and registration"
    ],
    "personal": [
        "Valid photo ID",
        "Proof of income (pay stubs or tax returns)",
        "Employment verification",
        "Bank statements (2-3 months)",
        "Credit score of 600+ (preferred)"
    ],
    "refinance": [
        "Current mortgage statement",
        "Home appraisal (if required)",
        "Proof of income (pay stubs, tax returns)",
        "Employment verification",
        "Homeowner's insurance policy",
        "Property tax statements"
    ]
}


def build_bullet_requirements(product: Optional[str]) -> str:
    """
    Build bullet list of requirements for a specific loan product.
    
    Args:
        product: Loan product type (car, home, business, etc.)
        
    Returns:
        Formatted bullet list string
    """
    if not product or product not in LOAN_REQUIREMENTS:
        return ""
    
    requirements = LOAN_REQUIREMENTS[product]
    bullet_list = "**Typical Requirements:**\n"
    
    for req in requirements:
        bullet_list += f"• {req}\n"
    
    bullet_list += "\n*Requirements may vary based on loan amount and creditworthiness.*"
    
    return bullet_list


def echo_prior_answers(memory: List[Dict[str, str]]) -> str:
    """
    Echo prior bot answers for context continuity.
    
    Args:
        memory: List of conversation turns with 'user' and 'bot' keys
        
    Returns:
        Formatted context echo string
    """
    if not memory or len(memory) == 0:
        return ""
    
    # Get the last bot response
    last_bot_response = None
    for turn in reversed(memory):
        if 'bot' in turn and turn['bot'].strip():
            last_bot_response = turn['bot']
            break
    
    if not last_bot_response:
        return ""
    
    # Truncate if too long
    if len(last_bot_response) > 150:
        last_bot_response = last_bot_response[:147] + "..."
    
    return f"**As we discussed:** {last_bot_response}\n\n"


def extract_product_from_memory(memory: List[Dict[str, str]]) -> Optional[str]:
    """
    Extract product context from conversation memory.
    
    Args:
        memory: List of conversation turns
        
    Returns:
        Detected product type or None
    """
    if not memory:
        return None
    
    # Look through recent conversations for product mentions
    for turn in reversed(memory[-3:]):  # Check last 3 turns
        user_text = turn.get('user', '').lower()
        bot_text = turn.get('bot', '').lower()
        
        combined_text = f"{user_text} {bot_text}"
        
        # Check for direct product mentions
        for product in LOAN_REQUIREMENTS.keys():
            if product in combined_text:
                return product
        
        # Check for related terms
        if any(term in combined_text for term in ['car', 'auto', 'vehicle']):
            return 'car'
        elif any(term in combined_text for term in ['home', 'house', 'mortgage']):
            return 'home'
        elif any(term in combined_text for term in ['business', 'commercial']):
            return 'business'
    
    return None


def format_cta_in_response(cta: Optional[Dict[str, str]], response_text: str) -> str:
    """
    Format CTA into response text.
    
    Args:
        cta: CTA dictionary with label and url
        response_text: Current response text
        
    Returns:
        Response text with CTA formatting
    """
    if not cta:
        return response_text
    
    # Add CTA as a formatted line
    cta_line = f"\n\n**Next Step:** {cta['label']}"
    
    return response_text + cta_line


def detect_conversation_stage(memory: List[Dict[str, str]]) -> str:
    """
    Detect what stage of the conversation we're in.
    
    Args:
        memory: Conversation history
        
    Returns:
        Stage: 'initial', 'exploring', 'qualifying', 'ready'
    """
    if not memory or len(memory) <= 1:
        return 'initial'
    
    # Count bot responses about requirements/details
    detail_responses = 0
    for turn in memory:
        bot_text = turn.get('bot', '').lower()
        if any(term in bot_text for term in ['requirement', 'document', 'credit', 'income']):
            detail_responses += 1
    
    if detail_responses >= 2:
        return 'ready'
    elif detail_responses >= 1:
        return 'qualifying'
    elif len(memory) >= 2:
        return 'exploring'
    else:
        return 'initial'


def get_contextual_suggestions(product: Optional[str], stage: str) -> List[Dict[str, str]]:
    """
    Get contextual quick reply suggestions based on product and conversation stage.
    
    Args:
        product: Current product context
        stage: Conversation stage
        
    Returns:
        List of suggestion dictionaries
    """
    base_suggestions = [
        {"label": "View Requirements", "value": f"what do I need for {product or 'a'} loan"},
        {"label": "Check Rates", "value": f"what are your {product or ''} loan rates"},
        {"label": "Start Application", "value": "I want to apply now"}
    ]
    
    if stage == 'initial':
        return [
            {"label": "Auto Loans", "value": "tell me about auto loans"},
            {"label": "Home Loans", "value": "tell me about home loans"}, 
            {"label": "Business Loans", "value": "tell me about business loans"}
        ]
    elif stage == 'exploring':
        return base_suggestions
    elif stage == 'qualifying':
        return [
            {"label": "Document List", "value": "what documents do I need"},
            {"label": "Pre-qualification", "value": "can I get pre-qualified"},
            {"label": "Timeline", "value": "how long does approval take"}
        ]
    else:  # ready
        return [
            {"label": "Apply Now", "value": "start my application"},
            {"label": "Speak to Advisor", "value": "connect me with a loan advisor"},
            {"label": "Calculate Payment", "value": "help me calculate payments"}
        ]
