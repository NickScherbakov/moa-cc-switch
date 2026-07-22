"""
Audit runner for infolimp.ru — overrides agent prompts for analytical tasks.
Uses all 6 CLI agents: claude, agy, codex, gemini (proposers), copilot (critic), kiro (aggregator).
"""
import asyncio
import sys
from moa_engine.clients import (
    ClaudeCLIClient,
    AntigravityCLIClient,
    CodexCLIClient,
    GeminiCLIClient,
    CopilotCLIClient,
    KiroCLIClient,
)
from moa_engine.domain import Message, Task, Artifact, VerificationResult
from moa_engine.reporter import ExecutionReporter
from rich.console import Console
from rich.panel import Panel

console = Console()

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


async def get_proposal(client, role_name: str, task_text: str, error_history: str = "") -> str:
    """Get analytical proposal from a proposer agent."""
    console.print(f"  → [{role_name}] generating proposal...")
    messages = [
        Message(
            role="system",
            content=(
                "Ты — эксперт-аналитик веб-сайтов. Твоя задача — провести исследование "
                "указанного сайта и написать структурированный аналитический отчёт на русском языке. "
                "Используй все доступные тебе инструменты для загрузки и анализа страниц сайта."
            ),
        ),
        Message(
            role="user",
            content=(
                f"{task_text}"
                + (f"\n\nИстория ошибок предыдущих итераций:\n{error_history}" if error_history else "")
            ),
        ),
    ]
    return await client.generate(messages, temperature=0.5)


async def get_critique(client, task_text: str, proposals: list[str]) -> str:
    """Get critique from the critic agent."""
    console.print("  → [copilot/critic] reviewing proposals...")
    proposals_text = "\n\n---\n\n".join(
        [f"Вариант {i+1}:\n{p}" for i, p in enumerate(proposals)]
    )
    messages = [
        Message(
            role="system",
            content=(
                "Ты — строгий редактор и фактчекер. Проанализируй предложенные варианты аналитического отчёта. "
                "Укажи: какие факты требуют проверки, где есть противоречия, что пропущено, "
                "что является домыслом без источника. Будь конкретен и критичен."
            ),
        ),
        Message(
            role="user",
            content=(
                f"Задача: {task_text}\n\n"
                f"Варианты отчётов от агентов:\n\n{proposals_text}\n\n"
                "Дай развёрнутую критику каждого варианта."
            ),
        ),
    ]
    return await client.generate(messages, temperature=0.2)


async def get_aggregation(client, task_text: str, proposals: list[str], critique: str) -> str:
    """Aggregate proposals into final report."""
    console.print("  → [kiro/aggregator] synthesizing final report...")
    proposals_text = "\n\n---\n\n".join(
        [f"Вариант {i+1}:\n{p}" for i, p in enumerate(proposals)]
    )
    messages = [
        Message(
            role="system",
            content=(
                "Ты — главный аналитик и редактор. Твоя задача — объединить лучшее из "
                "предложенных вариантов отчётов в один исчерпывающий, точный и хорошо структурированный "
                "аналитический отчёт на русском языке в формате Markdown. "
                "Учти все замечания критика. Не выдумывай факты — основывайся только на том, "
                "что реально содержится в вариантах. Если агенты не смогли загрузить сайт — честно об этом напиши."
            ),
        ),
        Message(
            role="user",
            content=(
                f"Задача:\n{task_text}\n\n"
                f"Варианты от агентов:\n\n{proposals_text}\n\n"
                f"Замечания критика:\n{critique}\n\n"
                "Верни ТОЛЬКО итоговый отчёт в формате Markdown."
            ),
        ),
    ]
    return await client.generate(messages, temperature=0.3)


def verify(content: str) -> bool:
    return len(content) > 500 and "infolimp" in content.lower()


async def main():
    console.print(Panel.fit(
        "[bold cyan]🚀 MoA Audit Engine[/bold cyan]\n"
        "[yellow]Task:[/yellow] Аудит сайта infolimp.ru\n"
        "[yellow]Agents:[/yellow] claude · agy · codex · gemini → copilot (critic) → kiro (aggregator)",
        title="MoA Engine — Website Audit"
    ))

    # Initialize clients
    proposer_clients = [
        ("claude",  ClaudeCLIClient()),
        ("agy",     AntigravityCLIClient()),
        ("codex",   CodexCLIClient()),
        ("gemini",  GeminiCLIClient()),
    ]
    critic_client    = CopilotCLIClient()
    aggregator_client = KiroCLIClient()

    reporter = ExecutionReporter()
    error_history = ""

    for iteration in range(1, 4):
        console.print(f"\n[bold]--- Итерация {iteration}/3 ---[/bold]")

        # 1. Run all proposers concurrently
        console.print("[cyan]Phase 1: Proposers (parallel)[/cyan]")
        proposal_tasks = [
            get_proposal(client, name, TASK_TEXT, error_history)
            for name, client in proposer_clients
        ]
        proposals_raw = await asyncio.gather(*proposal_tasks, return_exceptions=True)

        proposals = []
        for (name, _), result in zip(proposer_clients, proposals_raw):
            if isinstance(result, Exception):
                console.print(f"  ⚠️  [{name}] error: {result}", style="yellow")
            elif result and result.strip():
                proposals.append(result)
                console.print(f"  ✅ [{name}] proposal received ({len(result)} chars)")
            else:
                console.print(f"  ⚠️  [{name}] empty response", style="yellow")

        if not proposals:
            console.print("❌ No proposals received. Stopping.", style="red")
            break

        # 2. Critic reviews
        console.print("[cyan]Phase 2: Critic[/cyan]")
        critique = ""
        try:
            critique = await get_critique(critic_client, TASK_TEXT, proposals)
            console.print(f"  ✅ Critique received ({len(critique)} chars)")
        except Exception as e:
            console.print(f"  ⚠️  Critic error: {e}", style="yellow")

        # 3. Aggregator synthesizes
        console.print("[cyan]Phase 3: Aggregator[/cyan]")
        final_report = ""
        try:
            final_report = await get_aggregation(aggregator_client, TASK_TEXT, proposals, critique)
            console.print(f"  ✅ Final report received ({len(final_report)} chars)")
        except Exception as e:
            console.print(f"  ⚠️  Aggregator error: {e}", style="yellow")
            # Fallback: use best proposal directly
            final_report = max(proposals, key=len)
            console.print("  ℹ️  Using longest proposal as fallback")

        # 4. Save and verify
        artifact = Artifact(path="result.md", content=final_report)
        artifact.save()

        reporter.log_iteration(
            iteration=iteration,
            proposals_count=len(proposals),
            proposals_snippets=[p[:100] for p in proposals],
            critique_snippet=critique[:200] if critique else "",
            aggregated_code=final_report,
            is_success=verify(final_report),
            verification_log="",
        )

        if verify(final_report):
            console.print("\n[bold green]✨ Audit completed successfully! Report saved to result.md[/bold green]")
            reporter.generate_html_report()
            reporter.generate_markdown_report()
            reporter.generate_json_trace()
            return

        console.print("❌ Verification failed — report incomplete. Retrying...", style="red")
        error_history = f"Iteration {iteration}: report was incomplete or missing 'infolimp' reference."

    console.print("[bold red]❌ Max iterations reached. Partial result saved to result.md[/bold red]")
    reporter.generate_html_report()
    reporter.generate_markdown_report()
    reporter.generate_json_trace()


if __name__ == "__main__":
    asyncio.run(main())
