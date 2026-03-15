#!/usr/bin/env python3
"""Policy document indexer for the loan approval system."""

import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add app directory to Python path
sys.path.append(str(Path(__file__).parent.parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.graph.store import embed_texts, get_embedding_dimension
from app.utils.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PolicyIndexer:
    """Policy document indexer using Qdrant vector store."""
    
    def __init__(self, collection_name: str = None):
        self.collection_name = collection_name or settings.vector.collection_name
        self.chunks_path = settings.data.policy_chunks
        self.meta_path = Path("data/.policy_index.meta")
        
        # Initialize Qdrant client
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=False
        )
        
        logger.info(
            "indexer_initialized",
            collection_name=self.collection_name,
            chunks_path=self.chunks_path,
            qdrant_url=settings.qdrant_url
        )
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file."""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _load_index_metadata(self) -> Dict[str, Any]:
        """Load indexing metadata from file."""
        if not self.meta_path.exists():
            return {}
        
        try:
            with open(self.meta_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning("failed_to_load_metadata", error=str(e))
            return {}
    
    def _save_index_metadata(self, metadata: Dict[str, Any]):
        """Save indexing metadata to file."""
        try:
            self.meta_path.parent.mkdir(exist_ok=True)
            with open(self.meta_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.debug("metadata_saved", path=str(self.meta_path))
        except Exception as e:
            logger.error("failed_to_save_metadata", error=str(e))
    
    def _needs_reindex(self, force: bool = False) -> bool:
        """Check if reindexing is needed based on file hash."""
        if force:
            logger.info("reindex_forced")
            return True
        
        if not Path(self.chunks_path).exists():
            logger.error("chunks_file_not_found", path=self.chunks_path)
            return False
        
        current_hash = self._calculate_file_hash(self.chunks_path)
        metadata = self._load_index_metadata()
        stored_hash = metadata.get("file_hash")
        
        if current_hash != stored_hash:
            logger.info(
                "file_changed_reindex_needed",
                current_hash=current_hash[:16] + "...",
                stored_hash=(stored_hash[:16] + "...") if stored_hash else "none"
            )
            return True
        
        logger.info("file_unchanged_skipping_reindex")
        return False
    
    def _ensure_collection(self):
        """Ensure Qdrant collection exists with correct configuration."""
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_exists = any(
                collection.name == self.collection_name 
                for collection in collections.collections
            )
            
            if collection_exists:
                logger.info("collection_exists", name=self.collection_name)
                return
            
            # Create collection
            embedding_dim = get_embedding_dimension()
            
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=embedding_dim,
                    distance=models.Distance.COSINE
                )
            )
            
            logger.info(
                "collection_created",
                name=self.collection_name,
                dimension=embedding_dim
            )
            
        except Exception as e:
            logger.error("failed_to_ensure_collection", error=str(e))
            raise
    
    def _load_chunks(self) -> List[Dict[str, Any]]:
        """Load policy chunks from JSONL file."""
        chunks = []
        
        try:
            with open(self.chunks_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        chunk = json.loads(line.strip())
                        chunks.append(chunk)
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "invalid_json_line",
                            line_num=line_num,
                            error=str(e)
                        )
                        continue
            
            logger.info("chunks_loaded", count=len(chunks))
            return chunks
            
        except Exception as e:
            logger.error("failed_to_load_chunks", error=str(e))
            raise
    
    def _prepare_documents(self, chunks: List[Dict[str, Any]]) -> tuple[List[str], List[Dict[str, Any]]]:
        """Prepare documents for embedding and indexing."""
        texts = []
        documents = []
        
        for chunk in chunks:
            # Extract text for embedding
            text = chunk.get("text", "")
            if not text:
                logger.warning("empty_text_chunk", chunk_id=chunk.get("id"))
                continue
            
            texts.append(text)
            
            # Prepare document metadata (extract from nested metadata and top-level enriched fields)
            metadata = chunk.get("metadata", {})
            document = {
                "id": chunk.get("id"),
                "text": text,
                
                # Core metadata fields (from original structure)
                "section_id": metadata.get("section_id"),
                "section_title": metadata.get("section_title"),
                "section_type": metadata.get("section_type"),
                "heading_path": metadata.get("heading_path"),
                "page_start": metadata.get("page_start"),
                "page_end": metadata.get("page_end"),
                "tokens": metadata.get("tokens"),
                "source_file": metadata.get("source_file"),
                "segment_index": metadata.get("segment_index"),
                "chunk_index": metadata.get("chunk_index"),
                
                # Enriched metadata fields (from top-level)
                "section": chunk.get("section"),
                "source_page": chunk.get("source_page"),
                "tags": chunk.get("tags", []),
                "effective_date": chunk.get("effective_date")
            }
            documents.append(document)
        
        logger.info("documents_prepared", count=len(documents))
        return texts, documents
    
    def _upsert_documents(self, texts: List[str], documents: List[Dict[str, Any]]):
        """Upsert documents to Qdrant collection."""
        if not texts or not documents:
            logger.warning("no_documents_to_upsert")
            return
        
        # Generate embeddings
        logger.info("generating_embeddings", count=len(texts))
        embeddings = embed_texts(texts)
        
        if len(embeddings) != len(documents):
            raise ValueError(f"Embedding count mismatch: {len(embeddings)} != {len(documents)}")
        
        # Prepare points for Qdrant
        points = []
        for i, (embedding, doc) in enumerate(zip(embeddings, documents)):
            point = models.PointStruct(
                id=hash(doc["id"]) % (2**63),  # Convert string ID to int
                vector=embedding,
                payload=doc
            )
            points.append(point)
        
        # Upsert to Qdrant
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            
            logger.info(
                "documents_upserted",
                collection=self.collection_name,
                count=len(points)
            )
            
        except Exception as e:
            logger.error("failed_to_upsert", error=str(e))
            raise
    
    def index_policy(self, force: bool = False) -> bool:
        """
        Index policy documents.
        
        Args:
            force: Force reindexing even if file hasn't changed
        
        Returns:
            True if indexing was performed, False if skipped
        """
        logger.info("indexing_started", force=force)
        
        try:
            # Check if reindexing is needed
            if not self._needs_reindex(force=force):
                return False
            
            # Ensure collection exists
            self._ensure_collection()
            
            # Load chunks
            chunks = self._load_chunks()
            if not chunks:
                logger.warning("no_chunks_found")
                return False
            
            # Prepare documents
            texts, documents = self._prepare_documents(chunks)
            if not documents:
                logger.warning("no_valid_documents")
                return False
            
            # Upsert documents
            self._upsert_documents(texts, documents)
            
            # Save metadata
            file_hash = self._calculate_file_hash(self.chunks_path)
            metadata = {
                "file_hash": file_hash,
                "indexed_count": len(documents),
                "collection_name": self.collection_name,
                "indexed_at": str(Path(self.chunks_path).stat().st_mtime)
            }
            self._save_index_metadata(metadata)
            
            logger.info(
                "indexing_complete",
                documents_indexed=len(documents),
                collection=self.collection_name
            )
            
            return True
            
        except Exception as e:
            logger.error("indexing_failed", error=str(e))
            raise
    
    def get_collection_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the collection."""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "points_count": collection_info.points_count,
                "vectors_count": collection_info.vectors_count,
                "status": collection_info.status
            }
        except Exception as e:
            logger.error("failed_to_get_collection_info", error=str(e))
            return None


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(description="Index policy documents")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Force reindexing even if file hasn't changed"
    )
    parser.add_argument(
        "--collection-name",
        default=settings.vector.collection_name,
        help=f"Collection name (default: {settings.vector.collection_name})"
    )
    parser.add_argument(
        "--chunks-path",
        default=settings.data.policy_chunks,
        help=f"Path to chunks JSONL file (default: {settings.data.policy_chunks})"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Alias for --reindex"
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Show collection information"
    )
    
    args = parser.parse_args()
    
    # Override settings if provided
    if args.chunks_path != settings.data.policy_chunks:
        settings.data.policy_chunks = args.chunks_path
    
    indexer = PolicyIndexer(collection_name=args.collection_name)
    
    if args.info:
        info = indexer.get_collection_info()
        if info:
            print(f"Collection: {info['name']}")
            print(f"Points: {info['points_count']}")
            print(f"Vectors: {info['vectors_count']}")
            print(f"Status: {info['status']}")
        else:
            print("Collection not found or error occurred")
        sys.exit(0)
    
    force = args.reindex or args.force
    
    try:
        indexed = indexer.index_policy(force=force)
        
        if indexed:
            print("✅ Policy indexing completed successfully")
            
            # Show collection info
            info = indexer.get_collection_info()
            if info:
                print(f"📊 Collection '{info['name']}' now has {info['points_count']} documents")
        else:
            print("ℹ️ No indexing needed (file unchanged)")
        
        # Verification snippet - check Qdrant point count
        from qdrant_client import QdrantClient
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=False
        )
        try:
            info = client.get_collection(indexer.collection_name)
            print(f"⚡️ Qdrant has {info.points_count} points in collection '{indexer.collection_name}'")
        except Exception as e:
            print(f"⚠️ Could not verify collection: {e}")
        
        sys.exit(0)
        
    except Exception as e:
        print(f"❌ Indexing failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 