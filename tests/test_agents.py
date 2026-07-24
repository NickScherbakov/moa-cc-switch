import pytest
from moa_engine.domain import Task, Message
from moa_engine.clients import CCSwitchClient
from moa_engine.agents import ProposerAgent, CriticAgent, AggregatorAgent


@pytest.mark.asyncio
async def test_critic_and_aggregator_flow(respx_mock, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "mock-token")
    respx_mock.post("https://api.openai.com/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "class LRUCache:\n    pass"}}]}
    )
    client = CCSwitchClient("openai", "https://api.openai.com", "TEST_KEY")

    critic = CriticAgent(client)
    aggregator = AggregatorAgent(client)

    task = Task(description="Implement LRU Cache")
    critique = await critic.process(task)
    assert len(critique) > 0

    code = await aggregator.process_proposals(task, ["class LRUCache: pass"], critique=critique)
    assert "class LRUCache" in code

