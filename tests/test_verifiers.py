import pytest
from typing import List
from moa_engine.clients import LLMClient
from moa_engine.domain import Artifact, Message, VerificationResult
from moa_engine.verifiers import CommandVerifier, CompositeVerifier, LLMVerifier


class DummyLLMClient(LLMClient):
    def __init__(self, response: str):
        self.response = response
        self.last_messages: List[Message] = []
        self.last_temperature: float = 0.7

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        self.last_messages = messages
        self.last_temperature = temperature
        return self.response


@pytest.mark.asyncio
async def test_composite_verifier_all_pass():
    v1 = CommandVerifier("python -c \"assert True\"")
    v2 = CommandVerifier("python -c \"assert 1 == 1\"")
    composite = CompositeVerifier([v1, v2])

    art = Artifact(path="dummy.py", content="pass")
    res = await composite.verify(art)
    assert res.is_success is True
    assert "Step 1" in res.output_log
    assert "Step 2" in res.output_log


@pytest.mark.asyncio
async def test_composite_verifier_short_circuit_on_failure():
    v1 = CommandVerifier("python -c \"assert False, 'v1 error'\"")
    v2 = CommandVerifier("python -c \"assert True\"")
    composite = CompositeVerifier([v1, v2])

    art = Artifact(path="dummy.py", content="pass")
    res = await composite.verify(art)
    assert res.is_success is False
    assert "v1 error" in res.output_log
    assert "Step 2" not in res.output_log


@pytest.mark.asyncio
async def test_llm_verifier_success(tmp_path):
    client = DummyLLMClient('{"is_success": true, "reason": "Все супер"}')
    verifier = LLMVerifier(client=client, evaluation_prompt="Проверь отчет")
    art = Artifact(path=str(tmp_path / "result.md"), content="Отчет о работе")

    res = await verifier.verify(art)
    assert res.is_success is True
    assert res.output_log == "Все супер"
    assert len(client.last_messages) == 2
    assert client.last_messages[0].role == "system"
    assert client.last_messages[1].role == "user"
    assert "Отчет о работе" in client.last_messages[1].content
    assert client.last_temperature == 0.0


@pytest.mark.asyncio
async def test_llm_verifier_failure_with_markdown_codeblock(tmp_path):
    response = "```json\n{\"is_success\": false, \"reason\": \"Недостаточно информации\"}\n```"
    client = DummyLLMClient(response)
    verifier = LLMVerifier(client=client, evaluation_prompt="Проверь полноту")
    art = Artifact(path=str(tmp_path / "result.md"), content="Короткий текст")

    res = await verifier.verify(art)
    assert res.is_success is False
    assert res.output_log == "Недостаточно информации"


@pytest.mark.asyncio
async def test_llm_verifier_invalid_json(tmp_path):
    client = DummyLLMClient("Это не JSON ответ")
    verifier = LLMVerifier(client=client, evaluation_prompt="Проверь")
    art = Artifact(path=str(tmp_path / "result.md"), content="Текст")

    with pytest.raises(RuntimeError, match="Внутренняя ошибка LLM-верификатора"):
        await verifier.verify(art)


@pytest.mark.asyncio
async def test_llm_verifier_regex_json_parsing(tmp_path):
    response = "Вот разбор:\n```json\n{\"is_success\": true, \"reason\": \"Найден через regex\"}\n```\nНадеюсь помогло!"
    client = DummyLLMClient(response)
    verifier = LLMVerifier(client=client, evaluation_prompt="Проверь")
    art = Artifact(path=str(tmp_path / "result.md"), content="Текст")

    res = await verifier.verify(art)
    assert res.is_success is True
    assert res.output_log == "Найден через regex"


@pytest.mark.asyncio
async def test_llm_verifier_synergy_goal_injection(tmp_path):
    client = DummyLLMClient('{"is_success": true, "reason": "Цель учтена"}')
    verifier = LLMVerifier(client=client, evaluation_prompt="Проверь")
    art = Artifact(path=str(tmp_path / "result.md"), content="Текст")

    res = await verifier.verify(art, synergy_goal="Максимальное качество кода")
    assert res.is_success is True
    system_msg = client.last_messages[0].content
    assert "Максимальное качество кода" in system_msg
    assert "главную цель команды" in system_msg

