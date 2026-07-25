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
    assert task.synergy_goal == ""
    assert "Ошибок нет" in task.error_history

    task_synergy = Task(description="build something", synergy_goal="High quality")
    assert task_synergy.synergy_goal == "High quality"

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

    success = await orchestrator.run_until_proven("Implement LRU Cache", synergy_goal="Perfect code")
    assert success is True
    assert os.path.exists("test_output.py")
    if os.path.exists("test_output.py"):
        os.remove("test_output.py")


@pytest.mark.asyncio
async def test_fetch_urls_context_gather(respx_mock):
    from moa_engine.runner import fetch_urls_context

    respx_mock.get("http://example1.com").respond(text="<html><body><h1>Site 1</h1></body></html>")
    respx_mock.get("http://example2.com").respond(text="<html><body><h1>Site 2</h1></body></html>")

    context = await fetch_urls_context(["http://example1.com", "http://example2.com"])
    assert "Site 1" in context
    assert "Site 2" in context
    assert "Website Context (http://example1.com)" in context
    assert "Website Context (http://example2.com)" in context


@pytest.mark.asyncio
async def test_orchestrator_cumulative_error_history(respx_mock, monkeypatch):
    monkeypatch.setenv("MOCK_KEY", "mock-token")
    respx_mock.post("http://localhost:8080/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "class LRUCache:\n    pass"}}]}
    )
    client = CCSwitchClient("test-provider", "http://localhost:8080", "MOCK_KEY")
    proposer = ProposerAgent(client)
    aggregator = AggregatorAgent(client)
    verifier = CommandVerifier("python -c \"import sys; sys.exit(1)\"")

    orchestrator = MoAOrchestrator(
        proposers=[proposer],
        aggregator=aggregator,
        verifier=verifier,
        output_path="test_fail_output.py",
        max_iterations=2,
    )

    success = await orchestrator.run_until_proven("Failing Task", synergy_goal="High quality")
    assert success is False
    if os.path.exists("test_fail_output.py"):
        os.remove("test_fail_output.py")



