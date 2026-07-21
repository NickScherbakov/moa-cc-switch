from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class Task:
    description: str
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
