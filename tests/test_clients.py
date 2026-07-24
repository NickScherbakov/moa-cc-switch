import pytest
import respx
import httpx
from moa_engine.domain import Message
from moa_engine.clients import (
    AnthropicDialect,
    BaseHTTPClient,
    CCSwitchClient,
    DeepSeekClient,
    OllamaClient,
    OpenAIDialect,
    OpenAIClient,
    is_error_response,
)


@pytest.mark.asyncio
async def test_base_http_client_driver(respx_mock):
    respx_mock.post("https://api.anthropic.com/v1/messages").respond(
        json={"content": [{"text": "anthropic output"}]}
    )
    client = BaseHTTPClient(
        endpoint="https://api.anthropic.com",
        api_key_env="TEST_KEY",
        model_name="claude-3-5-sonnet-20241022",
        dialect=AnthropicDialect(),
    )

    import os
    os.environ["TEST_KEY"] = "sk-ant-fake"
    res = await client.generate([Message(role="user", content="hi")])
    assert res == "anthropic output"
    del os.environ["TEST_KEY"]



@pytest.mark.asyncio
async def test_openai_client_driver(respx_mock):
    respx_mock.post("https://api.openai.com/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "openai output"}}]}
    )
    client = OpenAIClient("https://api.openai.com/v1", api_key_env="TEST_KEY", model_name="gpt-4o")
    
    sim_res = await client.generate([Message(role="user", content="hi")])
    assert "Simulated response" in sim_res

    import os
    os.environ["TEST_KEY"] = "sk-fake"
    res = await client.generate([Message(role="user", content="hi")])
    assert res == "openai output"
    del os.environ["TEST_KEY"]


@pytest.mark.asyncio
async def test_deepseek_client_driver(respx_mock):
    respx_mock.post("https://api.deepseek.com/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "deepseek output"}}]}
    )
    client = DeepSeekClient("https://api.deepseek.com/v1", api_key_env="TEST_KEY", model_name="deepseek-coder")
    
    import os
    os.environ["TEST_KEY"] = "ds-fake"
    res = await client.generate([Message(role="user", content="hi")])
    assert res == "deepseek output"
    del os.environ["TEST_KEY"]


@pytest.mark.asyncio
async def test_ollama_client_driver(respx_mock):
    respx_mock.post("http://localhost:11434/api/chat").respond(
        json={"message": {"content": "ollama output"}}
    )
    client = OllamaClient("http://localhost:11434", model_name="qwen2.5-coder")
    res = await client.generate([Message(role="user", content="hi")])
    assert res == "ollama output"


@pytest.mark.asyncio
async def test_claude_cli_real_fallback():
    client = CCSwitchClient("anthropic", "https://api.anthropic.com", "NON_EXISTENT_KEY")
    res = await client.generate([Message(role="user", content="Respond with string OK_REAL_TEST")])
    assert isinstance(res, str)
    assert len(res) > 0


def test_is_error_response_helper():
    assert is_error_response("# Claude CLI error: failed\npass\n") is True
    assert is_error_response("# Gemini CLI Unavailable (Auth/API Error)\npass\n") is True
    assert is_error_response("# Local Ollama endpoint unreachable (http://loc): err\npass\n") is True
    assert is_error_response("class LRUCache:\n    pass") is False
    assert is_error_response("") is True

