import uuid
import secrets
from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ARRAY
from .db import Base


def gen_id():
    return str(uuid.uuid4())


def gen_api_key():
    return "ah_" + secrets.token_hex(32)


def utcnow():
    return datetime.now(timezone.utc)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(String(100), unique=True, default=gen_api_key)
    agent_type: Mapped[str] = mapped_column(String(30), default="custom")
    description: Mapped[str] = mapped_column(Text, default="")
    llm_provider: Mapped[str] = mapped_column(String(30), default="openai")
    llm_model: Mapped[str] = mapped_column(String(100), default="")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    parent_agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=True)
    required_skills_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Hub(Base):
    __tablename__ = "hubs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"))
    graph_id: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default="seeding")
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HubMember(Base):
    __tablename__ = "hub_members"
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Provenance(Base):
    __tablename__ = "provenance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    node_uuid: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    edge_uuid: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=True)
    episode_name: Mapped[str] = mapped_column(String(200), default="")
    paper_title: Mapped[str] = mapped_column(Text, nullable=True)
    paper_doi: Mapped[str] = mapped_column(String(200), nullable=True)
    paper_source: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Vote(Base):
    __tablename__ = "votes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    node_uuid: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    edge_uuid: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=False)
    vote: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Episode(Base):
    """Every piece of content added to the knowledge graph, with full source tracking."""
    __tablename__ = "episodes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_length: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=True)
    source_title: Mapped[str] = mapped_column(String(500), nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), default="text")
    search_query: Mapped[str] = mapped_column(String(500), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=True)
    agent_action: Mapped[str] = mapped_column(String(50), default="explore")
    entities_extracted: Mapped[int] = mapped_column(Integer, default=0)
    edges_extracted: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(2000), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str] = mapped_column(Text, nullable=True)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=True)
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentMemory(Base):
    __tablename__ = "agent_memory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    from_agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=False)
    to_agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=True)
    msg_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    ref_node_uuid: Mapped[str] = mapped_column(String(100), nullable=True)
    ref_edge_uuid: Mapped[str] = mapped_column(String(100), nullable=True)
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EntityAsset(Base):
    __tablename__ = "entity_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    node_uuid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    mime_type: Mapped[str] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EntityMeta(Base):
    __tablename__ = "entity_meta"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    node_uuid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HubSkill(Base):
    __tablename__ = "hub_skills"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    skill_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SkillExecution(Base):
    __tablename__ = "skill_executions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    skill_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_skills.id"))
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=True)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Activity(Base):
    __tablename__ = "activity_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hub_id: Mapped[str] = mapped_column(String(36), ForeignKey("hubs.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
