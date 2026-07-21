import pytest
import respx
import httpx
from moa_engine.domain import Message
from moa_engine.clients import CCSwitchClient
from moa_engine.config import Config


@pytest.mark.asyncio
async def test_cc_switch_http_success(respx_mock):
    respx_mock.post("https://api.openai.com/v1/chat/completions").respond(
        json={
            "choices": [
                {"message": {"content": "def hello(): return 'world'"}}
            ]
        }
    )

    client = CCSwitchClient("openai", "https://api.openai.com", "TEST_KEY")
    result = await client._http_generate([Message(role="user", content="hello")], temperature=0.5, api_key="sk-test")
    assert result == "def hello(): return 'world'"


@pytest.mark.asyncio
async def test_cc_switch_http_anthropic_format(respx_mock):
    respx_mock.post("https://api.anthropic.com/v1/messages").respond(
        json={
            "content": [
                {"type": "text", "text": "class A: pass"}
            ]
        }
    )

    client = CCSwitchClient("anthropic", "https://api.anthropic.com", "TEST_KEY")
    result = await client._http_generate([Message(role="user", content="hello")], temperature=0.7, api_key="sk-test")
    assert result == "class A: pass"


@pytest.mark.asyncio
async def test_cc_switch_http_retry_on_failure(respx_mock):
    route = respx_mock.post("https://api.openai.com/v1/chat/completions")
    route.side_effect = [
        httpx.Response(500),
        httpx.Response(200, json={"choices": [{"message": {"content": "recovered"}}]}),
    ]

    client = CCSwitchClient("openai", "https://api.openai.com", "TEST_KEY")
    result = await client._http_generate([Message(role="user", content="test")], temperature=0.5, api_key="sk-test")
    assert result == "recovered"
    assert route.call_count == 2
