import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from ..db import get_db
from ..models import ChatSession, ChatMessage, Hub
from ..services import qa

router = APIRouter(prefix="/api/hubs/{hub_id}/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    title: str = "New conversation"


class SendMessageRequest(BaseModel):
    content: str



@router.post("/sessions")
async def create_session(hub_id: str, req: CreateSessionRequest, db: AsyncSession = Depends(get_db)):
    """Create a new chat session."""
    session = ChatSession(hub_id=hub_id, title=req.title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"id": session.id, "title": session.title, "created_at": session.created_at.isoformat()}


@router.get("/sessions")
async def list_sessions(hub_id: str, db: AsyncSession = Depends(get_db)):
    """List chat sessions for this hub, most recent first."""
    result = await db.execute(
        select(
            ChatSession,
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.hub_id == hub_id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
    )
    return [
        {
            "id": s.id, "hub_id": s.hub_id, "title": s.title,
            "message_count": count,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
        }
        for s, count in result.all()
    ]


@router.get("/sessions/{session_id}")
async def get_session(hub_id: str, session_id: str, db: AsyncSession = Depends(get_db)):
    """Get a session with all its messages."""
    session = await db.get(ChatSession, session_id)
    if not session or session.hub_id != hub_id:
        raise HTTPException(404, "Session not found")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()

    return {
        "id": session.id, "hub_id": session.hub_id, "title": session.title,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "messages": [
            {
                "id": m.id, "role": m.role, "content": m.content,
                "citations": json.loads(m.citations_json) if m.citations_json else [],
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.delete("/sessions/{session_id}")
async def delete_session(hub_id: str, session_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a chat session and all its messages."""
    session = await db.get(ChatSession, session_id)
    if not session or session.hub_id != hub_id:
        raise HTTPException(404, "Session not found")
    await db.delete(session)
    await db.commit()
    return {"status": "deleted"}



@router.post("/sessions/{session_id}/messages")
async def send_message(
    hub_id: str, session_id: str, req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a message and get an AI response grounded in the knowledge graph."""
    session = await db.get(ChatSession, session_id)
    if not session or session.hub_id != hub_id:
        raise HTTPException(404, "Session not found")

    # Save user message
    user_msg = ChatMessage(session_id=session_id, role="user", content=req.content)
    db.add(user_msg)
    await db.flush()

    # Load conversation history
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    all_messages = result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in all_messages[:-1]]  # exclude the one we just added

    # Get AI response
    try:
        response = await qa.chat(hub_id, history, req.content)
    except Exception as e:
        response = {"answer": f"Error: {str(e)}", "citations": {}, "title_suggestion": None}

    # Save assistant message
    assistant_msg = ChatMessage(
        session_id=session_id, role="assistant",
        content=response["answer"],
        citations_json=json.dumps(response.get("citations", {})),
    )
    db.add(assistant_msg)

    # Update session title if suggested (first message)
    if response.get("title_suggestion") and session.title == "New conversation":
        session.title = response["title_suggestion"]

    # Update session timestamp
    from datetime import datetime, timezone
    session.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return {
        "user_message": {
            "id": user_msg.id, "role": "user", "content": user_msg.content,
            "created_at": user_msg.created_at.isoformat(),
        },
        "assistant_message": {
            "id": assistant_msg.id, "role": "assistant", "content": response["answer"],
            "citations": response.get("citations", {}),
            "created_at": assistant_msg.created_at.isoformat(),
        },
        "session_title": session.title,
    }
