#!/usr/bin/env python3
"""
Python RAG Verification Script
Tests that single-agent uses existing Qdrant collection and returns references
"""

import requests
import json
import sys
import os
from typing import Dict, Any, List, Union

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
USERNAME = os.getenv("TEST_USERNAME", "admin")
PASSWORD = os.getenv("TEST_PASSWORD", "")

# Test cases that must return INFORM with references
TEST_CASES = [
    {
        "name": "Eligibility Requirements",
        "question": "What are the eligibility requirements?",
        "expected_decision": "INFORM",
        "expected_section_contains": "Eligibility"
    },
    {
        "name": "Collateral Requirements",
        "question": "Do you require collateral for commercial loans?", 
        "expected_decision": "INFORM",
        "expected_section_contains": ["collateral", "loan", "commercial"]
    }
]

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    END = '\033[0m'

def print_colored(text: str, color: str) -> None:
    print(f"{color}{text}{Colors.END}")

def get_auth_token(base_url: str, username: str, password: str) -> str:
    """Get authentication token"""
    try:
        response = requests.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()["access_token"]
    
    except Exception as e:
        print_colored(f"❌ Login failed: {str(e)}", Colors.RED)
        return None

def test_single_agent_response(
    base_url: str, 
    token: str, 
    question: str, 
    expected_decision: str,
    expected_section_contains: Union[str, List[str]]
) -> bool:
    """Test single agent response for RAG integration"""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    body = {
        "question": question,
        "context": {
            "session_id": f"rag_verify_{int(1000000 * __import__('time').time())}"
        }
    }
    
    try:
        response = requests.post(f"{base_url}/ask", json=body, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Validate decision
        decision = data.get("decision")
        if decision != expected_decision:
            print_colored(f"❌ Wrong decision: expected {expected_decision}, got {decision}", Colors.RED)
            return False
        
        # Validate references exist
        references = data.get("references", [])
        if not references:
            print_colored("❌ No references found", Colors.RED)
            return False
        
        # Validate reference structure
        first_ref = references[0]
        if not first_ref.get("section") or not first_ref.get("page"):
            print_colored("❌ Invalid reference structure", Colors.RED)
            return False
        
        # Validate section content
        section_matches = False
        if isinstance(expected_section_contains, list):
            for term in expected_section_contains:
                if term.lower() in first_ref["section"].lower():
                    section_matches = True
                    break
        else:
            section_matches = expected_section_contains.lower() in first_ref["section"].lower()
        
        if not section_matches:
            print_colored(f"❌ Section doesn't match expected content: {first_ref['section']}", Colors.RED)
            return False
        
        # Validate RAG debug metadata
        rag_debug = data.get("metadata", {}).get("rag_debug", {})
        if not rag_debug or not rag_debug.get("collection") or rag_debug.get("snippets_found", 0) == 0:
            print_colored("❌ Missing or invalid RAG debug metadata", Colors.RED)
            return False
        
        # Print results
        print_colored(f"✅ Decision: {decision}", Colors.GREEN)
        print_colored(f"✅ References: {len(references)}", Colors.GREEN)
        print_colored(f"✅ Collection: {rag_debug['collection']}", Colors.GREEN)
        print_colored(f"✅ Snippets found: {rag_debug['snippets_found']}", Colors.GREEN)
        
        # Print first 3 references
        print_colored("📚 References:", Colors.CYAN)
        for i, ref in enumerate(references[:3]):
            print_colored(f"  S{i+1}: {ref['section']} (page {ref['page']})", Colors.WHITE)
        
        return True
        
    except Exception as e:
        print_colored(f"❌ Request failed: {str(e)}", Colors.RED)
        return False

def main():
    """Main verification execution"""
    print_colored("🔍 RAG Verification Script", Colors.YELLOW)
    print_colored("Testing auto-detection and reference generation...", Colors.CYAN)
    
    # Authenticate
    print_colored("🔐 Authenticating...", Colors.CYAN)
    token = get_auth_token(BASE_URL, USERNAME, PASSWORD)
    
    if not token:
        print_colored("❌ Authentication failed. Exiting.", Colors.RED)
        return 1
    
    print_colored("✅ Authentication successful", Colors.GREEN)
    
    pass_count = 0
    total_tests = len(TEST_CASES)
    
    for test_case in TEST_CASES:
        print_colored(f"\n🧪 Testing: {test_case['name']}", Colors.YELLOW)
        print_colored(f"❓ Question: {test_case['question']}", Colors.GRAY)
        
        result = test_single_agent_response(
            BASE_URL,
            token,
            test_case["question"],
            test_case["expected_decision"],
            test_case["expected_section_contains"]
        )
        
        if result:
            pass_count += 1
            print_colored("✅ PASS", Colors.GREEN)
        else:
            print_colored("❌ FAIL", Colors.RED)
    
    # Summary
    print_colored("\n📊 VERIFICATION RESULTS", Colors.YELLOW)
    color = Colors.GREEN if pass_count == total_tests else Colors.RED
    print_colored(f"Passed: {pass_count}/{total_tests}", color)
    
    if pass_count == total_tests:
        print_colored("🎉 ALL TESTS PASSED - RAG auto-detection working!", Colors.GREEN)
        return 0
    else:
        print_colored("❌ SOME TESTS FAILED - Check RAG configuration", Colors.RED)
        return 1

if __name__ == "__main__":
    sys.exit(main())
