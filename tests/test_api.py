"""Tests for FastAPI endpoints."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.schemas import LoanRequest, LoginRequest


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Mock authentication headers."""
    return {"Authorization": "Bearer test_token"}


@pytest.fixture
def mock_customer_data():
    """Mock customer data."""
    return {
        "client_id": 1001,
        "annual_income": 50.0,
        "risk_grade": "B",
        "education_level": 2,
        "family_size": 2,
        "credit_card_with_bank": 1
    }


class TestRootEndpoints:
    """Test root and health endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["version"] == "1.0.0"
    
    @patch('app.api.main.check_database_health')
    @patch('app.api.main.check_vector_store_health')
    @patch('app.api.main.check_market_data_health')
    def test_health_endpoint_healthy(
        self, mock_market_health, mock_vector_health, mock_db_health, client
    ):
        """Test health endpoint with all services healthy."""
        # Mock all services as healthy
        mock_db_health.return_value = {"connected": True}
        mock_vector_health.return_value = {"connected": True}
        mock_market_health.return_value = {"metrics_available": 3}
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["database"] == "connected"
        assert data["vector_store"] == "connected"
        assert data["market_data"] == "available"
    
    @patch('app.api.main.check_database_health')
    @patch('app.api.main.check_vector_store_health')
    @patch('app.api.main.check_market_data_health')
    def test_health_endpoint_degraded(
        self, mock_market_health, mock_vector_health, mock_db_health, client
    ):
        """Test health endpoint with degraded services."""
        # Mock database as disconnected
        mock_db_health.return_value = {"connected": False}
        mock_vector_health.return_value = {"connected": True}
        mock_market_health.return_value = {"metrics_available": 3}
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
    
    def test_workflow_info_endpoint(self, client):
        """Test workflow info endpoint."""
        with patch('app.api.main.get_workflow_info') as mock_info:
            mock_info.return_value = {
                "nodes": ["auth", "risk_gate", "market", "score", "decision", "policy_rag", "explain", "end"],
                "entry_point": "auth",
                "llm_nodes": ["explain"],
                "deterministic_nodes": ["auth", "risk_gate", "market", "score", "decision", "end"]
            }
            
            response = client.get("/workflow/info")
            
            assert response.status_code == 200
            data = response.json()
            assert "nodes" in data
            assert "entry_point" in data
            assert data["entry_point"] == "auth"
            assert "explain" in data["llm_nodes"]


class TestAuthEndpoints:
    """Test authentication endpoints."""
    
    @patch('app.api.auth.verify_user')
    @patch('app.api.auth.create_jwt')
    def test_login_success(self, mock_create_jwt, mock_verify_user, client):
        """Test successful login."""
        # Mock successful verification
        mock_verify_user.return_value = True
        mock_create_jwt.side_effect = ["access_token_123", "refresh_token_456"]
        
        login_data = {
            "user_id": "1001",
            "password": "password1001"
        }
        
        response = client.post("/v1/auth/login", json=login_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "access_token_123"
        assert data["refresh_token"] == "refresh_token_456"
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
    
    @patch('app.api.auth.verify_user')
    def test_login_invalid_credentials(self, mock_verify_user, client):
        """Test login with invalid credentials."""
        # Mock failed verification
        mock_verify_user.return_value = False
        
        login_data = {
            "user_id": "1001",
            "password": "wrong_password"
        }
        
        response = client.post("/v1/auth/login", json=login_data)
        
        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "HTTP_401"
        assert "Invalid user ID or password" in data["message"]
    
    def test_login_invalid_format(self, client):
        """Test login with invalid request format."""
        # Missing password
        login_data = {"user_id": "1001"}
        
        response = client.post("/v1/auth/login", json=login_data)
        
        assert response.status_code == 422  # Validation error
    
    @patch('app.api.auth.decode_jwt')
    @patch('app.api.auth.create_jwt')
    def test_refresh_token_success(self, mock_create_jwt, mock_decode_jwt, client):
        """Test successful token refresh."""
        # Mock valid refresh token
        mock_decode_jwt.return_value = {"sub": 1001}
        mock_create_jwt.side_effect = ["new_access_token", "new_refresh_token"]
        
        refresh_data = {"refresh_token": "valid_refresh_token"}
        
        response = client.post("/v1/auth/refresh", json=refresh_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new_access_token"
        assert data["refresh_token"] == "new_refresh_token"
    
    @patch('app.api.auth.decode_jwt')
    def test_refresh_token_invalid(self, mock_decode_jwt, client):
        """Test refresh with invalid token."""
        # Mock invalid token
        mock_decode_jwt.side_effect = Exception("Invalid token")
        
        refresh_data = {"refresh_token": "invalid_token"}
        
        response = client.post("/v1/auth/refresh", json=refresh_data)
        
        assert response.status_code == 401
        data = response.json()
        assert "Invalid or expired refresh token" in data["message"]
    
    def test_logout(self, client):
        """Test logout endpoint."""
        response = client.post("/v1/auth/logout")
        
        assert response.status_code == 200
        data = response.json()
        assert "Successfully logged out" in data["message"]
    
    @patch('app.api.deps.decode_jwt')
    @patch('app.api.deps.get_db_session')
    def test_get_user_info(self, mock_db_session, mock_decode_jwt, client, mock_customer_data):
        """Test get current user info."""
        # Mock JWT decoding
        mock_decode_jwt.return_value = {"sub": 1001}
        
        # Mock database
        mock_db = MagicMock()
        mock_customer = Mock()
        mock_customer.risk_grade = "B"
        mock_customer.education_level = 2
        mock_customer.family_size = 2
        mock_customer.credit_card_with_bank = 1
        mock_customer.digital_user = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_customer
        mock_db_session.return_value.__enter__.return_value = mock_db
        
        headers = {"Authorization": "Bearer valid_token"}
        response = client.get("/v1/auth/me", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 1001
        assert data["risk_grade"] == "B"
        assert data["education_level"] == 2


class TestLoanEndpoints:
    """Test loan decision endpoints."""
    
    @patch('app.api.deps.get_current_user')
    @patch('app.api.deps.validate_user_exists')
    @patch('app.api.loan.generate_answer')
    def test_loan_decision_success(
        self, mock_generate_answer, mock_validate_user, mock_get_user, client
    ):
        """Test successful loan decision."""
        # Mock authentication
        mock_get_user.return_value = 1001
        mock_validate_user.return_value = 1001
        
        # Mock workflow response
        mock_generate_answer.return_value = (
            "Decision: APPROVE. Your application meets our criteria...",
            {
                "req_id": "REQ-ABC123",
                "decision": "APPROVE",
                "score": 0.75,
                "reason_codes": ["Strong financial profile"],
                "market_stale": False,
                "success": True
            }
        )
        
        loan_request = {"question": "Can I get a personal loan?"}
        headers = {"Authorization": "Bearer valid_token"}
        
        response = client.post("/v1/loan/decision", json=loan_request, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "APPROVE"
        assert data["score"] == 0.75
        assert data["reasons"] == ["Strong financial profile"]
        assert "Your application meets our criteria" in data["explanation"]
        assert data["request_id"] == "REQ-ABC123"
        assert data["market_stale"] is False
        assert "processing_time_ms" in data
    
    @patch('app.api.deps.get_current_user')
    @patch('app.api.deps.validate_user_exists')
    @patch('app.api.loan.generate_answer')
    def test_loan_decision_decline(
        self, mock_generate_answer, mock_validate_user, mock_get_user, client
    ):
        """Test loan decision decline."""
        # Mock authentication
        mock_get_user.return_value = 1001
        mock_validate_user.return_value = 1001
        
        # Mock workflow response
        mock_generate_answer.return_value = (
            "Decision: DECLINE. Your application does not meet our current criteria...",
            {
                "req_id": "REQ-DEF456",
                "decision": "DECLINE",
                "score": 0.25,
                "reason_codes": ["High risk score", "Low income"],
                "market_stale": False,
                "success": True
            }
        )
        
        loan_request = {"question": "I need a loan urgently"}
        headers = {"Authorization": "Bearer valid_token"}
        
        response = client.post("/v1/loan/decision", json=loan_request, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "DECLINE"
        assert data["score"] == 0.25
        assert "High risk score" in data["reasons"]
        assert "Low income" in data["reasons"]
    
    def test_loan_decision_unauthorized(self, client):
        """Test loan decision without authentication."""
        loan_request = {"question": "Can I get a personal loan?"}
        
        response = client.post("/v1/loan/decision", json=loan_request)
        
        assert response.status_code == 401
    
    def test_loan_decision_invalid_request(self, client):
        """Test loan decision with invalid request."""
        # Empty question
        loan_request = {"question": ""}
        headers = {"Authorization": "Bearer valid_token"}
        
        response = client.post("/v1/loan/decision", json=loan_request, headers=headers)
        
        assert response.status_code == 422  # Validation error
    
    @patch('app.api.deps.get_current_user')
    @patch('app.api.deps.get_db_session')
    def test_loan_decision_stream(
        self, mock_run_workflow, mock_validate_user, mock_get_user, client
    ):
        """Test streaming loan decision."""
        # Mock authentication
        mock_get_user.return_value = 1001
        mock_validate_user.return_value = 1001
        
        # Mock workflow response
        mock_run_workflow.return_value = {
            "req_id": "REQ-STREAM123",
            "decision": "COUNTER",
            "score": 0.55,
            "reason_codes": ["Moderate risk factors"],
            "market_stale": False,
            "final_answer": "Decision: COUNTER. We can offer you a loan with modified terms."
        }
        
        loan_request = {"question": "What loan options do I have?"}
        headers = {"Authorization": "Bearer valid_token"}
        
        response = client.post("/v1/loan/decision/stream", json=loan_request, headers=headers)
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        
        # Check that response is streaming
        content = response.text
        assert "data:" in content
        assert "COUNTER" in content or "Decision" in content
    
    @patch('app.api.deps.get_current_user')
    @patch('app.api.deps.get_db_session')
    def test_loan_history(self, mock_db_session, mock_get_user, client):
        """Test loan decision history."""
        # Mock authentication
        mock_get_user.return_value = 1001
        
        # Mock database
        mock_db = MagicMock()
        mock_entry = Mock()
        mock_entry.req_id = "REQ-HIST001"
        mock_entry.ts.isoformat.return_value = "2024-01-01T12:00:00"
        mock_entry.state = {
            "decision": "APPROVE",
            "score": 0.8,
            "reason_codes": ["Strong profile"],
            "market_stale": False
        }
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_entry]
        mock_db_session.return_value.__enter__.return_value = mock_db
        
        headers = {"Authorization": "Bearer valid_token"}
        response = client.get("/v1/loan/history", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 1001
        assert len(data["history"]) == 1
        assert data["history"][0]["decision"] == "APPROVE"
        assert data["history"][0]["score"] == 0.8
    
    @patch('app.api.loan.get_workflow_info')
    @patch('app.api.loan.check_database_health')
    @patch('app.api.loan.check_vector_store_health')
    @patch('app.api.loan.check_market_data_health')
    def test_loan_service_status(
        self, mock_market_health, mock_vector_health, mock_db_health, mock_workflow_info, client
    ):
        """Test loan service status."""
        # Mock dependencies
        mock_workflow_info.return_value = {
            "nodes": ["auth", "explain"],
            "llm_nodes": ["explain"],
            "deterministic_nodes": ["auth"]
        }
        mock_db_health.return_value = {"connected": True}
        mock_vector_health.return_value = {"connected": True}
        mock_market_health.return_value = {"metrics_available": 3}
        
        response = client.get("/v1/loan/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "workflow" in data
        assert "dependencies" in data


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_404_endpoint(self, client):
        """Test non-existent endpoint."""
        response = client.get("/nonexistent")
        
        assert response.status_code == 404
    
    def test_method_not_allowed(self, client):
        """Test wrong HTTP method."""
        response = client.get("/v1/auth/login")  # Should be POST
        
        assert response.status_code == 405
    
    def test_request_too_large(self, client):
        """Test request size validation."""
        # Create a large payload
        large_question = "x" * (1024 * 1024 + 1)  # Larger than 1MB
        loan_request = {"question": large_question}
        
        response = client.post("/v1/loan/decision", json=loan_request)
        
        # Should be caught by middleware before reaching the endpoint
        assert response.status_code in [413, 422]  # Request too large or validation error
    
    @patch('app.api.loan.generate_answer')
    @patch('app.api.deps.get_current_user')
    @patch('app.api.deps.validate_user_exists')
    def test_internal_server_error(
        self, mock_validate_user, mock_get_user, mock_generate_answer, client
    ):
        """Test internal server error handling."""
        # Mock authentication
        mock_get_user.return_value = 1001
        mock_validate_user.return_value = 1001
        
        # Mock workflow failure
        mock_generate_answer.side_effect = Exception("Workflow failed")
        
        loan_request = {"question": "Can I get a loan?"}
        headers = {"Authorization": "Bearer valid_token"}
        
        response = client.post("/v1/loan/decision", json=loan_request, headers=headers)
        
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "INTERNAL_SERVER_ERROR"
        assert "request_id" in data


class TestMiddleware:
    """Test middleware functionality."""
    
    def test_request_id_header(self, client):
        """Test request ID tracking."""
        response = client.get("/")
        
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"].startswith("REQ-")
    
    def test_custom_request_id(self, client):
        """Test custom request ID header."""
        custom_id = "CUSTOM-REQ-123"
        headers = {"X-Request-ID": custom_id}
        
        response = client.get("/", headers=headers)
        
        assert response.headers["X-Request-ID"] == custom_id
    
    def test_processing_time_header(self, client):
        """Test processing time tracking."""
        response = client.get("/")
        
        assert "X-Processing-Time" in response.headers
        processing_time = response.headers["X-Processing-Time"]
        assert processing_time.endswith("s")
        assert float(processing_time[:-1]) >= 0
    
    def test_security_headers(self, client):
        """Test security headers."""
        response = client.get("/")
        
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block" 