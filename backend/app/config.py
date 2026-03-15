import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://agenthub:agenthub@localhost:5432/agenthub")
DATABASE_URL_SYNC = os.getenv("DATABASE_URL_SYNC", "postgresql://agenthub:agenthub@localhost:5432/agenthub")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "agenthub123")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")
BROWSERLESS_URL = os.getenv("BROWSERLESS_URL", "ws://localhost:3300")
BROWSERLESS_TOKEN = os.getenv("BROWSERLESS_TOKEN", "mobhub123")
