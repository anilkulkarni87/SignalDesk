from __future__ import annotations


class ToolError(Exception):
    code = "TOOL_ERROR"


class ToolNotFoundError(ToolError):
    code = "NOT_FOUND"


class ToolConflictError(ToolError):
    code = "CONFLICT"
