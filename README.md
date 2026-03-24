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

Requires an `ANTHROPIC_API_KEY` environment variable for hypothesis generation and critique.

## Quick start

**1. Initialize a workspace**

```sh
# From a Kaggle competition
compete init https://www.kaggle.com/competitions/titanic

# From a custom spec file
compete init spec.yaml --source custom

# With a time budget
compete init https://www.kaggle.com/competitions/titanic --time-budget 24
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

| Command | Description |
|---------|-------------|
| `compete init <url-or-path>` | Initialize workspace from competition URL or spec file |
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
- **Strategist** — pure LLM (Anthropic SDK). Generates and critiques hypotheses.
- **Executor** — mixed. Uses LLM for code generation, deterministic tooling for running/scoring.
- **Tracker + Controller** — pure code. No LLM calls.

## Configuration

Edit `config.yaml`:

```yaml
time_budget_hours: 48
submission_limit_per_day: 5
reserved_submissions_per_day: 1
execution_timeout_seconds: 1800
max_consecutive_failures: 5
critique_interval: 5
autonomy_mode: "approval"  # "approval" | "auto"
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

```sh
uv run pytest
```
