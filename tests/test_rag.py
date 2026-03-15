"""Tests for RAG functionality."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from app.graph.store import get_embedding, embed_texts, get_embedding_dimension
from app.rag.index_policy import PolicyIndexer
from app.rag.retriever import PolicyRetriever, retrieve_policy_snippets


class TestEmbeddings:
    """Test embedding functionality."""
    
    @patch('app.graph.store.openai.embeddings.create')
    def test_get_embedding_success(self, mock_create):
        """Test successful single embedding."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3])]
        mock_create.return_value = mock_response
        
        result = get_embedding("test text")
        
        assert result == [0.1, 0.2, 0.3]
        mock_create.assert_called_once()
    
    @patch('app.graph.store.openai.embeddings.create')
    def test_embed_texts_batch(self, mock_create):
        """Test batch embedding."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.data = [
            Mock(embedding=[0.1, 0.2, 0.3]),
            Mock(embedding=[0.4, 0.5, 0.6])
        ]
        mock_create.return_value = mock_response
        
        texts = ["text 1", "text 2"]
        result = embed_texts(texts)
        
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]
    
    def test_get_embedding_dimension(self):
        """Test embedding dimension lookup."""
        assert get_embedding_dimension("text-embedding-3-small") == 1536
        assert get_embedding_dimension("text-embedding-3-large") == 3072
        assert get_embedding_dimension("unknown-model") == 1536  # Default
    
    @patch('app.graph.store.openai.embeddings.create')
    def test_text_truncation(self, mock_create):
        """Test text truncation for long inputs."""
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3])]
        mock_create.return_value = mock_response
        
        # Very long text
        long_text = "a" * 10000
        get_embedding(long_text)
        
        # Check that the call was made (text should be truncated internally)
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert len(call_args[1]["input"]) <= 8000


class TestPolicyIndexer:
    """Test policy indexing functionality."""
    
    def create_test_chunks_file(self, temp_dir: Path) -> Path:
        """Create a test chunks JSONL file."""
        chunks_file = temp_dir / "test_chunks.jsonl"
        
        test_chunks = [
            {
                "id": "chunk1",
                "text": "Eligibility criteria for personal loans require minimum income.",
                "metadata": {
                    "section_id": "3.1",
                    "heading_path": "Eligibility > Income Requirements",
                    "page_start": 5,
                    "page_end": 5,
                    "tokens": 15,
                    "source_file": "policy.pdf"
                }
            },
            {
                "id": "chunk2", 
                "text": "Risk assessment considers credit history and employment.",
                "metadata": {
                    "section_id": "4.2",
                    "heading_path": "Assessment > Risk Factors",
                    "page_start": 8,
                    "page_end": 8,
                    "tokens": 12,
                    "source_file": "policy.pdf"
                }
            }
        ]
        
        with open(chunks_file, 'w') as f:
            for chunk in test_chunks:
                f.write(json.dumps(chunk) + '\n')
        
        return chunks_file
    
    @patch('app.rag.index_policy.QdrantClient')
    @patch('app.rag.index_policy.embed_texts')
    def test_indexer_initialization(self, mock_embed, mock_qdrant_client):
        """Test indexer initialization."""
        indexer = PolicyIndexer("test_collection")
        
        assert indexer.collection_name == "test_collection"
        mock_qdrant_client.assert_called_once()
    
    @patch('app.rag.index_policy.QdrantClient')
    @patch('app.rag.index_policy.embed_texts')
    def test_index_policy_new_file(self, mock_embed, mock_qdrant_client):
        """Test indexing with new file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            chunks_file = self.create_test_chunks_file(temp_path)
            
            # Mock Qdrant client
            mock_client = Mock()
            mock_qdrant_client.return_value = mock_client
            mock_client.get_collections.return_value = Mock(collections=[])
            
            # Mock embeddings
            mock_embed.return_value = [[0.1, 0.2], [0.3, 0.4]]
            
            # Create indexer with test file
            indexer = PolicyIndexer("test_collection")
            indexer.chunks_path = str(chunks_file)
            indexer.meta_path = temp_path / ".policy_index.meta"
            
            # Index policy
            result = indexer.index_policy(force=True)
            
            assert result is True
            mock_client.create_collection.assert_called_once()
            mock_client.upsert.assert_called_once()
            mock_embed.assert_called_once()
    
    def test_file_hash_calculation(self):
        """Test file hash calculation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_file = temp_path / "test.txt"
            test_file.write_text("test content")
            
            indexer = PolicyIndexer()
            hash1 = indexer._calculate_file_hash(str(test_file))
            hash2 = indexer._calculate_file_hash(str(test_file))
            
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA256 hex length
    
    def test_needs_reindex_logic(self):
        """Test reindex decision logic."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            chunks_file = self.create_test_chunks_file(temp_path)
            
            indexer = PolicyIndexer()
            indexer.chunks_path = str(chunks_file)
            indexer.meta_path = temp_path / ".policy_index.meta"
            
            # Force should always return True
            assert indexer._needs_reindex(force=True) is True
            
            # No metadata file should return True
            assert indexer._needs_reindex(force=False) is True


