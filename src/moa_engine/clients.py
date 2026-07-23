import asyncio
import os
import subprocess
import sys
import httpx
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from moa_engine.domain import Message
from moa_engine.config import config


def is_error_response(response: str) -> bool:
    """Check if a response text represents an error/fallback message instead of a valid LLM output."""
    if not response or not isinstance(response, str):
        return True
    first_lines = response.strip().splitlines()[:3]
    for line in first_lines:
        line_lower = line.strip().lower()
        if line_lower.startswith("#") and ("error" in line_lower or "unavailable" in line_lower or "unreachable" in line_lower):
            return True
    return False


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


class BaseHTTPClient(LLMClient):
    """Base class for HTTP-based LLM clients with retry logic and dialect parsing."""

    def __init__(
        self,
        endpoint: str,
        api_key_env: str,
        model_name: str,
        dialect: HTTPDialect,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.api_key_env = api_key_env
        self.model_name = model_name
        self._dialect = dialect
        self._http_client = http_client

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        api_key = os.getenv(self.api_key_env, "")
        if not api_key:
            return f"# Simulated response from {self.__class__.__name__} ({self.model_name})\npass\n"

        headers = self._dialect.get_headers(api_key)
        payload = self._dialect.get_payload(self.model_name, messages, temperature)
        url = self._dialect.get_url(self.endpoint)

        client = self._http_client or httpx.AsyncClient(timeout=config.timeout_seconds)
        should_close = self._http_client is None
        try:
            for attempt in range(1, config.max_retries + 1):
                try:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    return self._dialect.parse_response(data)
                except (httpx.HTTPStatusError, httpx.RequestError) as err:
                    if attempt == config.max_retries:
                        raise err
                    await asyncio.sleep(config.retry_backoff_factor ** attempt)
        finally:
            if should_close:
                await client.aclose()

        raise RuntimeError("Failed to receive response from LLM API after retries.")


class CCSwitchClient(BaseHTTPClient):
    """Client routing requests through CC Switch proxy or direct LLM APIs with HTTPX & Retry logic."""

    def __init__(
        self,
        provider_name: str,
        endpoint: str,
        api_key_env: str,
        model_name: str = "claude-3-5-sonnet-20241022",
        dialect: Optional[HTTPDialect] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.provider_name = provider_name
        resolved_dialect = dialect or (AnthropicDialect() if "anthropic" in provider_name.lower() else OpenAIDialect())
        super().__init__(
            endpoint=endpoint,
            api_key_env=api_key_env,
            model_name=model_name,
            dialect=resolved_dialect,
            http_client=http_client,
        )

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        api_key = os.getenv(self.api_key_env, "")
        if api_key:
            try:
                return await super().generate(messages, temperature)
            except Exception as e:
                print(f"⚠️ HTTP request to {self.provider_name} failed: {e}. Falling back to CLI.", file=sys.stderr)

        return await self._fallback_via_cli(messages)

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


class OpenAIClient(BaseHTTPClient):
    """Direct provider driver for OpenAI models (GPT-4o, GPT-3.5, etc.)."""

    def __init__(
        self,
        endpoint: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        model_name: str = "gpt-4o",
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(
            endpoint=endpoint,
            api_key_env=api_key_env,
            model_name=model_name,
            dialect=OpenAIDialect(),
            http_client=http_client,
        )


class DeepSeekClient(BaseHTTPClient):
    """Direct provider driver for DeepSeek API (DeepSeek-V3, DeepSeek-R1)."""

    def __init__(
        self,
        endpoint: str = "https://api.deepseek.com/v1",
        api_key_env: str = "DEEPSEEK_API_KEY",
        model_name: str = "deepseek-coder",
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(
            endpoint=endpoint,
            api_key_env=api_key_env,
            model_name=model_name,
            dialect=OpenAIDialect(),
            http_client=http_client,
        )


class OllamaClient(LLMClient):
    """Direct provider driver for local Ollama instances (Llama 3, Qwen 2.5, DeepSeek R1)."""

    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        model_name: str = "qwen2.5-coder",
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self._http_client = http_client

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        url = f"{self.endpoint}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {"temperature": temperature},
            "stream": False,
        }

        client = self._http_client or httpx.AsyncClient(timeout=config.timeout_seconds)
        should_close = self._http_client is None
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            return f"# Local Ollama endpoint unreachable ({self.endpoint}): {e}\npass\n"
        finally:
            if should_close:
                await client.aclose()


class BaseCLIClient(LLMClient):
    """Base class for CLI agent drivers providing safe subprocess execution without shell invocation."""

    def format_prompt(self, messages: List[Message]) -> str:
        return "\n".join([f"{m.role}: {m.content}" for m in messages])

    async def _exec_subprocess(
        self,
        cmd: List[str],
        input_data: Optional[bytes] = None,
        timeout: float = 45.0,
    ) -> Optional[str]:
        """Safely execute a CLI command using subprocess_exec (no shell=True)."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=subprocess.PIPE if input_data is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=input_data),
            timeout=timeout,
        )
        if process.returncode == 0 and stdout:
            res = stdout.decode("utf-8", errors="ignore").strip()
            if res:
                return res
        return None


class ClaudeCLIClient(BaseCLIClient):
    """Direct CLI agent driver for installed Claude Code CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = self.format_prompt(messages)
        try:
            res = await self._exec_subprocess(["claude", "--print", prompt_text], timeout=45.0)
            if res:
                return res
        except Exception as e:
            return f"# Claude CLI error: {e}\npass\n"
        return "# Claude CLI error: execution returned empty or non-zero\npass\n"


class CopilotCLIClient(BaseCLIClient):
    """Direct CLI agent driver for installed GitHub Copilot CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = self.format_prompt(messages)
        try:
            res = await self._exec_subprocess(["copilot", "-p", prompt_text, "--silent", "--yolo"], timeout=45.0)
            if res:
                return res
        except Exception as e:
            return f"# Copilot CLI error: {e}\npass\n"
        return "# Copilot CLI error: execution returned empty or non-zero\npass\n"


class CodexCLIClient(BaseCLIClient):
    """Direct CLI agent driver for installed Codex CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = self.format_prompt(messages)
        try:
            res = await self._exec_subprocess(["codex", "exec", prompt_text], input_data=b"\n", timeout=45.0)
            if res:
                return res
        except Exception as e:
            return f"# Codex CLI error: {e}\npass\n"
        return "# Codex CLI error: execution returned empty or non-zero\npass\n"


class GeminiCLIClient(BaseCLIClient):
    """Direct CLI agent driver for installed Gemini CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = self.format_prompt(messages)
        try:
            process = await asyncio.create_subprocess_exec(
                "gemini", "-p", prompt_text,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(input=b"\n"), timeout=45.0)
            err_output = stderr.decode("utf-8", errors="ignore").strip() + "\n" + stdout.decode("utf-8", errors="ignore").strip()
            
            if process.returncode != 0 or "Error authenticating" in err_output or "Cloud Code Private API" in err_output:
                print("⚠️ Gemini CLI authentication / API error: Cloud Code Private API disabled or unauthorized.", file=sys.stderr)
                return (
                    "# Gemini CLI Unavailable (Auth/API Error)\n"
                    "# Enable Cloud Code Private API on GCP console: https://console.developers.google.com/apis/api/cloudcode-pa.googleapis.com\npass\n"
                )
                
            if stdout:
                res = stdout.decode("utf-8", errors="ignore").strip()
                if res:
                    return res
        except Exception as e:
            return f"# Gemini CLI error: {e}\npass\n"
        return "# Gemini CLI error: execution returned empty or non-zero\npass\n"


class AntigravityCLIClient(BaseCLIClient):
    """Direct CLI agent driver for installed Antigravity CLI (agy)."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = self.format_prompt(messages)
        try:
            res = await self._exec_subprocess(["agy", "-p", prompt_text, "--dangerously-skip-permissions"], timeout=45.0)
            if res:
                return res
        except Exception as e:
            return f"# Antigravity CLI error: {e}\npass\n"
        return "# Antigravity CLI error: execution returned empty or non-zero\npass\n"


class KiroCLIClient(BaseCLIClient):
    """Direct CLI agent driver for installed Kiro CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = self.format_prompt(messages)

        # Attempt 1: kiro --print "<prompt>"
        try:
            res = await self._exec_subprocess(["kiro", "--print", prompt_text], timeout=45.0)
            if res:
                return res
        except Exception:
            pass

        # Attempt 2: kiro -p "<prompt>"
        try:
            res = await self._exec_subprocess(["kiro", "-p", prompt_text], timeout=45.0)
            if res:
                return res
        except Exception:
            pass

        # Attempt 3: kiro via stdin pipe
        try:
            res = await self._exec_subprocess(["kiro"], input_data=prompt_text.encode("utf-8"), timeout=45.0)
            if res:
                return res
        except Exception as e:
            print(f"⚠️ Kiro CLI unavailable: {e}", file=sys.stderr)
            return f"# Kiro CLI error: {e}\npass\n"

        return "# Kiro CLI error: all three invocation strategies returned empty or non-zero\npass\n"
