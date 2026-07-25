from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    name: Optional[str] = None


@dataclass
class DiscoveryState:
    current_summary: str = ""
    chat_history: List[Message] = field(default_factory=list)



@dataclass(frozen=True)
class Task:
    description: str
    synergy_goal: str = ""
    error_history: str = "Ошибок нет. Первая итерация."


@dataclass(frozen=True)
class VerificationResult:
    is_success: bool
    output_log: str


@dataclass
class Artifact:
    path: str
    content: str

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(self.content)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict


@dataclass(frozen=True)
class Action:
    tool_name: str
    arguments: dict

