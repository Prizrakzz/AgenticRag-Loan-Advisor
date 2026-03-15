"""Authentication endpoints for JWT token management."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from .schemas import LoginRequest, TokenResponse, RefreshRequest, ErrorResponse
from .deps import get_db, get_request_id, log_request_context
from ..utils.auth import verify_user, create_jwt, decode_jwt
from ..utils.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/auth", tags=["Authentication"])

# Security scheme for refresh token
security = HTTPBearer()


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="User login",
    description="Authenticate user with credentials and return JWT tokens"
)
async def login(
    request: LoginRequest,
    req_request: Request,
    request_id: str = Depends(get_request_id),
    _: None = Depends(log_request_context)
):
    """
    Authenticate user and return access + refresh tokens.
    
    Args:
        request: Login request with user_id and password
        req_request: FastAPI request object
        request_id: Request ID for tracking
    
    Returns:
        JWT tokens with expiration info
    
    Raises:
        HTTPException: On authentication failure
    """
    logger.info(
        "login_attempt",
        user_id=request.user_id,
        request_id=request_id
    )
    
    # DEBUG: Log incoming request details
    logger.debug(
        "login_debug_request",
        user_id=request.user_id,
        password_length=len(request.password),
        password_preview=request.password[:3] + "***" if len(request.password) > 3 else "***",
        request_id=request_id
    )
    
    try:
        # Verify user credentials
        verification_result = verify_user(request.user_id, request.password)
        
        # DEBUG: Log verification result
        logger.debug(
            "login_debug_verification",
            user_id=request.user_id,
            verification_result=verification_result,
            expected_password=f"password{request.user_id}",
            request_id=request_id
        )
        
        if not verification_result:
            logger.warning(
                "login_failed_invalid_credentials",
                user_id=request.user_id,
                request_id=request_id,
                user_agent=req_request.headers.get("user-agent", "unknown")
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID or password"
            )
        
        # Convert user_id to integer for JWT
        user_id_int = int(request.user_id)
        
        # Create access token (15 minutes)
        access_token_expires = settings.auth.access_token_expire_minutes
        access_token = create_jwt(
            sub=user_id_int,
            exp_minutes=access_token_expires
        )
        
        # Create refresh token (7 days)
        refresh_token_expires = 7 * 24 * 60  # 7 days in minutes
        refresh_token = create_jwt(
            sub=user_id_int,
            exp_minutes=refresh_token_expires
        )
        
        logger.info(
            "login_successful",
            user_id=user_id_int,
            request_id=request_id,
            access_expires_minutes=access_token_expires,
            refresh_expires_minutes=refresh_token_expires
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=access_token_expires * 60  # Convert to seconds
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
        
    except ValueError as e:
        # Handle invalid user_id format
        logger.warning(
            "login_failed_invalid_user_id",
            user_id=request.user_id,
            request_id=request_id,
            error=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
        
    except Exception as e:
        # Handle unexpected errors
        logger.error(
            "login_failed_system_error",
            user_id=request.user_id,
            request_id=request_id,
            error=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication system temporarily unavailable"
        )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Invalid or expired refresh token"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Refresh access token",
    description="Use refresh token to get new access and refresh tokens"
)
async def refresh_token(
    request: RefreshRequest,
    req_request: Request,
    request_id: str = Depends(get_request_id),
    _: None = Depends(log_request_context)
):
    """
    Refresh access token using valid refresh token.
    
    Args:
        request: Refresh request with refresh token
        req_request: FastAPI request object
        request_id: Request ID for tracking
    
    Returns:
        New JWT tokens with expiration info
    
    Raises:
        HTTPException: On token validation failure
    """
    logger.info(
        "token_refresh_attempt",
        request_id=request_id
    )
    
    try:
        # Decode and validate refresh token
        payload = decode_jwt(request.refresh_token)
        user_id = payload.get("sub")
        
        if not user_id:
            raise ValueError("Invalid token payload: missing user ID")
        
        # Create new access token (15 minutes)
        access_token_expires = settings.auth.access_token_expire_minutes
        access_token = create_jwt(
            sub=user_id,
            exp_minutes=access_token_expires
        )
        
        # Create new refresh token (7 days)
        refresh_token_expires = 7 * 24 * 60  # 7 days in minutes
        new_refresh_token = create_jwt(
            sub=user_id,
            exp_minutes=refresh_token_expires
        )
        
        logger.info(
            "token_refresh_successful",
            user_id=user_id,
            request_id=request_id,
            access_expires_minutes=access_token_expires
        )
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=access_token_expires * 60  # Convert to seconds
        )
        
    except Exception as e:
        # Handle token validation or system errors
        logger.warning(
            "token_refresh_failed",
            request_id=request_id,
            error=str(e),
            user_agent=req_request.headers.get("user-agent", "unknown")
        )
        
        # Don't leak specific error details for security
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )


@router.post(
    "/logout",
    responses={
        200: {"description": "Successfully logged out"},
        401: {"model": ErrorResponse, "description": "Invalid token"}
    },
    summary="User logout",
    description="Logout user (token invalidation would require token blacklist)"
)
async def logout(
    req_request: Request,
    request_id: str = Depends(get_request_id),
    _: None = Depends(log_request_context)
):
    """
    Logout user.
    
    Note: In a production system, this would typically involve:
    1. Adding the token to a blacklist/revocation list
    2. Clearing any server-side session data
    3. Potentially notifying other services
    
    For this MVP, we'll just log the logout event since we're using stateless JWTs.
    The client should discard the tokens on their side.
    
    Args:
        req_request: FastAPI request object
        request_id: Request ID for tracking
    
    Returns:
        Success message
    """
    # In a production system, you would:
    # 1. Extract the token from the Authorization header
    # 2. Add it to a token blacklist (Redis, database, etc.)
    # 3. Set appropriate cache headers
    
    logger.info(
        "user_logout",
        request_id=request_id,
        user_agent=req_request.headers.get("user-agent", "unknown")
    )
    
    return {
        "message": "Successfully logged out",
        "note": "Please discard your tokens on the client side"
    }


@router.get(
    "/me",
    responses={
        200: {"description": "User information"},
        401: {"model": ErrorResponse, "description": "Authentication required"}
    },
    summary="Get current user info",
    description="Get information about the currently authenticated user"
)
async def get_current_user_info(
    req_request: Request,
    user_id: int = Depends(lambda req, creds=Depends(security): decode_jwt(creds.credentials)["sub"]),
    request_id: str = Depends(get_request_id),
    db: Session = Depends(get_db)
):
    """
    Get current user information.
    
    Args:
        req_request: FastAPI request object
        user_id: Authenticated user ID
        request_id: Request ID for tracking
        db: Database session
    
    Returns:
        User information (non-sensitive fields only)
    """
    try:
        from ..db.models import Customer
        
        customer = db.query(Customer).filter(Customer.client_id == user_id).first()
        
        if not customer:
            logger.warning(
                "user_info_not_found",
                user_id=user_id,
                request_id=request_id
            )
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User information not found"
            )
        
        # Return non-sensitive user information
        user_info = {
            "user_id": user_id,
            "risk_grade": customer.risk_grade,
            "education_level": customer.education_level,
            "family_size": customer.family_size,
            "has_credit_card": bool(customer.credit_card_with_bank),
            "digital_user": bool(customer.digital_user),
            "request_id": request_id
        }
        
        logger.info(
            "user_info_retrieved",
            user_id=user_id,
            request_id=request_id
        )
        
        return user_info
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(
            "user_info_failed",
            user_id=user_id,
            request_id=request_id,
            error=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve user information"
        ) 