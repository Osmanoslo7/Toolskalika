from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.tokens import get_current_user
from ..db import get_db
from ..models import ToolRun, User
from .base import all_tools, get_tool

router = APIRouter(prefix="/tools", tags=["tools"])


class RunBody(BaseModel):
    prompt: str


class RunResponse(BaseModel):
    tool: str
    output: str
    used_llm: bool


@router.get("")
def list_tools(user: User = Depends(get_current_user)):
    return [{"name": t.name, "description": t.description} for t in all_tools()]


@router.post("/{name}/run", response_model=RunResponse)
def run_tool(
    name: str,
    body: RunBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tool = get_tool(name)
    if tool is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such tool: {name}")

    if not body.prompt.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "prompt must not be empty")

    output, used_llm = tool.handler(body.prompt)

    db.add(
        ToolRun(
            user_id=user.id,
            tool_name=name,
            input_prompt=body.prompt,
            output_text=output,
            used_llm=used_llm,
        )
    )
    db.commit()

    return RunResponse(tool=name, output=output, used_llm=used_llm)


@router.get("/history")
def history(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    runs = (
        db.query(ToolRun)
        .filter(ToolRun.user_id == user.id)
        .order_by(ToolRun.id.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": r.id,
            "tool": r.tool_name,
            "prompt": r.input_prompt,
            "output": r.output_text,
            "used_llm": r.used_llm,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]
