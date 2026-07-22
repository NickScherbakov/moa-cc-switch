import asyncio
import os
import pytest
from moa_engine.domain import Message, Task, VerificationResult, Artifact
from moa_engine.clients import CCSwitchClient
from moa_engine.agents import ProposerAgent, AggregatorAgent
from moa_engine.verifiers import CommandVerifier
from moa_engine.engine import MoAOrchestrator


def test_domain_dataclasses():
    msg = Message(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"

    task = Task(description="build something")
    assert task.description == "build something"
    assert "Ошибок нет" in task.error_history

    vr = VerificationResult(is_success=True, output_log="OK")
    assert vr.is_success is True
    assert vr.output_log == "OK"

    art = Artifact(path="test_art.tmp", content="print('test')")
    art.save()
    assert os.path.exists("test_art.tmp")
    with open("test_art.tmp", "r", encoding="utf-8") as f:
        assert f.read() == "print('test')"
    os.remove("test_art.tmp")


@pytest.mark.asyncio
async def test_cc_switch_client(respx_mock, monkeypatch):
    monkeypatch.setenv("MOCK_KEY", "mock-token")
    respx_mock.post("http://localhost:8080/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "class LRUCache:\n    pass"}}]}
    )
    client = CCSwitchClient("test-provider", "http://localhost:8080", "MOCK_KEY")
    res = await client.generate([Message(role="user", content="Implement lru_cache")])
    assert "LRUCache" in res


@pytest.mark.asyncio
async def test_agents(respx_mock, monkeypatch):
    monkeypatch.setenv("MOCK_KEY", "mock-token")
    respx_mock.post("http://localhost:8080/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "class LRUCache:\n    pass"}}]}
    )
    client = CCSwitchClient("test-provider", "http://localhost:8080", "MOCK_KEY")
    proposer = ProposerAgent(client)
    aggregator = AggregatorAgent(client)

    task = Task(description="Implement LRU cache")
    proposal = await proposer.process(task)
    assert "class LRUCache" in proposal

    aggregated = await aggregator.process_proposals(task, [proposal])
    assert "class LRUCache" in aggregated


@pytest.mark.asyncio
async def test_orchestrator_flow(respx_mock, monkeypatch):
    monkeypatch.setenv("MOCK_KEY", "mock-token")
    respx_mock.post("http://localhost:8080/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "class LRUCache:\n    pass"}}]}
    )
    client = CCSwitchClient("test-provider", "http://localhost:8080", "MOCK_KEY")
    proposer = ProposerAgent(client)
    aggregator = AggregatorAgent(client)
    verifier = CommandVerifier("python -c \"import os; assert os.path.exists('test_output.py')\"")


    orchestrator = MoAOrchestrator(
        proposers=[proposer],
        aggregator=aggregator,
        verifier=verifier,
        output_path="test_output.py",
        max_iterations=3,
    )

    success = await orchestrator.run_until_proven("Implement LRU Cache")
    assert success is True
    assert os.path.exists("test_output.py")
    if os.path.exists("test_output.py"):
        os.remove("test_output.py")

