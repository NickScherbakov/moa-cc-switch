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


@pytest.mark.asyncio
async def test_synergy_goal_prompt_injection(respx_mock, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "mock-token")
    
    captured_messages = []
    def capture_handler(request):
        import json
        body = json.loads(request.content)
        captured_messages.append(body["messages"])
        return respx_mock.post("https://api.openai.com/v1/chat/completions").return_value

    respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=capture_handler,
        return_value=httpx_response_mock() if False else None
    )
    respx_mock.post("https://api.openai.com/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "response"}}]}
    )

    client = CCSwitchClient("openai", "https://api.openai.com", "TEST_KEY")
    proposer = ProposerAgent(client)
    critic = CriticAgent(client)
    aggregator = AggregatorAgent(client)

    synergy_text = "Максимальная скорость и чистая архитектура"
    task = Task(description="Optimization task", synergy_goal=synergy_text)

    await proposer.process(task)
    await critic.process(task)
    await aggregator.process_proposals(task, ["proposal 1"])
    await aggregator.process(task)

    goal_marker = "🎯 ЦЕЛЬ СИНЕРГИЧЕСКОГО МЫШЛЕНИЯ КОМАНДЫ:"

    for msgs in captured_messages:
        user_msg = next(m for m in msgs if m["role"] == "user")
        assert goal_marker in user_msg["content"]
        assert synergy_text in user_msg["content"]

