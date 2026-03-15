#!/usr/bin/env python3
"""End-to-end test of RAG functionality."""

import sys
import asyncio
from pathlib import Path

# Add app directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.graph.workflow import generate_answer
from app.rag.retriever import search_policy_by_question
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def test_rag_e2e():
    """Test end-to-end RAG functionality."""
    print("🧪 Testing End-to-End RAG Functionality...")
    
    # Test 1: Direct retriever search
    print("\n1️⃣ Testing Direct Retriever Search")
    test_question = "What are the loan terms in Oklahoma?"
    
    try:
        docs = search_policy_by_question(test_question, top_k=3)
        print(f"✅ Found {len(docs)} documents for: '{test_question}'")
        
        for i, doc in enumerate(docs):
            content = doc.get('page_content', '')
            score = doc.get('score', 0)
            print(f"  📄 Doc {i+1} [score: {score:.3f}]: {content[:100]}...")
            
    except Exception as e:
        print(f"❌ Direct retriever test failed: {e}")
        return False
    
    # Test 2: Full workflow (simulated user ID)
    print("\n2️⃣ Testing Full Workflow")
    test_user_id = 101
    
    try:
        print(f"🔍 Running workflow for question: '{test_question}'")
        final_answer, metadata = await generate_answer(test_user_id, test_question)
        
        print("✅ Workflow completed successfully!")
        print(f"📊 Metadata: {metadata}")
        print(f"💬 Final Answer: {final_answer}")
        
        # Check if we got snippets
        snippets = metadata.get('snippets', [])
        print(f"📚 Retrieved {len(snippets)} snippets:")
        for i, snippet in enumerate(snippets):
            print(f"  📄 Snippet {i+1}: {snippet[:80]}...")
            
    except Exception as e:
        print(f"❌ Full workflow test failed: {e}")
        return False
    
    print("\n🎉 End-to-end RAG test completed successfully!")
    return True


async def main():
    """Main function."""
    success = await test_rag_e2e()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main()) 