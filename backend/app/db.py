"""Database models. SQLite by default; set DATABASE_URL to use PostgreSQL."""
import os
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./knowflow.db")
if DATABASE_URL.startswith("postgres://"):  # Render/Neon style URL
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    pw_hash = Column(String(300), nullable=False)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    is_demo = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)
    analyzed_at = Column(DateTime)


class Membership(Base):
    __tablename__ = "memberships"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role = Column(String(20), nullable=False)  # manager | developer | newcomer


class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    kind = Column(String(20), nullable=False)  # github | document | notes | tasks | interview
    name = Column(String(300), nullable=False)
    visibility = Column(String(20), default="everyone")  # everyone | managers
    content = Column(Text, default="")
    meta = Column(JSON, default=dict)
    added_by = Column(String(200), default="")
    created_at = Column(DateTime, default=now)


class Claim(Base):
    __tablename__ = "claims"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    fingerprint = Column(String(80), nullable=False)
    category = Column(String(30), nullable=False)
    title = Column(String(400), nullable=False)
    text = Column(Text, nullable=False)
    engine_state = Column(String(20), nullable=False)  # what the verifier decided
    state = Column(String(20), nullable=False)  # effective state (a reviewer may resolve a conflict)
    why = Column(Text, default="")
    origin = Column(String(20), default="rule")  # rule | llm
    origin_source = Column(Integer)  # source the claim was stated in, if any
    module = Column(String(300), default="")
    people = Column(JSON, default=list)
    evidence = Column(JSON, default=list)
    review_status = Column(String(20), default="pending")  # pending | approved | rejected
    edited_text = Column(Text)
    review_note = Column(Text, default="")
    reviewed_by = Column(String(200), default="")
    reviewed_at = Column(DateTime)


class Version(Base):
    __tablename__ = "versions"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    number = Column(Integer, nullable=False)
    score = Column(Float, default=0)
    note = Column(Text, default="")
    created_by = Column(String(200), default="")
    created_at = Column(DateTime, default=now)
    payload = Column(JSON, default=dict)


def init_db():
    Base.metadata.create_all(engine)
