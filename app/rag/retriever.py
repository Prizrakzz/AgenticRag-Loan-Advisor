"""Policy document retriever for the loan approval system."""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add app directory to Python path if running as script
if __name__ == "__main__":
    sys.path.append(str(Path(__file__).parent.parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.http import models
import json
import math
import threading

from app.graph.store import get_embedding
from app.utils.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Global cache for collection detection
_RAG_COLLECTION = None
_FIELD_MAP = None


def detect_rag_collection_and_schema(client: QdrantClient) -> tuple[str, Dict[str, str]]:
    """
    Auto-detect the RAG collection and payload schema.
    
    Returns:
        Tuple of (collection_name, field_map)
    """
    global _RAG_COLLECTION, _FIELD_MAP
    
    if _RAG_COLLECTION and _FIELD_MAP:
        return _RAG_COLLECTION, _FIELD_MAP
    
    logger.info("auto_detecting_rag_collection")
    
    try:
        # Get all collections
        collections_response = client.get_collections()
        collections = [c.name for c in collections_response.collections]
        
        logger.info("collections_found", collections=collections)
        
        # Prefer collections with 'policy' or 'policies' in the name
        policy_collections = [c for c in collections if 'policy' in c.lower() or 'policies' in c.lower()]
        
        if policy_collections:
            target_collection = policy_collections[0]
        elif collections:
            target_collection = collections[0] 
        else:
            raise ValueError("No collections found in Qdrant")
        
        logger.info("selected_collection", collection=target_collection)
        
        # Probe the collection to detect payload schema
        points, _ = client.scroll(target_collection, limit=3, with_payload=True)
        
        if not points:
            raise ValueError(f"Collection {target_collection} is empty")
        
        # Analyze payload structure
        sample_payload = points[0].payload
        logger.info("sample_payload_keys", keys=list(sample_payload.keys()))
        
        # Build field map based on available fields
        field_map = {}
        
        # Text field mapping
        if "text" in sample_payload:
            field_map["text"] = "text"
        elif "chunk" in sample_payload:
            field_map["text"] = "chunk"
        elif "content" in sample_payload:
            field_map["text"] = "content"
        else:
            raise ValueError("No text field found in payload")
        
        # Section field mapping - check for metadata structure
        if "metadata" in sample_payload and isinstance(sample_payload["metadata"], dict):
            metadata = sample_payload["metadata"]
            if "section_title" in metadata:
                field_map["section"] = "metadata.section_title"
            elif "heading_path" in metadata:
                field_map["section"] = "metadata.heading_path"
        
        # Direct section fields (current format)
        if "section" not in field_map:
            if "section_title" in sample_payload:
                field_map["section"] = "section_title"
            elif "heading_path" in sample_payload:
                field_map["section"] = "heading_path"
            elif "section_id" in sample_payload:
                field_map["section"] = "section_id"
            else:
                field_map["section"] = "Policy"  # Default fallback
        
        # Page field mapping
        if "metadata" in sample_payload and isinstance(sample_payload["metadata"], dict):
            metadata = sample_payload["metadata"]
            if "page_start" in metadata:
                field_map["page"] = "metadata.page_start"
        
        if "page" not in field_map:
            if "page_start" in sample_payload:
                field_map["page"] = "page_start"
            elif "source_page" in sample_payload:
                field_map["page"] = "source_page"
            elif "page" in sample_payload:
                field_map["page"] = "page"
        
        logger.info("field_map_detected", field_map=field_map)
        
        # Cache the results
        _RAG_COLLECTION = target_collection
        _FIELD_MAP = field_map
        
        return target_collection, field_map
        
    except Exception as e:
        logger.error("collection_detection_failed", error=str(e))
        raise ValueError(f"Failed to detect RAG collection: {str(e)}")


def extract_field_value(payload: Dict[str, Any], field_path: str) -> Any:
    """Extract value from payload using dot notation field path."""
    if "." not in field_path:
        return payload.get(field_path)
    
    parts = field_path.split(".")
    value = payload
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


class PolicyRetriever:
    """Policy document retriever using vector search with auto-detection.

    Adds an in-memory fallback mode when Qdrant is unreachable so the UI still
    returns policy grounded answers (best-effort cosine similarity over loaded
    chunks). This prevents silent INFORM fallbacks just because vector store
    isn't up yet.
    """

    _fallback_lock = threading.Lock()

    def __init__(self, collection_name: str = None):
        self.fallback_mode = False
        self._fallback_docs: list[dict] = []
        self._fallback_embeddings: list[list[float]] = []
        self.collection_name = collection_name or settings.vector.collection_name
        # Attempt to derive embedding dim from settings; fallback to 1536
        try:
            self._embed_dim = int(getattr(settings.vector, 'embedding_size', 1536))
        except Exception:
            self._embed_dim = 1536

        # Initialize Qdrant client (may fail later when used)
        qdrant_url = settings.qdrant_url
        if not qdrant_url:
            host, port = settings.qdrant_host_port
            qdrant_url = f"http://{host}:{port}"

        try:
            self.client = QdrantClient(
                url=qdrant_url,
                api_key=settings.qdrant_api_key,
                prefer_grpc=False
            )
            # Ping collections endpoint quickly
            try:
                _ = self.client.get_collections()
                # Auto-detect
                try:
                    self.collection_name, self.field_map = detect_rag_collection_and_schema(self.client)
                except Exception as e:
                    logger.error("auto_detection_failed", error=str(e))
                    self.field_map = {"text": "text", "section": "section_title", "page": "page_start"}
                logger.debug("retriever_initialized", collection_name=self.collection_name, field_map=self.field_map, qdrant_url=qdrant_url, mode="qdrant")
            except Exception as ping_err:
                logger.warning("qdrant_unreachable_falling_back", error=str(ping_err))
                self._enable_fallback()
        except Exception as e:
            logger.warning("qdrant_client_init_failed", error=str(e))
            self._enable_fallback()

    # ---------------- Fallback helpers -----------------
    def _enable_fallback(self):
        with self._fallback_lock:
            if self.fallback_mode:  # already enabled
                return
            self.fallback_mode = True
            self.field_map = {"text": "text", "section": "section", "page": "page_start"}
            chunks_path = settings.data.policy_chunks
            cache_path = Path(chunks_path).with_suffix('.embeddings.cache.json')
            try:
                path = Path(chunks_path)
                if not path.exists():
                    logger.error("fallback_chunks_missing", path=chunks_path)
                    return
                texts = []
                docs = []
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        text = obj.get("text") or obj.get("metadata", {}).get("text")
                        if not text:
                            continue
                        # Normalize doc structure similar to Qdrant payload
                        meta = obj.get("metadata", {})
                        payload = {
                            "text": text,
                            "section_id": meta.get("section_id") or obj.get("section_id"),
                            "section_title": meta.get("section_title") or obj.get("section_title"),
                            "heading_path": meta.get("heading_path") or obj.get("heading_path"),
                            "page_start": meta.get("page_start") or obj.get("page_start"),
                            "page_end": meta.get("page_end") or obj.get("page_end"),
                            "source_file": meta.get("source_file") or obj.get("source_file"),
                            "section": obj.get("section"),
                            "tags": obj.get("tags", []),
                        }
                        texts.append(text)
                        docs.append({"payload": payload})
                if texts:
                    embeddings: list[list[float]] = []
                    # Try load cache first
                    if cache_path.exists():
                        try:
                            cached = json.loads(cache_path.read_text(encoding='utf-8'))
                            if len(cached) == len(texts):
                                embeddings = cached
                                logger.info("fallback_loaded_from_cache", docs=len(docs))
                            else:
                                logger.warning("fallback_cache_mismatch_recomputing", cached=len(cached), texts=len(texts))
                        except Exception as cache_err:
                            logger.warning("fallback_cache_read_failed", error=str(cache_err))
                    if not embeddings:
                        for t in texts:
                            try:
                                embeddings.append(get_embedding(t))
                            except Exception as emb_err:
                                logger.warning("embedding_failed_fallback_doc", error=str(emb_err))
                                embeddings.append([])
                        # Persist cache best-effort
                        try:
                            cache_path.write_text(json.dumps(embeddings), encoding='utf-8')
                            logger.info("fallback_cache_written", path=str(cache_path))
                        except Exception as write_err:
                            logger.warning("fallback_cache_write_failed", error=str(write_err))
                    self._fallback_docs = docs
                    self._fallback_embeddings = embeddings
                    logger.info("fallback_loaded", docs=len(docs))
                else:
                    logger.warning("fallback_no_texts_loaded")
            except Exception as e:
                logger.error("fallback_init_failed", error=str(e))
        logger.info("retriever_initialized", collection_name=self.collection_name, field_map=self.field_map, mode="fallback")

    def _similarity_cosine(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x*y for x, y in zip(a, b))
        na = math.sqrt(sum(x*x for x in a))
        nb = math.sqrt(sum(y*y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
    
    # ---------- Embedding helpers (fallback safe) ---------
    def _pseudo_embed(self, text: str) -> list[float]:
        """Generate a deterministic pseudo-embedding when real embeddings fail."""
        dim = self._embed_dim
        vec = [0.0] * dim
        if not text:
            return vec
        for token in text.lower().split():
            h = hash(token) % dim
            vec[h] += 1.0
        norm = math.sqrt(sum(v*v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _safe_embedding(self, text: str) -> list[float]:
        try:
            emb = get_embedding(text)
            if emb:
                return emb
        except Exception as e:
            if not self.fallback_mode:
                logger.warning("embedding_failed_using_pseudo", error=str(e))
        return self._pseudo_embed(text)
    
    def similarity_search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Perform similarity search using embeddings.
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of search results with metadata
        """
        try:
            # Get query embedding
            query_vector = get_embedding(query)
            
            # Search in Qdrant
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
                score_threshold=0.1  # Minimum score threshold
            )
            
            # Transform results to expected format
            results = []
            for point in search_results:
                payload = point.payload
                
                # Extract fields using field map
                result = {
                    "id": str(point.id),
                    "score": point.score,
                    "text": extract_field_value(payload, self.field_map["text"]) or "",
                }
                
                # Add section if available
                section_value = extract_field_value(payload, self.field_map.get("section", ""))
                if section_value:
                    result["section"] = section_value
                    result["section_id"] = section_value  # Backward compatibility
                
                # Add page if available  
                page_value = extract_field_value(payload, self.field_map.get("page", ""))
                if page_value:
                    try:
                        result["page"] = int(page_value) if page_value else 1
                        result["page_start"] = result["page"]  # Backward compatibility
                    except (ValueError, TypeError):
                        result["page"] = 1
                
                # Add other useful fields from payload
                for key in ["heading_path", "source_file", "section_id", "tokens"]:
                    if key in payload:
                        result[key] = payload[key]
                
                results.append(result)
            
            logger.debug(
                "similarity_search_complete",
                query=query,
                results_count=len(results),
                collection=self.collection_name
            )
            
            return results
            
        except Exception as e:
            logger.error("similarity_search_failed", query=query, error=str(e))
            return []
    
    def _build_query(self, decision: str, reason_codes: List[str]) -> str:
        """
        Build query string from decision and reason codes.
        
        Args:
            decision: Loan decision (APPROVE, DECLINE, COUNTER)
            reason_codes: List of reason codes
        
        Returns:
            Query string for embedding
        """
        query_parts = [f"decision: {decision}"]
        
        if reason_codes:
            reasons_str = ", ".join(reason_codes)
            query_parts.append(f"reasons: {reasons_str}")
        
        query = " ".join(query_parts)
        
        logger.debug(
            "query_built",
            decision=decision,
            reason_codes=reason_codes,
            query=query
        )
        
        return query
    
    def _search_vectors(self, query_vector: List[float], top_k: int = 8) -> List[Dict[str, Any]]:
        """
        Perform vector search in Qdrant.
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of top results to retrieve
        
        Returns:
            List of search results with scores and payloads
        """
        if self.fallback_mode:
            # In-memory cosine similarity search
            results: list[dict] = []
            try:
                for idx, emb in enumerate(self._fallback_embeddings):
                    if not emb:
                        continue
                    score = self._similarity_cosine(query_vector, emb)
                    results.append({
                        "id": idx,
                        "score": score,
                        "payload": self._fallback_docs[idx]["payload"],
                    })
                # Sort and trim
                results.sort(key=lambda r: r["score"], reverse=True)
                trimmed = results[:top_k]
                logger.debug("vector_search_complete", query_dim=len(query_vector), results_count=len(trimmed), mode="fallback")
                return trimmed
            except Exception as e:
                logger.error("fallback_vector_search_failed", error=str(e))
                return []
        try:
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=top_k,
                with_payload=True,
                with_vectors=False
            )
            results = []
            for point in search_result:
                results.append({"id": point.id, "score": point.score, "payload": point.payload})
            logger.debug("vector_search_complete", query_dim=len(query_vector), results_count=len(results), top_score=results[0]["score"] if results else 0, mode="qdrant")
            return results
        except Exception as e:
            logger.error("vector_search_failed", error=str(e))
            # Attempt one-time fallback enable if not already
            if not self.fallback_mode:
                self._enable_fallback()
                return self._search_vectors(query_vector, top_k=top_k)
            raise
    
    def _filter_and_rerank(self, results: List[Dict[str, Any]], min_score: float = 0.1) -> List[Dict[str, Any]]:
        """
        Filter results by score and apply simple reranking.
        
        Args:
            results: Search results from vector search
            min_score: Minimum similarity score threshold
        
        Returns:
            Filtered and reranked results
        """
        # Filter by minimum score
        filtered = [r for r in results if r["score"] >= min_score]
        
        if not filtered:
            logger.warning(
                "no_results_above_threshold",
                min_score=min_score,
                original_count=len(results)
            )
            return []
        
        # Simple reranking: prefer sections with specific keywords
        # This is a simple heuristic - in production, you might use a more sophisticated reranker
        priority_keywords = [
            "eligibility", "criteria", "requirements", "approval", "decline",
            "risk", "income", "assessment", "policy", "loan"
        ]
        
        def calculate_boost(result: Dict[str, Any]) -> float:
            """Calculate boost score based on content relevance."""
            payload = result.get("payload", {})
            text = payload.get("text", "").lower()
            section_id = payload.get("section_id", "").lower()
            heading_path = payload.get("heading_path", "").lower()
            
            boost = 0.0
            
            # Boost for priority keywords in text
            for keyword in priority_keywords:
                if keyword in text:
                    boost += 0.1
                if keyword in section_id:
                    boost += 0.05
                if keyword in heading_path:
                    boost += 0.05
            
            # Boost for certain section types
            if any(term in section_id for term in ["eligibility", "criteria", "policy"]):
                boost += 0.2
            
            return min(boost, 0.5)  # Cap boost at 0.5
        
        # Apply boost to scores
        for result in filtered:
            boost = calculate_boost(result)
            result["original_score"] = result["score"]
            result["boost"] = boost
            result["score"] = result["score"] + boost
        
        # Sort by boosted score
        reranked = sorted(filtered, key=lambda x: x["score"], reverse=True)
        
        logger.debug(
            "reranking_complete",
            filtered_count=len(filtered),
            reranked_count=len(reranked)
        )
        
        return reranked
    
    def _format_snippets(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format search results into snippet format with enriched metadata.
        
        Args:
            results: Search results with payloads
        
        Returns:
            List of formatted snippets with enriched source information
        """
        snippets = []
        
        for result in results:
            payload = result.get("payload", {})
            
            snippet = {
                "section_id": payload.get("section_id"),
                "section_title": payload.get("section_title"),
                "section_type": payload.get("section_type"),
                "page_start": payload.get("page_start"),
                "page_end": payload.get("page_end"),
                "text": payload.get("text"),
                "heading_path": payload.get("heading_path"),
                "score": result.get("score"),
                "original_score": result.get("original_score"),
                "boost": result.get("boost", 0.0),
                
                # Enriched metadata fields
                "section": payload.get("section"),
                "source_page": payload.get("source_page"),
                "tags": payload.get("tags", []),
                "effective_date": payload.get("effective_date"),
                "source_file": payload.get("source_file"),
                "segment_index": payload.get("segment_index"),
                "chunk_index": payload.get("chunk_index"),
                
                # Reference formatting for LLM responses
                "reference": self._format_reference(payload)
            }
            
            # Clean up None values
            snippet = {k: v for k, v in snippet.items() if v is not None}
            
            snippets.append(snippet)
        
        return snippets
    
    def _format_reference(self, payload: Dict[str, Any]) -> str:
        """
        Format a reference string for source citation.
        
        Args:
            payload: Document payload with metadata
            
        Returns:
            Formatted reference string
        """
        parts = []
        
        # Section reference
        if payload.get("section_title"):
            section_ref = payload["section_title"]
            if payload.get("section_id"):
                section_ref = f"Section {payload['section_id']}: {section_ref}"
            parts.append(section_ref)
        elif payload.get("section_id"):
            parts.append(f"Section {payload['section_id']}")
        
        # Page reference
        page_start = payload.get("page_start")
        page_end = payload.get("page_end")
        if page_start:
            if page_end and page_end != page_start:
                parts.append(f"Pages {page_start}-{page_end}")
            else:
                parts.append(f"Page {page_start}")
        
        # Source file (clean filename)
    # Intentionally omit source_file (PDF name) from user-facing reference to reduce redundancy
    # source_file = payload.get("source_file")
    # if source_file:
    #     filename = source_file.replace(".pdf", "").replace("-", " ").title()
    #     parts.append(filename)
        
        return " | ".join(parts) if parts else "Policy Document"
    
    def retrieve_policy_snippets(
        self,
        decision: str,
        reason_codes: List[str],
        k: int = 3,
        search_k: int = 8,
        min_score: float = 0.1
    ) -> List[Dict[str, Any]]:
        """
        Retrieve policy snippets relevant to a loan decision.
        
        Args:
            decision: Loan decision (APPROVE, DECLINE, COUNTER)
            reason_codes: List of reason codes explaining the decision
            k: Number of final snippets to return
            search_k: Number of candidates to retrieve from vector search
            min_score: Minimum similarity score threshold
        
        Returns:
            List of policy snippets with metadata
        """
        logger.info(
            "retrieval_started",
            decision=decision,
            reason_codes=reason_codes,
            k=k,
            search_k=search_k
        )
        
        try:
            # Build query string
            query_text = self._build_query(decision, reason_codes)
            
            # Get query embedding
            query_vector = self._safe_embedding(query_text)
            
            # Perform vector search
            search_results = self._search_vectors(query_vector, top_k=search_k)
            
            if not search_results:
                logger.warning("no_search_results")
                return []
            
            # Filter and rerank
            filtered_results = self._filter_and_rerank(search_results, min_score=min_score)
            
            if not filtered_results:
                logger.warning("no_results_after_filtering")
                return []
            
            # Take top k results
            top_results = filtered_results[:k]
            
            # Format as snippets
            snippets = self._format_snippets(top_results)
            
            logger.info(
                "retrieval_complete",
                query=query_text,
                search_results=len(search_results),
                filtered_results=len(filtered_results),
                final_snippets=len(snippets)
            )
            
            return snippets
            
        except Exception as e:
            logger.error(
                "retrieval_failed",
                decision=decision,
                reason_codes=reason_codes,
                error=str(e)
            )
            raise
    
    def search_by_text(self, query_text: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Search policy documents by free text query.
        
        Args:
            query_text: Free text search query
            k: Number of results to return
        
        Returns:
            List of relevant snippets
        """
        logger.info("text_search_started", query=query_text, k=k)
        
        try:
            # Get query embedding
            query_vector = self._safe_embedding(query_text)
            
            # Perform vector search
            search_results = self._search_vectors(query_vector, top_k=k * 2)
            
            # Light filtering (lower threshold for free text search)
            filtered_results = self._filter_and_rerank(search_results, min_score=0.05)
            
            # Take top k results
            top_results = filtered_results[:k]
            
            # Format as snippets
            snippets = self._format_snippets(top_results)
            
            logger.info(
                "text_search_complete",
                query=query_text,
                results=len(snippets)
            )
            
            return snippets
            
        except Exception as e:
            logger.error("text_search_failed", query=query_text, error=str(e))
            raise

    def similarity_search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Perform similarity search for documents based on a user question.
        
        Args:
            query: User question or search query
            top_k: Number of top results to return
        
        Returns:
            List of relevant documents with enriched metadata
        """
        logger.debug("similarity_search", query=query, top_k=top_k)
        
        try:
            # Get query embedding
            query_vector = self._safe_embedding(query)
            
            # Perform vector search
            search_results = self._search_vectors(query_vector, top_k=top_k * 2)  # Get more for filtering
            
            if not search_results:
                logger.warning("no_search_results_for_query", query=query)
                return []
            
            # Filter by minimum score and take top_k
            min_score = 0.3  # Higher threshold for direct questions
            filtered_results = [r for r in search_results if r["score"] >= min_score]
            
            # Take top k results
            top_results = filtered_results[:top_k]
            
            # Convert to document format with enriched metadata
            documents = []
            for result in top_results:
                payload = result.get("payload", {})
                
                # Create a document-like object that works with LangChain and includes enriched metadata
                doc = {
                    "page_content": payload.get("text", ""),
                    "metadata": {
                        # Core metadata
                        "section_id": payload.get("section_id"),
                        "section_title": payload.get("section_title"),
                        "section_type": payload.get("section_type"),
                        "heading_path": payload.get("heading_path"),
                        "page_start": payload.get("page_start"),
                        "page_end": payload.get("page_end"),
                        "source_file": payload.get("source_file"),
                        "tokens": payload.get("tokens"),
                        "segment_index": payload.get("segment_index"),
                        "chunk_index": payload.get("chunk_index"),
                        
                        # Enriched metadata
                        "section": payload.get("section"),
                        "source_page": payload.get("source_page"),
                        "tags": payload.get("tags", []),
                        "effective_date": payload.get("effective_date"),
                        
                        # Reference for citation
                        "reference": self._format_reference(payload)
                    },
                    "score": result.get("score", 0.0)
                }
                documents.append(doc)
            
            logger.info(
                "similarity_search_complete",
                query=query,
                results_found=len(documents),
                avg_score=sum(d["score"] for d in documents) / len(documents) if documents else 0
            )
            
            return documents
            
        except Exception as e:
            logger.error("similarity_search_failed", query=query, error=str(e))
            return []


# Global retriever instance
_retriever = None


def get_retriever() -> PolicyRetriever:
    """Get global retriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = PolicyRetriever()
    return _retriever


def retrieve_policy_snippets(
    decision: str,
    reason_codes: List[str],
    k: int = 3,
    search_k: int = 8,
    min_score: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Convenience function to retrieve policy snippets.
    
    Args:
        decision: Loan decision (APPROVE, DECLINE, COUNTER)
        reason_codes: List of reason codes
        k: Number of snippets to return
        search_k: Number of candidates to search
        min_score: Minimum similarity score
    
    Returns:
        List of policy snippets
    """
    retriever = get_retriever()
    return retriever.retrieve_policy_snippets(
        decision=decision,
        reason_codes=reason_codes,
        k=k,
        search_k=search_k,
        min_score=min_score
    )


def search_policy_by_question(question: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Convenience function to search policy by user question.
    
    Args:
        question: User question
        top_k: Number of documents to return
    
    Returns:
        List of relevant documents
    """
    retriever = get_retriever()
    return retriever.similarity_search(question, top_k=top_k)


if __name__ == "__main__":
    # Simple CLI for testing
    import argparse
    
    parser = argparse.ArgumentParser(description="Test policy retrieval")
    parser.add_argument("--decision", default="DECLINE", help="Loan decision")
    parser.add_argument("--reasons", nargs="+", default=["High risk score"], help="Reason codes")
    parser.add_argument("--k", type=int, default=3, help="Number of snippets")
    parser.add_argument("--query", help="Free text query (overrides decision/reasons)")
    
    args = parser.parse_args()
    
    retriever = PolicyRetriever()
    
    if args.query:
        results = retriever.search_by_text(args.query, k=args.k)
    else:
        results = retriever.retrieve_policy_snippets(args.decision, args.reasons, k=args.k)
    
    print(f"\n🔍 Retrieved {len(results)} snippets:")
    for i, snippet in enumerate(results, 1):
        print(f"\n{i}. Section: {snippet.get('section_id', 'Unknown')}")
        print(f"   Score: {snippet.get('score', 0):.3f}")
        print(f"   Text: {snippet.get('text', '')[:200]}...")
        if snippet.get('page_start'):
            print(f"   Page: {snippet['page_start']}-{snippet.get('page_end', snippet['page_start'])}") 