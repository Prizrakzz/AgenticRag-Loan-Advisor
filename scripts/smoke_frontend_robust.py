"""
Frontend Smoke Test (Python) - ROBUST EDITION
Tests eligibility requirements (no 400 errors) and references display

How to run: python .\scripts\smoke_frontend_robust.py
"""

import requests
import json
import sys
import os

BASE = "http://localhost:3000/api"

def main():
    print("=== Frontend Proxy Smoke Test (Robust Edition) ===")
    print(f"Base URL: {BASE}")
    
    try:
        # Test 1: Health check
        print("[GET] /health")
        print("Test: Health check")
        response = requests.get(f"{BASE}/health", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Status: 200 OK")
        health_data = response.json()
        print(f"Health status: {health_data.get('status', 'Unknown')}")
        
        # Test 2: Authentication
        print("[POST] /v1/auth/login")
        print("Test: User authentication")
        login_data = {"user_id": os.getenv("TEST_USER_ID", "101"), "password": os.getenv("TEST_PASSWORD", "")}
        response = requests.post(f"{BASE}/v1/auth/login", json=login_data, timeout=10)
        assert response.status_code == 200, f"Login failed with {response.status_code}: {response.text}"
        print("✓ Status: 200 OK")
        print("✓ Login successful")
        
        auth_data = response.json()
        token = auth_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test 3: Informational query (must have references)
        print("[POST] /v1/decision")
        print("Test: Informational query")
        decision_data = {"question": "What are the eligibility requirements?"}
        
        response = requests.post(f"{BASE}/v1/decision", json=decision_data, headers=headers, timeout=30)
        assert response.status_code == 200, f"Decision failed with {response.status_code}: {response.text}"
        print("✓ Status: 200 OK")
        
        result = response.json()
        decision = result.get("decision")
        answer = result.get("answer", "")
        references = result.get("references", [])
        
        # Validate schema
        schema_errors = []
        if decision != "INFORM":
            schema_errors.append(f"Expected INFORM decision, got {decision}")
        if not answer or answer.strip() == "":
            schema_errors.append("Missing or empty 'answer' field for INFORM")
        if len(references) < 1:
            schema_errors.append("INFORM decision should have references.length ≥ 1, got 0")
        
        if schema_errors:
            print("✗ Schema errors:")
            for error in schema_errors:
                print(f"  - {error}")
            print(f"Decision: {decision}")
            print(f"Answer: {answer[:50]}..." if answer else "(no answer)")
            print(f"References: {len(references)}")
            return False
        else:
            print("✓ Schema valid")
            print(f"Decision: {decision}")
            print(f"Answer: {answer[:60]}...")
            print(f"References: {len(references)}")
            
            # Check for references line
            metadata = result.get("metadata", {})
            if metadata.get("references_line"):
                print(f"✓ References line: {metadata['references_line']}")
            else:
                # Synthesize references line
                ref_parts = []
                for ref in references:
                    source = ref.get("source", "S?")
                    section = ref.get("section", "Unknown")
                    page = ref.get("page", 1)
                    ref_parts.append(f"{source} — {section} (p.{page})")
                ref_line = f"References: {'; '.join(ref_parts)}"
                print(f"✓ Synthesized references: {ref_line}")
        
        # Test 4: Eligibility query (must not return 400)
        print("[POST] /v1/decision")
        print("Test: Eligibility query")
        eligibility_data = {"question": "Am I eligible for a $25,000 car loan?"}
        
        response = requests.post(f"{BASE}/v1/decision", json=eligibility_data, headers=headers, timeout=30)
        
        # Critical: Must not be 400
        if response.status_code == 400:
            print("✗✗ CRITICAL: Got 400 error on eligibility request!")
            print(f"Response: {response.text}")
            return False
        
        assert response.status_code == 200, f"Eligibility failed with {response.status_code}: {response.text}"
        print("✓ Status: 200 OK")
        
        result = response.json()
        decision = result.get("decision")
        answer = result.get("answer", "")
        
        # Validate eligibility response
        valid_decisions = ["APPROVE", "DECLINE", "COUNTER"]
        schema_errors = []
        
        if decision not in valid_decisions:
            schema_errors.append(f"Invalid eligibility decision: {decision}")
        if not answer or len(answer.strip()) < 10:
            schema_errors.append("Missing or empty 'answer' field for eligibility")
        
        if schema_errors:
            print("✗ Schema errors:")
            for error in schema_errors:
                print(f"  - {error}")
            print(f"Decision: {decision}")
            print(f"Answer: {answer[:50]}..." if answer else "(no answer)")
            return False
        else:
            print("✓ Schema valid")
            print(f"Decision: {decision}")
            print(f"Answer: {answer[:60]}...")
            
            # If COUNTER, check for specific missing items
            if decision == "COUNTER":
                missing_keywords = ["pay stubs", "employment", "DTI", "documentation", "verification"]
                if any(keyword in answer.lower() for keyword in missing_keywords):
                    print("✓ COUNTER response lists specific missing items")
                else:
                    print("! COUNTER response should list specific missing items")
        
        print("=== Test Summary ===")
        print("✓ All tests PASSED")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Request failed: {e}")
        return False
    except AssertionError as e:
        print(f"✗ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
