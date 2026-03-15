"""Unit tests for individual LangGraph nodes."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.graph.state import new_state
from app.graph.nodes import (
    auth_node, risk_gate_node, market_node, score_node,
    decision_node, policy_rag_node, explain_node, end_node,
    _build_explanation_prompt
)


class TestAuthNode:
    """Test authentication node logic."""
    
    @patch('app.graph.nodes.get_db_session')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_auth_node_success(self, mock_audit, mock_db_session):
        """Test successful customer loading."""
        # Mock customer data
        customer_data = {
            "client_id": 1001,
                        "annual_income": 50.0,
            "risk_grade": "B"
        }
        
        # Mock database
        mock_db = MagicMock()
        mock_customer = Mock()
        mock_customer.to_dict.return_value = customer_data
        mock_db.query.return_value.filter.return_value.first.return_value = mock_customer
        mock_db_session.return_value.__enter__.return_value = mock_db
        
        # Test
        state = new_state("TEST-001", 1001, "Test question")
        result = auth_node(state)
        
        assert result["client"] == customer_data
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.get_db_session')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_auth_node_customer_not_found(self, mock_audit, mock_db_session):
        """Test when customer is not found."""
        # Mock empty database result
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db_session.return_value.__enter__.return_value = mock_db
        
        # Test
        state = new_state("TEST-001", 9999, "Test question")
        result = auth_node(state)
        
        assert result["client"] is None
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.get_db_session')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_auth_node_database_error(self, mock_audit, mock_db_session):
        """Test database connection error."""
        # Mock database error
        mock_db_session.side_effect = Exception("Database connection failed")
        
        # Test
        state = new_state("TEST-001", 1001, "Test question")
        result = auth_node(state)
        
        assert result["client"] is None
        mock_audit.assert_called_once()


class TestRiskGateNode:
    """Test risk gate node logic."""
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_risk_gate_grade_a_decline(self, mock_audit):
        """Test early decline for Grade A (highest risk) customer."""
        state = new_state("TEST-001", 1001, "Test question")
        state["client"] = {"risk_grade": "A"}  # Grade A = highest risk
        
        result = risk_gate_node(state)
        
        assert result["decision"] == "DECLINE"
        assert "GRADE_A_HIGH_RISK" in result["reason_codes"]
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_risk_gate_grade_d_approve(self, mock_audit):
        """Test early approval for Grade D (lowest risk) customer."""
        state = new_state("TEST-001", 1002, "Test question")
        state["client"] = {"risk_grade": "D"}  # Grade D = lowest risk
        
        result = risk_gate_node(state)
        
        assert result["decision"] == "APPROVE"
        assert "GRADE_D_LOW_RISK" in result["reason_codes"]
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_risk_gate_grade_b_pass(self, mock_audit):
        """Test passing through for Grade B customer."""
        state = new_state("TEST-001", 1003, "Test question")
        state["client"] = {"risk_grade": "B"}  # Grade B = pass through
        
        result = risk_gate_node(state)
        
        assert result["decision"] is None  # No early decision
        assert result["reason_codes"] == ["GRADE_B"]
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_risk_gate_grade_c_pass(self, mock_audit):
        """Test passing through for Grade C customer."""
        state = new_state("TEST-001", 1004, "Test question")
        state["client"] = {"risk_grade": "C"}  # Grade C = pass through
        
        result = risk_gate_node(state)
        
        assert result["decision"] is None  # No early decision
        assert result["reason_codes"] == ["GRADE_C"]
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_risk_gate_no_client(self, mock_audit):
        """Test when no client data available."""
        state = new_state("TEST-001", 1001, "Test question")
        # No client data
        
        result = risk_gate_node(state)
        
        assert result["decision"] is None
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_risk_gate_no_risk_grade(self, mock_audit):
        """Test when client has no risk grade."""
        state = new_state("TEST-001", 1001, "Test question")
        state["client"] = {"annual_income": 50.0}  # No risk_grade
        
        result = risk_gate_node(state)
        
        assert result["decision"] is None
        mock_audit.assert_called_once()


class TestMarketNode:
    """Test market data node logic."""
    
    @patch('app.graph.nodes.read_all_metrics')
    @patch('app.graph.nodes.is_metric_stale')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_market_node_fresh_data(self, mock_audit, mock_is_stale, mock_read_metrics):
        """Test with fresh market data."""
        market_data = {
            "cbj_rate": {"value": 7.5},
            "cpi_yoy": {"value": 3.2},
            "market_risk_score": {"value": 0.4}
        }
        mock_read_metrics.return_value = market_data
        mock_is_stale.return_value = False
        
        state = new_state("TEST-001", 1001, "Test question")
        result = market_node(state)
        
        assert result["market"] == market_data
        assert result["market_stale"] is False
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.read_all_metrics')
    @patch('app.graph.nodes.is_metric_stale')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_market_node_stale_data(self, mock_audit, mock_is_stale, mock_read_metrics):
        """Test with stale market data."""
        market_data = {
            "cbj_rate": {"value": 7.5},
            "market_risk_score": {"value": 0.4}
        }
        mock_read_metrics.return_value = market_data
        mock_is_stale.return_value = True  # Data is stale
        
        state = new_state("TEST-001", 1001, "Test question")
        result = market_node(state)
        
        assert result["market"] == market_data
        assert result["market_stale"] is True
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.read_all_metrics')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_market_node_no_data(self, mock_audit, mock_read_metrics):
        """Test when no market data available."""
        mock_read_metrics.return_value = {}
        
        state = new_state("TEST-001", 1001, "Test question")
        result = market_node(state)
        
        assert result["market"] == {}
        assert result["market_stale"] is True
        mock_audit.assert_called_once()


class TestScoreNode:
    """Test score calculation node logic."""
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_score_node_calculation(self, mock_audit):
        """Test score calculation with normal inputs."""
        state = new_state("TEST-001", 1001, "Test question")
        state["client"] = {"risk_grade": "D"}  # Low risk = good
        state["market"] = {
            "market_risk_score": {"value": 0.4}  # Medium market risk
        }
        
        result = score_node(state)
        
        assert "score" in result
        assert 0.0 <= result["score"] <= 1.0
        # Low client risk should result in higher score
        assert result["score"] > 0.5
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_score_node_missing_data(self, mock_audit):
        """Test score calculation with missing data (uses defaults)."""
        state = new_state("TEST-001", 1001, "Test question")
        # No client or market data
        
        result = score_node(state)
        
        assert "score" in result
        assert 0.0 <= result["score"] <= 1.0
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_score_node_high_risk_inputs(self, mock_audit):
        """Test score calculation with high-risk inputs."""
        state = new_state("TEST-001", 1001, "Test question")
        state["client"] = {"risk_grade": "A"}  # Very high risk
        state["market"] = {
            "market_risk_score": {"value": 0.8}  # High market risk
        }
        
        result = score_node(state)
        
        assert "score" in result
        # High risks should result in lower score
        assert result["score"] < 0.5
        mock_audit.assert_called_once()


class TestDecisionNode:
    """Test decision mapping node logic."""
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_decision_node_approve(self, mock_audit):
        """Test approval decision."""
        state = new_state("TEST-001", 1001, "Test question")
        state["score"] = 0.75  # High score
        state["client"] = {
            "risk_grade": "D",
            "annual_income": 60.0,
            "family_size": 2,
            "credit_card_with_bank": 1
        }
        state["market"] = {}
        
        result = decision_node(state)
        
        assert result["decision"] == "APPROVE"
        assert len(result["reason_codes"]) > 0
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_decision_node_decline(self, mock_audit):
        """Test decline decision."""
        state = new_state("TEST-001", 1001, "Test question")
        state["score"] = 0.3  # Low score
        state["client"] = {
            "risk_grade": "A",
            "annual_income": 20.0,
            "family_size": 4,
            "credit_card_with_bank": 0
        }
        state["market"] = {}
        
        result = decision_node(state)
        
        assert result["decision"] == "DECLINE"
        assert len(result["reason_codes"]) > 0
        # Should include specific reasons for decline
        reason_text = " ".join(result["reason_codes"])
        assert any(keyword in reason_text.lower() for keyword in ["risk", "income", "banking"])
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_decision_node_counter(self, mock_audit):
        """Test counter-offer decision."""
        state = new_state("TEST-001", 1001, "Test question")
        state["score"] = 0.55  # Medium score
        state["client"] = {
            "risk_grade": "B",
            "annual_income": 35.0,
            "family_size": 2
        }
        state["market"] = {}
        
        result = decision_node(state)
        
        assert result["decision"] == "COUNTER"
        assert len(result["reason_codes"]) > 0
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_decision_node_market_factors(self, mock_audit):
        """Test decision with market-based reason codes."""
        state = new_state("TEST-001", 1001, "Test question")
        state["score"] = 0.4
        state["client"] = {"risk_grade": "B"}
        state["market"] = {
            "market_risk_score": {
                "extra": {
                    "components": {
                        "cbj_risk": 0.7,  # High interest rate risk
                        "cpi_risk": 0.8,  # High inflation risk
                        "re_risk": 0.3    # Low real estate risk
                    }
                }
            }
        }
        
        result = decision_node(state)
        
        reason_text = " ".join(result["reason_codes"])
        assert "interest rate" in reason_text.lower()
        assert "inflation" in reason_text.lower()
        mock_audit.assert_called_once()


class TestPolicyRagNode:
    """Test policy RAG node logic."""
    
    @patch('app.graph.nodes.retrieve_policy_snippets')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_policy_rag_node_success(self, mock_audit, mock_retrieve):
        """Test successful policy snippet retrieval."""
        mock_snippets = [
            {"section_id": "SEC-1", "text": "Policy text 1"},
            {"section_id": "SEC-2", "text": "Policy text 2"}
        ]
        mock_retrieve.return_value = mock_snippets
        
        state = new_state("TEST-001", 1001, "Test question")
        state["decision"] = "DECLINE"
        state["reason_codes"] = ["High risk score", "Low income"]
        
        result = policy_rag_node(state)
        
        assert result["policy_snippets"] == mock_snippets
        mock_retrieve.assert_called_once_with(
            decision="DECLINE",
            reason_codes=["High risk score", "Low income"],
            k=3
        )
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.retrieve_policy_snippets')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_policy_rag_node_no_decision(self, mock_audit, mock_retrieve):
        """Test when no decision is available."""
        state = new_state("TEST-001", 1001, "Test question")
        # No decision set
        
        result = policy_rag_node(state)
        
        assert result["policy_snippets"] == []
        mock_retrieve.assert_not_called()
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.retrieve_policy_snippets')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_policy_rag_node_retrieval_error(self, mock_audit, mock_retrieve):
        """Test when policy retrieval fails."""
        mock_retrieve.side_effect = Exception("Vector search failed")
        
        state = new_state("TEST-001", 1001, "Test question")
        state["decision"] = "DECLINE"
        state["reason_codes"] = ["High risk"]
        
        result = policy_rag_node(state)
        
        assert result["policy_snippets"] == []
        mock_audit.assert_called_once()


class TestExplainNode:
    """Test explanation generation node logic."""
    
    @patch('app.graph.nodes.openai.chat.completions.create')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_explain_node_success(self, mock_audit, mock_openai):
        """Test successful explanation generation."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Decision: APPROVE. Your application meets all criteria..."
        mock_openai.return_value = mock_response
        
        state = new_state("TEST-001", 1001, "Test question")
        state["decision"] = "APPROVE"
        state["score"] = 0.75
        state["reason_codes"] = ["Strong profile"]
        state["policy_snippets"] = [{"section_id": "SEC-1", "text": "Policy text"}]
        
        result = explain_node(state)
        
        assert result["final_answer"] == "Decision: APPROVE. Your application meets all criteria..."
        mock_openai.assert_called_once()
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.openai.chat.completions.create')
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_explain_node_openai_failure(self, mock_audit, mock_openai):
        """Test fallback when OpenAI call fails."""
        mock_openai.side_effect = Exception("API rate limit exceeded")
        
        state = new_state("TEST-001", 1001, "Test question")
        state["decision"] = "DECLINE"
        state["score"] = 0.3
        
        result = explain_node(state)
        
        assert "Decision: DECLINE" in result["final_answer"]
        assert "system error" in result["final_answer"].lower()
        mock_audit.assert_called_once()
    
    def test_build_explanation_prompt(self):
        """Test explanation prompt building."""
        state = new_state("TEST-001", 1001, "Test question")
        state["decision"] = "COUNTER"
        state["score"] = 0.55
        state["client"] = {
            "risk_grade": "B",
            "annual_income": 45.0,
            "education_level": 2
        }
        state["reason_codes"] = ["Moderate risk factors"]
        state["policy_snippets"] = [
            {
                "section_id": "SEC-2.1",
                "page_start": 12,
                "page_end": 12,
                "text": "Counter-offers may be extended for borderline applications..."
            }
        ]
        
        prompt = _build_explanation_prompt(state)
        
        assert "system" in prompt
        assert "user" in prompt
        assert "Decision: COUNTER" in prompt["user"]
        assert "Score: 0.55" in prompt["user"]
        assert "Risk Grade: B" in prompt["user"]
        assert "[§SEC-2.1]" in prompt["user"]
        assert "180 words" in prompt["system"]


class TestEndNode:
    """Test end node logic."""
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_end_node(self, mock_audit):
        """Test end node functionality."""
        state = new_state("TEST-001", 1001, "Test question")
        state["decision"] = "APPROVE"
        state["final_answer"] = "Your loan has been approved."
        
        result = end_node(state)
        
        # Should return state unchanged
        assert result == state
        mock_audit.assert_called_once()
    
    @patch('app.graph.nodes.AuditLog.create_entry')
    def test_end_node_incomplete_state(self, mock_audit):
        """Test end node with incomplete state."""
        state = new_state("TEST-001", 1001, "Test question")
        # Missing decision and final_answer
        
        result = end_node(state)
        
        # Should still return state unchanged
        assert result == state
        mock_audit.assert_called_once() 