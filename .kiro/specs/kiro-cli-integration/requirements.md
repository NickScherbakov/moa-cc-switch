# Requirements Document

## Introduction

Данная фича добавляет `KiroCLIClient` — нового LLM-провайдера в систему MoA Engine. Клиент реализует взаимодействие с локально установленным Kiro CLI через вызов подпроцессов (`subprocess`), следуя шаблонам уже существующих CLI-провайдеров (`ClaudeCLIClient`, `GeminiCLIClient`). Клиент регистрируется в фабрике `build_client_from_config` под ключами `"kiro-cli"` и `"kiro"`, а также покрывается тестами в файле `test_cli_agents.py`.

## Glossary

- **KiroCLIClient**: Реализация `LLMClient`, выполняющая запросы к LLM через Kiro CLI посредством вызова подпроцессов.
- **LLMClient**: Абстрактный базовый класс (`ABC`) в `clients.py`, определяющий контракт метода `generate`.
- **MoA Engine**: Система оркестрации Mixture-of-Agents, реализованная в пакете `moa_engine`.
- **build_client_from_config**: Фабричная функция в `runner.py`, возвращающая экземпляр `LLMClient` по строковому ключу провайдера.
- **Fallback-стратегия**: Последовательность попыток вызова Kiro CLI с разными флагами до первого успешного результата.
- **Prompt-текст**: Строка, формируемая конкатенацией сообщений в формате `"role: content"` через символ новой строки.
- **Kiro CLI**: Локально установленный исполняемый файл `kiro`, доступный в системном `PATH`.

## Requirements

### Requirement 1 — Реализация KiroCLIClient

**User Story:** As a MoA Engine user, I want to use Kiro CLI as an LLM provider, so that I can include locally installed Kiro in agent orchestration pipelines.

#### Acceptance Criteria

1. THE `KiroCLIClient` SHALL inherit from `LLMClient` and implement the `generate` method with the signature `async def generate(self, messages: List[Message], temperature: float = 0.7) -> str`.
2. WHEN `generate` is called, THE `KiroCLIClient` SHALL form the prompt-текст concatenation of all messages in the format `"role: content"` joined by newlines.
3. WHEN forming the subprocess call, THE `KiroCLIClient` SHALL first attempt to execute `kiro --print "<prompt>"` using `asyncio.create_subprocess_exec`.
4. IF the first attempt fails (non-zero return code or exception), THEN THE `KiroCLIClient` SHALL attempt to execute `kiro -p "<prompt>"` using `asyncio.create_subprocess_exec`.
5. IF both `--print` and `-p` attempts fail, THEN THE `KiroCLIClient` SHALL attempt to execute `kiro` and pass the prompt-текст to the process via stdin pipe.
6. WHEN any subprocess call returns with return code `0` and non-empty stdout, THE `KiroCLIClient` SHALL return the stdout content decoded as UTF-8, stripped of leading and trailing whitespace.
7. IF all three fallback attempts fail or raise an exception, THEN THE `KiroCLIClient` SHALL return a string beginning with `"# Kiro CLI error:"` followed by the exception description.
8. WHEN a subprocess call is awaited, THE `KiroCLIClient` SHALL apply a timeout of 45 seconds using `asyncio.wait_for`.

### Requirement 2 — Регистрация в фабрике build_client_from_config

**User Story:** As a MoA Engine user, I want to specify `"kiro-cli"` or `"kiro"` as a provider key in configuration, so that the engine instantiates `KiroCLIClient` automatically.

#### Acceptance Criteria

1. WHEN `build_client_from_config` is called with `provider` equal to `"kiro-cli"` (case-insensitive), THE `build_client_from_config` SHALL return an instance of `KiroCLIClient`.
2. WHEN `build_client_from_config` is called with `provider` equal to `"kiro"` (case-insensitive), THE `build_client_from_config` SHALL return an instance of `KiroCLIClient`.
3. THE `runner.py` module SHALL import `KiroCLIClient` from `moa_engine.clients` alongside all other existing CLI client imports.
4. WHILE all other existing provider registrations are present, THE `build_client_from_config` SHALL preserve their behavior unchanged after the addition of Kiro provider keys.

### Requirement 3 — Обнаружение бинарного файла Kiro CLI

**User Story:** As a MoA Engine user, I want the system to verify that the Kiro CLI binary is available, so that misconfigured environments are detected early.

#### Acceptance Criteria

1. THE `test_cli_agents.py` test `test_installed_cli_binaries_exist` SHALL include `"kiro"` in the list of CLI binary names verified via `shutil.which`.
2. IF `shutil.which("kiro")` returns `None`, THEN THE test SHALL fail with the assertion message `"CLI agent binary 'kiro' not found on system PATH"`.

### Requirement 4 — Тесты в test_cli_agents.py

**User Story:** As a developer, I want tests for KiroCLIClient, so that the implementation is verifiable and regressions are caught early.

#### Acceptance Criteria

1. THE `test_cli_agents.py` SHALL include a test `test_build_client_from_config_cli_agents` that asserts `build_client_from_config("kiro", "default")` returns an instance of `KiroCLIClient`.
2. THE `test_cli_agents.py` SHALL include a test `test_build_client_from_config_cli_agents` that asserts `build_client_from_config("kiro-cli", "default")` returns an instance of `KiroCLIClient`.
3. THE `test_cli_agents.py` SHALL include an `async` test decorated with `@pytest.mark.asyncio` that calls `KiroCLIClient().generate([Message(role="user", content="Respond with string SUCCESS_KIRO")])` and asserts the result is a non-empty `str`.
4. WHEN the Kiro CLI binary is unavailable on the system PATH, THE `KiroCLIClient.generate` test SHALL assert that the returned string is still a valid `str` instance (error path coverage).

### Requirement 5 — Совместимость с существующей инфраструктурой

**User Story:** As a developer, I want KiroCLIClient to follow established patterns, so that the codebase remains consistent and maintainable.

#### Acceptance Criteria

1. THE `KiroCLIClient` class SHALL be defined in `src/moa_engine/clients.py` alongside all other existing `LLMClient` implementations.
2. THE `KiroCLIClient` implementation SHALL use only modules already present in the project: `asyncio`, `subprocess`, `sys`, and standard library modules — without introducing new dependencies.
3. THE `clients.py` module SHALL export `KiroCLIClient` without modifying the existing public interface of any other class.
4. WHEN `KiroCLIClient.generate` writes diagnostic messages, THE `KiroCLIClient` SHALL write those messages to `sys.stderr`, not to `sys.stdout`, consistent with the pattern used by `GeminiCLIClient`.
