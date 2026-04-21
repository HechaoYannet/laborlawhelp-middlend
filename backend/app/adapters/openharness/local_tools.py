from app.tools.labor_compensation import LaborCompensationTool
from app.tools.labor_document import LaborDocumentTool
from app.tools.labor_fact_extract import LaborFactExtractTool
from app.tools.labor_lawyer_recommend import LaborLawyerRecommendTool

ALL_LOCAL_TOOLS = (
    LaborCompensationTool(),
    LaborDocumentTool(),
    LaborFactExtractTool(),
    LaborLawyerRecommendTool(),
)

__all__ = [
    "LaborCompensationTool",
    "LaborDocumentTool",
    "LaborFactExtractTool",
    "LaborLawyerRecommendTool",
    "ALL_LOCAL_TOOLS",
]
