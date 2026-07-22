# 🚀 MoA Engine with CC Switch & Deterministic Verification

[![CI/CD Pipeline](https://github.com/NickScherbakov/moa-cc-switch/actions/workflows/ci.yml/badge.svg)](https://github.com/NickScherbakov/moa-cc-switch/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Architecture: Clean/OOP](https://img.shields.io/badge/architecture-Clean%2FOOP-green.svg)](#-архитектурные-принципы-solid)
[![License: MIT](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

Автономный фреймворк оркестрации **Mixture-of-Agents (MoA)**, построенный на принципах чистого ООП и SOLID. Проект объединяет сильные стороны разных моделей LLM (Anthropic Claude, OpenAI GPT, DeepSeek, Ollama) в единый синергический коллектив с автоматической маршрутизацией через **CC Switch** и **доказуемой (детерминированной) верификацией** результатов.

---

## 🤖 Поддерживаемые провайдеры

| Ключ провайдера | Клиент | Способ вызова |
|---|---|---|
| `anthropic`, `ccswitch` | `CCSwitchClient` | HTTP + fallback CLI |
| `openai` | `OpenAIClient` | HTTP |
| `deepseek` | `DeepSeekClient` | HTTP |
| `ollama` | `OllamaClient` | HTTP (localhost) |
| `claude`, `claude-cli` | `ClaudeCLIClient` | `claude --print` |
| `copilot`, `copilot-cli` | `CopilotCLIClient` | `copilot -p ... --yolo` |
| `codex`, `codex-cli` | `CodexCLIClient` | `codex exec` |
| `gemini`, `gemini-cli` | `GeminiCLIClient` | `gemini -p` |
| `antigravity`, `agy` | `AntigravityCLIClient` | `agy -p ... --dangerously-skip-permissions` |
| **`kiro`, `kiro-cli`** | **`KiroCLIClient`** | **`kiro --print` / `-p` / stdin** |

---

## 🆕 Kiro CLI Integration

В состав провайдеров добавлен **`KiroCLIClient`** — интеграция с локально установленным [Kiro CLI](https://kiro.dev).

Клиент реализует трёхшаговую fallback-стратегию:

```
kiro --print "<prompt>"   →   kiro -p "<prompt>"   →   kiro (stdin pipe)
```

- Таймаут каждого шага — 45 секунд (`asyncio.wait_for`)
- При недоступности бинарника или ошибке возвращает строку `"# Kiro CLI error: ..."` — пайплайн не падает
- Диагностика пишется в `sys.stderr`, не засоряя stdout
- Новых зависимостей не добавляется — используются только `asyncio`, `subprocess`, `sys`

### Использование в пресете

```json
{
  "proposers": [
    { "provider": "kiro", "model": "default" },
    { "provider": "claude", "model": "default" }
  ],
  "aggregator": { "provider": "kiro-cli", "model": "default" }
}
```

### Использование в коде

```python
from moa_engine.clients import KiroCLIClient
from moa_engine.domain import Message

client = KiroCLIClient()
response = await client.generate([Message(role="user", content="Write a Python function")])
```

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
        +str api_key_env
        +str model_name
        +generate(messages: List~Message~, temperature: float) str
        -_http_generate(...) str
        -_fallback_via_cli(messages: List~Message~) str
    }
    class KiroCLIClient {
        +generate(messages: List~Message~, temperature: float) str
    }
    LLMClient <|.. CCSwitchClient
    LLMClient <|.. KiroCLIClient

    class Agent {
        <<abstract>>
        #LLMClient _client
        +process(task: Task)* str
    }
    class ProposerAgent {
        +float temperature
        +process(task: Task) str
    }
    class CriticAgent {
        +process(task: Task) str
    }
    class AggregatorAgent {
        +process_proposals(task: Task, proposals: List~str~, critique: str) str
        +process(task: Task) str
    }
    Agent <|.. ProposerAgent
    Agent <|.. CriticAgent
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
    class CompositeVerifier {
        -List~VerifierStrategy~ _verifiers
        +verify(artifact: Artifact) VerificationResult
    }
    VerifierStrategy <|.. CommandVerifier
    VerifierStrategy <|.. CompositeVerifier
    CompositeVerifier o-- VerifierStrategy

    class ExecutionReporter {
        +List~IterationLog~ logs
        +log_iteration(...) void
        +generate_html_report(output_file: str) str
    }

    class MoAOrchestrator {
        -List~ProposerAgent~ _proposers
        -AggregatorAgent _aggregator
        -VerifierStrategy _verifier
        -CriticAgent _critic
        -str _output_path
        -int _max_iterations
        +run_until_proven(task_description: str) bool
    }
    MoAOrchestrator o-- ProposerAgent
    MoAOrchestrator o-- AggregatorAgent
    MoAOrchestrator o-- CriticAgent
    MoAOrchestrator o-- VerifierStrategy
    MoAOrchestrator ..> Artifact
    MoAOrchestrator ..> Task
```

---

## 🏛 Архитектурные принципы (SOLID)

- **Single Responsibility (SRP)**: `CCSwitchClient` отвечает за HTTP-транспорт и ретраи, `Agent` — за роли и промпты, `VerifierStrategy` — за проверку артефактов, `ExecutionReporter` — за HTML-отчёты, `MoAOrchestrator` — за основной цикл.
- **Open/Closed (OCP)**: Добавление новых способов верификации (`CompositeVerifier`) или провайдеров происходит через реализацию абстрактных классов без модификации оркестратора.
- **Liskov Substitution (LSP)**: Любая реализация `LLMClient` или `VerifierStrategy` полностью взаимозаменяема.
- **Interface Segregation (ISP)**: Разделение узких дата-классов `Message`, `Task`, `Artifact`, `VerificationResult`.
- **Dependency Inversion (DIP)**: `MoAOrchestrator` зависит строго от интерфейсов `LLMClient`, `Agent` и `VerifierStrategy`.

---

## 🛠 Установка и запуск

### 1. Клонирование и установка
```bash
git clone https://github.com/NickScherbakov/moa-cc-switch.git
cd moa-cc-switch

# Установка пакета в режиме разработки
pip install -e .[dev]
```

### 2. Конфигурация (.env)
Создайте файл `.env` в корне проекта (опционально для реальных запросов к API):
```env
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key
DEEPSEEK_API_KEY=your_deepseek_key
CC_SWITCH_ENDPOINT=https://api.anthropic.com
MOA_TIMEOUT=60.0
MOA_MAX_RETRIES=3
```

### 3. Запуск через CLI (`moa-run`)
```bash
moa-run --task "Напиши кастомный LRU-кэш" --verify "pytest tests/test_lru_cache.py" --out "lru_cache.py"
```

### 4. Запуск тестов
```bash
pytest
```

### 5. Тесты CLI-агентов (включая Kiro)
```bash
pytest tests/test_cli_agents.py -v
```

---

## 👥 Авторы и соавторы

| Роль | Участник | Вклад |
|---|---|---|
| Автор проекта | [NickScherbakov](https://github.com/NickScherbakov) | Архитектура MoA Engine, CC Switch, HTTP-транспорт, CLI-агенты, верификация |
| Соавтор | [Kiro](https://kiro.dev) (AI-ассистент) | Спецификация и реализация `KiroCLIClient`, обновление документации, spec-driven разработка интеграции |
