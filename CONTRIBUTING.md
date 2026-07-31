# Contributing to Re:Zero Twin System

Thank you for your interest in improving this project.  
This document outlines the development standards and contribution process.

## Development Philosophy

- **State First**: Any new feature must first be expressible as a clear state or transition in the HardStateEngine.
- **LLM is a renderer, not a decision maker**: Never let the model directly modify favor, independence, stages, or other hard values.
- **Original Lore Priority**: When in conflict between "interesting" and "accurate to Re:Zero", accuracy wins.
- **Small, Testable Changes**: Prefer focused pull requests over large rewrites.

## Code Standards

### Python
- Python 3.10+
- Use type hints for all public functions and class attributes
- Prefer `Enum` / `IntEnum` for states
- Keep functions focused; avoid methods longer than ~40 lines when possible
- Docstrings for all non-obvious classes and methods

### Naming
- Hard state related: `HardStateEngine`, `TwinState`, `safe_add_favor`
- Prompt related: `PromptBuilder`, `build`
- Character specific: `RemAI`, `RamAI` (kept separate)

### State Update Rules
- All favor changes **must** go through `_safe_add_favor()` or an equivalent guarded method
- Independence and Ram stage changes should be intentional and logged in reason strings when debugging
- Never decrease high-value states (BELOVED / ACKNOWLEDGED) without clear high-risk triggers

## Adding New Features

1. First design the **state impact** (what new field or transition is needed?)
2. Update `HardStateEngine` and `TwinState`
3. Extend `PromptBuilder` so the LLM receives clear natural language instructions about the new state
4. Add test cases to `tests/smoke_test.py` (zero-API assertions preferred)
5. Update CHANGELOG.md and add a devlog entry under `docs/devlog/`

## Prompt Engineering Guidelines

- Keep the system prompt structured and dense
- Translate numerical states into behavioral guidance (e.g. "Independence 0.8 → rarely uses substitute speech")
- Prefer explicit instructions over hoping the model "understands"
- Temperature should generally stay between 0.6–0.75 for persona stability

## Testing Recommendations

Before submitting:
- [ ] Run `python tests/smoke_test.py` (all green)
- [ ] Test favor lock behavior (try to drop favor after BELOVED)
- [ ] Test independence growth and its effect on inferiority lines
- [ ] Test Ram stage progression and entrustment lines
- [ ] Test Empire arc amnesia → recovery transition
- [ ] Test Oni stages and Ram's reaction
- [ ] Verify LLM still respects output format under various states

For deeper behavioral evaluation, see `docs/evaluation/` (test case library + run reports).

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`feature/ram-initiative-v2`)
3. Make your changes following the standards above
4. Update CHANGELOG.md under the appropriate version
5. Open a Pull Request with a clear description of:
   - What problem it solves
   - Which states are affected
   - How to test it

## Questions & Discussion

Feel free to open an Issue for:
- Design discussions
- Lore accuracy questions
- Architecture proposals

We value thoughtful discussion about character psychology and system design as much as code contributions.
