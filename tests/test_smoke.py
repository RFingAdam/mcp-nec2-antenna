"""Smoke tests for mcp-nec2-antenna.

These don't run an actual NEC2 simulation. They verify the package and MCP
server module import and that the server object is built with its tool surface
registered.
"""
from __future__ import annotations

import mcp_nec2_antenna


def test_package_importable():
    """The package imports."""
    assert mcp_nec2_antenna is not None


def test_server_module_registers_mcp_tool_handlers():
    """The MCP server exposes its tool handlers through MCP 2 registration."""
    from mcp.types import CallToolRequestParams, ListToolsRequest

    from mcp_nec2_antenna import server

    assert server.server.name == "mcp-nec2-antenna"
    list_handler = server.server.get_request_handler("tools/list")
    call_handler = server.server.get_request_handler("tools/call")
    assert list_handler is not None
    assert list_handler.params_type is ListToolsRequest
    assert call_handler is not None
    assert call_handler.params_type is CallToolRequestParams
