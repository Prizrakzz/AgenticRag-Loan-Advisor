"""Database models for the loan approval system."""

import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import validates

from ..utils.logger import get_logger

logger = get_logger(__name__)

Base = declarative_base()


class Customer(Base):
    """Customer data model."""
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, unique=True, index=True, nullable=False)
    client_name = Column(String(255), nullable=False)
    education_level = Column(String(50))
    family_size = Column(Integer)
    employment_status = Column(String(100))
    employer_name = Column(String(255))
    annual_income = Column(Float)
    existing_loan_amount = Column(Float)
    past_defaults = Column(Integer, default=0)
    risk_grade = Column(String(5))
    risk_score = Column(Float)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert customer to dictionary."""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "education_level": self.education_level,
            "family_size": self.family_size,
            "employment_status": self.employment_status,
            "employer_name": self.employer_name,
            "annual_income": self.annual_income,
            "existing_loan_amount": self.existing_loan_amount,
            "past_defaults": self.past_defaults,
            "risk_grade": self.risk_grade,
            "risk_score": self.risk_score
        }
    
    @validates('risk_grade')
    def validate_risk_grade(self, key, value):
        """Validate risk grade values."""
        if value and value not in ['A', 'B', 'C', 'D']:
            raise ValueError(f"Invalid risk grade: {value}")
        return value
    
    def __repr__(self):
        return f"<Customer(client_id={self.client_id}, name='{self.client_name}', risk_grade='{self.risk_grade}')>"


class AuditLog(Base):
    """Enhanced audit log for tracking workflow execution and agent performance."""
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True, index=True)
    req_id = Column(String(50), index=True, nullable=False)
    username = Column(String(50), index=True, nullable=False)
    node = Column(String(100), index=True, nullable=False)
    ts = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    state = Column(JSON)
    
    # Enhanced fields for agent tracking
    autonomous_mode = Column(Boolean, default=False, index=True)
    iteration_count = Column(Integer, default=0)
    confidence_score = Column(Float)
    risk_tier = Column(String(20))
    data_sources_used = Column(JSON)  # List of data sources accessed
    action_success = Column(Boolean)  # Whether the node/action succeeded
    error_message = Column(Text)
    processing_time_ms = Column(Integer)
    
    # Agent performance metrics
    plan_steps_count = Column(Integer)
    executed_steps_count = Column(Integer)
    failed_steps_count = Column(Integer)
    final_decision = Column(String(20))
    decision_method = Column(String(50))  # e.g., "rule_based", "llm_assisted", "fallback"
    
    @classmethod
    def create_entry(
        cls,
        req_id: str,
        username: str,
        node: str,
        state: Dict[str, Any],
        autonomous_mode: bool = False,
        processing_time_ms: Optional[int] = None,
        action_success: Optional[bool] = None,
        error_message: Optional[str] = None
    ) -> "AuditLog":
        """
        Create an enhanced audit log entry.
        
        Args:
            req_id: Request ID for tracking
            username: User identifier
            node: Node or action name
            state: Current workflow state
            autonomous_mode: Whether using autonomous agent
            processing_time_ms: Processing time in milliseconds
            action_success: Whether the action succeeded
            error_message: Error message if applicable
        
        Returns:
            AuditLog instance
        """
        # Extract agent-specific information from state
        context = state.get("context", {})
        agent_audit = state.get("agent_audit", {})
        
        # Extract data sources information
        data_sources_used = []
        if context.get("data_sources"):
            for source, data in context["data_sources"].items():
                if data and (not isinstance(data, dict) or "error" not in data):
                    data_sources_used.append(source)
        
        # Extract plan information
        plan = state.get("plan", {})
        plan_steps_count = len(plan.get("steps", [])) if plan else None
        
        # Extract execution summary if available
        executed_steps_count = None
        failed_steps_count = None
        if context.get("history"):
            history = context["history"]
            executed_steps_count = len(history)
            failed_steps_count = sum(1 for action in history if not action.get("success", True))
        
        return cls(
            req_id=req_id,
            username=username,
            node=node,
            state=state,
            autonomous_mode=autonomous_mode or agent_audit.get("autonomous_mode", False),
            iteration_count=context.get("iteration_count", 0) or agent_audit.get("iteration_count", 0),
            confidence_score=context.get("confidence") or agent_audit.get("confidence"),
            risk_tier=context.get("risk_tier") or agent_audit.get("risk_tier"),
            data_sources_used=data_sources_used or agent_audit.get("available_data_sources", []),
            action_success=action_success,
            error_message=error_message,
            processing_time_ms=processing_time_ms,
            plan_steps_count=plan_steps_count,
            executed_steps_count=executed_steps_count,
            failed_steps_count=failed_steps_count,
            final_decision=state.get("decision"),
            decision_method=state.get("context", {}).get("data_sources", {}).get("decision", {}).get("method")
        )
    
    @classmethod
    def get_agent_performance_metrics(
        cls, 
        db_session, 
        req_id: Optional[str] = None,
        autonomous_only: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get agent performance metrics for analysis and learning.
        
        Args:
            db_session: Database session
            req_id: Optional specific request ID
            autonomous_only: Whether to filter to autonomous mode only
            limit: Maximum number of records
        
        Returns:
            List of performance metric dictionaries
        """
        query = db_session.query(cls)
        
        if req_id:
            query = query.filter(cls.req_id == req_id)
        
        if autonomous_only:
            query = query.filter(cls.autonomous_mode == True)
        
        # Get final decision nodes (end of workflow)
        query = query.filter(cls.node.in_(["agent_metrics_node", "explain", "end_node"]))
        
        records = query.order_by(cls.ts.desc()).limit(limit).all()
        
        metrics = []
        for record in records:
            metric = {
                "req_id": record.req_id,
                "timestamp": record.ts.isoformat(),
                "autonomous_mode": record.autonomous_mode,
                "iterations": record.iteration_count,
                "confidence": record.confidence_score,
                "risk_tier": record.risk_tier,
                "data_sources_used": record.data_sources_used or [],
                "data_sources_count": len(record.data_sources_used or []),
                "final_decision": record.final_decision,
                "decision_method": record.decision_method,
                "plan_steps": record.plan_steps_count,
                "executed_steps": record.executed_steps_count,
                "failed_steps": record.failed_steps_count,
                "success_rate": (
                    (record.executed_steps_count - (record.failed_steps_count or 0)) / record.executed_steps_count
                    if record.executed_steps_count and record.executed_steps_count > 0 else 0.0
                ),
                "processing_time_ms": record.processing_time_ms,
                "efficiency_score": (
                    record.confidence_score / record.iteration_count
                    if record.confidence_score and record.iteration_count and record.iteration_count > 0 else 0.0
                )
            }
            metrics.append(metric)
        
        return metrics
    
    @classmethod
    def get_frequent_failure_patterns(
        cls,
        db_session,
        days_back: int = 30,
        min_occurrences: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Identify frequent failure patterns for agent improvement.
        
        Args:
            db_session: Database session
            days_back: Number of days to look back
            min_occurrences: Minimum occurrences to consider a pattern
        
        Returns:
            List of failure pattern dictionaries
        """
        from sqlalchemy import func, and_
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        # Query for failed actions in autonomous mode
        failed_patterns = (
            db_session.query(
                cls.node,
                cls.risk_tier,
                cls.error_message,
                func.count(cls.id).label('occurrence_count'),
                func.avg(cls.iteration_count).label('avg_iterations')
            )
            .filter(
                and_(
                    cls.autonomous_mode == True,
                    cls.action_success == False,
                    cls.ts >= cutoff_date,
                    cls.error_message.isnot(None)
                )
            )
            .group_by(cls.node, cls.risk_tier, cls.error_message)
            .having(func.count(cls.id) >= min_occurrences)
            .order_by(func.count(cls.id).desc())
            .all()
        )
        
        patterns = []
        for pattern in failed_patterns:
            patterns.append({
                "node": pattern.node,
                "risk_tier": pattern.risk_tier,
                "error_message": pattern.error_message,
                "occurrence_count": pattern.occurrence_count,
                "avg_iterations": float(pattern.avg_iterations) if pattern.avg_iterations else 0.0
            })
        
        return patterns
    
    @classmethod
    def get_confidence_accuracy_correlation(
        cls,
        db_session,
        days_back: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze correlation between agent confidence and decision accuracy.
        This would require feedback on decision accuracy (future enhancement).
        
        Args:
            db_session: Database session
            days_back: Number of days to analyze
        
        Returns:
            Analysis results dictionary
        """
        from sqlalchemy import func, and_
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        # Get confidence score distribution
        confidence_stats = (
            db_session.query(
                func.avg(cls.confidence_score).label('avg_confidence'),
                func.min(cls.confidence_score).label('min_confidence'),
                func.max(cls.confidence_score).label('max_confidence'),
                func.count(cls.id).label('total_decisions')
            )
            .filter(
                and_(
                    cls.autonomous_mode == True,
                    cls.confidence_score.isnot(None),
                    cls.ts >= cutoff_date,
                    cls.final_decision.isnot(None)
                )
            )
            .first()
        )
        
        # Get decision distribution by confidence quartiles
        # This is a simplified analysis - would be enhanced with actual accuracy feedback
        decision_distribution = (
            db_session.query(
                cls.final_decision,
                func.avg(cls.confidence_score).label('avg_confidence'),
                func.count(cls.id).label('count')
            )
            .filter(
                and_(
                    cls.autonomous_mode == True,
                    cls.confidence_score.isnot(None),
                    cls.ts >= cutoff_date,
                    cls.final_decision.isnot(None)
                )
            )
            .group_by(cls.final_decision)
            .all()
        )
        
        analysis = {
            "analysis_period_days": days_back,
            "total_decisions": confidence_stats.total_decisions if confidence_stats else 0,
            "confidence_stats": {
                "avg": float(confidence_stats.avg_confidence) if confidence_stats and confidence_stats.avg_confidence else 0.0,
                "min": float(confidence_stats.min_confidence) if confidence_stats and confidence_stats.min_confidence else 0.0,
                "max": float(confidence_stats.max_confidence) if confidence_stats and confidence_stats.max_confidence else 0.0
            },
            "decision_distribution": [
                {
                    "decision": row.final_decision,
                    "avg_confidence": float(row.avg_confidence),
                    "count": row.count
                }
                for row in decision_distribution
            ]
        }
        
        return analysis
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert audit log to dictionary."""
        return {
            "id": self.id,
            "req_id": self.req_id,
            "username": self.username,
            "node": self.node,
            "timestamp": self.ts.isoformat() if self.ts else None,
            "state": self.state,
            "autonomous_mode": self.autonomous_mode,
            "iteration_count": self.iteration_count,
            "confidence_score": self.confidence_score,
            "risk_tier": self.risk_tier,
            "data_sources_used": self.data_sources_used,
            "action_success": self.action_success,
            "error_message": self.error_message,
            "processing_time_ms": self.processing_time_ms,
            "plan_steps_count": self.plan_steps_count,
            "executed_steps_count": self.executed_steps_count,
            "failed_steps_count": self.failed_steps_count,
            "final_decision": self.final_decision,
            "decision_method": self.decision_method
        }
    
    def __repr__(self):
        return f"<AuditLog(req_id='{self.req_id}', node='{self.node}', autonomous={self.autonomous_mode})>"


class AgentFeedback(Base):
    """Feedback table for agent learning and improvement."""
    __tablename__ = "agent_feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    req_id = Column(String(50), index=True, nullable=False)
    user_id = Column(String(50), index=True, nullable=False)
    decision = Column(String(20), nullable=False)
    user_rating = Column(Integer)  # 1-5 rating of decision quality
    accuracy_feedback = Column(String(20))  # "correct", "incorrect", "partially_correct"
    explanation_rating = Column(Integer)  # 1-5 rating of explanation quality
    suggested_decision = Column(String(20))  # User's suggested decision if different
    feedback_text = Column(Text)  # Free-form feedback
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Agent performance context at time of decision
    agent_confidence = Column(Float)
    agent_iterations = Column(Integer)
    data_sources_used = Column(JSON)
    
    @classmethod
    def create_feedback(
        cls,
        req_id: str,
        user_id: str,
        decision: str,
        user_rating: Optional[int] = None,
        accuracy_feedback: Optional[str] = None,
        explanation_rating: Optional[int] = None,
        suggested_decision: Optional[str] = None,
        feedback_text: Optional[str] = None,
        agent_context: Optional[Dict[str, Any]] = None
    ) -> "AgentFeedback":
        """
        Create a feedback entry for agent learning.
        
        Args:
            req_id: Request ID from the original decision
            user_id: User providing feedback
            decision: The decision that was made
            user_rating: User's rating of decision quality (1-5)
            accuracy_feedback: Whether decision was correct
            explanation_rating: User's rating of explanation quality (1-5)
            suggested_decision: User's suggested alternative decision
            feedback_text: Free-form feedback text
            agent_context: Context from the agent's decision process
        
        Returns:
            AgentFeedback instance
        """
        feedback = cls(
            req_id=req_id,
            user_id=user_id,
            decision=decision,
            user_rating=user_rating,
            accuracy_feedback=accuracy_feedback,
            explanation_rating=explanation_rating,
            suggested_decision=suggested_decision,
            feedback_text=feedback_text
        )
        
        if agent_context:
            feedback.agent_confidence = agent_context.get("confidence")
            feedback.agent_iterations = agent_context.get("iterations")
            feedback.data_sources_used = agent_context.get("data_sources_used")
        
        return feedback
    
    @validates('user_rating', 'explanation_rating')
    def validate_ratings(self, key, value):
        """Validate rating values are between 1 and 5."""
        if value is not None and (value < 1 or value > 5):
            raise ValueError(f"Rating must be between 1 and 5: {value}")
        return value
    
    @validates('accuracy_feedback')
    def validate_accuracy_feedback(self, key, value):
        """Validate accuracy feedback values."""
        valid_values = ["correct", "incorrect", "partially_correct"]
        if value and value not in valid_values:
            raise ValueError(f"Invalid accuracy feedback: {value}")
        return value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert feedback to dictionary."""
        return {
            "id": self.id,
            "req_id": self.req_id,
            "user_id": self.user_id,
            "decision": self.decision,
            "user_rating": self.user_rating,
            "accuracy_feedback": self.accuracy_feedback,
            "explanation_rating": self.explanation_rating,
            "suggested_decision": self.suggested_decision,
            "feedback_text": self.feedback_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "agent_confidence": self.agent_confidence,
            "agent_iterations": self.agent_iterations,
            "data_sources_used": self.data_sources_used
        }
    
    def __repr__(self):
        return f"<AgentFeedback(req_id='{self.req_id}', rating={self.user_rating}, accuracy='{self.accuracy_feedback}')>"


# Memory persistence helpers (SQLite-safe migration)
def ensure_chat_tables_exist(connection):
    """Ensure chat_messages table exists with safe migration."""
    try:
        # Create table if not exists (SQLite-safe)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create index if not exists
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_conv 
            ON chat_messages(conversation_id, created_at);
        """)
        
        connection.commit()
        logger.info("chat_tables_ensured")
        
    except Exception as e:
        logger.warning("chat_table_creation_failed", error=str(e))


def append_message(connection, conversation_id: str, user_id: int, role: str, content: str):
    """Append a message to conversation history."""
    try:
        connection.execute(
            "INSERT INTO chat_messages (conversation_id, user_id, role, content) VALUES (?, ?, ?, ?)",
            (conversation_id, user_id, role, content)
        )
        connection.commit()
    except Exception as e:
        logger.warning("message_append_failed", error=str(e))


def load_recent_messages(connection, conversation_id: str, user_id: int, limit: int = 6) -> List[Dict[str, Any]]:
    """Load recent messages for conversation context."""
    try:
        cursor = connection.execute("""
            SELECT role, content, created_at 
            FROM chat_messages 
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY created_at DESC 
            LIMIT ?
        """, (conversation_id, user_id, limit))
        
        messages = []
        for row in cursor.fetchall():
            messages.append({
                "role": row[0],
                "content": row[1],
                "ts": row[2]
            })
        
        # Return in chronological order (oldest first) for LLM context
        return list(reversed(messages))
        
    except Exception as e:
        logger.warning("message_load_failed", error=str(e))
        return [] 