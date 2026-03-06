import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")

MODELS = {
    "logic": os.getenv("OLLAMA_MODEL"),
    "reasoning": os.getenv("OLLAMA_REASON_MODEL"),
    "chat": os.getenv("OLLAMA_CHAT_MODEL")
}

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10
)