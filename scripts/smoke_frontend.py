#!/usr/bin/env python3
"""
Frontend Smoke Test (Python)

How to run: python .\scripts\smoke_frontend.py

Tests the loan decision API through Next.js proxy at http://localhost:3000/api.
Validates authentication, decision endpoints, and response schemas.
"""

import sys
import os
import json
import requests
from typing import Dict, Any, Optional, List

BASE_URL = "http://localhost:3000/api"
TIMEOUT = 10

class SmokeTest:
    def __init__(self):
        self.exit_code = 0
        self.session = requests.Session()
        self.session.timeout = TIMEOUT
    
    def test_endpoint(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                     headers: Optional[Dict] = None, description: str = "") -> Optional[Dict]:
        """Test an API endpoint and return response or None on failure."""
        print(f"\n[{method}] {endpoint}")
        print(f"Test: {description}")
        
        url = f"{BASE_URL}{endpoint}"
        request_headers = headers or {}
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, headers=request_headers)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, headers=request_headers)
            else:
                response = self.session.request(method, url, json=data, headers=request_headers)
            
            response.raise_for_status()
            print("✓ Status: 200 OK")
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed: {e}")
            self.exit_code = 1
            return None
    
    def test_schema(self, response: Dict[str, Any], test_name: str) -> None:
        """Validate response schema and print errors."""
        errors = []
        
        # Check decision field
        if "decision" not in response:
            errors.append("Missing 'decision' field")
        elif response["decision"] not in ["INFORM", "APPROVE", "DECLINE", "COUNTER", "REFUSE"]:
            errors.append(f"Invalid decision: {response['decision']}")
        
        # Check answer field for non-REFUSE decisions
        if response.get("decision") != "REFUSE":
            if not response.get("answer") or len(response["answer"]) == 0:
                errors.append(f"Missing or empty 'answer' field for {response.get('decision')}")
        
        # Check references field
        if "references" not in response:
            errors.append("Missing 'references' field")
        elif not isinstance(response["references"], list):
            errors.append("'references' is not an array")
        elif response.get("decision") == "INFORM" and len(response["references"]) == 0:
            errors.append(f"INFORM decision should have references.length ≥ 1, got {len(response['references'])}")
        
        if not errors:
            print("✓ Schema valid")
        else:
            print("✗ Schema errors:")
            for error in errors:
                print(f"  - {error}")
            self.exit_code = 1
    
    def show_response_summary(self, response: Dict[str, Any], test_name: str) -> None:
        """Display a summary of the response."""
        if not response:
            return
        
        # Truncate answer to 120 characters
        answer = response.get("answer", "(no answer)")
        if len(answer) > 120:
            answer = answer[:120] + "..."
        
        print(f"Decision: {response.get('decision')}")
        print(f"Answer: {answer}")
        print(f"References: {len(response.get('references', []))}")
        
        # Show RAG debug info if available
        metadata = response.get("metadata", {})
        rag_debug = metadata.get("rag_debug")
        if rag_debug:
            collection = rag_debug.get("collection", "unknown")
            query = rag_debug.get("query", "unknown")
            snippets_found = rag_debug.get("snippets_found", 0)
            print(f"RAG Debug: collection={collection}, query='{query}', snippets={snippets_found}")
    
    def run(self) -> int:
        """Run all smoke tests and return exit code."""
        print("=== Frontend Proxy Smoke Test ===")
        print(f"Base URL: {BASE_URL}")
        
        # Test 1: Health Check
        health = self.test_endpoint("GET", "/health", description="Health check")
        if health:
            print("Health status: OK")
        
        # Test 2: Login
        login_data = {
            "user_id": os.getenv("TEST_USER_ID", "101"),
            "password": os.getenv("TEST_PASSWORD", "")
        }
        login_response = self.test_endpoint("POST", "/v1/auth/login", data=login_data, description="User authentication")
        
        if not login_response or "access_token" not in login_response:
            print("✗ Login failed - cannot continue with authenticated tests")
            self.exit_code = 1
            return self.exit_code
        
        print("✓ Login successful")
        auth_headers = {
            "Authorization": f"Bearer {login_response['access_token']}"
        }
        
        # Test 3: Informational Decision
        info_data = {
            "question": "What are the car loan requirements?",
            "autonomous": True
        }
        info_response = self.test_endpoint("POST", "/v1/decision", data=info_data, 
                                         headers=auth_headers, description="Informational query")
        if info_response:
            self.test_schema(info_response, "Informational")
            self.show_response_summary(info_response, "Informational")
        
        # Test 4: Eligibility Decision
        elig_data = {
            "question": "Am I eligible for a $5,000 personal loan?",
            "autonomous": True
        }
        elig_response = self.test_endpoint("POST", "/v1/decision", data=elig_data,
                                         headers=auth_headers, description="Eligibility query")
        if elig_response:
            self.test_schema(elig_response, "Eligibility")
            self.show_response_summary(elig_response, "Eligibility")
        
        # Summary
        print("\n=== Test Summary ===")
        if self.exit_code == 0:
            print("✓ All tests PASSED")
        else:
            print("✗ Some tests FAILED")
        
        return self.exit_code


if __name__ == "__main__":
    test = SmokeTest()
    exit_code = test.run()
    sys.exit(exit_code)
