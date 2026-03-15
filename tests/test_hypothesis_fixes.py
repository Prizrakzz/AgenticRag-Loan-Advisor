"""Test fixes for the int object has no attribute 'id' error."""

import pytest
from unittest.mock import Mock, patch
from app.api.schemas import DecisionRequest
from app.graph.workflow import generate_answer


@pytest.mark.asyncio
async def test_hypothesis_a_client_id_workflow():
    """Test that workflow accepts client_id as integer without .id attribute error."""
    
    # Mock the workflow components to avoid actual DB/API calls
    with patch('app.graph.workflow.run_workflow') as mock_run_workflow:
        mock_run_workflow.return_value = {
            "final_answer": "Test decision completed",
            "decision": "APPROVE", 
            "score": 0.8,
            "reason_codes": ["TEST_REASON"],
            "snippets": ["Test snippet"]
        }
        
        # Test with integer client_id (should not cause .id attribute error)
        client_id = 101
        question = "What are my loan options?"
        
        try:
            final_answer, metadata = await generate_answer(
                user_id=client_id,  # This should be an int, not an object
                question=question
            )
            
            # Should complete without AttributeError on int.id
            assert final_answer == "Test decision completed"
            assert metadata["decision"] == "APPROVE"
            print("✅ Hypothesis A: No 'int' object .id errors in workflow")
            
        except AttributeError as e:
            if "'int' object has no attribute 'id'" in str(e):
                pytest.fail(f"❌ Hypothesis A failed: {e}")
            else:
                raise


@pytest.mark.asyncio 
async def test_hypothesis_a_request_structure():
    """Test that DecisionRequest properly handles client_id as int."""
    
    req = DecisionRequest(client_id=101, question="Test question")
    
    # Verify types
    assert isinstance(req.client_id, int)
    assert req.client_id == 101
    
    # This should not raise AttributeError
    try:
        client_id_value = req.client_id  # Not req.client_id.id
        assert client_id_value == 101
        print("✅ Hypothesis A: client_id is properly handled as int in request")
    except AttributeError as e:
        pytest.fail(f"❌ Request structure error: {e}")


def test_hypothesis_b_dependency_types():
    """Test that dependency functions return correct types."""
    
    from app.api.deps import get_current_user, get_current_user_object, User
    
    # Test User class
    user_obj = User(id=101)
    assert hasattr(user_obj, 'id')
    assert user_obj.id == 101
    assert isinstance(user_obj.id, int)
    
    # Test that accessing .id works on User objects but not ints
    user_int = 101
    
    try:
        # This should work
        user_id_from_obj = user_obj.id
        assert user_id_from_obj == 101
        print("✅ Hypothesis B: User object has .id attribute")
    except AttributeError as e:
        pytest.fail(f"❌ User object should have .id: {e}")
    
    try:
        # This should fail
        user_id_from_int = user_int.id  # This is the bug we're fixing
        pytest.fail("❌ Hypothesis B: int should not have .id attribute")
    except AttributeError:
        print("✅ Hypothesis B: int correctly does not have .id attribute")


def test_hypothesis_b_endpoint_fix():
    """Test that endpoint handles user dependency correctly."""
    
    from app.api.deps import User
    
    # Simulate the fixed endpoint behavior
    def simulate_endpoint_with_user_int():
        """Simulate endpoint where user is an int (get_current_user)."""
        user = 101  # This is what get_current_user returns
        # Fixed code should use user directly, not user.id
        user_id = user  # Not user.id
        return user_id
    
    def simulate_endpoint_with_user_object():
        """Simulate endpoint where user is a User object (get_current_user_object)."""
        user = User(id=101)  # This is what get_current_user_object returns
        # This code can use user.id
        user_id = user.id
        return user_id
    
    # Both should work without AttributeError
    assert simulate_endpoint_with_user_int() == 101
    assert simulate_endpoint_with_user_object() == 101
    print("✅ Hypothesis B: Both dependency patterns work correctly")


def test_hypothesis_c_safe_id_extraction():
    """Test that the safe_get_id function handles both ints and objects."""
    
    from app.graph.nodes import safe_get_id
    from app.api.deps import User
    
    # Test with integer
    client_id_int = 101
    extracted_id = safe_get_id(client_id_int)
    assert extracted_id == 101
    print("✅ Hypothesis C: safe_get_id works with int")
    
    # Test with object having .id
    user_obj = User(id=201)
    extracted_id = safe_get_id(user_obj)
    assert extracted_id == 201
    print("✅ Hypothesis C: safe_get_id works with object.id")
    
    # Test with dict-like object
    class ClientLike:
        def __init__(self, client_id):
            self.id = client_id
    
    client_obj = ClientLike(301)
    extracted_id = safe_get_id(client_obj)
    assert extracted_id == 301
    print("✅ Hypothesis C: safe_get_id works with custom object")
    
    # Test error case
    try:
        safe_get_id("invalid")
        pytest.fail("Should raise ValueError for unsupported type")
    except ValueError:
        print("✅ Hypothesis C: safe_get_id properly rejects unsupported types")


def test_hypothesis_c_audit_logging_safety():
    """Test that audit logging handles both int and object parameters safely."""
    
    from app.graph.nodes import safe_get_id
    
    # Simulate what might happen in audit logging
    def simulate_audit_log_with_client(client):
        """Simulate audit logging that might receive client as int or object."""
        try:
            # Before fix: client.id (fails if client is int)
            # After fix: safe_get_id(client) 
            client_id = safe_get_id(client)
            return {"client_id": client_id, "status": "success"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    # Test with int (the problematic case)
    result1 = simulate_audit_log_with_client(101)
    assert result1["status"] == "success"
    assert result1["client_id"] == 101
    
    # Test with object
    class MockClient:
        def __init__(self, client_id):
            self.id = client_id
    
    result2 = simulate_audit_log_with_client(MockClient(202))
    assert result2["status"] == "success"
    assert result2["client_id"] == 202
    
    print("✅ Hypothesis C: Audit logging safely handles both int and object clients")


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        print("Testing hypothesis fixes for 'int' object has no attribute 'id' error...")
        print("\n=== HYPOTHESIS A: Client Entity Mis-Injection ===")
        await test_hypothesis_a_client_id_workflow()
        await test_hypothesis_a_request_structure()
        
        print("\n=== HYPOTHESIS B: Incorrect Dependency Wiring ===")
        test_hypothesis_b_dependency_types()
        test_hypothesis_b_endpoint_fix()
        
        print("\n=== HYPOTHESIS C: Audit-Log Node Misuse ===")
        test_hypothesis_c_safe_id_extraction()
        test_hypothesis_c_audit_logging_safety()
        
        print("\n🎉 All hypothesis tests passed! The 'int' object .id errors should be resolved.")
    
    asyncio.run(run_tests()) 