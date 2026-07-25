# Walkthrough - Integration of Synergy Goal (Цель синергического мышления команды)

Date: 2026-07-25

The concept of **Synergy Goal (Цель синергического мышления команды)** has been fully implemented across all architectural layers of the engine.

## Changes Made

### 1. Domain Layer
- **[domain.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/domain.py)**: Added `synergy_goal: str = ""` field to `Task` frozen dataclass.

### 2. Config & Presets Layer
- **[presets.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/presets.py)**: Added `synergy_goal: str = ""` optional field to `PresetConfig`, with full dict/JSON/YAML roundtrip support in `from_dict`.

### 3. CLI Runner Layer
- **[runner.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/runner.py)**:
  - Added CLI parameter `--goal`: `parser.add_argument("--goal", help="Цель синергического мышления команды")`.
  - Config precedence: CLI argument `--goal` overrides `preset.synergy_goal`.
  - Updated `main()` to pass `synergy_goal` to `orchestrator.run_until_proven(task_desc, synergy_goal=synergy_goal)`.

### 4. Orchestrator Engine
- **[engine.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/engine.py)**:
  - Updated signature: `async def run_until_proven(self, task_description: str, synergy_goal: str = "") -> bool:`.
  - Passed `synergy_goal` when constructing `Task` instances in the execution loop and retry logic.
  - Formatted victory console output when `synergy_goal` is present:
    ```
    🏆 В результате синергического мышления команды была достигнута цель:
    <synergy_goal>
    ```

### 5. Agents Layer
- **[agents.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/agents.py)**:
  - Modified prompt construction in `ProposerAgent.process`, `CriticAgent.process`, `AggregatorAgent.process`, and `AggregatorAgent.process_proposals`.
  - When `task.synergy_goal` is non-empty, hard-injects the exact required instruction block into the user prompt:
    ```
    🎯 ЦЕЛЬ СИНЕРГИЧЕСКОГО МЫШЛЕНИЯ КОМАНДЫ:
    <task.synergy_goal>
    Все твои рассуждения и итоговый ответ должны быть подчинены достижению этой цели.
    ```

### 6. Test Suite Updates
- **[test_moa_engine.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/tests/test_moa_engine.py)**: Updated `test_domain_dataclasses` and orchestrator test calls.
- **[test_agents.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/tests/test_agents.py)**: Added `test_synergy_goal_prompt_injection` to verify hard prompt injection across all agent types.
- **[test_presets.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/tests/test_presets.py)**: Added assertions for `synergy_goal` in JSON and YAML roundtrips.

---

## Verification Results

### Automated Tests
Executed unit tests:
```bash
pytest -k "not test_cli_agents"
```
Output:
`27 passed in 8.73s`
