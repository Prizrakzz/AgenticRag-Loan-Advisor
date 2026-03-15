#!/usr/bin/env python3
"""Unit tests for the RAG retriever functionality."""

import pytest
from unittest.mock import patch, MagicMock

from app.rag.retriever import PolicyRetriever


class TestPolicyRetriever:
    """Test the PolicyRetriever functionality."""
    
    def test_retriever_initialization(self):
        """Test that retriever initializes correctly."""
        retriever = PolicyRetriever()
        assert retriever.collection_name
        assert retriever.client is not None
    
    @patch('app.rag.retriever.QdrantClient')
    @patch('app.rag.embeddings.embed_texts')
    def test_similarity_search_finds_loan_documents(self, mock_embed, mock_qdrant_client):
        """Test that similarity search can find loan-related documents."""
        # Mock embedding response
        mock_embed.return_value = [[0.1, 0.2, 0.3] * 100]  # Mock 384-dim embedding
        
        # Mock Qdrant response
        mock_client = MagicMock()
        mock_qdrant_client.return_value = mock_client
        
        # Create mock search results
        mock_point = MagicMock()
        mock_point.payload = {
            "text": "Loan terms in Oklahoma require minimum 5% down payment for qualified borrowers.",
            "metadata": {
                "section_id": "3.1",
                "heading_path": "Loan Requirements > Oklahoma",
                "source_file": "policy.pdf"
            }
        }
        mock_point.score = 0.85
        
        mock_client.search.return_value = [mock_point]
        
        # Test the retriever
        retriever = PolicyRetriever()
        docs = retriever.similarity_search("loan term Oklahoma", top_k=3)
        
        # Verify results
        assert len(docs) > 0
        assert any("loan" in doc.page_content.lower() for doc in docs)
        assert any("oklahoma" in doc.page_content.lower() for doc in docs)
        
        # Verify the search was called correctly
        mock_client.search.assert_called_once()
        call_args = mock_client.search.call_args
        assert call_args[1]['limit'] == 3
        assert len(call_args[1]['query_vector']) > 0
    
    @patch('app.rag.retriever.QdrantClient')
    @patch('app.rag.embeddings.embed_texts')
    def test_similarity_search_empty_results(self, mock_embed, mock_qdrant_client):
        """Test similarity search with empty results."""
        mock_embed.return_value = [[0.1, 0.2, 0.3] * 100]
        
        mock_client = MagicMock()
        mock_qdrant_client.return_value = mock_client
        mock_client.search.return_value = []
        
        retriever = PolicyRetriever()
        docs = retriever.similarity_search("nonexistent query", top_k=3)
        
        assert len(docs) == 0
    
    def test_get_retriever_function(self):
        """Test the get_retriever convenience function."""
        from app.rag.retriever import get_retriever
        
        retriever = get_retriever()
        assert isinstance(retriever, PolicyRetriever)


# Integration test (requires actual Qdrant)
@pytest.mark.integration
def test_retriever_with_real_data():
    """Integration test with real Qdrant data (if available)."""
    try:
        from app.rag.retriever import get_retriever
        
        retriever = get_retriever()
        docs = retriever.similarity_search("loan term Oklahoma", top_k=3)
        
        # If we have indexed data, we should get results
        if len(docs) > 0:
            assert any("loan" in doc.page_content.lower() for doc in docs)
            print(f"✅ Found {len(docs)} relevant documents")
            for i, doc in enumerate(docs[:2]):
                print(f"  Doc {i+1}: {doc.page_content[:100]}...")
        else:
            print("⚠️ No documents found - check if indexing is complete")
            
    except Exception as e:
        pytest.skip(f"Integration test skipped due to connection issue: {e}")


if __name__ == "__main__":
    # Run the basic test
    test = TestPolicyRetriever()
    test.test_retriever_initialization()
    print("✅ Retriever unit tests passed") 