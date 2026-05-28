from typing import List
from pydantic import BaseModel, Field

class AgentTask(BaseModel):
    id: str = Field(..., description="Unique task identifier")
    description: str = Field(..., description="The user requested task")
    mode: str = Field("plan", description="Execution mode: plan, build, auto")

class ContextData(BaseModel):
    files_analyzed: int = 0
    relevant_snippets: List[str] = []

class FileModification(BaseModel):
    filepath: str
    content: str
    is_new: bool = False

class BuildResponse(BaseModel):
    success: bool
    message: str
    modifications: List[FileModification] = []
    tokens_used: int = 0
