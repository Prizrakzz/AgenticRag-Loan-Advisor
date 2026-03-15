"""Content filtering utilities for LLM responses."""

import re
from typing import List

# Forbidden terms that should trigger content filtering
FORBIDDEN_TERMS = [
    # Religious terms
    "religion", "religious", "god", "allah", "jesus", "christ", "christian", "islam", "islamic", 
    "muslim", "judaism", "jewish", "hindu", "hinduism", "buddhism", "buddhist", "prayer", 
    "worship", "bible", "quran", "torah", "church", "mosque", "synagogue", "temple",
    
    # Political terms
    "politics", "political", "politician", "election", "vote", "voting", "democracy", 
    "republican", "democrat", "conservative", "liberal", "government", "president", 
    "prime minister", "congress", "parliament", "senate", "campaign", "party",
    
    # Sensitive topics
    "abortion", "euthanasia", "suicide", "terrorism", "genocide", "war crimes",
    "racial", "racist", "discrimination", "hate speech", "extremist", "radical"
]

# System prompt for Arab Bank Loan Advisor
SYSTEM_PROMPT_GUARDRAIL = """You are an assistant for Arab Bank's Loan Advisor. Under no circumstances should you discuss or provide content on religion, politics, or any other sensitive or inappropriate topics. Focus only on loan advisory, banking services, and financial guidance."""

def contains_forbidden(text: str) -> bool:
    """
    Check if text contains any forbidden terms.
    
    Args:
        text: Text to check for forbidden content
        
    Returns:
        True if forbidden content is detected, False otherwise
    """
    if not text:
        return False
    
    # Convert to lowercase for case-insensitive matching
    text_lower = text.lower()
    
    # Check for forbidden terms
    for term in FORBIDDEN_TERMS:
        # Use word boundary regex to avoid partial matches
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, text_lower):
            return True
    
    return False


def get_filtered_response(original_response: str) -> str:
    """
    Filter LLM response and return safe content.
    
    Args:
        original_response: Original LLM response
        
    Returns:
        Filtered response (original if safe, fallback if forbidden content detected)
    """
    if contains_forbidden(original_response):
        return "I'm sorry, but I can't assist with that."
    
    return original_response


def get_system_message() -> dict:
    """
    Get the standardized system message for LLM calls.
    
    Returns:
        System message dict for OpenAI chat completion
    """
    return {
        "role": "system",
        "content": SYSTEM_PROMPT_GUARDRAIL
    }
