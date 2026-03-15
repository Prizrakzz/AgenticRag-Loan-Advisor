#!/usr/bin/env python3
"""
Python test script for anti-hedging eligibility decisions.
Tests that eligibility responses are decisive without hedging phrases.
"""

import requests
import json
import sys
import os
import re

BASE_URL = "http://localhost:3000/api"

def test_eligibility_no_hedge():
    """Test that eligibility decisions are decisive without hedging."""
    print("=== Anti-Hedging Eligibility Test (Python) ===")
    
    # Step 1: Login
    try:
        login_response = requests.post(
            f"{BASE_URL}/v1/auth/login",
            json={"user_id": os.getenv("TEST_USER_ID", "101"), "password": os.getenv("TEST_PASSWORD", "")},
            headers={"Content-Type": "application/json"}
        )
        login_response.raise_for_status()
        token = login_response.json()["access_token"]
        print("✓ Login successful")
    except Exception as e:
        print(f"✗ Login failed: {e}")
        return False
    
    # Step 2: Test eligibility question
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        decision_response = requests.post(
            f"{BASE_URL}/v1/decision",
            json={"question": "Am I eligible for a $25,000 car loan?"},
            headers=headers
        )
        decision_response.raise_for_status()
        
        data = decision_response.json()
        decision = data["decision"]
        answer = data["answer"]
        answer_preview = answer[:120]
        
        print(f"Decision: {decision}")
        print(f"Answer preview: {answer_preview}...")
        
        # Validate decision type
        if decision not in ["APPROVE", "DECLINE", "COUNTER"]:
            print(f"✗ Invalid decision type: {decision}")
            return False
        
        # Check for hedging if APPROVE/DECLINE
        if decision in ["APPROVE", "DECLINE"]:
            hedging_phrases = [
                "depend on", "depends on", "will depend", "may vary", 
                "cannot determine", "insufficient", "need more details", "specific policies"
            ]
            answer_lower = answer.lower()
            
            hedging_found = False
            for phrase in hedging_phrases:
                if phrase in answer_lower:
                    print(f"✗ Hedging phrase detected: '{phrase}'")
                    hedging_found = True
            
            if not hedging_found:
                print("✓ No hedging detected in decisive answer")
                return True
            else:
                return False
        else:
            print("✓ COUNTER decision (acceptable when data missing)")
            return True
            
    except Exception as e:
        print(f"✗ Decision request failed: {e}")
        return False

if __name__ == "__main__":
    success = test_eligibility_no_hedge()
    if success:
        print("=== All tests PASSED ===")
        sys.exit(0)
    else:
        print("=== Test FAILED ===")
        sys.exit(1)
