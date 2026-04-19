"""Local labor-law tools that run inside the middlend process.

These tools are registered into the OpenHarness ToolRegistry so the LLM
can call them alongside MCP-based PKULaw tools.
"""

from app.tools.labor_compensation import LaborCompensationTool
from app.tools.labor_document import LaborDocumentTool

ALL_LOCAL_TOOLS = (
    LaborCompensationTool(),
    LaborDocumentTool(),
)

__all__ = [
    "LaborCompensationTool",
    "LaborDocumentTool",
    "ALL_LOCAL_TOOLS",
]
