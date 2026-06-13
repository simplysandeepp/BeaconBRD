"""
adk_config.py
Google ADK configuration — model, session service, and runner setup.
"""
import os
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner


def get_adk_model() -> LiteLlm:
    """Create the shared ADK model instance backed by OpenRouter."""
    model_name = os.environ.get("OPENROUTER_MODEL", "openrouter/owl-alpha")
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    return LiteLlm(model=model_name, api_key=api_key)


def get_session_service() -> InMemorySessionService:
    """Create an in-memory session service. Replace with DB-backed for production."""
    return InMemorySessionService()


def get_runner(session_service: InMemorySessionService, root_agent) -> Runner:
    """Create the ADK Runner that executes the workflow graph."""
    return Runner(
        agent=root_agent,
        session_service=session_service,
        app_name="beacon_brd",
    )
