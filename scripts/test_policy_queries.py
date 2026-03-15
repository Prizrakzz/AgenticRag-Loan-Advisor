#!/usr/bin/env python
"""Ad-hoc test script to exercise policy retrieval (fallback or Qdrant)."""
from app.rag.retriever import get_retriever

queries = [
    "eligibility requirements",
    "interest rates",
    "loan products",
    "collateral requirements",
    "maximum loan amount",
]

r = get_retriever()
print(f"Fallback mode: {getattr(r, 'fallback_mode', False)}")
print(f"Loaded fallback docs: {len(getattr(r, '_fallback_docs', []))}")

for q in queries:
    docs = r.similarity_search(q, top_k=3)
    print(f"\nQuery: {q}")
    if not docs:
        print("  -> No results")
        continue
    for i, d in enumerate(docs, 1):
        score = d.get('score') or d.get('metadata', {}).get('score')
        text = d.get('page_content') or d.get('text') or ''
        meta = d.get('metadata', {})
        ref = meta.get('reference') or meta.get('section_title') or meta.get('section_id')
        print(f"  {i}. score={score:.3f} ref={ref} text={text[:120].replace('\n',' ')}...")
