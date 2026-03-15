"""Data source modules for autonomous agent operation.

These modules are refactored from the original nodes to support dynamic invocation
based on agent planning. Each module follows a standard interface:
- Input: Context and parameters dict
- Output: Updated Context with populated data_sources
- Error handling: Log errors and flag in context
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from .state import Context, AgentAction
from ..db.database import get_db_session
from ..db.models import Customer
from ..scrape.store import read_all_metrics, is_metric_stale, get_market_store
from ..scrape.scheduler import get_scheduler
from ..rag.retriever import retrieve_policy_snippets
from ..utils.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _log_module_action(module_name: str, context: Context, success: bool, error: str = None):
    """Log module execution for audit trail."""
    action = AgentAction(
        action=module_name,
        params={},  # Could include sanitized params
        success=success,
        error=error,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )
    context["history"].append(action)
    
    logger.info(
        "module_executed",
        module=module_name,
        success=success,
        error=error,
        req_id=context.get("req_id", "unknown")
    )


def fetch_customer(context: Context, params: Dict[str, Any]) -> Context:
    """
    Fetch customer data from database.
    
    Args:
        context: Current agent context
        params: {"client_id": int, "include_risk_assessment": bool}
    
    Returns:
        Updated context with customer data in data_sources
    """
    try:
        client_id = params.get("client_id")
        if not client_id:
            # Try to get from context if not in params
            client_id = context.get("user_id")
        
        if not client_id:
            raise ValueError("No client_id provided")
        
        with get_db_session() as db:
            customer = db.query(Customer).filter(Customer.client_id == client_id).first()
            
            if not customer:
                raise ValueError(f"Customer {client_id} not found")
            
            customer_data = customer.to_dict()
            
            # Determine risk tier for agent reasoning
            risk_grade = customer_data.get("risk_grade", "C")
            risk_tier_map = {"A": "high", "B": "medium", "C": "medium", "D": "low"}
            context["risk_tier"] = risk_tier_map.get(risk_grade, "medium")
            
            # Store in data sources
            context["data_sources"]["customer"] = customer_data
            
            # Update confidence based on data quality
            has_risk_score = bool(customer_data.get("risk_score"))
            has_income = bool(customer_data.get("annual_income"))
            context["confidence"] = 0.8 if has_risk_score and has_income else 0.6
            
            _log_module_action("fetch_customer", context, True)
            logger.info("customer_fetched", client_id=client_id, risk_grade=risk_grade)
            
    except Exception as e:
        context["data_sources"]["customer"] = {"error": str(e)}
        _log_module_action("fetch_customer", context, False, str(e))
        logger.error("fetch_customer_failed", error=str(e))
    
    return context


def fetch_market(context: Context, params: Dict[str, Any]) -> Context:
    """
    Fetch market data from cache or trigger refresh.
    
    Args:
        context: Current agent context
        params: {"region": str, "force_refresh": bool, "include_computed": bool}
    
    Returns:
        Updated context with market data in data_sources
    """
    try:
        force_refresh = params.get("force_refresh", False)
        include_computed = params.get("include_computed", True)
        
        # Check if we need to refresh stale data
        stale_threshold_hours = settings.scrape.stale_threshold_hours
        
        if force_refresh:
            # Trigger immediate scraping (be careful with this in production)
            scheduler = get_scheduler()
            scheduler.run_once()
            logger.info("market_data_refreshed", forced=True)
        
        # Read metrics from cache
        metrics = read_all_metrics()
        
        if not metrics:
            raise ValueError("No market metrics available")
        
        # Check staleness for U.S./Oklahoma key metrics
        stale_metrics = []
        key_metrics = ["fed_funds_rate", "oklahoma_cpi_yoy", "okc_home_price_index", "30yr_mortgage_rate"]
        for metric_key in key_metrics:
            if metric_key in metrics and is_metric_stale(metric_key, stale_threshold_hours):
                stale_metrics.append(metric_key)
        
        market_stale = len(stale_metrics) > 0
        
        # Organize market data by category
        market_categories = {
            "federal_rates": {
                "fed_funds_rate": metrics.get("fed_funds_rate"),
                "30yr_mortgage_rate": metrics.get("30yr_mortgage_rate")
            },
            "oklahoma_economy": {
                "oklahoma_cpi_yoy": metrics.get("oklahoma_cpi_yoy"),
                "oklahoma_unemployment_rate": metrics.get("oklahoma_unemployment_rate"),
                "okc_home_price_index": metrics.get("okc_home_price_index")
            },
            "automotive_market": {
                "used_car_value_index": metrics.get("used_car_value_index"),
                "used_car_yoy_change": metrics.get("used_car_yoy_change")
            },
            "lending_benchmarks": {
                "federal_student_loan_undergrad": metrics.get("federal_student_loan_undergrad"),
                "federal_student_loan_grad": metrics.get("federal_student_loan_grad"),
                "federal_student_loan_plus": metrics.get("federal_student_loan_plus"),
                "personal_loan_median": metrics.get("personal_loan_median"),
                "personal_loan_min": metrics.get("personal_loan_min"),
                "personal_loan_max": metrics.get("personal_loan_max")
            }
        }
        
        # Remove None values
        for category, category_metrics in market_categories.items():
            market_categories[category] = {k: v for k, v in category_metrics.items() if v is not None}
        
        # Enrich with computed risk score if available
        if include_computed and "market_risk_score" in metrics:
            market_risk_data = metrics["market_risk_score"]
            risk_score = market_risk_data.get("value", 0.5)
            
            # Categorize market conditions for agent reasoning
            if risk_score > 0.7:
                market_condition = "high_risk"
                condition_description = "Elevated market risk - exercise caution in lending decisions"
            elif risk_score > 0.4:
                market_condition = "moderate_risk"
                condition_description = "Moderate market risk - standard lending practices apply"
            else:
                market_condition = "low_risk"
                condition_description = "Favorable market conditions for lending"
        else:
            market_condition = "unknown"
            condition_description = "Market risk assessment unavailable"
        
        # Store in data sources with enriched structure
        context["data_sources"]["market_data"] = {
            "categories": market_categories,
            "all_metrics": metrics,
            "stale": market_stale,
            "stale_metrics": stale_metrics,
            "condition": market_condition,
            "condition_description": condition_description,
            "last_updated": max([m.get("asof", "") for m in metrics.values()] or [""]),
            "data_sources": {
                "federal_economic_data": "Federal Reserve Economic Data (FRED)",
                "oklahoma_labor_statistics": "Bureau of Labor Statistics (BLS)",
                "automotive_market": "Cox Automotive",
                "student_loan_rates": "Federal Student Aid",
                "personal_loan_benchmarks": "Market Rate Aggregation"
            }
        }
        
        # Adjust confidence based on data freshness
        if market_stale:
            current_confidence = context.get("confidence", 0.5)
            context["confidence"] = max(0.3, current_confidence - 0.2)  # Reduce confidence
        
        _log_module_action("fetch_market", context, True)
        logger.info(
            "market_fetched",
            metrics_count=len(metrics),
            stale=market_stale,
            condition=market_condition,
            categories_populated=len([cat for cat, data in market_categories.items() if data])
        )
        
    except Exception as e:
        context["data_sources"]["market_data"] = {"error": str(e)}
        _log_module_action("fetch_market", context, False, str(e))
        logger.error("fetch_market_failed", error=str(e))
    
    return context


def rag_search(context: Context, params: Dict[str, Any]) -> Context:
    """
    Perform RAG search over policy documents.
    
    Args:
        context: Current agent context
        params: {
            "query": str,
            "decision_context": str (optional),
            "k": int (default 3),
            "min_score": float (default 0.1)
        }
    
    Returns:
        Updated context with RAG results in data_sources
    """
    try:
        query = params.get("query")
        if not query:
            # Auto-generate query from context
            decision_context = params.get("decision_context", "")
            risk_tier = context.get("risk_tier", "unknown")
            query = f"loan approval criteria {risk_tier} risk {decision_context}".strip()
        
        k = params.get("k", 3)
        min_score = params.get("min_score", 0.1)
        
        # Build decision and reason codes for retrieval
        # This is a simplified approach - in full implementation,
        # we'd have a preliminary decision to guide RAG
        decision_hint = params.get("decision_context", "EVALUATE")
        reason_codes = []
        
        if context.get("risk_tier") == "high":
            reason_codes.append("High risk profile")
        
        market_data = context["data_sources"].get("market_data", {})
        if market_data.get("condition") == "high_risk":
            reason_codes.append("Volatile market conditions")
        
        # Retrieve policy snippets with rich metadata
        snippets = retrieve_policy_snippets(
            decision=decision_hint,
            reason_codes=reason_codes,
            k=k
        )
        
        # Filter by minimum score if specified
        if min_score > 0:
            snippets = [s for s in snippets if s.get("score", 0) >= min_score]
        
        # Enhance snippets with additional metadata for agent reasoning
        enhanced_snippets = []
        for i, snippet in enumerate(snippets):
            if isinstance(snippet, dict):
                enhanced = {
                    **snippet,  # Preserve all original metadata including id, section, source_page
                    "chunk_id": f"RAG-{i+1}",
                    "relevance_rank": i + 1,
                    "confidence_tier": "HIGH" if snippet.get("score", 0) > 0.8 else 
                                     "MEDIUM" if snippet.get("score", 0) > 0.6 else "LOW",
                    "citation_label": f"P{i+1}",  # Policy citation label
                    "document_type": snippet.get("heading_path", "").split("/")[0] if snippet.get("heading_path") else "Unknown",
                    "section_summary": f"§{snippet.get('section_id', 'N/A')} - {snippet.get('heading_path', 'General Policy')}",
                    # Ensure metadata fields are preserved for references
                    "id": snippet.get("id") or snippet.get("section_id"),
                    "section": snippet.get("section") or snippet.get("section_title"),
                    "source_page": snippet.get("source_page") or snippet.get("page_start")
                }
                enhanced_snippets.append(enhanced)
            else:
                # Fallback for plain text snippets
                enhanced_snippets.append({
                    "text": str(snippet),
                    "chunk_id": f"RAG-{i+1}",
                    "relevance_rank": i + 1,
                    "confidence_tier": "UNKNOWN",
                    "citation_label": f"P{i+1}",
                    "document_type": "Unknown",
                    "section_summary": "General Policy"
                })
        
        # Store enhanced data in context for agent reasoning
        context["data_sources"]["rag"] = {
            "snippets": enhanced_snippets,  # Rich metadata for agents
            "query": query,
            "total_found": len(snippets),
            "search_params": {"k": k, "min_score": min_score},
            "metadata_enhanced": True,  # Flag for agent prompts
            "high_confidence_count": len([s for s in enhanced_snippets if s.get("confidence_tier") == "HIGH"]),
            "avg_relevance_score": sum(s.get("score", 0) for s in enhanced_snippets) / len(enhanced_snippets) if enhanced_snippets else 0
        }
        
        # Boost confidence if we found relevant policies
        if snippets:
            current_confidence = context.get("confidence", 0.5)
            context["confidence"] = min(1.0, current_confidence + 0.2)
        
        _log_module_action("rag_search", context, True)
        logger.info(
            "rag_search_completed",
            query=query,
            snippets_found=len(snippets),
            min_score=min_score
        )
        
    except Exception as e:
        context["data_sources"]["rag"] = {"error": str(e)}
        _log_module_action("rag_search", context, False, str(e))
        logger.error("rag_search_failed", error=str(e))
    
    return context


def compute_decision(context: Context, params: Dict[str, Any]) -> Context:
    """
    Compute loan decision based on available data.
    
    Args:
        context: Current agent context
        params: {"method": str ("rule_based" or "llm_assisted")}
    
    Returns:
        Updated context with decision and reasoning
    """
    try:
        method = params.get("method", "rule_based")
        
        customer_data = context["data_sources"].get("customer")
        market_data = context["data_sources"].get("market_data", {})
        
        if not customer_data or "error" in customer_data:
            raise ValueError("Customer data required for decision")
        
        if method == "rule_based":
            # Use existing rule-based logic
            decision, score, reasons = _compute_rule_based_decision(customer_data, market_data)
        else:
            # Could implement LLM-assisted decision here
            decision, score, reasons = _compute_rule_based_decision(customer_data, market_data)
        
        # Store decision in context (this will be moved to state later)
        context["data_sources"]["decision"] = {
            "decision": decision,
            "score": score,
            "reasons": reasons,
            "method": method,
            "computed_at": datetime.utcnow().isoformat() + "Z"
        }
        
        _log_module_action("compute_decision", context, True)
        logger.info(
            "decision_computed",
            decision=decision,
            score=score,
            method=method
        )
        
    except Exception as e:
        context["data_sources"]["decision"] = {"error": str(e)}
        _log_module_action("compute_decision", context, False, str(e))
        logger.error("compute_decision_failed", error=str(e))
    
    return context


def _compute_rule_based_decision(customer_data: Dict[str, Any], market_data: Dict[str, Any]) -> tuple:
    """Enhanced rule-based decision logic with stronger market weighting."""
    # Extract risk grade
    risk_grade = customer_data.get("risk_grade", "C")
    
    # Early decline for high risk
    if risk_grade == "A":
        return "DECLINE", 0.2, ["High risk grade"]
    
    # Quick approve for low risk
    if risk_grade == "D":
        return "APPROVE", 0.8, ["Low risk grade"]
    
    # For B/C, consider market conditions with enhanced weighting
    base_score = {"B": 0.6, "C": 0.5}.get(risk_grade, 0.4)
    market_adjustments = []
    
    # ENHANCED: Stronger market condition impact (was ±0.1, now ±0.25)
    market_condition = market_data.get("condition", "unknown")
    if market_condition == "high_risk":
        base_score -= 0.25
        market_adjustments.append(f"High-risk market conditions (-25pts)")
    elif market_condition == "low_risk":
        base_score += 0.25
        market_adjustments.append(f"Favorable market conditions (+25pts)")
    
    # ENHANCED: Prime rate impact (new feature)
    prime_rate = market_data.get("prime_rate")
    if prime_rate is not None:
        if prime_rate < 4.0:
            base_score += 0.15
            market_adjustments.append(f"Low prime rate {prime_rate}% (+15pts)")
        elif prime_rate > 7.0:
            base_score -= 0.15
            market_adjustments.append(f"High prime rate {prime_rate}% (-15pts)")
        elif prime_rate > 6.0:
            base_score -= 0.05
            market_adjustments.append(f"Elevated prime rate {prime_rate}% (-5pts)")
    
    # ENHANCED: Economic indicators impact (new feature)
    econ_indicators = market_data.get("economic_indicators", {})
    if econ_indicators:
        gdp_growth = econ_indicators.get("gdp_growth")
        unemployment = econ_indicators.get("unemployment")
        
        if gdp_growth is not None:
            if gdp_growth < 1.0:
                base_score -= 0.1
                market_adjustments.append(f"Low GDP growth {gdp_growth}% (-10pts)")
            elif gdp_growth > 3.0:
                base_score += 0.1
                market_adjustments.append(f"Strong GDP growth {gdp_growth}% (+10pts)")
        
        if unemployment is not None:
            if unemployment > 6.0:
                base_score -= 0.1
                market_adjustments.append(f"High unemployment {unemployment}% (-10pts)")
            elif unemployment < 4.0:
                base_score += 0.05
                market_adjustments.append(f"Low unemployment {unemployment}% (+5pts)")
    
    # Combine all reasons
    reasons = [f"Risk grade {risk_grade}"] + market_adjustments
    
    # Map score to decision with market-aware thresholds
    if base_score >= 0.7:
        return "APPROVE", base_score, reasons
    elif base_score >= 0.45:  # Lowered threshold due to stronger market impact
        return "COUNTER", base_score, reasons
    else:
        return "DECLINE", base_score, reasons


# Module registry for dynamic invocation
MODULE_REGISTRY = {
    "fetch_customer": fetch_customer,
    "fetch_market": fetch_market,
    "rag_search": rag_search,
    "compute_decision": compute_decision,
}


def get_available_modules() -> List[str]:
    """Get list of available module names."""
    return list(MODULE_REGISTRY.keys())


def invoke_module(module_name: str, context: Context, params: Dict[str, Any]) -> Context:
    """
    Dynamically invoke a data source module.
    
    Args:
        module_name: Name of module to invoke
        context: Current agent context
        params: Parameters for the module
    
    Returns:
        Updated context
    
    Raises:
        ValueError: If module not found
    """
    if module_name not in MODULE_REGISTRY:
        raise ValueError(f"Unknown module: {module_name}")
    
    module_func = MODULE_REGISTRY[module_name]
    return module_func(context, params)
