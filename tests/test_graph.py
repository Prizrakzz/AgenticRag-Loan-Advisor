"""Tests for LangGraph workflow functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from app.graph.state import State, new_state, generate_request_id, sanitize_state_for_logging
from app.graph.workflow import run_workflow_sync, generate_answer, get_workflow_info
from app.graph.nodes import (
    auth_node, risk_gate_node, market_node, score_node,
    decision_node, policy_rag_node, explain_node, end_node
)


@pytest.fixture
def mock_high_risk_customer():
    """High-risk customer fixture (Grade A - should be declined early)."""
    return {
        "client_id": 1001,
        "annual_income": 25.0,
        "risk_grade": "A",  # Grade A = highest risk = early decline
        "education_level": 1,
        "family_size": 4,
        "credit_card_with_bank": 0,
        "has_personal_loan": 0
    }


@pytest.fixture
def mock_medium_risk_customer():
    """Medium-risk customer fixture (Grade B/C - should go through full evaluation)."""
    return {
        "client_id": 1002,
        "annual_income": 45.0,
        "risk_grade": "B",  # Grade B = medium risk = full analysis
        "education_level": 2,
        "family_size": 2,
        "credit_card_with_bank": 1,
        "has_personal_loan": 0
    }


@pytest.fixture
def mock_low_risk_customer():
    """Low-risk customer fixture (Grade D - should be approved early)."""
    return {
        "client_id": 1003,
        "annual_income": 75.0,
        "risk_grade": "D",  # Grade D = lowest risk = early approve
        "education_level": 3,
        "family_size": 2,
        "credit_card_with_bank": 1,
        "has_personal_loan": 0
    }


@pytest.fixture
def mock_market_data():
    """Mock market data fixture."""
    return {
        "cbj_rate": {"value": 7.5, "asof": "2024-01-01T12:00:00Z"},
        "cpi_yoy": {"value": 3.2, "asof": "2024-01-01T12:00:00Z"},
        "re_price_index": {"value": 125.0, "asof": "2024-01-01T12:00:00Z"},
        "market_risk_score": {
            "value": 0.4,
            "asof": "2024-01-01T12:00:00Z",
            "extra": {
                "components": {
                    "cbj_risk": 0.5,
                    "cpi_risk": 0.3,
                    "re_risk": 0.2
                }
            }
        }
    }


@pytest.fixture
def mock_policy_snippets():
    """Mock policy snippets fixture."""
    return [
        {
            "section_id": "SEC-1.2",
            "page_start": 5,
            "page_end": 5,
            "text": "Loan applications with risk scores above 0.8 require additional documentation.",
            "score": 0.95
        },
        {
            "section_id": "SEC-2.1",
            "page_start": 12,
            "page_end": 13,
            "text": "Annual income requirements vary based on family size and market conditions.",
            "score": 0.87
        },
        {
            "section_id": "SEC-3.4",
            "page_start": 18,
            "page_end": 18,
            "text": "Existing banking relationships are considered positive factors in loan evaluation.",
            "score": 0.76
        }
    ]


class TestStateManagement:
    """Test state creation and management."""
    
    def test_new_state_creation(self):
        """Test creating a new state."""
        req_id = "TEST-REQ-001"
        user_id = 1001
        question = "Can I get a personal loan?"
        
        state = new_state(req_id, user_id, question)
        
        assert state["req_id"] == req_id
        assert state["user_id"] == user_id
        assert state["question"] == question
        assert state["client"] is None
        assert state["market"] is None
        assert state["market_stale"] is False
        assert state["decision"] is None
        assert state["reason_codes"] == []
        assert state["score"] is None
        assert state["policy_snippets"] == []
        assert state["final_answer"] is None
    
    def test_generate_request_id(self):
        """Test request ID generation."""
        req_id = generate_request_id()
        
        assert req_id.startswith("REQ-")
        assert len(req_id) == 16  # REQ- + 12 hex chars
        
        # Should be unique
        req_id2 = generate_request_id()
        assert req_id != req_id2
    
    def test_sanitize_state_for_logging(self):
        """Test state sanitization for logging."""
        state = new_state("TEST-001", 1001, "Test question")
        state["client"] = {
            "client_id": 1001,
            "annual_income": 50.0,
            "risk_score": 0.3,
            "sensitive_data": "secret"
        }
        state["final_answer"] = "This is a very long answer that should be truncated for logging purposes because it exceeds the preview length limit."
        
        sanitized = sanitize_state_for_logging(state)
        
        assert "req_id" in sanitized
        assert "user_id" in sanitized
        assert sanitized["client"]["client_id"] == 1001
        assert "sensitive_data" not in sanitized["client"]
        assert sanitized["final_answer_length"] == len(state["final_answer"])
        assert "final_answer_preview" in sanitized


class TestIndividualNodes:
    """Test individual workflow nodes."""
    
    @patch('app.graph.nodes.get_db_session')
    def test_auth_node_success(self, mock_db_session, mock_medium_risk_customer):
        """Test successful authentication node."""
        # Mock database query
        mock_db = MagicMock()
        mock_customer = Mock()
        mock_customer.to_dict.return_value = mock_medium_risk_customer
        mock_db.query.return_value.filter.return_value.first.return_value = mock_customer
        mock_db_session.return_value.__enter__.return_value = mock_db
        
        state = new_state("TEST-001", 1002, "Test question")
        result_state = auth_node(state)
        
        assert result_state["client"] == mock_medium_risk_customer
    
    @patch('app.graph.nodes.get_db_session')
    def test_auth_node_customer_not_found(self, mock_db_session):
        """Test authentication node when customer not found."""
        # Mock database query returning None
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db_session.return_value.__enter__.return_value = mock_db
        
        state = new_state("TEST-001", 9999, "Test question")
        result_state = auth_node(state)
        
        assert result_state["client"] is None
    
    def test_risk_gate_node_high_risk_decline(self, mock_high_risk_customer):
        """Test risk gate node with high-risk customer (early decline)."""
        state = new_state("TEST-001", 1001, "Test question")
        state["client"] = mock_high_risk_customer
        
        result_state = risk_gate_node(state)
        
        assert result_state["decision"] == "DECLINE"
        assert "High risk score" in result_state["reason_codes"]
    
    def test_risk_gate_node_low_risk_pass(self, mock_low_risk_customer):
        """Test risk gate node with low-risk customer (passes through)."""
        state = new_state("TEST-001", 1003, "Test question")
        state["client"] = mock_low_risk_customer
        
        result_state = risk_gate_node(state)
        
        assert result_state["decision"] is None  # No early decline
    
    @patch('app.graph.nodes.read_all_metrics')
    @patch('app.graph.nodes.is_metric_stale')
    def test_market_node_success(self, mock_is_stale, mock_read_metrics, mock_market_data):
        """Test market node with successful data loading."""
        mock_read_metrics.return_value = mock_market_data
        mock_is_stale.return_value = False
        
        state = new_state("TEST-001", 1002, "Test question")
        result_state = market_node(state)
        
        assert result_state["market"] == mock_market_data
        assert result_state["market_stale"] is False
    
    @patch('app.graph.nodes.read_all_metrics')
    def test_market_node_no_data(self, mock_read_metrics):
        """Test market node when no metrics available."""
        mock_read_metrics.return_value = {}
        
        state = new_state("TEST-001", 1002, "Test question")
        result_state = market_node(state)
        
        assert result_state["market"] == {}
        assert result_state["market_stale"] is True
    
    def test_score_node_calculation(self, mock_medium_risk_customer, mock_market_data):
        """Test score calculation node."""
        state = new_state("TEST-001", 1002, "Test question")
        state["client"] = mock_medium_risk_customer
        state["market"] = mock_market_data
        
        result_state = score_node(state)
        
        assert "score" in result_state
        assert 0.0 <= result_state["score"] <= 1.0
    
    def test_decision_node_approve(self, mock_low_risk_customer, mock_market_data):
        """Test decision node for approval case."""
        state = new_state("TEST-001", 1003, "Test question")
        state["client"] = mock_low_risk_customer
        state["market"] = mock_market_data
        state["score"] = 0.75  # High score
        
        result_state = decision_node(state)
        
        assert result_state["decision"] == "APPROVE"
        assert len(result_state["reason_codes"]) > 0
    
    def test_decision_node_decline(self, mock_high_risk_customer, mock_market_data):
        """Test decision node for decline case."""
        state = new_state("TEST-001", 1001, "Test question")
        state["client"] = mock_high_risk_customer
        state["market"] = mock_market_data
        state["score"] = 0.3  # Low score
        
        result_state = decision_node(state)
        
        assert result_state["decision"] == "DECLINE"
        assert len(result_state["reason_codes"]) > 0
    
    def test_decision_node_counter(self, mock_medium_risk_customer, mock_market_data):
        """Test decision node for counter-offer case."""
        state = new_state("TEST-001", 1002, "Test question")
        state["client"] = mock_medium_risk_customer
        state["market"] = mock_market_data
        state["score"] = 0.55  # Medium score
        
        result_state = decision_node(state)
        
        assert result_state["decision"] == "COUNTER"
        assert len(result_state["reason_codes"]) > 0
    
    @patch('app.graph.nodes.retrieve_policy_snippets')
    def test_policy_rag_node_success(self, mock_retrieve, mock_policy_snippets):
        """Test policy RAG node with successful retrieval."""
        mock_retrieve.return_value = mock_policy_snippets
        
        state = new_state("TEST-001", 1002, "Test question")
        state["decision"] = "DECLINE"
        state["reason_codes"] = ["High risk score"]
        
        result_state = policy_rag_node(state)
        
        assert result_state["policy_snippets"] == mock_policy_snippets
        mock_retrieve.assert_called_once_with(
            decision="DECLINE",
            reason_codes=["High risk score"],
            k=3
        )
    
    @patch('app.graph.nodes.openai.chat.completions.create')
    def test_explain_node_success(self, mock_openai):
        """Test explanation node with successful LLM call."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Decision: DECLINE. Based on your risk profile..."
        mock_openai.return_value = mock_response
        
        state = new_state("TEST-001", 1001, "Test question")
        state["decision"] = "DECLINE"
        state["score"] = 0.3
        state["reason_codes"] = ["High risk score"]
        state["policy_snippets"] = []
        
        result_state = explain_node(state)
        
        assert result_state["final_answer"] == "Decision: DECLINE. Based on your risk profile..."
        mock_openai.assert_called_once()
    
    @patch('app.graph.nodes.openai.chat.completions.create')
    def test_explain_node_failure_fallback(self, mock_openai):
        """Test explanation node with LLM failure and fallback."""
        # Mock OpenAI failure
        mock_openai.side_effect = Exception("API Error")
        
        state = new_state("TEST-001", 1001, "Test question")
        state["decision"] = "DECLINE"
        state["score"] = 0.3
        
        result_state = explain_node(state)
        
        assert "Decision: DECLINE" in result_state["final_answer"]
        assert "system error" in result_state["final_answer"].lower()
    
    def test_end_node(self):
        """Test end node."""
        state = new_state("TEST-001", 1001, "Test question")
        state["decision"] = "APPROVE"
        state["final_answer"] = "Test answer"
        
        result_state = end_node(state)
        
        # Should return the state unchanged
        assert result_state == state


