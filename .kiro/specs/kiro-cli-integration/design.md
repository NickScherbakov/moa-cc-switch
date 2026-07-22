# Design Document

## Feature: kiro-cli-integration

## Overview

`KiroCLIClient` — новая реализация `LLMClient`, интегрирующая локально установленный Kiro CLI в систему MoA Engine. Клиент следует тем же шаблонам, что `ClaudeCLIClient` и `GeminiCLIClient`: формирует prompt-текст из списка сообщений, вызывает бинарный файл `kiro` через `asyncio.create_subprocess_exec` с последовательным fallback, применяет таймаут 45 с и возвращает строку. Новых зависимостей не вводится.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  runner.py                                                           │
│  build_client_from_config("kiro" | "kiro-cli", model)               │
│            │                                                         │
│            ▼                                                         │
│  KiroCLIClient  (clients.py)                                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  generate(messages, temperature) → str                       │   │
│  │                                                              │   │
│  │  1. prompt_text = "\n".join("role: content")                │   │
│  │  2. attempt: kiro --print "<prompt>"  ──→ rc==0 & stdout?   │   │
│  │                 ↓ fail                                       │   │
│  │  3. attempt: kiro -p "<prompt>"       ──→ rc==0 & stdout?   │   │
│  │                 ↓ fail                                       │   │
│  │  4. attempt: kiro  (stdin pipe)       ──→ rc==0 & stdout?   │   │
│  │                 ↓ fail                                       │   │
│  │  5. return "# Kiro CLI error: <exc>"                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Components

### KiroCLIClient (`src/moa_engine/clients.py`)

Место: добавляется в конец `clients.py` рядом с `AntigravityCLIClient`.

```python
class KiroCLIClient(LLMClient):
    """Direct CLI agent driver for installed Kiro CLI."""

    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str:
        prompt_text = "\n".join([f"{m.role}: {m.content}" for m in messages])

        # Attempt 1: kiro --print "<prompt>"
        try:
            process = await asyncio.create_subprocess_exec(
                "kiro", "--print", prompt_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=45.0)
            if process.returncode == 0 and stdout:
                result = stdout.decode("utf-8", errors="ignore").strip()
                if result:
                    return result
        except Exception:
            pass

        # Attempt 2: kiro -p "<prompt>"
        try:
            process = await asyncio.create_subprocess_exec(
                "kiro", "-p", prompt_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=45.0)
            if process.returncode == 0 and stdout:
                result = stdout.decode("utf-8", errors="ignore").strip()
                if result:
                    return result
        except Exception:
            pass

        # Attempt 3: kiro via stdin pipe
        try:
            process = await asyncio.create_subprocess_exec(
                "kiro",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(input=prompt_text.encode("utf-8")),
                timeout=45.0,
            )
            if process.returncode == 0 and stdout:
                result = stdout.decode("utf-8", errors="ignore").strip()
                if result:
                    return result
        except Exception as e:
            print(f"⚠️ Kiro CLI unavailable: {e}", file=sys.stderr)
            return f"# Kiro CLI error: {e}"

        return "# Kiro CLI error: all three invocation strategies returned empty or non-zero"
```

**Ключевые детали:**
- Никаких новых `import` — `asyncio`, `subprocess`, `sys` уже импортированы в `clients.py`.
- Таймаут 45 с обёртывает `process.communicate()` через `asyncio.wait_for`.
- Диагностика пишется в `sys.stderr` (как в `GeminiCLIClient`).
- При любом финальном сбое строка начинается с `"# Kiro CLI error:"`.

---

### runner.py — регистрация в фабрике

В `build_client_from_config` добавляется одна ветка:

```python
# В секции импортов:
from moa_engine.clients import (
    ...,
    KiroCLIClient,       # добавить
)

# В теле build_client_from_config, перед elif provider_lower == "openai":
elif provider_lower in ("kiro-cli", "kiro"):
    return KiroCLIClient()
```

Все существующие ветки остаются без изменений.

---

### test_cli_agents.py — расширение тестов

Добавляются:

1. `"kiro"` в список `cli_name` в `test_installed_cli_binaries_exist`.
2. Два `isinstance`-assert в `test_build_client_from_config_cli_agents`.
3. Новый `async` тест `test_kiro_cli_real_execution`.

