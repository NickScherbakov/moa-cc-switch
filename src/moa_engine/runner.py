import argparse
import asyncio
import os
import sys
import httpx
from bs4 import BeautifulSoup
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel

from moa_engine.agents import AggregatorAgent, CriticAgent, ProposerAgent
from moa_engine.clients import build_client
from moa_engine.config import config
from moa_engine.engine import MoAOrchestrator
from moa_engine.presets import PresetConfig
from moa_engine.verifiers import CommandVerifier, CompositeVerifier, LLMVerifier

console = Console()


def parse_html_to_text(html: str) -> str:
    """Parse raw HTML, strip invisible tags, and return clean plain text (sync, safe for threading)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "meta", "head"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)[:15000]


async def _fetch_single_url(client: httpx.AsyncClient, url: str) -> str:
    console.print(f"[cyan]🌐 Скачивание контекста с {url}...[/cyan]")
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        clean_text = await asyncio.to_thread(parse_html_to_text, resp.text)
        console.print(f"[green]✅ Успешно загружен очищенный контекст {url} ({len(clean_text)} символов)[/green]")
        return f"\n\n--- Website Context ({url}) ---\n{clean_text}"
    except Exception as e:
        console.print(f"[bold red]❌ Ошибка при скачивании веб-контекста {url}: {e}[/bold red]")
        sys.exit(1)


async def fetch_urls_context(urls: List[str]) -> str:
    """Fetch HTML from multiple URLs asynchronously using asyncio.gather, clean invisible elements, extract text, and return concatenated context."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=config.timeout_seconds) as client:
        tasks = [_fetch_single_url(client, url) for url in urls]
        results = await asyncio.gather(*tasks)
    return "".join(results)


async def main(args: argparse.Namespace) -> None:
    """Async main function for MoA Engine execution."""
    task_desc = args.task or "Напиши кастомный LRU-кэш"

    if args.context_url:
        task_desc += await fetch_urls_context(args.context_url)

    output_path = args.out
    preset = None

    if args.preset and os.path.exists(args.preset):
        if args.preset.endswith(".yaml") or args.preset.endswith(".yml"):
            preset = PresetConfig.from_yaml(args.preset)
        else:
            preset = PresetConfig.from_json(args.preset)

        console.print(
            Panel.fit(
                f"[bold cyan]🚀 Loaded Preset: {preset.preset_name}[/bold cyan]\n"
                f"[yellow]Task:[/yellow] {task_desc}\n"
                f"[yellow]Output File:[/yellow] {preset.output_path}",
                title="MoA Engine Config Preset",
            )
        )
        output_path = preset.output_path
        
        proposers = [
            ProposerAgent(
                build_client(p.provider, p.model, p.endpoint, p.api_key_env),
                temperature=p.temperature,
                system_prompt=p.system_prompt,
            )
            for p in preset.proposers
        ]
        critic = (
            CriticAgent(
                build_client(preset.critic.provider, preset.critic.model, preset.critic.endpoint, preset.critic.api_key_env),
                system_prompt=preset.critic.system_prompt,
            )
            if preset.critic
            else None
        )
        aggregator = (
            AggregatorAgent(
                build_client(preset.aggregator.provider, preset.aggregator.model, preset.aggregator.endpoint, preset.aggregator.api_key_env),
                system_prompt=preset.aggregator.system_prompt,
            )
            if preset.aggregator
            else AggregatorAgent(build_client("anthropic", "default"))
        )
    else:
        console.print(
            Panel.fit(
                "[bold cyan]🚀 Mixture-of-Agents Autonomous Engine[/bold cyan]\n"
                f"[yellow]Task:[/yellow] {task_desc}\n"
                f"[yellow]Target File:[/yellow] {output_path}",
                title="MoA Engine v0.3.0",
            )
        )

        claude_client = build_client("anthropic", "claude-3-5-haiku-20241022")
        gpt_client = build_client("openai", "gpt-4o-mini")

        proposers = [
            ProposerAgent(gpt_client, temperature=0.8),
            ProposerAgent(claude_client, temperature=0.3),
        ]
        critic = CriticAgent(claude_client)
        aggregator = AggregatorAgent(claude_client)

    if args.verify:
        verifier = CommandVerifier(args.verify)
    elif preset and preset.verifier_config:
        vc = preset.verifier_config
        if isinstance(vc, dict) and vc.get("type") == "llm":
            if "provider" in vc:
                verifier_client = build_client(
                    provider=vc["provider"],
                    model=vc.get("model", "gpt-4o-mini"),
                    endpoint=vc.get("endpoint"),
                    api_key_env=vc.get("api_key_env"),
                )
            else:
                verifier_client = build_client("openai", vc.get("model", "gpt-4o-mini"))
            eval_prompt = vc.get("evaluation_prompt", "")
            verifier = LLMVerifier(client=verifier_client, evaluation_prompt=eval_prompt)
        elif isinstance(vc, dict) and vc.get("type") == "command":
            cmd = vc.get("command") or vc.get("verify_cmd") or "pytest tests/test_lru_cache.py"
            verifier = CommandVerifier(cmd)
        elif isinstance(vc, str):
            verifier = CommandVerifier(vc)
        else:
            verifier = CommandVerifier("pytest tests/test_lru_cache.py")
    else:
        verifier = CommandVerifier("pytest tests/test_lru_cache.py")

    max_iterations = preset.max_iterations if preset else 50
    synergy_goal = args.goal or (preset.synergy_goal if preset else "")

    orchestrator = MoAOrchestrator(
        proposers=proposers,
        aggregator=aggregator,
        verifier=verifier,
        output_path=output_path,
        critic=critic,
        max_iterations=max_iterations,
    )

    success = await orchestrator.run_until_proven(task_desc, synergy_goal=synergy_goal)
    if success:
        console.print("[bold green]✨ Orchestration completed successfully![/bold green]")
        console.print("[cyan]Generated reports: moa_report.html, moa_report.md, moa_trace.json[/cyan]")
    else:
        console.print("[bold red]❌ Orchestration stopped: max iterations reached.[/bold red]")

    sys.exit(0 if success else 1)


def cli() -> None:
    """CLI entry point for running the MoA Engine with Rich UI & Preset support."""
    parser = argparse.ArgumentParser(description="Autonomous MoA Engine")
    parser.add_argument("--task", help="Описание задачи")
    parser.add_argument("--goal", help="Цель синергического мышления команды")
    parser.add_argument("--verify", help="Команда верификации")
    parser.add_argument("--out", default="result.py", help="Файл для сохранения")
    parser.add_argument("--preset", help="Путь к файлу пресета конфигурации (.yaml или .json)")
    parser.add_argument("--context-url", nargs="+", help="URL(s) to fetch and append to the task description")
    args = parser.parse_args()

    asyncio.run(main(args))



if __name__ == "__main__":
    cli()
