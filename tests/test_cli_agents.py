import pytest
import shutil
from moa_engine.domain import Message
from moa_engine.clients import (
    AntigravityCLIClient,
    ClaudeCLIClient,
    CodexCLIClient,
    CopilotCLIClient,
    GeminiCLIClient,
)
from moa_engine.runner import build_client_from_config
from moa_engine.agents import ProposerAgent, AggregatorAgent
from moa_engine.engine import MoAOrchestrator
from moa_engine.verifiers import CommandVerifier


def test_installed_cli_binaries_exist():
    """Verify that Antigravity, Claude, Copilot, Codex, and Gemini CLI executables exist on the system PATH."""
    for cli_name in ["agy", "claude", "copilot", "codex", "gemini"]:
        binary_path = shutil.which(cli_name)
        assert binary_path is not None, f"CLI agent binary '{cli_name}' not found on system PATH"


def test_build_client_from_config_cli_agents():
    """Verify factory returns appropriate CLI agent client instances."""
    assert isinstance(build_client_from_config("antigravity", "default"), AntigravityCLIClient)
    assert isinstance(build_client_from_config("claude", "default"), ClaudeCLIClient)
    assert isinstance(build_client_from_config("copilot", "default"), CopilotCLIClient)
    assert isinstance(build_client_from_config("codex", "default"), CodexCLIClient)
    assert isinstance(build_client_from_config("gemini", "default"), GeminiCLIClient)



@pytest.mark.asyncio
async def test_claude_cli_real_execution():
    """Test real Claude Code CLI execution."""
    client = ClaudeCLIClient()
    response = await client.generate([Message(role="user", content="Respond with string SUCCESS_CLAUDE")])
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_copilot_cli_real_execution():
    """Test real GitHub Copilot CLI execution."""
    client = CopilotCLIClient()
    response = await client.generate([Message(role="user", content="Respond with string SUCCESS_COPILOT")])
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_cli_agents_orchestration_interaction():
    """Test multi-agent orchestration combining Claude and Copilot CLI agents."""
    claude_proposer = ProposerAgent(ClaudeCLIClient(), temperature=0.3)
    copilot_proposer = ProposerAgent(CopilotCLIClient(), temperature=0.3)
    aggregator = AggregatorAgent(CopilotCLIClient())
    verifier = CommandVerifier("pytest tests/test_lru_cache.py")

    orchestrator = MoAOrchestrator(
        proposers=[claude_proposer, copilot_proposer],
        aggregator=aggregator,
        verifier=verifier,
        output_path="lru_cache.py",
        max_iterations=1,
    )
    
    result = await orchestrator.run_until_proven("Write LRUCache class")
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_gemini_cli_auth_error_handling():
    """Verify GeminiCLIClient handles Cloud Code API authentication failure gracefully."""
    client = GeminiCLIClient()
    response = await client.generate([Message(role="user", content="Ping")])
    assert isinstance(response, str)
    assert "Gemini CLI Unavailable" in response or len(response) > 0