```python
# В test_installed_cli_binaries_exist:
for cli_name in ["agy", "claude", "copilot", "codex", "gemini", "kiro"]:
    ...

# В test_build_client_from_config_cli_agents:
assert isinstance(build_client_from_config("kiro", "default"), KiroCLIClient)
assert isinstance(build_client_from_config("kiro-cli", "default"), KiroCLIClient)

# Новый тест:
@pytest.mark.asyncio
async def test_kiro_cli_real_execution():
    """Test real Kiro CLI execution (or graceful error path if binary absent)."""
    client = KiroCLIClient()
    response = await client.generate([Message(role="user", content="Respond with string SUCCESS_KIRO")])
    assert isinstance(response, str)
    assert len(response) > 0
```

---

## Data Models

Новых моделей нет. `KiroCLIClient` использует `Message` из `moa_engine.domain` — тот же тип, что все остальные клиенты.

```
Message(role: str, content: str)
   │
   └─→ prompt_text: str  ←  "\n".join(f"{m.role}: {m.content}" for m in messages)
```

---

## Interfaces

`KiroCLIClient` полностью соответствует контракту `LLMClient`:

```python
class LLMClient(ABC):
    @abstractmethod
    async def generate(self, messages: List[Message], temperature: float = 0.7) -> str: ...
```

Параметр `temperature` принимается для совместимости с интерфейсом, но не передаётся в CLI (Kiro CLI не поддерживает управление температурой через флаги).

---

## Fallback Strategy

| Шаг | Команда | Метод |
|-----|---------|-------|
| 1 | `kiro --print "<prompt>"` | `asyncio.create_subprocess_exec` |
| 2 | `kiro -p "<prompt>"` | `asyncio.create_subprocess_exec` |
| 3 | `kiro` + stdin pipe | `asyncio.create_subprocess_exec` + `communicate(input=...)` |
| — | ошибка | возврат `"# Kiro CLI error: ..."` |

Переход к следующему шагу происходит при:
- ненулевом коде возврата (`returncode != 0`);
- пустом stdout после strip;
- любом исключении (`FileNotFoundError`, `asyncio.TimeoutError`, и т.д.).

---

## Error Handling

| Ситуация | Поведение |
|----------|-----------|
| Бинарник `kiro` отсутствует в PATH | `FileNotFoundError` → fallback по цепочке → возврат `"# Kiro CLI error: ..."` |
| Таймаут (>45 с) | `asyncio.TimeoutError` → то же |
| Ненулевой returncode | следующий шаг fallback |
| Пустой stdout | следующий шаг fallback |
| Все три попытки вернули пустой stdout | `"# Kiro CLI error: all three invocation strategies returned empty or non-zero"` |

Любой сбой гарантированно возвращает `str`, что обеспечивает совместимость со всеми потребителями `LLMClient`.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Prompt formation preserves all messages

*For any* non-empty list of `Message` objects with arbitrary `role` and `content` strings, the prompt text formed by `KiroCLIClient` must equal `"\n".join(f"{m.role}: {m.content}" for m in messages)` — every message appears exactly once, in order, with no content omitted or transformed.

**Validates: Requirements 1.2**

---

### Property 2: Successful subprocess output is decoded and stripped

*For any* byte string returned as stdout from a subprocess call that exits with return code 0, the value returned by `generate` must equal `stdout.decode("utf-8", errors="ignore").strip()` — leading and trailing whitespace is removed, and the encoding is UTF-8 with error replacement.

**Validates: Requirements 1.6**

---

### Property 3: All failure paths return a valid error string

*For any* exception raised during all three subprocess attempts (including `FileNotFoundError`, `asyncio.TimeoutError`, `OSError`, or any other exception with arbitrary message text), the value returned by `generate` must be a `str` instance that begins with `"# Kiro CLI error:"`.

**Validates: Requirements 1.7, 4.4**

---

### Property 4: Factory dispatch is case-insensitive for Kiro keys

*For any* string that is a case-variant of `"kiro"` (e.g. `"KIRO"`, `"Kiro"`, `"kIrO"`) or `"kiro-cli"` (e.g. `"KIRO-CLI"`, `"Kiro-Cli"`), `build_client_from_config` must return an instance of `KiroCLIClient`.

**Validates: Requirements 2.1, 2.2**
