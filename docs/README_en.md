# Re:Zero Twin System

> A stateful character system for Ram & Rem from *Re:Zero − Starting Life in Another World*  
> Evolving from pure rule-based engine to **Hard Constraints × Soft Expression** with LLM

This project implements a dual-maid role-playing system centered on Ram and Rem.  
It has gone through a complete iteration path: Rule Engine → Deep Psychological State Machine → State Machine + LLM Bridge.

**Core Goal**:  
Preserve the hard constraints of original lore, numerical progression, and risk control, while granting the LLM highly flexible and soulful natural language expression.

---

## Vision

In character AI, two extremes are common:

- Pure rule systems → Stable but rigid, lacking soul
- Pure LLM systems → Flexible but prone to persona collapse, forgotten settings, and numerical chaos

This project explores a third path:  
**Let the state machine guard boundaries and growth logic, while the LLM unleashes linguistic and emotional expressiveness.**

---

## Core Design Principles

1. **Numbers and logic must be controlled by the state machine** (favor, independence, evaluation stages, Oni form, etc.)
2. **The LLM is only responsible for "how to say it", never for "what it becomes"**
3. **Relationships have structure** (not just favor point arithmetic)
   - Rem: Emotional salvation ↔ Personal independence
   - Ram: Observation → Recognition → Entrustment
4. **High favor should have "loyalty lock"**, matching the emotional quality of the later original work
5. **The twins must have functional division of labor**, not just taking turns speaking

---

## Architecture Overview

See [architecture.md](architecture.md) for Mermaid diagrams.

```
User Input
 ↓
HardStateEngine (hard constraint layer)
 ├─ Intent detection
 ├─ Safe favor / independence / Ram stage updates
 ├─ Oni stage machine
 ├─ Context summary
 └─ TwinState snapshot
 ↓
PromptBuilder (state → natural language instructions)
 ↓
LLM (DeepSeek / OpenAI / local model)
 ↓
Twin response matching the current state
```

---

## Quick Start (LLM Version)

```bash
pip install -r requirements.txt

# create .env in the project root:
# DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

python main.py --mode llm   # terminal
python gui.py               # GUI (chat window)
```

Useful commands:
- `status` — View all hard states
- `empire` / `mansion` / `late` — Switch story arc
- `recover 0.6` — Set memory recovery progress
- `/llm` / `/local` (GUI) — Switch between LLM bridge and local template mode
- `quit` — Exit

---

## Current State Features (V9.5+)

- Rem Favor + Loyalty Lock (with tiered deduction exemption)
- Identity Independence (affirmation-driven growth)
- Ram Independent Favor + 5 Evaluation Stages
- Oni Transformation (3 stages + aftermath)
- Empire Arc Memory Recovery Progress
- Long-term Event Memory (milestone moments injected into prompt)
- Structured Context Summary
- Gentle Push + Procrastination Detection
- Breaker Easter Egg

---

## Design Insights for Future Projects

1. **Clarify relationship structure before writing code**  
   Favor is surface-level. What matters is how characters define each other.

2. **High-value states need anti-decay design**  
   Once deep trust is given, it should not easily regress from daily friction.

3. **Supporting characters deserve independent state machines**  
   Ram's evaluation stages and initiative significantly elevated the overall experience.

4. **State machine owns "truth", LLM owns "beauty"**  
   This is currently one of the more sustainable architectures for character AI.

5. **Easter eggs and narrative beats can be rare, but must carry weight**  
   The Breaker line has extremely low trigger rate, yet creates strong emotional memory.

---

## Disclaimer

This is a personal learning and character understanding project.  
All characters and settings belong to the original author of *Re:Zero* and related rights holders.

For technical exploration and doujin exchange only.

---

**Maintainers**: 小东 & K  
**Last Updated**: 2026-07-31
