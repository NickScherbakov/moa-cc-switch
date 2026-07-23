"""
Audit runner for infolimp.ru — overrides agent prompts for analytical tasks.
Uses all 6 CLI agents: claude, agy, codex, gemini (proposers), copilot (critic), kiro (aggregator).
"""
import asyncio
from moa_engine.agents import AggregatorAgent, CriticAgent, ProposerAgent
from moa_engine.clients import (
    AntigravityCLIClient,
    ClaudeCLIClient,
    CodexCLIClient,
    CopilotCLIClient,
    GeminiCLIClient,
    KiroCLIClient,
)
from moa_engine.engine import MoAOrchestrator
from moa_engine.verifiers import CommandVerifier

TASK_TEXT = """Исследуй сайт infolimp.ru и напиши подробный аналитический отчёт на русском языке.

Для исследования загрузи главную страницу сайта и несколько внутренних страниц через HTTP-запрос (используй curl, python requests, или любой доступный инструмент). Изучи содержимое, мета-данные, структуру страниц, ссылки, заголовки.

Отчёт должен содержать следующие разделы:

1. **Назначение сайта** — что это за ресурс, его тематика, целевая аудитория
2. **Техническое состояние** — доступность по HTTPS, структура URL, признаки современного стека
3. **Содержание** — актуальность материалов, качество и полнота контента, навигация
4. **UX/UI и дизайн** — соответствие стандартам июля 2026 года: адаптивность, визуальный стиль, удобство интерфейса
5. **SEO** — мета-теги, заголовки, описания страниц
6. **Фактчекинг статей** — если на сайте есть статьи или публикации, проверь фактическую точность утверждений. Фейки, непроверенные факты и "жареные факты" должны быть явно отмечены. Каждое сомнительное утверждение сопровождается объяснением.
7. **Адекватность** — соответствие содержания заявленной цели, достоверность информации, доверие к ресурсу
8. **Итоговая оценка** — вердикт по каждому пункту, конкретные рекомендации по улучшению

Результат — подробный отчёт в формате Markdown."""

VERIFY_CMD = "python -c \"content=open('result.md', encoding='utf-8').read(); assert len(content)>500 and 'infolimp' in content.lower(), 'Report incomplete'; print('OK')\""

PROPOSER_SYSTEM_PROMPT = (
    "Ты — эксперт-аналитик веб-сайтов. Твоя задача — провести исследование "
    "указанного сайта и написать структурированный аналитический отчёт на русском языке. "
    "Используй все доступные тебе инструменты для загрузки и анализа страниц сайта."
)

CRITIC_SYSTEM_PROMPT = (
    "Ты — строгий редактор и фактчекер. Проанализируй предложенные варианты аналитического отчёта. "
    "Укажи: какие факты требуют проверки, где есть противоречия, что пропущено, "
    "что является домыслом без источника. Будь конкретен и критичен."
)

AGGREGATOR_SYSTEM_PROMPT = (
    "Ты — главный аналитик и редактор. Твоя задача — объединить лучшее из "
    "предложенных вариантов отчётов в один исчерпывающий, точный и хорошо структурированный "
    "аналитический отчёт на русском языке в формате Markdown. "
    "Учти все замечания критика. Не выдумывай факты — основывайся только на том, "
    "что реально содержится в вариантах. Если агенты не смогли загрузить сайт — честно об этом напиши."
)


async def main():
    proposers = [
        ProposerAgent(ClaudeCLIClient(), temperature=0.5, system_prompt=PROPOSER_SYSTEM_PROMPT),
        ProposerAgent(AntigravityCLIClient(), temperature=0.5, system_prompt=PROPOSER_SYSTEM_PROMPT),
        ProposerAgent(CodexCLIClient(), temperature=0.5, system_prompt=PROPOSER_SYSTEM_PROMPT),
        ProposerAgent(GeminiCLIClient(), temperature=0.5, system_prompt=PROPOSER_SYSTEM_PROMPT),
    ]

    critic = CriticAgent(CopilotCLIClient(), system_prompt=CRITIC_SYSTEM_PROMPT)
    aggregator = AggregatorAgent(KiroCLIClient(), system_prompt=AGGREGATOR_SYSTEM_PROMPT)

    verifier = CommandVerifier(VERIFY_CMD)

    orchestrator = MoAOrchestrator(
        proposers=proposers,
        aggregator=aggregator,
        verifier=verifier,
        output_path="result.md",
        critic=critic,
        max_iterations=3,
    )

    await orchestrator.run_until_proven(TASK_TEXT)


if __name__ == "__main__":
    asyncio.run(main())
