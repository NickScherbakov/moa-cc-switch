import os
import pytest
from moa_engine.presets import PresetConfig, AgentConfig


def test_preset_config_json_roundtrip(tmp_path):
    preset = PresetConfig(
        preset_name="test_preset",
        description="Test Preset Description",
        max_iterations=10,
        output_path="out.py",
        verify_cmd="python test.py",
        proposers=[
            AgentConfig(name="prop1", role="proposer", provider="openai", model="gpt-4o", system_prompt="Prompt 1"),
            AgentConfig(name="prop2", role="proposer", provider="anthropic", model="claude-3-5-sonnet"),
        ],
        critic=AgentConfig(name="critic", role="critic", provider="anthropic", model="claude-3-5-sonnet", system_prompt="Critic Prompt"),
        aggregator=AgentConfig(name="agg", role="aggregator", provider="openai", model="gpt-4o"),
    )

    json_file = tmp_path / "preset.json"
    preset.to_json(str(json_file))

    loaded = PresetConfig.from_json(str(json_file))
    assert loaded.preset_name == "test_preset"
    assert loaded.verify_cmd == "python test.py"
    assert len(loaded.proposers) == 2
    assert loaded.proposers[0].provider == "openai"
    assert loaded.proposers[0].system_prompt == "Prompt 1"
    assert loaded.critic.model == "claude-3-5-sonnet"
    assert loaded.critic.system_prompt == "Critic Prompt"


def test_preset_config_yaml_roundtrip(tmp_path):
    preset = PresetConfig(
        preset_name="yaml_preset",
        description="YAML Preset",
        proposers=[AgentConfig(name="p1", role="proposer", provider="ollama", model="llama3")],
    )

    yaml_file = tmp_path / "preset.yaml"
    preset.to_yaml(str(yaml_file))

    loaded = PresetConfig.from_yaml(str(yaml_file))
    assert loaded.preset_name == "yaml_preset"
    assert loaded.proposers[0].model == "llama3"


def test_infolimp_audit_preset_loading():
    preset = PresetConfig.from_json("presets/infolimp-audit.json")
    assert preset.preset_name == "infolimp-audit"
    assert preset.verify_cmd is not None
    assert "result.md" in preset.verify_cmd
    assert len(preset.proposers) == 4
    for p in preset.proposers:
        assert p.system_prompt is not None
    assert preset.critic.system_prompt is not None
    assert preset.aggregator.system_prompt is not None

