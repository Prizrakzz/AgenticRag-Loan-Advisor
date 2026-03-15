"""Pydantic schemas for API request/response models."""

from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field, validator, field_validator
from datetime import datetime


# Auth Schemas
class LoginRequest(BaseModel):
    """Login request schema."""
    user_id: str = Field(..., description="User ID for authentication")
    password: str = Field(..., description="User password", min_length=1)


class TokenResponse(BaseModel):
    """Token response schema."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")


class RefreshRequest(BaseModel):
    """Token refresh request schema."""
    refresh_token: str = Field(..., description="Valid refresh token")


class DecisionRequest(BaseModel):
    """Loan decision request schema."""
    client_id: int = Field(..., description="Client ID to evaluate", gt=0)
    question: str = Field(
        ..., 
        description="User's loan question",
        min_length=1,
        max_length=500,
        example="What are the loan terms in Oklahoma?"
    )
    
    @field_validator("client_id", mode="before")
    @classmethod
    def _coerce_client_id(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.isdigit():
                return int(v)
            raise ValueError("client_id must be an integer")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "client_id": 12345,
                "question": "What are my current loans?"
            }
        }


# Loan Decision Schemas
class Reference(BaseModel):
    """Reference to policy document."""
    source: str = Field(..., description="Reference label (S1, S2, S3)")
    section: Optional[str] = Field(None, description="Section name")
    page: Optional[int] = Field(None, description="Page number")


class QuickReply(BaseModel):
    """Quick reply option for user."""
    label: str = Field(..., description="Display text for quick reply")


class CTA(BaseModel):
    """Call-to-action for next steps."""
    text: str = Field(..., description="CTA text")
    action: Literal["apply_now", "contact_officer", "schedule_call"] = Field(
        ..., description="Action type"
    )


class DecisionResponse(BaseModel):
    """Enhanced loan decision response schema."""
    decision: Literal["APPROVE", "COUNTER", "DECLINE", "INFORM", "REFUSE", "ACK"] = Field(
        ..., 
        description="Final loan decision"
    )
    answer: str = Field(
        ..., 
        description="Conversational response to user question"
    )
    references: List[Reference] = Field(
        default=[], 
        description="Policy references used"
    )
    quick_replies: List[QuickReply] = Field(
        default=[], 
        description="Suggested follow-up actions"
    )
    cta: Optional[CTA] = Field(
        None, 
        description="Call-to-action for next steps"
    )
    request_id: str = Field(
        ..., 
        description="Unique request identifier"
    )
    processing_time_ms: Optional[int] = Field(
        None, 
        description="Processing time in milliseconds"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata including references_line for UI rendering"
    )


class LoanRequest(BaseModel):
    """Loan decision request schema."""
    question: str = Field(
        ..., 
        description="User's loan question",
        min_length=1,
        max_length=500,
        example="Can I get a personal loan for $10,000?"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "I'm looking to apply for a personal loan. What are my options?"
            }
        }


class LoanDecision(BaseModel):
    """LEGACY: Loan decision response schema."""
    decision: Literal["APPROVE", "COUNTER", "DECLINE"] = Field(
        ..., 
        description="Final loan decision"
    )
    score: float = Field(
        ..., 
        description="Composite risk score (0.0 = high risk, 1.0 = low risk)",
        ge=0.0,
        le=1.0
    )
    reasons: List[str] = Field(
        ..., 
        description="List of factors influencing the decision"
    )
    explanation: str = Field(
        ..., 
        description="Detailed explanation with policy citations"
    )
    request_id: str = Field(
        ..., 
        description="Unique request identifier for tracking"
    )
    market_stale: bool = Field(
        ..., 
        description="Whether market data used was stale"
    )
    processing_time_ms: Optional[int] = Field(
        None, 
        description="Processing time in milliseconds"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "decision": "APPROVE",
                "score": 0.78,
                "reasons": ["Strong financial profile", "Favorable market conditions"],
                "explanation": "Decision: APPROVE. Your application meets our criteria with a composite score of 0.78. Based on your risk grade A and annual income category, along with current favorable market conditions, we can offer you a personal loan. [§SEC-1.2 p.5]",
                "request_id": "REQ-ABC123456789",
                "market_stale": False,
                "processing_time_ms": 850
            }
        }


class LoanStreamChunk(BaseModel):
    """Streaming response chunk schema."""
    type: Literal["token", "done", "error"] = Field(
        ..., 
        description="Chunk type"
    )
    content: str = Field(
        ..., 
        description="Chunk content"
    )
    request_id: str = Field(
        ..., 
        description="Request identifier"
    )


# Health and Status Schemas
class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(..., description="Check timestamp")
    version: str = Field(..., description="API version")
    database: str = Field(..., description="Database connection status")
    vector_store: str = Field(..., description="Vector store connection status")
    market_data: str = Field(..., description="Market data status")
    single_agent: bool = Field(..., description="Single-agent system enabled status")
    rag_ready: bool = Field(..., description="RAG system readiness")
    vector_count: int = Field(..., description="Number of vectors in RAG collection")
    last_indexed: Optional[str] = Field(None, description="Last time RAG was indexed (ISO8601)")


class DatabaseStatus(BaseModel):
    """Database status details."""
    connected: bool = Field(..., description="Database connection status")
    customer_count: Optional[int] = Field(None, description="Number of customers")
    audit_log_count: Optional[int] = Field(None, description="Number of audit entries")


class VectorStoreStatus(BaseModel):
    """Vector store status details."""
    connected: bool = Field(..., description="Vector store connection status")
    collection_exists: bool = Field(..., description="Policy collection exists")
    document_count: Optional[int] = Field(None, description="Number of indexed documents")


class MarketDataStatus(BaseModel):
    """Market data status details."""
    metrics_available: int = Field(..., description="Number of available metrics")
    stale_metrics: int = Field(..., description="Number of stale metrics")
    last_update: Optional[datetime] = Field(None, description="Last update timestamp")


class StatusResponse(BaseModel):
    """Detailed status response schema."""
    status: str = Field(..., description="Overall service status")
    timestamp: datetime = Field(..., description="Check timestamp")
    database: DatabaseStatus = Field(..., description="Database status details")
    vector_store: VectorStoreStatus = Field(..., description="Vector store status details")
    market_data: MarketDataStatus = Field(..., description="Market data status details")


# Error Schemas
class ErrorResponse(BaseModel):
    """Error response schema."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    request_id: Optional[str] = Field(None, description="Request identifier if available")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "AUTHENTICATION_FAILED",
                "message": "Invalid credentials provided",
                "details": {"user_id": "1001"},
                "request_id": "REQ-ABC123456789",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }


