"""Tests for reference rendering in responses."""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from app.api.main import app


client = TestClient(app)


class TestReferenceRendering:
    """Test that policy references are properly rendered in responses."""
    
    @patch('app.graph.workflow.run_decision')
    def test_policy_question_includes_references(self, mock_run_decision):
        """Test that policy questions return references."""
        # Mock workflow response with references
        mock_run_decision.return_value = {
            "decision": "INFORM",
            "final_answer": "Our personal loan rates range from 6.99% to 24.99% APR (S1). Business loans start at Prime + 2% (S2).",
            "references": [
                {"source": "S1", "section": "Personal Loan Rates", "page": 15},
                {"source": "S2", "section": "Business Loan Rates", "page": 23}
            ],
            "quick_replies": [{"label": "Apply now"}, {"label": "Check eligibility"}],
            "cta": {"text": "Get pre-qualified", "action": "apply_now"}
        }
        
        response = client.post(
            "/api/v1/decision",
            json={"question": "What are your loan rates?"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify references are present and properly formatted
        assert len(data["references"]) >= 1
        assert data["references"][0]["source"] == "S1"
        assert data["references"][0]["section"] == "Personal Loan Rates"
        assert data["references"][0]["page"] == 15
        
        # Verify answer includes inline citations
        assert "(S1)" in data["answer"]
    
    @patch('app.graph.workflow.run_decision')
    def test_collateral_requirements_question(self, mock_run_decision):
        """Test specific collateral requirements question includes references."""
        mock_run_decision.return_value = {
            "decision": "INFORM",
            "final_answer": "Collateral requirements vary by loan type (S1). Personal loans typically don't require collateral, while business loans may require real estate or equipment as security (S2).",
            "references": [
                {"source": "S1", "section": "Collateral Policy", "page": 42},
                {"source": "S2", "section": "Business Loan Requirements", "page": 58}
            ],
            "quick_replies": [
                {"label": "Personal loan info"},
                {"label": "Business loan info"}
            ],
            "cta": None
        }
        
        response = client.post(
            "/api/v1/decision",
            json={"question": "What are collateral requirements?"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["references"]) >= 1
        assert any("Collateral" in ref["section"] for ref in data["references"])
        assert len(data["quick_replies"]) >= 1
    
    @patch('app.graph.workflow.run_decision')
    def test_documentation_requirements_question(self, mock_run_decision):
        """Test documentation requirements question includes references."""
        mock_run_decision.return_value = {
            "decision": "INFORM", 
            "final_answer": "Required documentation includes proof of income, bank statements, and tax returns (S1). Additional business documentation may be needed for commercial loans (S2).",
            "references": [
                {"source": "S1", "section": "Required Documentation", "page": 12},
                {"source": "S2", "section": "Business Documentation", "page": 67}
            ],
            "quick_replies": [
                {"label": "Document checklist"},
                {"label": "Upload documents"}
            ],
            "cta": {"text": "Start application", "action": "apply_now"}
        }
        
        response = client.post(
            "/api/v1/decision",
            json={"question": "What documentation do I need to apply?"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["references"]) >= 1
        assert any("Documentation" in ref["section"] for ref in data["references"])
        assert data["cta"] is not None
        assert data["cta"]["action"] == "apply_now"
    
    def test_reference_structure_validation(self):
        """Test that reference objects have required structure."""
        response = client.post(
            "/api/v1/decision",
            json={"question": "Tell me about your interest rates"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that each reference has required fields
        for ref in data["references"]:
            assert "source" in ref
            assert isinstance(ref["source"], str)
            assert ref["source"].startswith("S")  # Should be S1, S2, S3, etc.
            
            # Section and page are optional but should be strings/ints if present
            if "section" in ref and ref["section"] is not None:
                assert isinstance(ref["section"], str)
            if "page" in ref and ref["page"] is not None:
                assert isinstance(ref["page"], int)
    
    def test_inline_citations_match_references(self):
        """Test that inline citations (S1, S2) match the references array."""
        response = client.post(
            "/api/v1/decision",
            json={"question": "What are your loan terms and conditions?"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        answer = data["answer"]
        references = data["references"]
        
        # Find all inline citations in the answer
        import re
        inline_citations = re.findall(r'\(S\d+\)', answer)
        reference_sources = [ref["source"] for ref in references]
        
        # Each inline citation should have a corresponding reference
        for citation in inline_citations:
            source = citation.strip("()")  # Remove parentheses
            assert source in reference_sources, f"Citation {citation} not found in references"


class TestReferenceContent:
    """Test the content and quality of references."""
    
    def test_references_are_relevant(self):
        """Test that references are relevant to the question asked."""
        test_cases = [
            {
                "question": "What are interest rates for personal loans?",
                "expected_keywords": ["rate", "personal", "loan", "apr", "interest"]
            },
            {
                "question": "What collateral is required?",
                "expected_keywords": ["collateral", "security", "requirement"]
            },
            {
                "question": "How long does approval take?",
                "expected_keywords": ["approval", "process", "time", "timeline"]
            }
        ]
        
        for case in test_cases:
            response = client.post(
                "/api/v1/decision",
                json={"question": case["question"]},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Check that references relate to the question topic
            if data["references"]:
                sections = [ref.get("section", "").lower() for ref in data["references"]]
                section_text = " ".join(sections)
                
                # At least one keyword should appear in reference sections
                found_relevant = any(
                    keyword in section_text 
                    for keyword in case["expected_keywords"]
                )
                
                assert found_relevant, f"No relevant references found for question: {case['question']}"
    
    def test_no_empty_references(self):
        """Test that empty or malformed references are not included."""
        response = client.post(
            "/api/v1/decision",
            json={"question": "Tell me about your loan policies"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for ref in data["references"]:
            # Source should never be empty
            assert ref["source"] is not None
            assert ref["source"].strip() != ""
            
            # If section is provided, it should not be empty
            if "section" in ref and ref["section"] is not None:
                assert ref["section"].strip() != ""
    
    def test_reference_limit(self):
        """Test that references are limited to reasonable number."""
        response = client.post(
            "/api/v1/decision",
            json={"question": "Tell me everything about loans"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should not return excessive number of references
        assert len(data["references"]) <= 5, "Too many references returned"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
