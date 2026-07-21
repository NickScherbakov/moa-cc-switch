# 🚀 MoA Engine with CC Switch & Deterministic Verification

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Architecture: Clean/OOP](https://img.shields.io/badge/architecture-Clean%2FOOP-green.svg)](#-архитектура)
[![License: MIT](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

Автономный фреймворк оркестрации **Mixture-of-Agents (MoA)**, построенный на принципах чистого ООП и SOLID. Проект объединяет сильные стороны разных моделей LLM (Anthropic Claude, OpenAI GPT, DeepSeek, Ollama) в единый синергический коллектив с автоматической маршрутизацией через **CC Switch** и **доказуемой (детерминированной) верификацией** результатов.

---

## 📐 Диаграмма классов (Class Diagram)

```mermaid
classDiagram
    class Message {
        +str role
        +str content
    }
    class Task {
        +str description
        +str error_history
    }
    class VerificationResult {
        +bool is_success
        +str output_log
    }
    class Artifact {
        +str path
        +str content
        +save() void
    }

    class LLMClient {
        <<abstract>>
        +generate(messages: List~Message~, temperature: float)* str
    }
    class CCSwitchClient {
        +str provider_name
        +str endpoint
        +str api_key
        +generate(messages: List~Message~, temperature: float) str
        -_fallback_via_cli(messages: List~Message~) str
    }
    LLMClient <|.. CCSwitchClient

    class Agent {
        <<abstract>>
        #LLMClient _client
        +process(task: Task)* str
    }
    class ProposerAgent {
        +process(task: Task) str
    }
    class AggregatorAgent {
        +process_proposals(task: Task, proposals: List~str~) str
        +process(task: Task) str
    }
    Agent <|.. ProposerAgent
    Agent <|.. AggregatorAgent
    Agent o-- LLMClient

    class VerifierStrategy {
        <<abstract>>
        +verify(artifact: Artifact)* VerificationResult
    }
    class CommandVerifier {
        -str _command
        -int _timeout
        +verify(artifact: Artifact) VerificationResult
    }
    VerifierStrategy <|.. CommandVerifier

    class MoAOrchestrator {
        -List~ProposerAgent~ _proposers
        -AggregatorAgent _aggregator
        -VerifierStrategy _verifier
        -str _output_path
        -int _max_iterations
        +run_until_proven(task_description: str) bool
    }
    MoAOrchestrator o-- ProposerAgent
    MoAOrchestrator o-- AggregatorAgent
    MoAOrchestrator o-- VerifierStrategy
    MoAOrchestrator ..> Artifact
    MoAOrchestrator ..> Task

🏛 Архитектурные принципы (SOLID)

Single Responsibility (SRP): Клиент отвечает за транспорт, Агент — за промпты и роль, Верификатор — за проверку, Оркестратор — за главный цикл.

Open/Closed (OCP): Добавление новых способов проверки реализуется через наследование от VerifierStrategy.

Liskov Substitution (LSP): Любой класс LLMClient взаимозаменяем.

Interface Segregation (ISP): Узкие сущности Message, Task, Artifact вместо обобщенных dict.

Dependency Inversion (DIP): Оркестратор зависит только от абстракций.

🛠 Установка и запуск
Bash
# 1. Распаковать архив и перейти в папку
unzip moa-cc-switch.zip
cd moa-cc-switch

# 2. Установить в режиме разработки
pip install -e .

# 3. Запустить CLI
moa-run --task "Напиши кастомный LRU-кэш" --verify "pytest tests/test_lru_cache.py" --out "lru_cache.py"


