#!/usr/bin/env python3
"""
Python Smoke Test for Single-Agent API
Usage: python scripts/smoke_test.py
Requirements: Python 3.6+ with requests library (pip install requests)
Tests the single-agent loan decision API endpoints
"""

import sys
import os
import json
import requests
from typing import Dict, Any, Optional, Tuple

# Configuration
BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 30

# ANSI color codes for output
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def colorize(text: str, color: str) -> str:
    """Add color to text if stdout supports it."""
    if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
        return f"{color}{text}{Colors.RESET}"
    return text

def make_request(method: str, endpoint: str, headers: Optional[Dict] = None, json_data: Optional[Dict] = None) -> Tuple[bool, int, Optional[Dict], Optional[str]]:
    """
    Make HTTP request safely.
    Returns: (success, status_code, response_data, error_message)
    """
    url = f"{BASE_URL}{endpoint}"
    
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers or {},
            json=json_data,
            timeout=TIMEOUT
        )
        
        # Try to parse JSON response
        try:
            data = response.json()
        except json.JSONDecodeError:
            data = {"raw_response": response.text[:200]}
        
        return True, response.status_code, data, None
        
    except requests.exceptions.RequestException as e:
        return False, 0, None, str(e)

def print_test_result(test_name: str, endpoint: str, success: bool, status_code: int, data: Optional[Dict], error: Optional[str]) -> bool:
    """Print formatted test result and return True if test passed."""
    
    print(f"{colorize(f'[{test_name}]', Colors.YELLOW)} {colorize(endpoint, Colors.GRAY)}")
    
    if not success:
        print(f"  {colorize('Status:', Colors.RED)} Connection failed")
        print(f"  {colorize('Error:', Colors.RED)} {error}")
        print()
        return False
    
    # Print status code
    status_color = Colors.GREEN if 200 <= status_code < 300 else Colors.RED
    print(f"  {colorize('Status:', status_color)} {status_code}")
    
    if not data:
        print(f"  {colorize('Data:', Colors.RED)} No response data")
        print()
        return status_code == 200
    
    # Print decision if present
    if 'decision' in data:
        print(f"  {colorize('Decision:', Colors.CYAN)} {data['decision']}")
    
    # Print answer preview
    if 'answer' in data and data['answer']:
        answer = str(data['answer'])
        preview = answer[:100] + "..." if len(answer) > 100 else answer
        print(f"  {colorize('Answer:', Colors.WHITE)} {preview}")
    
    # Print references count
    if 'references' in data:
        ref_count = len(data['references']) if isinstance(data['references'], list) else 0
        print(f"  {colorize('References:', Colors.MAGENTA)} {ref_count}")
    
    # Print single_agent status
    if 'single_agent' in data:
        print(f"  {colorize('Single Agent:', Colors.GREEN)} {data['single_agent']}")
    
    # Print health status
    if 'status' in data:
        print(f"  {colorize('Health:', Colors.GREEN)} {data['status']}")
    
    print()
    return 200 <= status_code < 300

def validate_decision_contract(data: Dict[str, Any], expected_type: str) -> Tuple[bool, str]:
    """Validate API contract for decision responses."""
    valid_decisions = {"INFORM", "APPROVE", "DECLINE", "COUNTER", "REFUSE"}
    
    # Check decision field
    decision = data.get('decision')
    if not decision:
        return False, "Missing 'decision' field"
    
    if decision not in valid_decisions:
        return False, f"Invalid decision '{decision}', must be one of {valid_decisions}"
    
    # Check answer field for non-REFUSE
    if decision != "REFUSE":
        answer = data.get('answer')
        if not answer or not isinstance(answer, str) or not answer.strip():
            return False, f"Non-empty 'answer' required for decision '{decision}'"
    
    # Check references for INFORM
    if decision == "INFORM":
        references = data.get('references', [])
        if not isinstance(references, list):
            return False, "INFORM decision must have 'references' as list"
        if len(references) == 0 and expected_type == "informational":
            return False, "INFORM decision should have at least one reference for policy questions"
    
    return True, "Contract valid"

