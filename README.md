# comp-agent

A CLI framework that turns Claude Code into a persistent optimization loop for competitions. Instead of solving a problem once, it iterates toward the best score under time and submission constraints.

Works with Kaggle competitions, hackathons, Jane Street puzzles, and custom problem specs.

## How it works

```
Parse → Classify → Hypothesize → Execute → Score → Accept/Reject → Repeat
```

Each hypothesis runs on its own git branch. Accepted improvements merge to main. Rejected branches are preserved for reference. A SQLite tracker logs every run, and a markdown report updates automatically.

The loop is time-budget-aware: it spends early time exploring approaches, then shifts to ensembling, polishing, and finally submitting as the deadline approaches.

## Install

```sh
uv sync
```

Copy `.env.example` to `.env` and configure your LLM provider:

```sh
cp .env.example .env
# then edit .env
```

**Two provider options:**

- **`api`** (default) — Uses the Anthropic API. Set `ANTHROPIC_API_KEY` in `.env`. Billed per token.
- **`claude-code`** — Uses the Claude Code CLI (`claude --print`). Consumes your Claude Code subscription instead of API credits. Requires `claude` to be installed and authenticated.

Select via env var, CLI flag, or `config.yaml`:

```sh
# Env var (from .env)
COMPETE_PROVIDER=claude-code

# Or per-command CLI flag
uv run compete --provider claude-code run
```

## Running commands

The `compete` CLI is installed into the project's uv-managed virtualenv, not on your global PATH. Always invoke it via `uv run`:

```sh
uv run compete <command> [options]
```

All examples below use this form.

## Quick start

**1. Initialize a workspace**

```sh
# From a Kaggle competition
uv run compete init https://www.kaggle.com/competitions/titanic

# From a custom spec file
uv run compete init spec.yaml --source custom

# With a time budget
uv run compete init https://www.kaggle.com/competitions/titanic --time-budget 24
```

This parses the competition, downloads data, creates `problem_spec.json`, and initializes the tracker.

**2. Write a baseline**

Create `solution/train.py` that:
- Reads data from `data/`
- Trains a model
- Prints `SCORE: <number>` to stdout
- Saves predictions to `submissions/submission.csv`

**3. Run the optimization loop**

```sh
# Default: generates hypotheses, waits for your approval
uv run compete run

# Autonomous mode, 10 iterations
uv run compete run --auto -n 10

# Force a specific phase
uv run compete run --phase ensemble
```

**4. Check progress**

```sh
uv run compete status
uv run compete status --verbose
uv run compete history --last 20
```

**5. Submit**

```sh
uv run compete submit --validate-only  # check format first
uv run compete submit
```

## CLI reference

| Command | Description |
|---------|-------------|
| `uv run compete init <url-or-path>` | Initialize workspace from competition URL or spec file |
| `uv run compete run` | Run the optimization loop (approval-gated by default) |
| `uv run compete run --auto -n 5` | Run 5 autonomous iterations |
| `uv run compete approve <id>` | Execute a specific pending hypothesis |
| `uv run compete status` | Show current score, run history, pending hypotheses |
| `uv run compete history` | Show run history table |
| `uv run compete submit` | Validate and generate final submission |

## Architecture

```
comp_agent/
├── models/          # ProblemSpec, Hypothesis, Result dataclasses
├── parser/          # Extract specs from Kaggle, hackathons, puzzles, YAML
├── strategist/      # LLM-powered hypothesis generation + critique
│   └── playbooks/   # Strategy guides per problem type
├── executor/        # Git branches, code runner, validator, ensemble builder
├── tracker/         # SQLite storage + markdown report generator
├── controller/      # Time-budget policy, phase selection, main loop
└── cli.py           # Click CLI entry point
```

**Module boundaries:**
- **Strategist** — pure LLM. Generates and critiques hypotheses.
- **Executor** — mixed. Uses LLM for code generation, deterministic tooling for running/scoring.
- **Tracker + Controller** — pure code. No LLM calls.
- **LLM layer** (`comp_agent/llm.py`) — Thin provider abstraction. Routes all calls to either the Anthropic SDK or the Claude Code CLI.

## Configuration

Edit `config.yaml`:

```yaml
llm_provider: "api"              # "api" | "claude-code"
llm_model: "claude-sonnet-4-20250514"
time_budget_hours: 48
submission_limit_per_day: 5
reserved_submissions_per_day: 1
execution_timeout_seconds: 1800
max_consecutive_failures: 5
critique_interval: 5
autonomy_mode: "approval"        # "approval" | "auto"
```

## Phase selection

The controller automatically selects a strategy phase based on remaining time:

| Time remaining | Phase | Behavior |
|---------------|-------|----------|
| No runs yet | `baseline` | Build simplest valid submission |
| > 24 hours | `improve` | Feature engineering, model experiments |
| 6–24 hours | `ensemble` | Combine top approaches |
| 2–6 hours | `polish` | Hyperparameter tuning, post-processing |
| < 2 hours | `submit` | Finalize and ship |

If the last 5 hypotheses all fail, the controller enters `pivot` mode and flags for human input.

## Custom problem specs

Create a YAML file:

```yaml
name: my-competition
source: custom
problem_type: regression
metric: rmse
metric_direction: minimize
target_column: price
submission_format: "csv with id and price columns"
data_paths:
  - data/train.csv
  - data/test.csv
rules:
  - no external data
```

Then: `uv run compete init spec.yaml --source custom`

## Testing

```sh
uv run pytest
```
