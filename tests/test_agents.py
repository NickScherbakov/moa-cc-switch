import pytest
from moa_engine.domain import Task, Message
from moa_engine.clients import CCSwitchClient
from moa_engine.agents import ProposerAgent, CriticAgent, AggregatorAgent


@pytest.mark.asyncio
async def test_critic_and_aggregator_flow():
    client = CCSwitchClient("openai", "https://api.openai.com", "TEST_KEY")
    critic = CriticAgent(client)
    aggregator = AggregatorAgent(client)

    task = Task(description="Implement LRU Cache")
    critique = await critic.process(task)
    assert len(critique) > 0

    code = await aggregator.process_proposals(task, ["class LRUCache: pass"], critique=critique)
    assert "class LRUCache" in code
