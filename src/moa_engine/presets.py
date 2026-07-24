import json
import yaml
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class AgentConfig:
    name: str
    role: str  # "proposer", "critic", "aggregator"
    provider: str  # "anthropic", "openai", "deepseek", "ollama", "cc-switch"
    model: str
    temperature: float = 0.7
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None
    system_prompt: Optional[str] = None


@dataclass
class PresetConfig:
    preset_name: str
    description: str
    max_iterations: int = 50
    output_path: str = "result.py"
    verify_cmd: Optional[str] = None
    proposers: List[AgentConfig] = field(default_factory=list)
    critic: Optional[AgentConfig] = None
    aggregator: Optional[AgentConfig] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, filepath: str) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def to_yaml(self, filepath: str) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True, sort_keys=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresetConfig":
        proposers = [AgentConfig(**p) for p in data.get("proposers", [])]
        critic = AgentConfig(**data["critic"]) if data.get("critic") else None
        aggregator = AgentConfig(**data["aggregator"]) if data.get("aggregator") else None
        
        return cls(
            preset_name=data.get("preset_name", "default"),
            description=data.get("description", ""),
            max_iterations=data.get("max_iterations", 50),
            output_path=data.get("output_path", "result.py"),
            verify_cmd=data.get("verify_cmd"),
            proposers=proposers,
            critic=critic,
            aggregator=aggregator,
        )

    @classmethod
    def from_json(cls, filepath: str) -> "PresetConfig":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_yaml(cls, filepath: str) -> "PresetConfig":
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)
