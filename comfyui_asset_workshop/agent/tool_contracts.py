"""Shared MCP side-effect hints and argument descriptions."""
from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field


READ = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                       idempotent_hint=True, open_world_hint=False)
LOCAL = ToolAnnotations(read_only_hint=False, destructive_hint=False,
                        idempotent_hint=False, open_world_hint=False)
START = ToolAnnotations(read_only_hint=False, destructive_hint=False,
                        idempotent_hint=False, open_world_hint=True)
REMOVE = ToolAnnotations(read_only_hint=False, destructive_hint=True,
                          idempotent_hint=False, open_world_hint=False)
DISPATCH = ToolAnnotations(read_only_hint=False, destructive_hint=True,
                            idempotent_hint=False, open_world_hint=True)

RunId = Annotated[str, Field(description="Run ID returned by the matching create or status action.")]
CreationId = Annotated[str, Field(description="Creation ID from this workflow's create, Gallery or status response.")]
RequestId = Annotated[str, Field(description="Unique ID for this intentional start. Retry the same operation and payload with the same ID.")]
InputPath = Annotated[str, Field(description="Local file authorized by an explicit input root or file in the MCP configuration.")]


def tool_registration(server, checked):
    def tool(annotations, *, structured_output=True):
        register = server.tool(annotations=annotations, structured_output=structured_output)
        return lambda function: register(checked(function))
    return tool
