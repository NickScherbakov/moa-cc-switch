import argparse
import asyncio
import os
import sys
import httpx
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel

from moa_engine.agents import AggregatorAgent, CriticAgent, ProposerAgent
from moa_engine.clients import (
    AnthropicDialect,
    AntigravityCLIClient,
    BaseHTTPClient,
    CCSwitchClient,
    ClaudeCLIClient,
    CodexCLIClient,
    CopilotCLIClient,
    DeepSeekClient,
    GeminiCLIClient,
    KiroCLIClient,
    OllamaClient,
    OpenAIDialect,
    OpenAIClient,
)
from moa_engine.config import config
from moa_engine.engine import MoAOrchestrator
from moa_engine.presets import PresetConfig
from moa_engine.verifiers import CommandVerifier, CompositeVerifier

console = Console()


def build_client_from_config(provider: str, model: str, endpoint: Optional[str] = None, api_key_env: Optional[str] = None):
    provider_lower = provider.lower()
    if provider_lower in ("antigravity-cli", "antigravity", "agy"):
        return AntigravityCLIClient()
    elif provider_lower in ("claude-cli", "claude"):
        return ClaudeCLIClient()
    elif provider_lower in ("copilot-cli", "copilot"):
        return CopilotCLIClient()
    elif provider_lower in ("codex-cli", "codex"):
        return CodexCLIClient()
    elif provider_lower in ("gemini-cli", "gemini"):
        return GeminiCLIClient()
    elif provider_lower in ("kiro-cli", "kiro"):
        return KiroCLIClient()
    elif provider_lower == "openai":
        return OpenAIClient(endpoint=endpoint or "https://api.openai.com/v1", api_key_env=api_key_env or "OPENAI_API_KEY", model_name=model)
    elif provider_lower == "deepseek":
        return DeepSeekClient(endpoint=endpoint or "https://api.deepseek.com/v1", api_key_env=api_key_env or "DEEPSEEK_API_KEY", model_name=model)
    elif provider_lower == "ollama":
        return OllamaClient(endpoint=endpoint or "http://localhost:11434", model_name=model)
    else:
        dialect = AnthropicDialect() if "anthropic" in provider_lower else OpenAIDialect()
        return CCSwitchClient(
            provider_name=provider,
            endpoint=endpoint or "https://api.anthropic.com",
            api_key_env=api_key_env or "ANTHROPIC_API_KEY",
            model_name=model,
            dialect=dialect,
        )


def cli() -> None:
    """CLI entry point for running the MoA Engine with Rich UI & Preset support."""
    parser = argparse.ArgumentParser(description="Autonomous MoA Engine")
    parser.add_argument("--task", help="Описание задачи")
    parser.add_argument("--verify", help="Команда верификации")
    parser.add_argument("--out", default="result.py", help="Файл для сохранения")
    parser.add_argument("--preset", help="Путь к файлу пресета конфигурации (.yaml или .json)")
    parser.add_argument("--context-url", help="URL to fetch and append to the task description")
    args = parser.parse_args()

    task_desc = args.task or "Напиши кастомный LRU-кэш"

    if args.context_url:
        console.print(f"[cyan]🌐 Скачивание контекста с {args.context_url}...[/cyan]")
        try:
            with httpx.Client(follow_redirects=True, timeout=config.timeout_seconds) as client:
                resp = client.get(args.context_url)
                resp.raise_for_status()
                site_content = resp.text[:15000]
                task_desc += f"\n\n--- Website Context ({args.context_url}) ---\n{site_content}"
                console.print(f"[green]✅ Успешно загружен веб-контекст ({len(site_content)} символов)[/green]")
        except Exception as e:
            console.print(f"[bold red]❌ Ошибка при скачивании веб-контекста {args.context_url}: {e}[/bold red]")
            sys.exit(1)

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
                build_client_from_config(p.provider, p.model, p.endpoint, p.api_key_env),
                temperature=p.temperature,
                system_prompt=p.system_prompt,
            )
            for p in preset.proposers
        ]
        critic = (
            CriticAgent(
                build_client_from_config(preset.critic.provider, preset.critic.model, preset.critic.endpoint, preset.critic.api_key_env),
                system_prompt=preset.critic.system_prompt,
            )
            if preset.critic
            else None
        )
        aggregator = (
            AggregatorAgent(
                build_client_from_config(preset.aggregator.provider, preset.aggregator.model, preset.aggregator.endpoint, preset.aggregator.api_key_env),
                system_prompt=preset.aggregator.system_prompt,
            )
            if preset.aggregator
            else AggregatorAgent(CCSwitchClient("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY"))
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

        claude_client = CCSwitchClient("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY")
        gpt_client = CCSwitchClient("openai", "https://api.openai.com/v1", "OPENAI_API_KEY")

        proposers = [
            ProposerAgent(gpt_client, temperature=0.8),
            ProposerAgent(claude_client, temperature=0.3),
        ]
        critic = CriticAgent(claude_client)
        aggregator = AggregatorAgent(claude_client)

    if args.verify:
        verify_cmd = args.verify
    elif preset and preset.verify_cmd:
        verify_cmd = preset.verify_cmd
    else:
        verify_cmd = "pytest tests/test_lru_cache.py"

    verifier = CommandVerifier(verify_cmd)
    max_iterations = preset.max_iterations if preset else 50

    orchestrator = MoAOrchestrator(
        proposers=proposers,
        aggregator=aggregator,
        verifier=verifier,
        output_path=output_path,
        critic=critic,
        max_iterations=max_iterations,
    )

    success = asyncio.run(orchestrator.run_until_proven(task_desc))
    if success:
        console.print("[bold green]✨ Orchestration completed successfully![/bold green]")
        console.print("[cyan]Generated reports: moa_report.html, moa_report.md, moa_trace.json[/cyan]")
    else:
        console.print("[bold red]❌ Orchestration stopped: max iterations reached.[/bold red]")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    cli()
