#!/usr/bin/env python
"""Direct in-process RAG + decision endpoint manual test.

Runs FastAPI app in-process (TestClient) and exercises several policy questions,
printing decision, reference count, first reference, and answer snippet. Also
prints retriever fallback mode so you know if Qdrant was used or in-memory.
"""
import os, sys
from fastapi.testclient import TestClient

# Ensure project root on path when executed directly
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.api.main import create_app
from app.rag.retriever import get_retriever

QUESTIONS = [
    "What are the eligibility requirements for a small business loan?",
    "List the available loan products",
    "What collateral is required for secured loans?",
    "Explain the interest rate policy"
]

def main():
    app = create_app()
    client = TestClient(app)

    # Login
    resp = client.post("/v1/auth/login", json={"user_id": "1", "password": os.getenv("TEST_PASSWORD", "")})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    results = []
    for q in QUESTIONS:
        r = client.post("/v1/decision", json={"client_id": 1, "question": q}, headers=headers)
        status = r.status_code
        try:
            data = r.json()
        except Exception:
            data = {"_raw": r.text}
        refs = data.get("references", []) if isinstance(data, dict) else []
        results.append({
            "question": q,
            "status": status,
            "decision": data.get("decision"),
            "ref_count": len(refs),
            "first_ref": refs[0] if refs else None,
            "answer_snippet": (data.get("answer", "")[:160] + ("..." if len(data.get("answer", ""))>160 else "")) if isinstance(data, dict) else None
        })

    # Show retriever mode
    r = get_retriever()
    print(f"\nRetriever fallback_mode={getattr(r,'fallback_mode', False)} loaded_docs={len(getattr(r,'_fallback_docs', []))}")

    for res in results:
        print(f"Q: {res['question']}\n status={res['status']} decision={res['decision']} refs={res['ref_count']}")
        if res['first_ref']:
            print(f" first_ref={res['first_ref']}")
        print(f" answer={res['answer_snippet']}\n")

if __name__ == "__main__":
    main()
