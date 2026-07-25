import json
import pytest
from unittest.mock import AsyncMock, patch

from moa_engine.domain import Message, DiscoveryState, Task
from moa_engine.agents import ProposerAgent, CriticAgent, AggregatorAgent
from moa_engine.engine import MoAOrchestrator
from moa_engine.verifiers import CommandVerifier


def test_discovery_domain():
    msg = Message(role="user", content="Hello", name="Alice")
    assert msg.role == "user"
    assert msg.content == "Hello"
    assert msg.name == "Alice"

    state = DiscoveryState(current_summary="Initial idea")
    assert state.current_summary == "Initial idea"
    assert state.chat_history == []

    state.chat_history.append(msg)
    assert len(state.chat_history) == 1
    assert state.chat_history[0].name == "Alice"


@pytest.mark.asyncio
async def test_agents_process_discovery(respx_mock, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "mock-token")
    
    # Mock LLM API response for discovery JSON
    aggregator_json = json.dumps({
        "summary": "Compressed architectural spec for custom LRU cache",
        "reply": "What max size should the cache support?"
    })

    respx_mock.post("https://api.openai.com/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": aggregator_json}}]}
    )

    from moa_engine.clients import CCSwitchClient
    client = CCSwitchClient("openai", "https://api.openai.com", "TEST_KEY")

    proposer = ProposerAgent(client)
    critic = CriticAgent(client)
    aggregator = AggregatorAgent(client)

    state = DiscoveryState(
        current_summary="Make a high performance LRU cache",
        chat_history=[Message(role="user", content="Need O(1) ops", name="User")]
    )

    prop_res = await proposer.process(state)
    assert len(prop_res) > 0

    crit_res = await critic.process(state)
    assert len(crit_res) > 0

    agg_res = await aggregator.process_discovery(state, [prop_res], crit_res)
    assert "Compressed architectural spec" in agg_res
    assert "What max size" in agg_res


@pytest.mark.asyncio
async def test_run_discovery_chat_repl_execute(respx_mock, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "mock-token")

    agg_response_1 = json.dumps({
        "summary": "Initial summary + requirement 1",
        "reply": "Got it. Anything else?"
    })

    respx_mock.post("https://api.openai.com/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": agg_response_1}}]}
    )

    from moa_engine.clients import CCSwitchClient
    client = CCSwitchClient("openai", "https://api.openai.com", "TEST_KEY")

    proposers = [ProposerAgent(client)]
    critic = CriticAgent(client)
    aggregator = AggregatorAgent(client)
    verifier = CommandVerifier("pytest")

    orchestrator = MoAOrchestrator(
        proposers=proposers,
        aggregator=aggregator,
        verifier=verifier,
        output_path="result.py",
        critic=critic,
    )

    inputs = iter(["/execute"])
    def mock_input(prompt):
        return next(inputs)

    with patch("asyncio.to_thread", side_effect=lambda fn, prompt: mock_input(prompt)):

        final_summary = await orchestrator.run_discovery_chat("Initial user idea")
        assert final_summary == "Initial summary + requirement 1"
