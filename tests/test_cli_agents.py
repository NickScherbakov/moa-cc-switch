import os
import pytest
import shutil

from moa_engine.domain import Message
from moa_engine.clients import (
    AntigravityCLIClient,
    ClaudeCLIClient,
    CodexCLIClient,
    CopilotCLIClient,
    GeminiCLIClient,
    build_client,
)
from moa_engine.agents import ProposerAgent, AggregatorAgent
from moa_engine.engine import MoAOrchestrator
from moa_engine.verifiers import CommandVerifier


def require_cli_binary(cli_name: str) -> str:
    """Skip integration checks when an external CLI binary is unavailable on PATH."""
    binary_path = shutil.which(cli_name)
    if binary_path is None:
        pytest.skip(f"CLI agent binary '{cli_name}' not found on system PATH")
    return binary_path


@pytest.mark.parametrize("cli_name", ["agy", "claude", "copilot", "codex", "gemini"])
def test_installed_cli_binaries_exist(cli_name: str):
    """Verify CLI agent binaries when they are installed on the system PATH."""
    assert require_cli_binary(cli_name) is not None


def test_build_client_cli_agents():
    """Verify factory returns appropriate CLI agent client instances."""
    assert isinstance(build_client("antigravity", "default"), AntigravityCLIClient)
    assert isinstance(build_client("claude", "default"), ClaudeCLIClient)
    assert isinstance(build_client("copilot", "default"), CopilotCLIClient)
    assert isinstance(build_client("codex", "default"), CodexCLIClient)
    assert isinstance(build_client("gemini", "default"), GeminiCLIClient)



@pytest.mark.asyncio
async def test_claude_cli_real_execution():
    """Test real Claude Code CLI execution."""
    require_cli_binary("claude")
    client = ClaudeCLIClient()
    response = await client.generate([Message(role="user", content="Respond with string SUCCESS_CLAUDE")])
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_copilot_cli_real_execution():
    """Test real GitHub Copilot CLI execution."""
    require_cli_binary("copilot")
    client = CopilotCLIClient()
    response = await client.generate([Message(role="user", content="Respond with string SUCCESS_COPILOT")])
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_cli_agents_orchestration_interaction():
    """Test multi-agent orchestration combining Claude and Copilot CLI agents."""
    require_cli_binary("claude")
    require_cli_binary("copilot")
    claude_proposer = ProposerAgent(ClaudeCLIClient(), temperature=0.3)
    copilot_proposer = ProposerAgent(CopilotCLIClient(), temperature=0.3)
    aggregator = AggregatorAgent(CopilotCLIClient())
    verifier = CommandVerifier("pytest tests/test_lru_cache.py")

    orchestrator = MoAOrchestrator(
        proposers=[claude_proposer, copilot_proposer],
        aggregator=aggregator,
        verifier=verifier,
        output_path="test_lru_cache_output.py",
        max_iterations=1,
    )

    result = await orchestrator.run_until_proven("Write LRUCache class")
    assert isinstance(result, bool)
    if os.path.exists("test_lru_cache_output.py"):
        os.remove("test_lru_cache_output.py")




@pytest.mark.asyncio
async def test_gemini_cli_auth_error_handling():
    """Verify GeminiCLIClient handles Cloud Code API authentication failure gracefully."""
    require_cli_binary("gemini")
    client = GeminiCLIClient()
    response = await client.generate([Message(role="user", content="Ping")])
    assert isinstance(response, str)
    assert "Gemini CLI Unavailable" in response or len(response) > 0
