"""JSON serialization utilities."""

from typing import Any, Optional
from datetime import datetime
from decimal import Decimal
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder


def safe_json_response(
    obj: Any,
    status_code: int = 200,
    headers: Optional[dict] = None
) -> JSONResponse:
    """
    Safely serialize any object to JSON response, handling special types.
    
    Args:
        obj: Object to serialize
        status_code: HTTP status code
        headers: Optional response headers
    
    Returns:
        FastAPI JSONResponse with safely serialized content
    """
    # Pre-process known problematic types
    if isinstance(obj, dict):
        obj = {
            k: v.isoformat() if isinstance(v, datetime)
            else str(v) if isinstance(v, Decimal)
            else v
            for k, v in obj.items()
        }
    
    # Use FastAPI's encoder with fallback to str
    encoded = jsonable_encoder(obj, custom_encoder={
        datetime: lambda v: v.isoformat(),
        Decimal: str
    })
    
    return JSONResponse(
        content=encoded,
        status_code=status_code,
        headers=headers
    ) 