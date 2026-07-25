import json
from abc import ABC, abstractmethod
from typing import List, Optional, Union

from moa_engine.clients import LLMClient
from moa_engine.domain import DiscoveryState, Message, Task, Tool


def format_tools_prompt(tools: Optional[List[Tool]]) -> str:
    """Format available tools specifications into a prompt section."""
    if not tools:
        return ""
    tools_desc = []
    for tool in tools:
        schema_json = json.dumps(tool.input_schema, ensure_ascii=False)
        tools_desc.append(
            f"- Инструмент: `{tool.name}`\n"
            f"  Описание: {tool.description}\n"
            f"  JSON-схема параметров: {schema_json}"
        )
    return "\n\n🛠 Доступные инструменты:\n" + "\n".join(tools_desc)


class Agent(ABC):
    """Abstract base class for all Mixture-of-Agents participants."""

    def __init__(
        self,
        client: LLMClient,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
    ):
        self._client = client
        self.system_prompt = system_prompt
        self.tools: List[Tool] = tools or []

    def set_tools(self, tools: List[Tool]) -> None:
        """Set or update available tools for the agent."""
        self.tools = tools

    @abstractmethod
    async def process(self, task: Union[Task, DiscoveryState]) -> str:
        """Process a task or discovery state and generate a response."""
        pass


class ProposerAgent(Agent):
    """Agent responsible for generating initial code solutions and fix proposals."""

    def __init__(
        self,
        client: LLMClient,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
    ):
        super().__init__(client, system_prompt, tools=tools)
        self.temperature = temperature
        if self.system_prompt is None:
            self.system_prompt = (
                "Вы — эксперт-разработчик. Напишите чистый, рабочий Python-код "
                "для решения указанной задачи без дополнительных пояснений."
            )

    async def process(self, task: Union[Task, DiscoveryState]) -> str:
        if isinstance(task, DiscoveryState):
            user_content = f"Текущая выжимка требований:\n{task.current_summary}"
            if task.chat_history:
                history_lines = [
                    f"{m.name or m.role}: {m.content}" for m in task.chat_history
                ]
                user_content += "\n\nТекущий шаг обсуждения:\n" + "\n".join(history_lines)
        else:
            user_content = (
                f"Задача: {task.description}\n\n"
                f"История ошибок предыдущих запусков:\n{task.error_history}"
            )
            if task.synergy_goal:
                user_content += (
                    f"\n\n🎯 ЦЕЛЬ СИНЕРГИЧЕСКОГО МЫШЛЕНИЯ КОМАНДЫ:\n{task.synergy_goal}\n"
                    "Все твои рассуждения и итоговый ответ должны быть подчинены достижению этой цели."
                )

        system_content = (self.system_prompt or "") + format_tools_prompt(self.tools)
        messages = [
            Message(
                role="system",
                content=system_content,
            ),
            Message(
                role="user",
                content=user_content,
            ),
        ]
        return await self._client.generate(messages, temperature=self.temperature)


class CriticAgent(Agent):
    """Agent responsible for reviewing proposals for security, edge cases, and PEP8 compliance."""

    def __init__(
        self,
        client: LLMClient,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
    ):
        super().__init__(client, system_prompt, tools=tools)
        if self.system_prompt is None:
            self.system_prompt = (
                "Вы — старейший ревьюер кода (Critic). Проанализируйте задачу и дайте критические указания по потенциальным багам."
            )

    async def process(self, task: Union[Task, DiscoveryState]) -> str:
        if isinstance(task, DiscoveryState):
            user_content = f"Текущая выжимка требований:\n{task.current_summary}"
            if task.chat_history:
                history_lines = [
                    f"{m.name or m.role}: {m.content}" for m in task.chat_history
                ]
                user_content += "\n\nТекущий шаг обсуждения:\n" + "\n".join(history_lines)
        else:
            user_content = f"Задача: {task.description}\nОшибки: {task.error_history}"
            if task.synergy_goal:
                user_content += (
                    f"\n\n🎯 ЦЕЛЬ СИНЕРГИЧЕСКОГО МЫШЛЕНИЯ КОМАНДЫ:\n{task.synergy_goal}\n"
                    "Все твои рассуждения и итоговый ответ должны быть подчинены достижению этой цели."
                )

        system_content = (self.system_prompt or "") + format_tools_prompt(self.tools)
        messages = [
            Message(
                role="system",
                content=system_content,
            ),
            Message(
                role="user",
                content=user_content,
            ),
        ]
        return await self._client.generate(messages, temperature=0.2)


