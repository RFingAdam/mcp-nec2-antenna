"""Smoke tests for mcp-nec2-antenna.

These don't run an actual NEC2 simulation — they verify the package and MCP
server module import and that the server object is built with its tool surface
registered.
"""
from __future__ import annotations

import mcp_nec2_antenna


def test_package_importable():
    """The package imports."""
    assert mcp_nec2_antenna is not None


def test_server_module_importable():
    """The MCP server module imports and exposes a named Server."""
    from mcp_nec2_antenna import server

    assert server.server is not None
    assert server.server.name == "mcp-nec2-antenna"
