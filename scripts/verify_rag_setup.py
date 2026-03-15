#!/usr/bin/env python3
"""Verification script for RAG setup and functionality."""

import sys
import asyncio
from pathlib import Path

# Add app directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.rag.index_policy import PolicyIndexer
from app.rag.retriever import get_retriever
from app.utils.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def verify_rag_setup():
    """Verify RAG setup is working properly."""
    print("🔧 Verifying RAG Setup...")
    
    # 1. Check if policy chunks file exists
    chunks_path = settings.data.policy_chunks
    if not Path(chunks_path).exists():
        print(f"❌ Policy chunks file not found: {chunks_path}")
        return False
    
    print(f"✅ Policy chunks file found: {chunks_path}")
    
    # Count lines in JSONL file
    with open(chunks_path, 'r', encoding='utf-8') as f:
        line_count = sum(1 for line in f)
    print(f"📄 JSONL file contains {line_count} lines")
    
    # 2. Check Qdrant collection
    try:
        indexer = PolicyIndexer()
        info = indexer.get_collection_info()
        
        if info:
            print(f"✅ Qdrant collection '{info['name']}' exists with {info['points_count']} points")
            
            if info['points_count'] != line_count:
                print(f"⚠️ Point count mismatch: {info['points_count']} points vs {line_count} lines")
                print("   Consider re-running indexing")
            else:
                print("✅ Point count matches JSONL line count")
        else:
            print("❌ Qdrant collection not found")
            return False
            
    except Exception as e:
        print(f"❌ Qdrant connection failed: {e}")
        return False
    
    # 3. Test retriever
    try:
        print("\n🔍 Testing Retriever...")
        retriever = get_retriever()
        
        # Test question-based search
        test_queries = [
            "loan terms in Oklahoma",
            "eligibility requirements",
            "interest rates",
        ]
        
        for query in test_queries:
            docs = retriever.similarity_search(query, top_k=3)
            print(f"Query: '{query}' → {len(docs)} results")
            
            if docs:
                for i, doc in enumerate(docs[:2]):
                    content = doc.get('page_content', '')
                    score = doc.get('score', 0)
                    print(f"  {i+1}. [{score:.3f}] {content[:80]}...")
            else:
                print("  No results found")
        
        print("✅ Retriever tests completed")
        
    except Exception as e:
        print(f"❌ Retriever test failed: {e}")
        return False
    
    print("\n🎉 RAG setup verification completed successfully!")
    return True


async def main():
    """Main function."""
    success = await verify_rag_setup()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main()) 