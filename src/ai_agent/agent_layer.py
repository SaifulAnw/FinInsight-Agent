from smolagents import ToolCallingAgent, OpenAIServerModel
from dotenv import load_dotenv
import os

load_dotenv()

BASE_URL = os.getenv("OLLAMA_BASE_URL").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL")


def build_reasoning_model():
    return OpenAIServerModel(
        model_id=MODEL,
        api_base=BASE_URL + "/v1",
        api_key="dummy"
    )