class ValidationErrorResponse(BaseModel):
    """Validation error response schema."""
    error: str = Field(default="VALIDATION_ERROR", description="Error type")
    message: str = Field(..., description="Validation error message")
    field_errors: List[Dict[str, Any]] = Field(..., description="Field-specific errors")
    request_id: Optional[str] = Field(None, description="Request identifier if available")


# Workflow Schemas
class WorkflowInfo(BaseModel):
    """Workflow information schema."""
    nodes: List[str] = Field(..., description="List of workflow nodes")
    entry_point: str = Field(..., description="Workflow entry point")
    llm_nodes: List[str] = Field(..., description="Nodes that use LLM")
    deterministic_nodes: List[str] = Field(..., description="Deterministic nodes")
    external_calls: Dict[str, str] = Field(..., description="External service calls by node")


# Audit Schemas
class AuditLogEntry(BaseModel):
    """Audit log entry schema."""
    id: int = Field(..., description="Audit entry ID")
    req_id: str = Field(..., description="Request ID")
    username: str = Field(..., description="Username")
    node: str = Field(..., description="Node name")
    timestamp: datetime = Field(..., description="Entry timestamp")
    
    class Config:
        from_attributes = True


# Configuration Validation
class ConfigValidation(BaseModel):
    """Configuration validation helpers."""
    pass


# Response Metadata
class ResponseMetadata(BaseModel):
    """Response metadata for tracking and debugging."""
    request_id: str = Field(..., description="Unique request identifier")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    api_version: str = Field(default="1.0", description="API version")
    model_version: str = Field(default="1.0", description="ML model version")
    rag_debug: Optional[Dict[str, Any]] = Field(None, description="RAG system debug information")


# Pagination Schemas
class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    size: int = Field(default=20, ge=1, le=100, description="Page size (max 100)")
    
    @property
    def offset(self) -> int:
        """Calculate offset for database queries."""
        return (self.page - 1) * self.size


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    items: List[Any] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    size: int = Field(..., description="Page size")
    pages: int = Field(..., description="Total number of pages")
    
    @validator('pages', pre=False, always=True)
    def calculate_pages(cls, v, values):
        """Calculate total pages based on total and size."""
        total = values.get('total', 0)
        size = values.get('size', 1)
        return (total + size - 1) // size if total > 0 else 0 