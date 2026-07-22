# Implementation Plan: kiro-cli-integration

## Overview

Добавляем `KiroCLIClient` в `clients.py` с трёхшаговой fallback-стратегией и таймаутом 45 с, регистрируем его в фабрике `build_client_from_config` в `runner.py`, расширяем существующие тесты в `test_cli_agents.py` и добавляем property-based тесты для четырёх свойств корректности из design-документа.

## Tasks

- [ ] 1. Добавить KiroCLIClient в clients.py
  - [ ] 1.1 Реализовать класс KiroCLIClient
    - Добавить класс `KiroCLIClient(LLMClient)` в конец `src/moa_engine/clients.py` рядом с `AntigravityCLIClient`
    - Реализовать метод `async def generate(self, messages: List[Message], temperature: float = 0.7) -> str`
    - Формировать `prompt_text = "\n".join(f"{m.role}: {m.content}" for m in messages)`
    - Шаг 1: `asyncio.create_subprocess_exec("kiro", "--print", prompt_text, ...)` с таймаутом 45 с
    - Шаг 2 (fallback): `asyncio.create_subprocess_exec("kiro", "-p", prompt_text, ...)` с таймаутом 45 с
    - Шаг 3 (fallback): `asyncio.create_subprocess_exec("kiro", ...)` с передачей prompt через stdin pipe
    - При любом финальном сбое возвращать строку, начинающуюся с `"# Kiro CLI error:"`
    - Диагностические сообщения писать в `sys.stderr`
    - Новых импортов не добавлять — `asyncio`, `subprocess`, `sys` уже присутствуют
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 5.1, 5.2, 5.3, 5.4_

  - [ ]* 1.2 Написать property-тест: формирование prompt-текста (Property 1)
    - **Property 1: Prompt formation preserves all messages**
    - Использовать `hypothesis` (`@given(st.lists(...))`): для произвольного непустого списка `Message` проверить, что `prompt_text == "\n".join(f"{m.role}: {m.content}" for m in messages)`
    - **Validates: Requirements 1.2**

  - [ ]* 1.3 Написать property-тест: декодирование и strip stdout (Property 2)
    - **Property 2: Successful subprocess output is decoded and stripped**
    - Используя `unittest.mock.patch` + `hypothesis` (`@given(st.binary())`): для произвольного байтового stdout с `returncode == 0` проверить, что результат `generate` равен `stdout.decode("utf-8", errors="ignore").strip()`
    - **Validates: Requirements 1.6**

  - [ ]* 1.4 Написать property-тест: все пути сбоя возвращают строку с "# Kiro CLI error:" (Property 3)
    - **Property 3: All failure paths return a valid error string**
    - Используя `unittest.mock.patch` + `hypothesis` (`@given(st.text())`): для произвольного исключения (`FileNotFoundError`, `asyncio.TimeoutError`, `OSError` с произвольным сообщением) проверить, что `generate` возвращает `str`, начинающийся с `"# Kiro CLI error:"`
    - **Validates: Requirements 1.7, 4.4**

- [ ] 2. Зарегистрировать KiroCLIClient в runner.py
  - [ ] 2.1 Добавить импорт и ветку в build_client_from_config
    - Добавить `KiroCLIClient` в импорт `from moa_engine.clients import (...)` в `runner.py`
    - Добавить ветку `elif provider_lower in ("kiro-cli", "kiro"): return KiroCLIClient()` перед веткой `"openai"`
    - Убедиться, что все существующие ветки остались без изменений
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 2.2 Написать property-тест: регистрация без учёта регистра (Property 4)
    - **Property 4: Factory dispatch is case-insensitive for Kiro keys**
    - Используя `hypothesis` (`@given(st.sampled_from(["kiro", "kiro-cli"]).map(randomize_case))`): для любого case-варианта строк `"kiro"` и `"kiro-cli"` проверить, что `build_client_from_config(variant, "default")` возвращает `isinstance(..., KiroCLIClient)`
    - **Validates: Requirements 2.1, 2.2**

- [ ] 3. Checkpoint — убедиться, что существующие тесты проходят
  - Запустить `pytest tests/test_clients.py tests/test_agents.py` и убедиться в отсутствии регрессий. Если тесты падают — исправить перед продолжением.

- [ ] 4. Расширить тесты в test_cli_agents.py
  - [ ] 4.1 Добавить "kiro" в test_installed_cli_binaries_exist
    - Расширить список `["agy", "claude", "copilot", "codex", "gemini"]` до `["agy", "claude", "copilot", "codex", "gemini", "kiro"]`
    - _Requirements: 3.1, 3.2_

  - [ ] 4.2 Расширить test_build_client_from_config_cli_agents
    - Добавить `from moa_engine.clients import (..., KiroCLIClient)` в импорты теста
    - Добавить два assert: `isinstance(build_client_from_config("kiro", "default"), KiroCLIClient)` и `isinstance(build_client_from_config("kiro-cli", "default"), KiroCLIClient)`
    - _Requirements: 4.1, 4.2_

  - [ ] 4.3 Добавить async-тест test_kiro_cli_real_execution
    - Написать `@pytest.mark.asyncio async def test_kiro_cli_real_execution():`
    - Вызвать `KiroCLIClient().generate([Message(role="user", content="Respond with string SUCCESS_KIRO")])`
    - Проверить `isinstance(response, str)` и `len(response) > 0`
    - Тест должен проходить как при наличии бинарника `kiro`, так и при его отсутствии (error path)
    - _Requirements: 4.3, 4.4_

- [ ] 5. Финальный checkpoint — все тесты проходят
  - Запустить `pytest tests/test_cli_agents.py -v` и убедиться, что все новые тесты присутствуют и проходят (или пропускаются при отсутствии бинарника). Если тесты падают — исправить.

## Notes

- Задачи с `*` — опциональные property-based тесты; их можно пропустить для быстрого MVP
- Property-тесты требуют `hypothesis`; убедитесь, что он присутствует в `pyproject.toml` (он уже есть как зависимость проекта)
- Каждая задача ссылается на конкретные пункты требований для трассируемости
- `KiroCLIClient` не вводит новых зависимостей — использует только уже импортированные модули

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "4.1", "4.2"] },
    { "id": 3, "tasks": ["4.3"] }
  ]
}
```
