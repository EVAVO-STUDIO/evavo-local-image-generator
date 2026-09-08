"""Tests for EVAVO generators"""

import pytest
from evavo_local_image_generator.storage import BeeStorageClient
from evavo_local_image_generator.mcp_server import EvavoLocalImageGeneratorMCPServer


def test_storage_client():
    """Test storage client"""
    client = BeeStorageClient()
    data = b"test data"
    digest = client.compute_digest(data)
    assert len(digest) == 64  # SHA-256 hex string


def test_mcp_server_initialization():
    """Test MCP server initialization"""
    server = EvavoLocalImageGeneratorMCPServer()
    assert len(server.tools) == 5
    assert any(t["name"] == "generate_image" for t in server.tools)


@pytest.mark.asyncio
async def test_tool_call():
    """Test tool call handling"""
    server = EvavoLocalImageGeneratorMCPServer()
    result = await server.handle_tool_call("generate_image", {"prompt": "test"})
    assert result["status"] == "queued"
    assert result["tool"] == "generate_image"
