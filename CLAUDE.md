# Litikj Agent Framework Development Guide

## Overview
Litikj Agent Framework is a lightweight (<40MB), 100% offline-ready, local-first multi-agent operating framework designed for high-performance agentic engineering.

## Architecture Highlights
- **Microkernel 底座 (`core/`)**: Pure standard-library foundation providing contracts, discovery, tool-runner, quota management, and AST safety scanner.
- **0-Token Fast-Path**: Instant execution (<10ms) for deterministic commands (`ping`, `config`, `check`, `heal`) avoiding wasteful LLM token usage.
- **Fail-Early Preflight & Self-Healing**: Early health checks via `PreflightItem` with background silent dependency recovery.
- **Metadata-Driven UI**: `config.yaml` and `CONFIG_SCHEMA` drive dynamic UI rendering in Vue 3 + Tauri desktop apps without hardcoded frontend buttons.
- **Human-in-the-Loop Workflows**: Breakpoint pause and resumption via `Human Gate`.

## Development Rules (SOP Checklist)
1. **Never use top-level third-party imports**: All third-party libraries must be imported lazily inside class methods (SOP §4.3).
2. **Inherit StandardAgent**: Always subclass `StandardAgent` and export `setup(registry)`.
3. **Pure Config Schema**: Provide `CONFIG_SCHEMA` (JSON Schema) for settings modal auto-generation.
4. **Local-First & Zero Leakage**: Keep configs neutral (`gateway.mode: "custom"`). Never commit production IPs or private secrets.

## CLI Commands
```bash
python run.py diagnose                    # Health check and environment audit
python run.py list                        # List active agents, skills, workflows
python run.py new agent <agent_name>      # Scaffold compliant agent
python run.py new workflow <flow_name>    # Scaffold compliant workflow
python run.py new skill <skill_name>      # Scaffold compliant atomic skill (docs/AI_SKILL_DEVELOPER_SPEC.md)
python run.py run <agent> [payload]       # Dispatch batch task
python run.py chat [agent]                # Start interactive dialogue
pytest tests/ -v                          # Run comprehensive test suite
```

## AI Assistant Triggers (docs/DEVELOPER_SOP.md)
- `【研发】: <需求>`: Automatically analyzes, creates feature branch, writes code following Iron Laws, and runs unit tests.
- `【交付】`: Runs full `pytest tests/ -v` gate, commits with Conventional Commits, merges to main, pushes to GitHub, and outputs Handover Card.

