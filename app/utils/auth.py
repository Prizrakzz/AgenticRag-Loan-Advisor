"""JWT authentication utilities for the loan approval system."""

import jwt
from datetime import datetime, timedelta
from typing import Dict, Optional
from fastapi import HTTPException, status

from .config import settings
from .logger import get_logger

logger = get_logger(__name__)


# ── password hashing ─────────────────────────────────────────────
import hashlib, hmac, os as _os

_HASH_ITERATIONS = 260_000
_HASH_ALGO = "sha256"


def _hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Return (salt, dk) using PBKDF2."""
    if salt is None:
        salt = _os.urandom(16)
    dk = hashlib.pbkdf2_hmac(_HASH_ALGO, password.encode(), salt, _HASH_ITERATIONS)
    return salt, dk


def _verify_password(password: str, salt: bytes, expected_dk: bytes) -> bool:
    _, dk = _hash_password(password, salt)
    return hmac.compare_digest(dk, expected_dk)


# In-memory credential store (loaded once at import time from DB).
# For a real deployment swap this with a proper DB-backed lookup.
_CREDENTIALS: dict[int, tuple[bytes, bytes]] = {}   # user_id → (salt, dk)


def _ensure_credentials_loaded() -> None:
    """Lazily load / bootstrap the credentials table."""
    if _CREDENTIALS:
        return
    try:
        from ..db.database import get_db_session
        from ..db.models import Customer
        with get_db_session() as db:
            for c in db.query(Customer).all():
                cid = c.client_id
                # Bootstrap: hash a per-user default password for demo purposes.
                # In production, users would set their own passwords.
                salt, dk = _hash_password(f"password{cid}")
                _CREDENTIALS[cid] = (salt, dk)
    except Exception as exc:
        logger.warning("credential_bootstrap_failed", error=str(exc))


def verify_user(user_id: str, password: str) -> bool:
    """
    Verify user credentials using PBKDF2 hashed passwords.

    Args:
        user_id: User ID as string
        password: Password to verify

    Returns:
        True if credentials are valid, False otherwise
    """
    try:
        id_int = int(user_id)

        logger.info("login_attempt", user_id=user_id)

        _ensure_credentials_loaded()

        creds = _CREDENTIALS.get(id_int)
        if creds is None:
            logger.warning("login_failure", user_id=user_id, reason="unknown_user")
            return False

        salt, expected_dk = creds
        is_valid = _verify_password(password, salt, expected_dk)

        if is_valid:
            logger.info("login_success", user_id=user_id)
        else:
            logger.warning("login_failure", user_id=user_id, reason="invalid_credentials")

        return is_valid

    except ValueError:
        logger.warning("login_failure", user_id=user_id, reason="invalid_user_id_format")
        return False
    except Exception as e:
        logger.error("login_error", user_id=user_id, error=str(e))
        return False


def create_jwt(sub: int, exp_minutes: int = None) -> str:
    """
    Create JWT token for authenticated user.
    
    Args:
        sub: User ID (subject)
        exp_minutes: Token expiration in minutes (default from settings)
    
    Returns:
        JWT token string
    
    Raises:
        HTTPException: If token creation fails
    """
    try:
        if exp_minutes is None:
            exp_minutes = settings.auth.access_token_expire_minutes
        
        # Create token payload
        now = datetime.utcnow()
        expire = now + timedelta(minutes=exp_minutes)
        
        payload = {
            "sub": str(sub),  # Subject (user ID)
            "exp": expire,    # Expiration
            "iat": now,       # Issued at
        }
        
        # Encode JWT
        token = jwt.encode(
            payload,
            settings.auth.secret_key,
            algorithm=settings.auth.algorithm
        )
        
        logger.info(
            "jwt_created",
            user_id=sub,
            expires_at=expire.isoformat()
        )
        
        return token
        
    except Exception as e:
        logger.error("jwt_creation_failed", user_id=sub, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create access token"
        )


def decode_jwt(token: str) -> Dict[str, str]:
    """
    Decode and validate JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token payload
    
    Raises:
        HTTPException: If token is invalid or expired (HTTP 401)
    """
    try:
        # Decode JWT
        payload = jwt.decode(
            token,
            settings.auth.secret_key,
            algorithms=[settings.auth.algorithm]
        )
        
        # Extract user ID
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject"
            )
        
        logger.debug(
            "jwt_decoded",
            user_id=user_id,
            token_preview=token[:20] + "..." if len(token) > 20 else "short_token"
        )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.warning(
            "jwt_expired",
            token_preview=token[:20] + "..." if len(token) > 20 else "short_token"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        logger.warning(
            "jwt_invalid",
            error=str(e),
            token_preview=token[:20] + "..." if len(token) > 20 else "short_token"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    except Exception as e:
        logger.error(
            "jwt_decode_error",
            error=str(e),
            token_preview=token[:20] + "..." if len(token) > 20 else "short_token"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )


def get_user_id_from_token(token: str) -> int:
    """
    Extract user ID from JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        User ID as integer
    
    Raises:
        HTTPException: If token is invalid or user ID cannot be extracted
    """
    payload = decode_jwt(token)
    user_id_str = payload.get("sub")
    
    try:
        user_id = int(user_id_str)
        return user_id
    except (ValueError, TypeError):
        logger.error("invalid_user_id_in_token", user_id_str=user_id_str)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token"
        )


def mask_token_for_logging(token: str) -> str:
    """
    Mask JWT token for safe logging.
    
    Args:
        token: JWT token string
    
    Returns:
        Masked token string for logging
    """
    if not token:
        return "empty_token"
    if len(token) <= 20:
        return "***masked***"
    return f"{token[:10]}...{token[-5:]}"


def create_login_response(user_id: int, token: str, exp_minutes: int) -> Dict[str, any]:
    """
    Create standardized login response.
    
    Args:
        user_id: Authenticated user ID
        token: JWT access token
        exp_minutes: Token expiration in minutes
    
    Returns:
        Login response dictionary
    """
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": exp_minutes * 60,  # Convert to seconds
        "user_id": user_id
    }


# Back-compat shims for legacy imports
def get_current_user(*args, **kwargs):
    """Back-compat shim. Import from app.api.deps instead."""
    from ..api.deps import get_current_user as _get_current_user
    return _get_current_user(*args, **kwargs)


# Aliases for common auth functions
create_access_token = create_jwt
decode_token = decode_jwt 