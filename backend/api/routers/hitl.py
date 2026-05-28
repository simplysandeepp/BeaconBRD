import os
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(PROJECT_ROOT)

from brd_module.hitl.orchestrator import submit_ad_hoc_prompt, get_hitl_status

router = APIRouter(
    prefix="/sessions/{session_id}/hitl",
    tags=["HITL"]
)

class PromptRequest(BaseModel):
    prompt: str

@router.post("/prompt")
def process_ai_prompt(session_id: str, body: PromptRequest):
    """
    Handle natural language commands from the AI Command Bar.
    """
    res = submit_ad_hoc_prompt(session_id, body.prompt)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "AI prompt failed"))
    return res

@router.get("/status")
def get_status(session_id: str):
    return get_hitl_status(session_id)

@router.post("/start")
def start_hitl(session_id: str, round: int = 1):
    # Stub for now
    return {"message": "HITL round started", "complete": True}

@router.get("/questions")
def get_questions(session_id: str):
    return {"questions": []}

@router.post("/answers")
def submit_answers(session_id: str, body: Dict[str, Any]):
    return {"message": "Answers received"}

@router.put("/requirements")
def edit_requirement(session_id: str, body: Dict[str, Any]):
    return {"message": "Requirement updated"}
