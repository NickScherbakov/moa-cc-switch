# Implementation Plan - Integration of "Synergy Goal" (Синергическая цель мышления команды)

Date: 2026-07-25

This document outlines the changes required to propagate `synergy_goal` across all architecture layers of `moa_engine`: domain model, preset configuration, CLI parser & runner, orchestrator, agent prompt injection, and unit test suite.

## Proposed Changes

---

### Domain Layer

#### [MODIFY] [domain.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/domain.py)
- Add `synergy_goal: str = ""` field to the `Task` dataclass.

---

### Presets Layer

#### [MODIFY] [presets.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/presets.py)
- Add optional `synergy_goal: str = ""` field to `PresetConfig`.
- Update `PresetConfig.from_dict` to extract `synergy_goal` from dict with default `""`.

---

### CLI Runner Layer

#### [MODIFY] [runner.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/runner.py)
- Add CLI argument `--goal`: `parser.add_argument("--goal", help="Цель синергического мышления команды")`.
- Determine active `synergy_goal` using CLI precedence: `args.goal if args.goal is not None else (preset.synergy_goal if preset else "")`.
- Pass `synergy_goal` to `orchestrator.run_until_proven(task_desc, synergy_goal=synergy_goal)` in `main()`.

---

### Orchestrator Layer

#### [MODIFY] [engine.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/engine.py)
- Update signature: `async def run_until_proven(self, task_description: str, synergy_goal: str = "") -> bool:`.
- Create initial and retry `Task` instances with `Task(description=task_description, synergy_goal=synergy_goal, ...)`.
- On success (`if result.is_success:`), if `synergy_goal` is non-empty, print:
  `console.print(f"\n[bold green]🏆 В результате синергического мышления команды была достигнута цель:[/bold green]\n[italic green]{synergy_goal}[/italic green]")`.
  Otherwise, print standard victory message.

---

### Agents Layer

#### [MODIFY] [agents.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/src/moa_engine/agents.py)
- In `ProposerAgent.process`, `CriticAgent.process`, `AggregatorAgent.process`, and `AggregatorAgent.process_proposals`:
  If `task.synergy_goal` is set (`if task.synergy_goal:`), append the exact required instruction block to the user message content:
  `f"\n\n🎯 ЦЕЛЬ СИНЕРГИЧЕСКОГО МЫШЛЕНИЯ КОМАНДЫ:\n{task.synergy_goal}\nВсе твои рассуждения и итоговый ответ должны быть подчинены достижению этой цели."`.

---

### Test Suite

#### [MODIFY] [test_moa_engine.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/tests/test_moa_engine.py)
- Verify `Task.synergy_goal` default value and custom value in `test_domain_dataclasses`.
- Update `run_until_proven` calls and test `synergy_goal` pass-through and success console output.

#### [MODIFY] [test_agents.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/tests/test_agents.py)
- Add tests verifying prompt injection for `ProposerAgent`, `CriticAgent`, and `AggregatorAgent` (`process` and `process_proposals`) when `synergy_goal` is present and absent.

#### [MODIFY] [test_presets.py](file:///C:/Users/Admin/Documents/antigravity/quirky-hawking/tests/test_presets.py)
- Add test for `synergy_goal` serialization and deserialization in JSON/YAML roundtrip.

---

## Verification Plan

### Automated Tests
- Run `pytest` across all test files to verify full test suite passes.
- Specifically run `pytest tests/test_agents.py tests/test_moa_engine.py tests/test_presets.py`.