class TestWorkflowIntegration:
    """Test complete workflow integration scenarios."""
    
    @patch('app.graph.nodes.get_db_session')
    @patch('app.graph.nodes.read_all_metrics')
    @patch('app.graph.nodes.is_metric_stale')
    @patch('app.graph.nodes.retrieve_policy_snippets')
    @patch('app.graph.nodes.openai.chat.completions.create')
    def test_high_risk_workflow_path(
        self, mock_openai, mock_retrieve, mock_is_stale, mock_read_metrics, mock_db_session,
        mock_high_risk_customer, mock_market_data, mock_policy_snippets
    ):
        """Test complete workflow for high-risk customer (early decline path)."""
        # Setup mocks
        self._setup_workflow_mocks(
            mock_db_session, mock_read_metrics, mock_is_stale, mock_retrieve, mock_openai,
            mock_high_risk_customer, mock_market_data, mock_policy_snippets
        )
        
        # Run workflow
        final_state = run_workflow_sync(
            question="Can I get a loan?",
            user_id=1001,
            req_id="TEST-HIGH-RISK"
        )
        
        # Assertions
        assert final_state["decision"] == "DECLINE"
        assert "High risk score" in final_state["reason_codes"]
        assert final_state["policy_snippets"] == mock_policy_snippets
        assert final_state["final_answer"] is not None
        
        # Should NOT have called market/score/decision nodes (early decline)
        mock_read_metrics.assert_not_called()
    
    @patch('app.graph.nodes.get_db_session')
    @patch('app.graph.nodes.read_all_metrics')
    @patch('app.graph.nodes.is_metric_stale')
    @patch('app.graph.nodes.retrieve_policy_snippets')
    @patch('app.graph.nodes.openai.chat.completions.create')
    def test_medium_risk_workflow_path(
        self, mock_openai, mock_retrieve, mock_is_stale, mock_read_metrics, mock_db_session,
        mock_medium_risk_customer, mock_market_data, mock_policy_snippets
    ):
        """Test complete workflow for medium-risk customer (full evaluation path)."""
        # Setup mocks
        self._setup_workflow_mocks(
            mock_db_session, mock_read_metrics, mock_is_stale, mock_retrieve, mock_openai,
            mock_medium_risk_customer, mock_market_data, mock_policy_snippets
        )
        
        # Run workflow
        final_state = run_workflow_sync(
            question="What are my loan options?",
            user_id=1002,
            req_id="TEST-MEDIUM-RISK"
        )
        
        # Assertions
        assert final_state["decision"] in ["APPROVE", "COUNTER", "DECLINE"]
        assert final_state["score"] is not None
        assert 0.0 <= final_state["score"] <= 1.0
        assert final_state["market"] == mock_market_data
        assert final_state["policy_snippets"] == mock_policy_snippets
        assert final_state["final_answer"] is not None
        
        # Should have called all nodes
        mock_read_metrics.assert_called_once()
    
    @patch('app.graph.nodes.get_db_session')
    @patch('app.graph.nodes.read_all_metrics')
    @patch('app.graph.nodes.is_metric_stale')
    @patch('app.graph.nodes.retrieve_policy_snippets')
    @patch('app.graph.nodes.openai.chat.completions.create')
    def test_low_risk_workflow_path(
        self, mock_openai, mock_retrieve, mock_is_stale, mock_read_metrics, mock_db_session,
        mock_low_risk_customer, mock_market_data, mock_policy_snippets
    ):
        """Test complete workflow for low-risk customer (approval path)."""
        # Setup mocks
        self._setup_workflow_mocks(
            mock_db_session, mock_read_metrics, mock_is_stale, mock_retrieve, mock_openai,
            mock_low_risk_customer, mock_market_data, mock_policy_snippets
        )
        
        # Run workflow
        final_state = run_workflow_sync(
            question="I'd like to apply for a personal loan",
            user_id=1003,
            req_id="TEST-LOW-RISK"
        )
        
        # Assertions
        assert final_state["decision"] in ["APPROVE", "COUNTER"]  # Should not be declined
        assert final_state["score"] is not None
        assert final_state["score"] > 0.5  # Should have decent score
        assert final_state["final_answer"] is not None
    
    @patch('app.graph.nodes.get_db_session')
    def test_workflow_customer_not_found(self, mock_db_session):
        """Test workflow when customer is not found."""
        # Mock customer not found
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db_session.return_value.__enter__.return_value = mock_db
        
        final_state = run_workflow_sync(
            question="Can I get a loan?",
            user_id=9999,
            req_id="TEST-NOT-FOUND"
        )
        
        assert final_state["client"] is None
        assert final_state["decision"] == "DECLINE"
        assert "system error" in final_state["final_answer"].lower()
    
    def _setup_workflow_mocks(
        self, mock_db_session, mock_read_metrics, mock_is_stale, mock_retrieve, mock_openai,
        customer_data, market_data, policy_snippets
    ):
        """Helper to setup common workflow mocks."""
        # Mock database
        mock_db = MagicMock()
        mock_customer = Mock()
        mock_customer.to_dict.return_value = customer_data
        mock_db.query.return_value.filter.return_value.first.return_value = mock_customer
        mock_db_session.return_value.__enter__.return_value = mock_db
        
        # Mock market data
        mock_read_metrics.return_value = market_data
        mock_is_stale.return_value = False
        
        # Mock policy retrieval
        mock_retrieve.return_value = policy_snippets
        
        # Mock OpenAI
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Professional loan decision explanation..."
        mock_openai.return_value = mock_response


