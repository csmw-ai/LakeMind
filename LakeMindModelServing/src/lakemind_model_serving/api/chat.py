from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..auth import check_auth

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "auto"
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 0
    stream: bool = False


@router.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionRequest, request: Request):
    check_auth(request)
    if body.stream:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "STREAMING_NOT_SUPPORTED_IN_V0_2_0",
                "message": "Streaming is not supported in v0.2.0. Set stream=false.",
            },
        )
    gateway = request.app.state.gateway
    registry = request.app.state.registry
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    target_model = body.model
    resolved = registry.resolve_profile(body.model)
    if resolved:
        target_model = resolved["model_name"]

    try:
        result = gateway.chat(
            messages=messages,
            model=target_model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            stream=False,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
