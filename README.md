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

Install `compete` as a uv tool so it's on your PATH from anywhere. Use `--editable` so edits to this repo take effect without reinstalling:

```sh
uv tool install --editable .
```

After install, make sure uv's tool bin is on your PATH (`uv tool update-shell` will set this up if it isn't).

For Kaggle competitions, also install the Kaggle CLI and configure credentials:

```sh
uv tool install kaggle
# Then drop a token at ~/.kaggle/kaggle.json
# (Kaggle → Account → API → Create New Token)
```

Configure your LLM provider in `~/.comp-agent.env` or a per-workspace `.env`:

```sh
cp .env.example .env  # or ~/.comp-agent.env
# then edit
```

**Two provider options:**

- **`api`** (default) — Uses the Anthropic API. Set `ANTHROPIC_API_KEY`. Billed per token.
- **`claude-code`** — Uses the Claude Code CLI (`claude --print`). Consumes your Claude Code subscription instead of API credits. Requires `claude` to be installed and authenticated.

Select via env var, CLI flag, or `config.yaml`:

```sh
COMPETE_PROVIDER=claude-code
# or per-command:
compete --provider claude-code run
```

## Workspaces

Each competition lives in its own directory. `compete` reads and writes files — `problem_spec.json`, `data/`, `solution/`, `tracker.db`, git history — relative to your current working directory. There is no global registry: the workspace *is* the directory you're in.

This means every `compete` command must be run from inside the workspace. Create one per competition:

```sh
mkdir -p ~/competitions/titanic && cd ~/competitions/titanic
compete init https://www.kaggle.com/competitions/titanic
```

`init` refuses to run inside the comp-agent source repo or any directory that already has a `problem_spec.json`.

## Quick start

**1. Initialize a workspace**

```sh
mkdir -p ~/competitions/titanic && cd ~/competitions/titanic

# From a Kaggle competition
compete init https://www.kaggle.com/competitions/titanic

# From a custom spec file
compete init spec.yaml --source custom

# With a time budget
compete init https://www.kaggle.com/competitions/titanic --time-budget 24
```

This parses the competition, downloads data, creates `problem_spec.json`, and initializes the tracker — all inside the current directory.

**2. Generate a baseline (or write your own)**

```sh
compete baseline
```

This asks the LLM to read `problem_spec.json`, peek at `data/`, and write a minimal `solution/train.py` that trains a simple model and produces a valid submission. `compete run` will also generate this automatically on its first invocation if the file is missing.

Solution scripts are run via `uv run --script`, so each `solution/train.py` declares its own dependencies with a [PEP 723](https://peps.python.org/pep-0723/) header:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "numpy", "scikit-learn"]
# ///
```

`uv` installs them on first run — no venv setup required. If you hand-write the script, include this header and declare every package you import. The script must:
- Read data from `data/`
- Train a model
- Print `SCORE: <number>` on its own line
- Save predictions to `submissions/submission.csv`

**3. Run the optimization loop**

```sh
# Default: generates hypotheses, waits for your approval
compete run

# Autonomous mode, 10 iterations
compete run --auto -n 10

# Force a specific phase
compete run --phase ensemble
```

**4. Check progress**

```sh
compete status
compete status --verbose
compete history --last 20
```

**5. Submit**

```sh
compete submit --validate-only  # check format first
compete submit
```

## CLI reference

All commands run from inside a workspace directory.

| Command | Description |
|---------|-------------|
| `compete init <url-or-path>` | Initialize workspace from competition URL or spec file |
| `compete baseline` | Generate `solution/train.py` from the spec (auto-runs on first `compete run`) |
| `compete run` | Run the optimization loop (approval-gated by default) |
| `compete run --auto -n 5` | Run 5 autonomous iterations |
| `compete approve <id>` | Execute a specific pending hypothesis |
| `compete status` | Show current score, run history, pending hypotheses |
| `compete history` | Show run history table |
| `compete submit` | Validate and generate final submission |

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
llm_model: "claude-opus-4-7"
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

Then: `compete init spec.yaml --source custom`

## Testing

From the comp-agent source repo:

```sh
uv run pytest
```
