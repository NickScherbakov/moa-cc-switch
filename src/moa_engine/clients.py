import asyncio
import os
import subprocess
import sys
import httpx
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from moa_engine.domain import Message
from moa_engine.config import config


class LLMClient(ABC):
    """Abstract interface for LLM client integration."""

    @abstractmethod
    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        """Generate response from language model given a list of messages."""
        pass


class HTTPDialect(ABC):
    """Strategy interface for provider-specific HTTP protocol variations."""

    @abstractmethod
    def get_url(self, endpoint: str) -> str:
        """Construct full API URL from base endpoint."""
        pass

    @abstractmethod
    def get_headers(self, api_key: str) -> Dict[str, str]:
        """Construct HTTP headers including authentication and API versioning."""
        pass

    @abstractmethod
    def get_payload(
        self, model_name: str, messages: List[Message], temperature: float
    ) -> Dict[str, Any]:
        """Construct request JSON payload."""
        pass

    @abstractmethod
    def parse_response(self, data: Dict[str, Any]) -> str:
        """Extract generated text content from API response dictionary."""
        pass


class AnthropicDialect(HTTPDialect):
    """Dialect for Anthropic Messages API format."""

    def get_url(self, endpoint: str) -> str:
        base = endpoint.rstrip("/")
        return f"{base}/v1/messages" if not base.endswith("/v1") else f"{base}/messages"

    def get_headers(self, api_key: str) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

    def get_payload(
        self, model_name: str, messages: List[Message], temperature: float
    ) -> Dict[str, Any]:
        return {
            "model": model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": 4096,
        }

    def parse_response(self, data: Dict[str, Any]) -> str:
        if "content" in data:
            content = data["content"]
            if isinstance(content, list) and len(content) > 0:
                return content[0].get("text", "")
            return str(content)
        return str(data)


class OpenAIDialect(HTTPDialect):
    """Dialect for OpenAI Chat Completions API format (default for OpenAI, DeepSeek, etc.)."""

    def get_url(self, endpoint: str) -> str:
        base = endpoint.rstrip("/")
        return f"{base}/v1/chat/completions" if not base.endswith("/v1") else f"{base}/chat/completions"

    def get_headers(self, api_key: str) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def get_payload(
        self, model_name: str, messages: List[Message], temperature: float
    ) -> Dict[str, Any]:
        return {
            "model": model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }

    def parse_response(self, data: Dict[str, Any]) -> str:
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        return str(data)


class CCSwitchClient(LLMClient):
    """Client routing requests through CC Switch proxy or direct LLM APIs with HTTPX & Retry logic."""

    def __init__(
        self,
        provider_name: str,
        endpoint: str,
        api_key_env: str,
        model_name: str = "claude-3-5-sonnet-20241022",
        dialect: Optional[HTTPDialect] = None,
    ):
        self.provider_name = provider_name
        self.endpoint = endpoint.rstrip("/")
        self.api_key_env = api_key_env
        self.model_name = model_name
        self._dialect = dialect or (AnthropicDialect() if "anthropic" in provider_name.lower() else OpenAIDialect())

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        api_key = os.getenv(self.api_key_env, "")
        
        if api_key:
            try:
                return await self._http_generate(messages, temperature, api_key)
            except Exception as e:
                print(f"⚠️ HTTP request to {self.provider_name} failed: {e}. Falling back to CLI.", file=sys.stderr)

        return await self._fallback_via_cli(messages)

    async def _http_generate(self, messages: List[Message], temperature: float, api_key: str) -> str:
        """Asynchronous HTTP request execution with exponential backoff retries using Strategy pattern."""
        headers = self._dialect.get_headers(api_key)
        payload = self._dialect.get_payload(self.model_name, messages, temperature)
        url = self._dialect.get_url(self.endpoint)

        async with httpx.AsyncClient(timeout=config.timeout_seconds) as http_client:
            for attempt in range(1, config.max_retries + 1):
                try:
                    response = await http_client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    return self._dialect.parse_response(data)
                except (httpx.HTTPStatusError, httpx.RequestError) as err:
                    if attempt == config.max_retries:
                        raise err
                    await asyncio.sleep(config.retry_backoff_factor ** attempt)

        raise RuntimeError("Failed to receive response from LLM API after retries.")


    async def _fallback_via_cli(self, messages: List[Message]) -> str:
        """Execute real CLI fallback via cc-switch utility."""
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])
        try:
            process = await asyncio.create_subprocess_exec(
                "cc-switch",
                "--provider",
                self.provider_name,
                "--model",
                self.model_name,
                prompt_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
            if process.returncode == 0:
                return stdout.decode("utf-8", errors="ignore").strip()

            error_msg = stderr.decode("utf-8", errors="ignore").strip() or f"Process exited with code {process.returncode}"
            return f"# CC Switch CLI fallback error: {error_msg}\npass\n"
        except Exception as e:
            return f"# CC Switch CLI fallback error: {e}\npass\n"



class OpenAIClient(LLMClient):
    """Direct provider driver for OpenAI models (GPT-4o, GPT-3.5, etc.)."""

    def __init__(
        self,
        endpoint: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        model_name: str = "gpt-4o",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.api_key_env = api_key_env
        self.model_name = model_name

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        api_key = os.getenv(self.api_key_env, "")
        if not api_key:
            return f"# Simulated response from OpenAIClient ({self.model_name})\npass\n"

        url = f"{self.endpoint}/chat/completions" if not self.endpoint.endswith("/chat/completions") else self.endpoint
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class DeepSeekClient(LLMClient):
    """Direct provider driver for DeepSeek API (DeepSeek-V3, DeepSeek-R1)."""

    def __init__(
        self,
        endpoint: str = "https://api.deepseek.com/v1",
        api_key_env: str = "DEEPSEEK_API_KEY",
        model_name: str = "deepseek-coder",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.api_key_env = api_key_env
        self.model_name = model_name

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        api_key = os.getenv(self.api_key_env, "")
        if not api_key:
            return f"# Simulated response from DeepSeekClient ({self.model_name})\npass\n"

        url = f"{self.endpoint}/chat/completions" if not self.endpoint.endswith("/chat/completions") else self.endpoint
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class OllamaClient(LLMClient):
    """Direct provider driver for local Ollama instances (Llama 3, Qwen 2.5, DeepSeek R1)."""

    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        model_name: str = "qwen2.5-coder",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        url = f"{self.endpoint}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {"temperature": temperature},
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except Exception as e:
            return f"# Local Ollama endpoint unreachable ({self.endpoint}): {e}\npass\n"


class ClaudeCLIClient(LLMClient):
    """Direct CLI agent driver for installed Claude Code CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])
        try:
            process = await asyncio.create_subprocess_exec(
                "claude", "--print", prompt_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45.0)
            if process.returncode == 0 and stdout:
                return stdout.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            return f"# Claude CLI error: {e}\npass\n"
        return f"# Claude CLI execution completed\npass\n"


class CopilotCLIClient(LLMClient):
    """Direct CLI agent driver for installed GitHub Copilot CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])
        try:
            cmd = f'copilot -p "{prompt_text}" --silent --yolo'
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45.0)
            if stdout:
                return stdout.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            return f"# Copilot CLI error: {e}\npass\n"
        return f"# Copilot CLI execution completed\npass\n"


