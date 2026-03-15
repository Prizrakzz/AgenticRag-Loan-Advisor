"""Loan approval API endpoints."""

import os
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from typing import Dict, Any, List

from ..graph.workflow import run_decision, get_workflow_info
from ..nodes.guardrail import GuardrailError
from ..utils.logger import get_logger
from ..utils.config import settings
from .deps import get_request_id, get_current_user
from ..db.chat_repo import save_message, load_recent_messages
from .schemas import DecisionResponse, LoanRequest

logger = get_logger(__name__)

router = APIRouter()


class WorkflowInfoResponse(BaseModel):
    """Response model for workflow info endpoint."""
    modes: Dict[str, Any]
    available_modules: List[str]
    routing: Dict[str, str]


@router.get("/workflow-info", response_model=WorkflowInfoResponse)
async def get_loan_workflow_info(
    current_user_id: int = Depends(get_current_user)
) -> WorkflowInfoResponse:
    """
    Get information about available workflow modes and capabilities.
    
    This endpoint provides details about:
    - Rule-based vs autonomous workflow modes
    - Available data source modules for autonomous mode
    - Routing and decision logic
    """
    try:
        logger.info(
            "workflow_info_request",
            user_id=current_user_id
        )
        
        info = get_workflow_info()
        
        return WorkflowInfoResponse(
            modes=info["modes"],
            available_modules=info["available_modules"],
            routing=info["routing"]
        )
        
    except Exception as e:
        logger.error(
            "workflow_info_failed",
            user_id=current_user_id,
            error=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow information"
        )


