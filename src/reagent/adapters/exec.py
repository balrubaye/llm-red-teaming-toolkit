import asyncio
import importlib.util
import time
from pathlib import Path

from reagent.adapters.base import Adapter, parse_model_string
from reagent.models import ChatRequest, ChatResponse, ChatUsage


class ScriptAdapter(Adapter):
    """Adapter for executing a custom Python script.
    
    The script must define a `complete(prompt: str) -> str` function (can be async).
    """
    name = "exec"

    def __init__(self):
        self.script_path = None
        self.module = None

    def supports(self, model_str: str) -> bool:
        provider, _ = parse_model_string(model_str)
        return provider == self.name

    def supports_seed(self) -> bool:
        return False

    async def aclose(self) -> None:
        pass

    async def complete(self, request: ChatRequest) -> ChatResponse:
        _, script_path_str = parse_model_string(request.model)
        
        # Lazy load the module once
        if not self.module:
            self.script_path = Path(script_path_str).resolve()
            if not self.script_path.exists():
                raise FileNotFoundError(f"Script not found: {self.script_path}")
                
            spec = importlib.util.spec_from_file_location("custom_adapter_script", self.script_path)
            if not spec or not spec.loader:
                raise ImportError(f"Could not load script: {self.script_path}")
                
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
            
            if not hasattr(self.module, "complete"):
                raise AttributeError(f"Script {self.script_path} must define a 'complete' function.")

        start_time = time.monotonic()
        
        # Extract the final attack payload
        prompt = ""
        if request.messages:
            prompt = request.messages[-1].content
            
        # Call the custom script
        if asyncio.iscoroutinefunction(self.module.complete):
            result = await self.module.complete(prompt)
        else:
            result = self.module.complete(prompt)
            
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        
        return ChatResponse(
            text=str(result),
            model=request.model,
            usage=ChatUsage(prompt_tokens=0, completion_tokens=0),
            latency_ms=elapsed_ms,
            cost_usd=0.0,
            finish_reason="stop",
            cached=False,
            raw=None,
        )
