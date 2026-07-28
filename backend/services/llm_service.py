# backend/services/llm_service.py
from backend.services.llm import create_orchestrator

class LLMService:
    instance = None

    def __init__(self, model_type, model_name, api_key="", base_url=None,
                 thinking="enabled", reasoning_effort="high"):
        self.orchestrator = create_orchestrator(
            model_type, model_name, api_key, base_url, thinking, reasoning_effort
        )

    async def generate_response(self, **kwargs):
        async for chunk in self.orchestrator.generate_response(**kwargs):
            yield chunk