@router.post("/decision", response_model=DecisionResponse)
async def make_enhanced_decision(
    request: LoanRequest,
    response_obj: Response,
    req_id: str = Depends(get_request_id),
    current_user_id: int = Depends(get_current_user)
) -> DecisionResponse:
    """
    Enhanced loan decision endpoint with memory-driven conversation.
    
    - **question**: The loan application question
    
    Returns enhanced response with references, quick_replies, and CTA.
    """
    start_time = os.times().elapsed if hasattr(os, 'times') else 0
    
    # Feature flag for single-agent orchestration - now default enabled
    use_single_agent = os.getenv("SINGLE_AGENT_ENABLED", "true").lower() != "false"
    
    if use_single_agent:
        # Use new single-agent orchestration with memory
        try:
            from ..nodes.single_agent import process_request
            
            # Trace-enabled debug logs for eligibility debugging
            trace_enabled = os.getenv("SINGLE_AGENT_TRACE", "false").lower() == "true"
            if trace_enabled:
                logger.info(
                    "eligibility_request",
                    req_id=req_id,
                    has_customer=bool(current_user_id),
                    has_market=True,  # Market always available
                    jwt_sub_present=bool(current_user_id),
                    body_keys=list(request.__dict__.keys())
                )
            
            logger.info(
                "single_agent_decision_request",
                req_id=req_id,
                user_id=current_user_id,
                question_length=len(request.question)
            )
            
            # Load conversation memory (last 10 messages)
            try:
                conversation_id = getattr(request, 'conversation_id', None) or f"user_{current_user_id}"
                # Open database connection for memory loading
                conn = sqlite3.connect(settings.database_url.replace("sqlite:///", ""))
                memory = load_recent_messages(conn, conversation_id, current_user_id, 10)
                conn.close()
                # Convert to memory format
                memory_messages = []
                for msg in memory:
                    memory_messages.append({
                        "role": "user" if msg.get("role") == "user" else "assistant",
                        "content": msg.get("content", "")
                    })
            except Exception as e:
                logger.warning("memory_load_failed", req_id=req_id, error=str(e))
                memory_messages = []
            
            # Build request for single agent
            agent_request = {
                "req_id": req_id,
                "question": request.question,
                "client_id": str(current_user_id),
                "memory": memory_messages
            }
            
            # Process with single agent
            response = await process_request(agent_request)
            
            # Save conversation to memory
            try:
                conversation_id = getattr(request, 'conversation_id', None) or f"user_{current_user_id}"
                # Open database connection for memory saving
                conn = sqlite3.connect(settings.database_url.replace("sqlite:///", ""))
                save_message(conn, conversation_id, current_user_id, "user", request.question)
                save_message(conn, conversation_id, current_user_id, "assistant", response["answer"])
                conn.close()
            except Exception as e:
                logger.warning("memory_save_failed", req_id=req_id, error=str(e))
            
            # Calculate processing time
            end_time = os.times().elapsed if hasattr(os, 'times') else 0
            processing_time_ms = int((end_time - start_time) * 1000) if start_time > 0 else None
            
            logger.info(
                "single_agent_decision_complete",
                req_id=req_id,
                user_id=current_user_id,
                decision=response["decision"],
                processing_time_ms=processing_time_ms
            )
            
            # Helper functions for backward compatibility
            def get_confidence_score(decision: str) -> float:
                score_map = {
                    "APPROVE": 0.9,
                    "DECLINE": 0.8, 
                    "INFORM": 0.95,
                    "COUNTER": 0.7,
                    "REFUSE": 1.0
                }
                return score_map.get(decision, 0.5)

            def get_reason_codes(decision: str) -> list:
                if decision == "REFUSE":
                    return ["Content violates usage policy"]
                elif decision == "DECLINE":
                    return ["Loan application declined based on analysis"]
                elif decision == "COUNTER":
                    return ["Additional information required"]
                else:
                    return ["Decision completed successfully"]
            
            # Add response header for decision engine
            response_obj.headers["X-Decision-Engine"] = "single_agent"
            
            # Map to API response format
            return DecisionResponse(
                request_id=req_id,
                decision=response["decision"],
                answer=response["answer"],
                references=response["references"],
                quick_replies=response["quick_replies"],
                cta=response["cta"],
                processing_time_ms=processing_time_ms,
                metadata=response.get("metadata")
            )
            
        except Exception as e:
            logger.error("single_agent_error", req_id=req_id, error=str(e))
            # Fallback to legacy system on error
            use_single_agent = False
    
    # Use legacy graph-based system (fallback or when explicitly disabled)
    logger.warning(
        "legacy_system_used",
        req_id=req_id,
        reason="single_agent_disabled_or_error",
        message="Using legacy graph system - consider enabling single-agent for better performance"
    )
    
    try:
        from ..nodes.guardrail import GuardrailError
        
        logger.info(
            "enhanced_decision_request",
            req_id=req_id,
            user_id=current_user_id,
            question_length=len(request.question)
        )
        
        # Run the enhanced workflow with guardrails
        final_state = run_decision(
            req_id=req_id,
            user_id=current_user_id,
            question=request.question,
            autonomous=False,  # Use new judge-based flow
            memory=[]  # Keep simple for now
        )
        
        # Extract enhanced response data
        decision = final_state.get("decision", "INFORM")
        final_answer = final_state.get("final_answer") or final_state.get("answer", "No answer generated.")
        references = final_state.get("references", [])
        quick_replies = final_state.get("quick_replies", [])
        cta = final_state.get("cta")
        
        # Calculate processing time
        end_time = os.times().elapsed if hasattr(os, 'times') else 0
        processing_time_ms = int((end_time - start_time) * 1000) if start_time > 0 else None
        
        logger.info(
            "enhanced_decision_completed",
            req_id=req_id,
            decision=decision,
            answer_length=len(final_answer),
            references_count=len(references),
            quick_replies_count=len(quick_replies),
            has_cta=bool(cta),
            processing_time_ms=processing_time_ms
        )
        
        return DecisionResponse(
            decision=decision,
            answer=final_answer,
            explanation=final_answer,  # Keep both for compatibility
            references=references,
            quick_replies=quick_replies,
            cta=cta,
            req_id=req_id,
            processing_time_ms=processing_time_ms,
            system_version="legacy_graph"
        )
        
    except GuardrailError as e:
        logger.warning("enhanced_decision_guardrail_violation", req_id=req_id, error=str(e))
        
        # Return REFUSE response for guardrail violations
        return DecisionResponse(
            decision="REFUSE",
            answer="I'm sorry, but I can't help with that.",
            explanation="Content blocked by guardrails",
            references=[],
            quick_replies=[],
            cta=None,
            req_id=req_id,
            processing_time_ms=None,
            system_version="legacy_graph"
        )
        
    except Exception as e:
        logger.error(
            "enhanced_decision_failed",
            req_id=req_id,
            user_id=current_user_id,
            error=str(e)
        )
        
        # Return error response
        return DecisionResponse(
            decision="DECLINE",
            answer="I'm experiencing technical difficulties. Please try again later.",
            explanation="System error occurred",
            references=[],
            quick_replies=[],
            cta=None,
            req_id=req_id,
            processing_time_ms=None,
            system_version="legacy_graph"
        )