class AggregatorAgent(Agent):
    """Agent responsible for synthesizing multiple proposals into a single optimal code solution."""

    def __init__(
        self,
        client: LLMClient,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
    ):
        super().__init__(client, system_prompt, tools=tools)
        if self.system_prompt is None:
            self.system_prompt = (
                "Вы — главный архитектор кода (Aggregator). Объедините лучшие идеи "
                "из предложенных вариантов в один безупречный итоговый Python-код."
            )

    async def process_discovery(self, state: DiscoveryState, proposals: List[str], critique: str = "") -> str:
        proposals_formatted = "\n---\n".join(
            [f"Вариант {i+1}:\n{p}" for i, p in enumerate(proposals)]
        )
        critique_section = f"\nЗамечания критика:\n{critique}\n" if critique else ""
        history_section = ""
        if state.chat_history:
            history_lines = [f"{m.name or m.role}: {m.content}" for m in state.chat_history]
            history_section = "Текущий шаг обсуждения:\n" + "\n".join(history_lines) + "\n\n"

        system_prompt = (
            "Вы — Агрегатор в режиме Discovery Chat. Проанализируйте выжимку требований, "
            "историю шага обсуждения, идеи Пропоузеров и замечания Критика.\n"
            "Верните ответ СТРОГО в формате JSON без дополнительного текста вокруг:\n"
            '{"summary": "новая сжатая выжимка всего диалога", "reply": "вопросы или сообщение для пользователя"}'
        )
        system_prompt += format_tools_prompt(self.tools)

        user_content = (
            f"Текущая выжимка требований:\n{state.current_summary}\n\n"
            f"{history_section}"
            f"Предложения от агентов:\n{proposals_formatted}\n"
            f"{critique_section}\n"
            "Верните ответ СТРОГО в формате JSON с ключами summary и reply."
        )

        messages = [
            Message(
                role="system",
                content=system_prompt,
            ),
            Message(
                role="user",
                content=user_content,
            ),
        ]
        return await self._client.generate(messages, temperature=0.2)

    async def process_proposals(self, task: Task, proposals: List[str], critique: str = "") -> str:
        proposals_formatted = "\n---\n".join(
            [f"Вариант {i+1}:\n{p}" for i, p in enumerate(proposals)]
        )
        critique_section = f"\nЗамечания критика:\n{critique}\n" if critique else ""

        system_prompt = self.system_prompt or ""
        system_prompt += format_tools_prompt(self.tools)
        if self.tools:
            system_prompt += (
                "\n\nВы можете запрашивать выполнение инструментов. Если вы хотите использовать инструменты "
                "или вернуть код, верните ответ в формате JSON:\n"
                "{\n"
                '  "code": "итоговый Python-код (или решение)",\n'
                '  "actions": [\n'
                '    {"tool_name": "название_инструмента", "arguments": {"команда": "значение"}}\n'
                '  ]\n'
                "}\n"
                "Если вызовы инструментов не требуются, поле \"actions\" должно быть пустым списком []."
            )

        user_content = (
            f"Задача: {task.description}\n\n"
            f"Предложения от агентов:\n{proposals_formatted}\n"
            f"{critique_section}\n"
            f"История ошибок:\n{task.error_history}\n\n"
        )
        if self.tools:
            user_content += "Верните ответ в формате JSON с ключами 'code' и при необходимости 'actions'."
        else:
            user_content += "Верните ТОЛЬКО итоговый Python-код."

        if task.synergy_goal:
            user_content += (
                f"\n\n🎯 ЦЕЛЬ СИНЕРГИЧЕСКОГО МЫШЛЕНИЯ КОМАНДЫ:\n{task.synergy_goal}\n"
                "Все твои рассуждения и итоговый ответ должны быть подчинены достижению этой цели."
            )

        messages = [
            Message(
                role="system",
                content=system_prompt,
            ),
            Message(
                role="user",
                content=user_content,
            ),
        ]
        return await self._client.generate(messages, temperature=0.2)

    async def process(self, task: Union[Task, DiscoveryState]) -> str:
        if isinstance(task, DiscoveryState):
            user_content = f"Текущая выжимка требований: {task.current_summary}"
        else:
            user_content = f"Выполните задачу: {task.description}"
            if task.synergy_goal:
                user_content += (
                    f"\n\n🎯 ЦЕЛЬ СИНЕРГИЧЕСКОГО МЫШЛЕНИЯ КОМАНДЫ:\n{task.synergy_goal}\n"
                    "Все твои рассуждения и итоговый ответ должны быть подчинены достижению этой цели."
                )

        system_content = (self.system_prompt or "") + format_tools_prompt(self.tools)
        messages = [
            Message(
                role="system",
                content=system_content,
            ),
            Message(
                role="user",
                content=user_content,
            ),
        ]
        return await self._client.generate(messages)


