#!/usr/bin/env python3
"""Simple test to verify clean reference formatting"""

import sys
import os
import requests
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_clean_references():
    """Test that references no longer contain PDF filename"""
    print("Testing clean reference formatting...")
    
    # First, get a token (using the hardcoded auth pattern)
    login_data = {"user_id": "1", "password": os.getenv("TEST_PASSWORD", "")}
    
    try:
        # Login
        login_response = requests.post("http://localhost:8000/v1/auth/login", json=login_data)
        if login_response.status_code != 200:
            print(f"Login failed: {login_response.status_code}")
            return
            
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Test question
        decision_data = {"client_id": 1, "question": "what are the commercial loan rates"}
        
        # Make decision request
        response = requests.post("http://localhost:8000/v1/decision", json=decision_data, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            print(f"\nStatus: SUCCESS")
            print(f"Decision: {result.get('decision')}")
            print(f"Answer: {result.get('answer')[:100]}...")
            
            references = result.get('references', [])
            print(f"\nReferences ({len(references)} found):")
            
            pdf_found = False
            for i, ref in enumerate(references):
                ref_text = f"{ref.get('source')}: {ref.get('section')} (p.{ref.get('page')})"
                print(f"  {ref_text}")
                
                # Check if PDF filename is present
                if 'cpcdc-commercial-lending-program-loan-policy.pdf' in ref_text:
                    pdf_found = True
                    
            if pdf_found:
                print("\n❌ FAILED: PDF filename still present in references")
            else:
                print("\n✅ SUCCESS: No PDF filename found in references")
                
        else:
            print(f"Decision request failed: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"Test failed with error: {e}")

if __name__ == "__main__":
    test_clean_references()
