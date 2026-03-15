# MCP Integration Concept

This directory will contain a minimal Model Context Protocol (MCP) server stub exposing internal resources (customer, market metrics, policy search, scoring) as protocol-compliant tools/resources for a planner-enabled agent.

Planned files:
- server.py: Minimal MCP server exposing tools
- tools.py: Implementations of callable tools (wrappers around existing internal functions)
- schemas.py: Pydantic models for tool IO
- adapter.py: Helper to let existing single_agent flow optionally call MCP tools instead of direct functions

