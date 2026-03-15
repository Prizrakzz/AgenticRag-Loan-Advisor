"""Tests for LLM-as-Judge decision paths."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import json
from app.nodes.llm_judge import judge_decision, build_prompt, judge_and_explain_node, _judge_decision_sync


class TestJudgeDecision:
    """Test the LLM judge decision logic."""
    
    @pytest.fixture
    def sample_context(self):
        """Sample context for testing."""
        return {
            "question": "Can I get a $50,000 business loan?",
            "customer": {
                "risk_grade": "B",
                "annual_income": 75,
                "family_size": 2,
                "credit_card_with_bank": True
            },
            "market": {
                "market_risk_score": {"value": 0.3}
            },
            "snippets": [
                "Business loans are available from $10,000 to $500,000 for qualified applicants.",
                "Credit requirements include minimum 640 credit score and debt-to-income ratio below 40%."
            ],
            "score": 0.75,
            "reason_codes": ["Strong income", "Existing relationship"]
        }
    
    @pytest.mark.asyncio
    @patch('app.nodes.llm_judge.openai.OpenAI')
    async def test_judge_decision_approve_path(self, mock_openai, sample_context):
        """Test LLM judge for approval decision."""
        # Mock OpenAI response for approval
        mock_response = Mock()
        mock_response.choices[0].message.content = json.dumps({
            "decision": "APPROVE",
            "answer": "Great news! Based on your strong financial profile with a risk score of 0.75, we can approve your $50,000 business loan request (S1).",
            "references": [{"source": "S1", "section": "Business Loan Policy", "page": 15}],
            "quick_replies": [{"label": "Apply now"}, {"label": "Check rates"}],
            "cta": {"text": "Start your application", "action": "apply_now"}
        })
        
        mock_client = Mock()
        mock_client.chat.completions.acreate = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client
        
        result = await judge_decision(sample_context)
        
        assert result["decision"] == "APPROVE"
        assert "strong financial profile" in result["answer"].lower()
        assert len(result["references"]) == 1
        assert len(result["quick_replies"]) == 2
        assert result["cta"]["action"] == "apply_now"
    
    @pytest.mark.asyncio
    @patch('app.nodes.llm_judge.openai.OpenAI')
    async def test_judge_decision_decline_path(self, mock_openai):
        """Test LLM judge for decline decision."""
        high_risk_context = {
            "question": "I need a $100,000 loan",
            "customer": {
                "risk_grade": "A",  # High risk in this system
                "annual_income": 25,
                "family_size": 4,
                "credit_card_with_bank": False
            },
            "score": 0.2,  # Low score = high risk
            "reason_codes": ["High risk grade", "Low income", "Large family"]
        }
        
        # Mock OpenAI response for decline
        mock_response = Mock()
        mock_response.choices[0].message.content = json.dumps({
            "decision": "DECLINE",
            "answer": "Unfortunately, we can't approve this loan request due to high risk factors including low income relative to family size (S1).",
            "references": [{"source": "S1", "section": "Risk Assessment", "page": 8}],
            "quick_replies": [{"label": "Alternative options"}, {"label": "Speak to advisor"}],
            "cta": {"text": "Contact loan officer", "action": "contact_officer"}
        })
        
        mock_client = Mock()
        mock_client.chat.completions.acreate = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client
        
        result = await judge_decision(high_risk_context)
        
        assert result["decision"] == "DECLINE"
        assert "can't approve" in result["answer"].lower()
        assert result["cta"]["action"] == "contact_officer"
    
    @pytest.mark.asyncio
    @patch('app.nodes.llm_judge.openai.OpenAI')
    async def test_judge_decision_counter_path(self, mock_openai):
        """Test LLM judge for counter offer."""
        moderate_risk_context = {
            "question": "Can I get a personal loan?",
            "customer": {
                "risk_grade": "C",
                "annual_income": 45,
                "family_size": 1,
                "credit_card_with_bank": True
            },
            "score": 0.55,  # Moderate score
            "reason_codes": ["Moderate risk", "Existing relationship"]
        }
        
        # Mock OpenAI response for counter
        mock_response = Mock()
        mock_response.choices[0].message.content = json.dumps({
            "decision": "COUNTER",
            "answer": "We can offer you a personal loan with adjusted terms - perhaps a lower amount or higher rate based on your profile (S1).",
            "references": [{"source": "S1", "section": "Personal Loans", "page": 12}],
            "quick_replies": [{"label": "View terms"}, {"label": "Discuss options"}],
            "cta": {"text": "Schedule consultation", "action": "schedule_call"}
        })
        
        mock_client = Mock()
        mock_client.chat.completions.acreate = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client
        
        result = await judge_decision(moderate_risk_context)
        
        assert result["decision"] == "COUNTER"
        assert "adjusted terms" in result["answer"].lower()
        assert result["cta"]["action"] == "schedule_call"
    
    @pytest.mark.asyncio
    @patch('app.nodes.llm_judge.openai.OpenAI')
    async def test_judge_decision_inform_path(self, mock_openai):
        """Test LLM judge for policy information."""
        policy_context = {
            "question": "What are your interest rates?",
            "customer": {},  # No customer context
            "snippets": [
                "Personal loan rates range from 6.99% to 24.99% APR based on creditworthiness.",
                "Business loan rates start at Prime + 2% for qualified borrowers."
            ],
            "score": 0.0,  # No score for policy questions
            "reason_codes": []
        }
        
        # Mock OpenAI response for inform
        mock_response = Mock()
        mock_response.choices[0].message.content = json.dumps({
            "decision": "INFORM",
            "answer": "Our personal loan rates range from 6.99% to 24.99% APR depending on your credit profile (S1). Business loans start at Prime + 2% for qualified applicants (S2).",
            "references": [
                {"source": "S1", "section": "Personal Loan Rates", "page": 3},
                {"source": "S2", "section": "Business Loan Rates", "page": 7}
            ],
            "quick_replies": [{"label": "Check eligibility"}, {"label": "Apply online"}],
            "cta": {"text": "Get pre-qualified", "action": "apply_now"}
        })
        
        mock_client = Mock()
        mock_client.chat.completions.acreate = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client
        
        result = await judge_decision(policy_context)
        
        assert result["decision"] == "INFORM"
        assert "rates range" in result["answer"].lower()
        assert len(result["references"]) == 2


class TestBuildPrompt:
    """Test prompt building for LLM judge."""
    
    def test_build_prompt_with_full_context(self):
        """Test building prompt with complete context."""
        ctx = {
            "question": "Can I get a loan?",
            "customer": {
                "risk_grade": "B",
                "annual_income": 60,
                "family_size": 3,
                "credit_card_with_bank": True
            },
            "market": {
                "market_risk_score": {"value": 0.4}
            },
            "snippets": ["Snippet 1", "Snippet 2"],
            "score": 0.65
        }
        
        prompt = build_prompt(ctx)
        
        assert "QUESTION: Can I get a loan?" in prompt
        assert "Customer Risk Grade: B" in prompt
        assert "Annual Income: $60K" in prompt
        assert "Banking Relationship: Yes" in prompt
        assert "Composite Score: 0.65 (Moderate Risk)" in prompt
        assert "S1: Snippet 1" in prompt
        assert "S2: Snippet 2" in prompt
    
    def test_build_prompt_minimal_context(self):
        """Test building prompt with minimal context."""
        ctx = {
            "question": "What are your rates?",
            "customer": {},
            "snippets": []
        }
        
        prompt = build_prompt(ctx)
        
        assert "QUESTION: What are your rates?" in prompt
        assert "CONTEXT:" in prompt
        assert "Return valid JSON" in prompt


class TestJudgeAndExplainNode:
    """Test the combined judge and explain node."""
    
    @patch('app.nodes.llm_judge._judge_decision_sync')
    def test_judge_and_explain_node_success(self, mock_judge):
        """Test successful judge and explain node execution."""
        # Mock successful judge response
        mock_judge.return_value = {
            "decision": "APPROVE",
            "answer": "We can approve your loan request based on your strong profile.",
            "references": [{"source": "S1", "section": "Approval Criteria"}],
            "quick_replies": [{"label": "Apply now"}],
            "cta": {"text": "Start application", "action": "apply_now"}
        }
        
        state = {
            "req_id": "test-123",
            "question": "Can I get a loan?",
            "client": {"risk_grade": "C"},
            "score": 0.7
        }
        
        result = judge_and_explain_node(state)
        
        assert result["decision"] == "APPROVE"
        assert result["final_answer"] == "We can approve your loan request based on your strong profile."
        assert len(result["references"]) == 1
        assert len(result["quick_replies"]) == 1
        assert result["cta"]["action"] == "apply_now"
    
    @patch('app.nodes.llm_judge._judge_decision_sync')
    @patch('app.graph.nodes.decision_node')
    @patch('app.graph.nodes.explain_node')
    def test_judge_and_explain_node_fallback(self, mock_explain, mock_decision, mock_judge):
        """Test fallback to legacy nodes when judge fails."""
        # Mock judge failure
        mock_judge.side_effect = Exception("LLM service unavailable")
        
        # Mock legacy nodes
        mock_decision.return_value = {"decision": "COUNTER", "reason_codes": ["Moderate risk"]}
        mock_explain.return_value = {
            "decision": "COUNTER", 
            "final_answer": "We can offer adjusted terms.",
            "explanation": "We can offer adjusted terms."
        }
        
        state = {
            "req_id": "test-123",
            "question": "Can I get a loan?",
            "client": {"risk_grade": "C"},
            "score": 0.5
        }
        
        result = judge_and_explain_node(state)
        
        # Should fall back to legacy decision
        assert result["decision"] == "COUNTER"
        assert mock_decision.called
        assert mock_explain.called


class TestSyncJudge:
    """Test synchronous judge function."""
    
    @patch('app.nodes.llm_judge.openai.OpenAI')
    def test_sync_judge_success(self, mock_openai):
        """Test successful synchronous judge execution."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices[0].message.content = json.dumps({
            "decision": "DECLINE",
            "answer": "Unable to approve due to risk factors."
        })
        
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        ctx = {
            "question": "I need a loan",
            "customer": {"risk_grade": "A"},
            "score": 0.2
        }
        
        result = _judge_decision_sync(ctx)
        
        assert result["decision"] == "DECLINE"
        assert "risk factors" in result["answer"]
        assert result["references"] == []  # Should set defaults
        assert result["quick_replies"] == []
        assert result["cta"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