class TestAPIConvenienceFunctions:
    """Test API convenience functions."""
    
    @patch('app.graph.workflow.run_workflow')
    async def test_generate_answer_success(self, mock_run_workflow):
        """Test successful answer generation."""
        # Mock successful workflow
        mock_state = {
            "req_id": "TEST-001",
            "decision": "APPROVE",
            "score": 0.75,
            "reason_codes": ["Strong profile"],
            "market_stale": False,
            "policy_snippets": [{"section_id": "SEC-1"}],
            "final_answer": "Your loan application has been approved."
        }
        mock_run_workflow.return_value = mock_state
        
        answer, metadata = await generate_answer(1001, "Can I get a loan?")
        
        assert answer == "Your loan application has been approved."
        assert metadata["decision"] == "APPROVE"
        assert metadata["score"] == 0.75
        assert metadata["success"] is True
    
    @patch('app.graph.workflow.run_workflow')
    async def test_generate_answer_failure(self, mock_run_workflow):
        """Test answer generation with workflow failure."""
        # Mock workflow failure
        mock_run_workflow.side_effect = Exception("Workflow error")
        
        answer, metadata = await generate_answer(1001, "Can I get a loan?")
        
        assert "system error" in answer.lower()
        assert metadata["decision"] == "DECLINE"
        assert metadata["success"] is False
    
    def test_get_workflow_info(self):
        """Test workflow information retrieval."""
        info = get_workflow_info()
        
        assert "nodes" in info
        assert "auth" in info["nodes"]
        assert "risk_gate" in info["nodes"]
        assert "explain" in info["nodes"]
        assert info["entry_point"] == "auth"
        assert "llm_nodes" in info
        assert "explain" in info["llm_nodes"] 