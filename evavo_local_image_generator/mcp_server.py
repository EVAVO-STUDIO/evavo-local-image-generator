"""
MCP server for EVAVO local image generator.

Provides Model Context Protocol integration for multi-modal AI generation
with evavo-local-storage, evavo-local-compute, and evavo-storage.
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

# MCP protocol support (when running as MCP server)
try:
    from mcp import Server, Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


logger = logging.getLogger(__name__)


class EvavoLocalImageGeneratorMCPServer:
    """MCP server for EVAVO local image generation."""
    
    def __init__(self):
        """Initialize MCP server."""
        self.mode = os.getenv("EVAVO_LOCAL_IMAGE_GENERATOR_MODE", "development")
        self.storage_uri = os.getenv(
            "EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE",
            "bee://primary/EVAVO/ImageGeneration"
        )
        self.comfyui_endpoint = os.getenv(
            "EVAVO_COMFYUI_ENDPOINT",
            "http://127.0.0.1:8188"
        )
        
        self.name = "evavo-local-image-generator"
        self.version = "0.1.0"
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_tools()
        
        logger.info(f"Initialized {self.name} in {self.mode} mode")
        logger.info(f"Storage URI: {self.storage_uri}")
        logger.info(f"ComfyUI Endpoint: {self.comfyui_endpoint}")
    
    def _register_tools(self) -> None:
        """Register available MCP tools."""
        self._tools = {
            "generate_image": {
                "description": "Generate images from text prompts using local ComfyUI",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Text prompt for image generation"
                        },
                        "negative_prompt": {
                            "type": "string",
                            "description": "Negative prompt to avoid certain features"
                        },
                        "width": {
                            "type": "integer",
                            "description": "Output image width in pixels",
                            "default": 512
                        },
                        "height": {
                            "type": "integer",
                            "description": "Output image height in pixels",
                            "default": 512
                        },
                        "steps": {
                            "type": "integer",
                            "description": "Number of inference steps",
                            "default": 20
                        },
                        "cfg_scale": {
                            "type": "number",
                            "description": "Guidance scale for prompt adherence",
                            "default": 7.5
                        },
                        "project_name": {
                            "type": "string",
                            "description": "Optional project context for organizing outputs"
                        }
                    },
                    "required": ["prompt"]
                }
            },
            "batch_generate_images": {
                "description": "Generate multiple images in batch",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prompts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of text prompts"
                        },
                        "project_name": {
                            "type": "string",
                            "description": "Project name for organizing outputs"
                        },
                        "width": {
                            "type": "integer",
                            "default": 512
                        },
                        "height": {
                            "type": "integer",
                            "default": 512
                        }
                    },
                    "required": ["prompts"]
                }
            },
            "get_storage_paths": {
                "description": "Get bee:// URIs for storage locations",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location_type": {
                            "type": "string",
                            "enum": ["outputs", "models", "workflows", "projects"],
                            "description": "Type of storage location"
                        },
                        "project_name": {
                            "type": "string",
                            "description": "Project name for projects location"
                        }
                    },
                    "required": ["location_type"]
                }
            },
            "get_generation_status": {
                "description": "Get status of generation tasks",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "Task ID to check"
                        }
                    }
                }
            }
        }
    
    def get_tools(self) -> Dict[str, Dict[str, Any]]:
        """Get registered tools."""
        return self._tools
    
    def process_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> str:
        """
        Process a tool call and return result.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            JSON string with result
        """
        if tool_name == "generate_image":
            return self._handle_generate_image(arguments)
        elif tool_name == "batch_generate_images":
            return self._handle_batch_generate(arguments)
        elif tool_name == "get_storage_paths":
            return self._handle_get_storage_paths(arguments)
        elif tool_name == "get_generation_status":
            return self._handle_get_status(arguments)
        else:
            return json.dumps({
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(self._tools.keys())
            })
    
    def _handle_generate_image(self, args: Dict[str, Any]) -> str:
        """Handle single image generation request."""
        result = {
            "status": "queued",
            "prompt": args.get("prompt"),
            "task_id": self._generate_task_id(),
            "timestamp": datetime.utcnow().isoformat(),
            "storage_uri": f"{self.storage_uri}/outputs",
            "mode": self.mode
        }
        return json.dumps(result, indent=2)
    
    def _handle_batch_generate(self, args: Dict[str, Any]) -> str:
        """Handle batch image generation request."""
        prompts = args.get("prompts", [])
        tasks = [
            {
                "index": i,
                "task_id": self._generate_task_id(),
                "prompt": prompt
            }
            for i, prompt in enumerate(prompts)
        ]
        
        result = {
            "status": "batch_queued",
            "count": len(tasks),
            "tasks": tasks,
            "storage_uri": f"{self.storage_uri}/outputs",
            "timestamp": datetime.utcnow().isoformat()
        }
        return json.dumps(result, indent=2)
    
    def _handle_get_storage_paths(self, args: Dict[str, Any]) -> str:
        """Handle storage path requests."""
        location_type = args.get("location_type", "outputs")
        
        paths = {
            "outputs": f"{self.storage_uri}/outputs",
            "models": "bee://primary/EVAVO/AI/Models",
            "workflows": f"{self.storage_uri}/workflows",
        }
        
        if location_type == "projects" and "project_name" in args:
            paths["project"] = f"bee://primary/Projects/{args['project_name']}"
        
        result = {
            "location_type": location_type,
            "paths": paths,
            "base_storage_uri": self.storage_uri
        }
        return json.dumps(result, indent=2)
    
    def _handle_get_status(self, args: Dict[str, Any]) -> str:
        """Handle status request."""
        result = {
            "server_name": self.name,
            "version": self.version,
            "mode": self.mode,
            "timestamp": datetime.utcnow().isoformat(),
            "storage_uri": self.storage_uri,
            "comfyui_endpoint": self.comfyui_endpoint
        }
        return json.dumps(result, indent=2)
    
    def _generate_task_id(self) -> str:
        """Generate unique task ID."""
        import hashlib
        timestamp = datetime.utcnow().isoformat()
        return hashlib.sha256(timestamp.encode()).hexdigest()[:16]


# Entry point for MCP server
def main():
    """Run as MCP server."""
    import sys
    
    server = EvavoLocalImageGeneratorMCPServer()
    
    # Simple STDIO protocol handler
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            
            try:
                request = json.loads(line)
                
                if request.get("jsonrpc") != "2.0":
                    continue
                
                method = request.get("method", "")
                params = request.get("params", {})
                request_id = request.get("id")
                
                if method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "tools": [
                                {
                                    "name": name,
                                    **spec
                                }
                                for name, spec in server.get_tools().items()
                            ]
                        }
                    }
                
                elif method == "tools/call":
                    tool_name = params.get("name", "")
                    tool_args = params.get("arguments", {})
                    
                    result = server.process_tool_call(tool_name, tool_args)
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": [{"type": "text", "text": result}]}
                    }
                
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"Unknown method: {method}"}
                    }
                
                print(json.dumps(response))
                sys.stdout.flush()
            
            except Exception as e:
                logger.error(f"Error processing request: {e}")
    
    except KeyboardInterrupt:
        logger.info("Server stopped")


if __name__ == "__main__":
    main()