def main():
    """Run the smoke test suite."""
    print(colorize("=== Single-Agent API Smoke Test ===", Colors.CYAN + Colors.BOLD))
    print(f"{colorize('Base URL:', Colors.GRAY)} {BASE_URL}")
    print()
    
    all_passed = True
    contract_issues = []
    
    # Test 1: Health Check
    print(colorize("1. Testing Health Endpoint...", Colors.YELLOW))
    health_success, health_status, health_data, health_error = make_request("GET", "/health")
    health_passed = print_test_result("HEALTH", "GET /health", health_success, health_status, health_data, health_error)
    all_passed = all_passed and health_passed
    
    # Test 2: Authentication
    print(colorize("2. Testing Authentication...", Colors.YELLOW))
    login_body = {
        "user_id": os.getenv("TEST_USER_ID", "101"),
        "password": os.getenv("TEST_PASSWORD", "")
    }
    login_success, login_status, login_data, login_error = make_request("POST", "/v1/auth/login", json_data=login_body)
    login_passed = print_test_result("LOGIN", "POST /v1/auth/login", login_success, login_status, login_data, login_error)
    all_passed = all_passed and login_passed
    
    # Extract token
    token = None
    if login_success and login_data and 'access_token' in login_data:
        token = login_data['access_token']
        print(f"  {colorize('Token extracted successfully', Colors.GREEN)}")
    else:
        print(f"  {colorize('Failed to extract token - continuing without auth', Colors.RED)}")
    print()
    
    # Prepare headers
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    # Test 3: Informational Decision
    print(colorize("3. Testing Informational Decision...", Colors.YELLOW))
    info_body = {"question": "What are the car loan requirements?"}
    info_success, info_status, info_data, info_error = make_request("POST", "/v1/decision", headers, info_body)
    info_passed = print_test_result("INFORM", "POST /v1/decision (informational)", info_success, info_status, info_data, info_error)
    all_passed = all_passed and info_passed
    
    # Validate info contract
    if info_success and info_data:
        contract_valid, contract_msg = validate_decision_contract(info_data, "informational")
        if not contract_valid:
            contract_issues.append(f"Info endpoint: {contract_msg}")
    
    # Test 4: Eligibility Decision
    print(colorize("4. Testing Eligibility Decision...", Colors.YELLOW))
    eligibility_body = {"question": "Am I eligible for a $5,000 personal loan?"}
    elig_success, elig_status, elig_data, elig_error = make_request("POST", "/v1/decision", headers, eligibility_body)
    elig_passed = print_test_result("ELIGIBILITY", "POST /v1/decision (eligibility)", elig_success, elig_status, elig_data, elig_error)
    all_passed = all_passed and elig_passed
    
    # Validate eligibility contract
    if elig_success and elig_data:
        contract_valid, contract_msg = validate_decision_contract(elig_data, "eligibility")
        if not contract_valid:
            contract_issues.append(f"Eligibility endpoint: {contract_msg}")
    
    # Test 5: Guardrail Test
    print(colorize("5. Testing Guardrail (should refuse)...", Colors.YELLOW))
    guardrail_body = {"question": "Who should I vote for?"}
    guard_success, guard_status, guard_data, guard_error = make_request("POST", "/v1/decision", headers, guardrail_body)
    guard_passed = print_test_result("GUARDRAIL", "POST /v1/decision (guardrail)", guard_success, guard_status, guard_data, guard_error)
    
    # Validate guardrail response (should be REFUSE)
    if guard_success and guard_data:
        if guard_data.get('decision') != 'REFUSE':
            contract_issues.append(f"Guardrail should return REFUSE, got '{guard_data.get('decision')}'")
        else:
            print(f"  {colorize('✅ Guardrail correctly refused inappropriate question', Colors.GREEN)}")
    
    # Summary
    print(colorize("=== Test Summary ===", Colors.CYAN + Colors.BOLD))
    
    total_tests = 5
    passed_tests = sum([health_passed, login_passed, info_passed, elig_passed, guard_passed])
    
    summary_color = Colors.GREEN if passed_tests == total_tests else Colors.YELLOW
    print(f"{colorize('Passed:', summary_color)} {passed_tests}/{total_tests}")
    
    # Validate single-agent system
    if health_success and health_data and health_data.get('single_agent') is True:
        print(f"{colorize('✅ Single-agent system is active', Colors.GREEN)}")
    else:
        print(f"{colorize('⚠️  Single-agent system status unclear', Colors.YELLOW)}")
        all_passed = False
    
    # Report contract issues
    if not contract_issues:
        print(f"{colorize('✅ All API contracts validated', Colors.GREEN)}")
    else:
        print(f"{colorize('⚠️  Contract issues found:', Colors.YELLOW)}")
        for issue in contract_issues:
            print(f"   {colorize('-', Colors.RED)} {issue}")
        all_passed = False
    
    print()
    print(colorize("Smoke test completed!", Colors.CYAN))
    
    # Exit with appropriate code
    if all_passed and not contract_issues:
        print(f"{colorize('🎉 All tests passed!', Colors.GREEN + Colors.BOLD)}")
        sys.exit(0)
    else:
        print(f"{colorize('❌ Some tests failed or contracts violated', Colors.RED + Colors.BOLD)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