class CodexCLIClient(LLMClient):
    """Direct CLI agent driver for installed Codex CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])
        try:
            process = await asyncio.create_subprocess_exec(
                "codex", "exec", prompt_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(input=b"\n"), timeout=45.0)
            if stdout:
                return stdout.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            return f"# Codex CLI error: {e}\npass\n"
        return f"# Codex CLI execution completed\npass\n"


class GeminiCLIClient(LLMClient):
    """Direct CLI agent driver for installed Gemini CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])
        try:
            process = await asyncio.create_subprocess_exec(
                "gemini", "-p", prompt_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(input=b"\n"), timeout=45.0)
            err_output = stderr.decode("utf-8", errors="ignore").strip() + "\n" + stdout.decode("utf-8", errors="ignore").strip()
            
            if process.returncode != 0 or "Error authenticating" in err_output or "Cloud Code Private API" in err_output:
                print(f"⚠️ Gemini CLI authentication / API error: Cloud Code Private API disabled or unauthorized.", file=sys.stderr)
                return f"# Gemini CLI Unavailable (Auth/API Error)\n# Enable Cloud Code Private API on GCP console: https://console.developers.google.com/apis/api/cloudcode-pa.googleapis.com\npass\n"
                
            if stdout:
                return stdout.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            return f"# Gemini CLI error: {e}\npass\n"
        return f"# Gemini CLI execution completed\npass\n"


class AntigravityCLIClient(LLMClient):
    """Direct CLI agent driver for installed Antigravity CLI (agy)."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])
        try:
            cmd = f'agy -p "{prompt_text}" --dangerously-skip-permissions'
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45.0)
            if stdout:
                return stdout.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            return f"# Antigravity CLI error: {e}\npass\n"
        return f"# Antigravity CLI execution completed\npass\n"


class KiroCLIClient(LLMClient):
    """Direct CLI agent driver for installed Kiro CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])

        # Attempt 1: kiro --print "<prompt>"
        try:
            process = await asyncio.create_subprocess_exec(
                "kiro", "--print", prompt_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=45.0)
            if process.returncode == 0 and stdout:
                result = stdout.decode("utf-8", errors="ignore").strip()
                if result:
                    return result
        except Exception:
            pass

        # Attempt 2: kiro -p "<prompt>"
        try:
            process = await asyncio.create_subprocess_exec(
                "kiro", "-p", prompt_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=45.0)
            if process.returncode == 0 and stdout:
                result = stdout.decode("utf-8", errors="ignore").strip()
                if result:
                    return result
        except Exception:
            pass

        # Attempt 3: kiro via stdin pipe
        try:
            process = await asyncio.create_subprocess_exec(
                "kiro",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(input=prompt_text.encode("utf-8")),
                timeout=45.0,
            )
            if process.returncode == 0 and stdout:
                result = stdout.decode("utf-8", errors="ignore").strip()
                if result:
                    return result
        except Exception as e:
            print(f"⚠️ Kiro CLI unavailable: {e}", file=sys.stderr)
            return f"# Kiro CLI error: {e}\npass\n"

        return "# Kiro CLI error: all three invocation strategies returned empty or non-zero\npass\n"




