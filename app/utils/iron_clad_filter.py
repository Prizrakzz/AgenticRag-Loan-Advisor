"""Iron-clad content filtering for strict content validation."""

from .content_filter import contains_forbidden, get_filtered_response


def filter_content_strict(content: str, is_user_input: bool = False) -> str:
    """
    Apply strict content filtering to ensure compliance with banking guidelines.
    
    Args:
        content: Content to filter
        is_user_input: Whether the content is user input (not currently used)
        
    Returns:
        Filtered content (original if safe, fallback if forbidden content detected)
    """
    if not content:
        return content
    
    # Use existing content filtering logic
    return get_filtered_response(content)
