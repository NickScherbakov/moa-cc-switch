from abc import ABC, abstractmethod
from typing import List

from moa_engine.clients import LLMClient
from moa_engine.domain import Message, Task


class Agent(ABC):
    """Abstract base class for all Mixture-of-Agents participants."""

    def __init__(self, client: LLMClient):
        self._client = client

    @abstractmethod
    async def process(self, task: Task) -> str:
        """Process a task and generate a code output or proposal."""
        pass


class ProposerAgent(Agent):
    """Agent responsible for generating initial code solutions and fix proposals."""

    async def process(self, task: Task) -> str:
        messages = [
            Message(
                role="system",
                content=(
                    "Вы — эксперт-разработчик. Напишите чистый, рабочий Python-код "
                    "для решения указанной задачи без дополнительных пояснений."
                ),
            ),
            Message(
                role="user",
                content=(
                    f"Задача: {task.description}\n\n"
                    f"История ошибок предыдущих запусков:\n{task.error_history}"
                ),
            ),
        ]
        return await self._client.generate(messages, temperature=0.7)


class AggregatorAgent(Agent):
    """Agent responsible for synthesizing multiple proposals into a single optimal code solution."""

    async def process_proposals(self, task: Task, proposals: List[str]) -> str:
        proposals_formatted = "\n---\n".join(
            [f"Вариант {i+1}:\n{p}" for i, p in enumerate(proposals)]
        )
        messages = [
            Message(
                role="system",
                content=(
                    "Вы — главный архитектор кода (Aggregator). Объедините лучшие идеи "
                    "из предложенных вариантов в один безупречный итоговый Python-код."
                ),
            ),
            Message(
                role="user",
                content=(
                    f"Задача: {task.description}\n\n"
                    f"Предложения от агентов:\n{proposals_formatted}\n\n"
                    f"История ошибок:\n{task.error_history}\n\n"
                    "Верните ТОЛЬКО итоговый Python-код."
                ),
            ),
        ]
        return await self._client.generate(messages, temperature=0.2)

    async def process(self, task: Task) -> str:
        messages = [
            Message(
                role="user",
                content=f"Выполните задачу: {task.description}",
            )
        ]
        return await self._client.generate(messages)