class TestPolicyRetriever:
    """Test policy retrieval functionality."""
    
    @patch('app.rag.retriever.QdrantClient')
    def test_retriever_initialization(self, mock_qdrant_client):
        """Test retriever initialization."""
        retriever = PolicyRetriever("test_collection")
        
        assert retriever.collection_name == "test_collection"
        mock_qdrant_client.assert_called_once()
    
    def test_build_query(self):
        """Test query building from decision and reasons."""
        retriever = PolicyRetriever()
        
        query = retriever._build_query("DECLINE", ["High risk", "Low income"])
        expected = "decision: DECLINE reasons: High risk, Low income"
        
        assert query == expected
    
    def test_build_query_no_reasons(self):
        """Test query building with no reason codes."""
        retriever = PolicyRetriever()
        
        query = retriever._build_query("APPROVE", [])
        expected = "decision: APPROVE"
        
        assert query == expected
    
    @patch('app.rag.retriever.QdrantClient')
    @patch('app.rag.retriever.get_embedding')
    def test_retrieve_policy_snippets(self, mock_get_embedding, mock_qdrant_client):
        """Test complete snippet retrieval flow."""
        # Mock embedding
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        
        # Mock Qdrant client and search results
        mock_client = Mock()
        mock_qdrant_client.return_value = mock_client
        
        mock_search_result = [
            Mock(
                id=1,
                score=0.8,
                payload={
                    "section_id": "3.1",
                    "text": "Eligibility criteria for loans",
                    "page_start": 5,
                    "page_end": 5
                }
            ),
            Mock(
                id=2,
                score=0.6,
                payload={
                    "section_id": "4.2", 
                    "text": "Risk assessment procedures",
                    "page_start": 8,
                    "page_end": 8
                }
            )
        ]
        mock_client.search.return_value = mock_search_result
        
        # Test retrieval
        retriever = PolicyRetriever("test_collection")
        results = retriever.retrieve_policy_snippets("DECLINE", ["High risk"], k=2)
        
        assert len(results) == 2
        assert results[0]["section_id"] == "3.1"
        assert results[0]["text"] == "Eligibility criteria for loans"
        assert "score" in results[0]
        
        mock_get_embedding.assert_called_once()
        mock_client.search.assert_called_once()
    
    def test_filter_and_rerank(self):
        """Test filtering and reranking logic."""
        retriever = PolicyRetriever()
        
        # Mock search results
        results = [
            {
                "score": 0.8,
                "payload": {
                    "text": "eligibility criteria requirements",
                    "section_id": "3.1",
                    "heading_path": "Eligibility"
                }
            },
            {
                "score": 0.05,  # Below threshold
                "payload": {
                    "text": "unrelated content",
                    "section_id": "9.9",
                    "heading_path": "Appendix"
                }
            },
            {
                "score": 0.6,
                "payload": {
                    "text": "risk assessment policy",
                    "section_id": "4.2",
                    "heading_path": "Assessment"
                }
            }
        ]
        
        filtered = retriever._filter_and_rerank(results, min_score=0.1)
        
        # Should filter out low score result
        assert len(filtered) == 2
        
        # Should boost results with priority keywords
        assert all("boost" in result for result in filtered)
        assert all("original_score" in result for result in filtered)
    
    def test_format_snippets(self):
        """Test snippet formatting."""
        retriever = PolicyRetriever()
        
        results = [
            {
                "score": 0.8,
                "original_score": 0.7,
                "boost": 0.1,
                "payload": {
                    "section_id": "3.1",
                    "text": "Test content",
                    "page_start": 5,
                    "page_end": 6
                }
            }
        ]
        
        snippets = retriever._format_snippets(results)
        
        assert len(snippets) == 1
        snippet = snippets[0]
        
        assert snippet["section_id"] == "3.1"
        assert snippet["text"] == "Test content"
        assert snippet["page_start"] == 5
        assert snippet["page_end"] == 6
        assert snippet["score"] == 0.8
        assert snippet["boost"] == 0.1


class TestIntegrationScenarios:
    """Test complete RAG integration scenarios."""
    
    @patch('app.rag.retriever.QdrantClient')
    @patch('app.rag.retriever.get_embedding')
    def test_complete_retrieval_flow(self, mock_get_embedding, mock_qdrant_client):
        """Test complete retrieval flow using convenience function."""
        # Mock embedding
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        
        # Mock Qdrant search
        mock_client = Mock()
        mock_qdrant_client.return_value = mock_client
        mock_client.search.return_value = [
            Mock(
                id=1,
                score=0.9,
                payload={
                    "section_id": "3.1",
                    "text": "Loan eligibility requires stable income",
                    "page_start": 5,
                    "page_end": 5,
                    "heading_path": "Eligibility > Income"
                }
            )
        ]
        
        # Test convenience function
        results = retrieve_policy_snippets("DECLINE", ["Insufficient income"], k=1)
        
        assert len(results) == 1
        assert results[0]["section_id"] == "3.1"
        assert "Loan eligibility" in results[0]["text"]
    
    @patch('app.rag.retriever.QdrantClient')
    @patch('app.rag.retriever.get_embedding')
    def test_no_results_handling(self, mock_get_embedding, mock_qdrant_client):
        """Test handling when no results are found."""
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        
        mock_client = Mock()
        mock_qdrant_client.return_value = mock_client
        mock_client.search.return_value = []  # No results
        
        results = retrieve_policy_snippets("DECLINE", ["Rare reason"], k=3)
        
        assert results == []
    
    @patch('app.rag.retriever.QdrantClient')
    @patch('app.rag.retriever.get_embedding')
    def test_low_score_filtering(self, mock_get_embedding, mock_qdrant_client):
        """Test filtering of low-score results."""
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        
        mock_client = Mock()
        mock_qdrant_client.return_value = mock_client
        mock_client.search.return_value = [
            Mock(
                id=1,
                score=0.05,  # Very low score
                payload={
                    "section_id": "9.9",
                    "text": "Unrelated content",
                    "page_start": 99
                }
            )
        ]
        
        retriever = PolicyRetriever()
        results = retriever.retrieve_policy_snippets("DECLINE", ["High risk"], k=3)
        
        # Should be filtered out due to low score
        assert results == [] 