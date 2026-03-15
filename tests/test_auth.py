"""Tests for authentication functionality."""

import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
import jwt

from app.utils.auth import (
    verify_user, create_jwt, decode_jwt, get_user_id_from_token,
    mask_token_for_logging, create_login_response
)
from app.utils.config import settings


class TestUserVerification:
    """Test hardcoded user verification."""
    
    def test_verify_user_valid_credentials(self):
        """Test successful user verification."""
        assert verify_user("101", "password101") is True
        assert verify_user("42", "password42") is True
        assert verify_user("1000", "password1000") is True
    
    def test_verify_user_invalid_password(self):
        """Test user verification with wrong password."""
        assert verify_user("101", "wrongpassword") is False
        assert verify_user("101", "password102") is False
        assert verify_user("101", "") is False
    
    def test_verify_user_invalid_user_id(self):
        """Test user verification with invalid user ID."""
        assert verify_user("abc", "passwordabc") is False
        assert verify_user("", "password") is False
        assert verify_user("101.5", "password101.5") is False
    
    def test_verify_user_edge_cases(self):
        """Test edge cases for user verification."""
        assert verify_user("0", "password0") is True
        assert verify_user("-1", "password-1") is True  # Negative IDs allowed


class TestJWTOperations:
    """Test JWT creation and validation."""
    
    def test_create_jwt_success(self):
        """Test successful JWT creation."""
        token = create_jwt(101, exp_minutes=60)
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are typically long
    
    def test_create_jwt_default_expiration(self):
        """Test JWT creation with default expiration."""
        token = create_jwt(101)
        payload = decode_jwt(token)
        assert payload["sub"] == "101"
    
    def test_decode_jwt_success(self):
        """Test successful JWT decoding."""
        token = create_jwt(101, exp_minutes=60)
        payload = decode_jwt(token)
        
        assert payload["sub"] == "101"
        assert "exp" in payload
        assert "iat" in payload
    
    def test_decode_jwt_expired(self):
        """Test JWT decoding with expired token."""
        # Create token that expires immediately
        past_time = datetime.utcnow() - timedelta(minutes=1)
        payload = {
            "sub": "101",
            "exp": past_time,
            "iat": past_time
        }
        
        expired_token = jwt.encode(
            payload,
            settings.auth.secret_key,
            algorithm=settings.auth.algorithm
        )
        
        with pytest.raises(HTTPException) as exc_info:
            decode_jwt(expired_token)
        
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()
    
    def test_decode_jwt_invalid_signature(self):
        """Test JWT decoding with invalid signature."""
        # Create token with wrong secret
        payload = {
            "sub": "101",
            "exp": datetime.utcnow() + timedelta(minutes=60)
        }
        
        invalid_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        
        with pytest.raises(HTTPException) as exc_info:
            decode_jwt(invalid_token)
        
        assert exc_info.value.status_code == 401
    
    def test_decode_jwt_malformed(self):
        """Test JWT decoding with malformed token."""
        with pytest.raises(HTTPException) as exc_info:
            decode_jwt("not.a.jwt")
        
        assert exc_info.value.status_code == 401
    
    def test_get_user_id_from_token(self):
        """Test extracting user ID from JWT token."""
        token = create_jwt(101)
        user_id = get_user_id_from_token(token)
        assert user_id == 101
    
    def test_get_user_id_from_token_invalid(self):
        """Test extracting user ID from invalid token."""
        with pytest.raises(HTTPException):
            get_user_id_from_token("invalid.token.here")


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_mask_token_for_logging(self):
        """Test token masking for safe logging."""
        long_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMDEifQ.signature"
        masked = mask_token_for_logging(long_token)
        
        assert "eyJhbGciOi" in masked  # First 10 chars
        assert "ature" in masked      # Last 5 chars
        assert "..." in masked        # Ellipsis
        assert len(masked) < len(long_token)
    
    def test_mask_token_short(self):
        """Test masking short tokens."""
        short_token = "short"
        masked = mask_token_for_logging(short_token)
        assert masked == "***masked***"
    
    def test_mask_token_empty(self):
        """Test masking empty token."""
        masked = mask_token_for_logging("")
        assert masked == "empty_token"
    
    def test_create_login_response(self):
        """Test login response creation."""
        token = "sample.jwt.token"
        response = create_login_response(101, token, 60)
        
        assert response["access_token"] == token
        assert response["token_type"] == "bearer"
        assert response["expires_in"] == 3600  # 60 minutes in seconds
        assert response["user_id"] == 101


class TestIntegrationScenarios:
    """Test complete authentication scenarios."""
    
    def test_successful_login_flow(self):
        """Test complete successful login flow."""
        # 1. Verify credentials
        assert verify_user("101", "password101") is True
        
        # 2. Create JWT
        token = create_jwt(101, exp_minutes=60)
        
        # 3. Validate JWT
        payload = decode_jwt(token)
        assert payload["sub"] == "101"
        
        # 4. Extract user ID
        user_id = get_user_id_from_token(token)
        assert user_id == 101
        
        # 5. Create response
        response = create_login_response(101, token, 60)
        assert response["user_id"] == 101
    
    def test_failed_login_flow(self):
        """Test failed login flow."""
        # 1. Invalid credentials
        assert verify_user("101", "wrongpassword") is False
        
        # No JWT should be created in this case
        # (This would be handled in the API layer)
    
    def test_token_expiration_flow(self):
        """Test token expiration handling."""
        # Create token with very short expiration
        token = create_jwt(101, exp_minutes=0)  # Expires immediately
        
        # Wait a moment and try to decode
        import time
        time.sleep(0.1)
        
        with pytest.raises(HTTPException) as exc_info:
            decode_jwt(token)
        
        assert exc_info.value.status_code == 401 