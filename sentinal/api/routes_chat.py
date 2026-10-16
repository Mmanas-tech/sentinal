from typing import Any

from fastapi import APIRouter

from sentinal.chat import route

router = APIRouter()


@router.post("/chat")
def chat(payload: dict[str, Any]):
    question = payload.get("question")
    analysis = payload.get("analysis")
    return route(question, analysis)
