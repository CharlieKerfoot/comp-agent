# Competition Agent — Claude Code Implementation Plan

## What This Is

A CLI agent framework that turns Claude Code into a persistent optimization loop for winning hackathons, Kaggle competitions, Jane Street puzzles, and similar scored challenges. The agent doesn't just *solve* — it *iterates toward the best score* under time and submission constraints.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    CLI Entry Point                   │
│              compete <command> [options]             │
└──────────────┬──────────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │    Problem Parser   │  ← Ingests specs, datasets, rules
    └──────────┬──────────┘
               │ ProblemSpec
    ┌──────────▼──────────┐
    │     Strategist      │  ← LLM-powered hypothesis generation
    │  (priority queue)   │     + problem classification
    └──────────┬──────────┘
               │ Hypothesis
    ┌──────────▼──────────┐
    │      Executor       │  ← Writes code, runs it, captures output
    │  (sandboxed env)    │
    └──────────┬──────────┘
               │ Result
    ┌──────────▼──────────┐
    │    Score Tracker     │  ← Lab notebook: every run logged
    │  (sqlite + markdown) │
    └──────────┬──────────┘
               │ ScoreHistory
    ┌──────────▼──────────┐
    │   Loop Controller   │  ← Time-budget-aware meta-policy
    │  (accept/reject +   │     decides: iterate, pivot, or ship
    │   strategy select)  │
    └─────────────────────┘
```

The outer loop: **Parse → Classify → Hypothesize → Execute → Score → Accept/Reject → Repeat**

---

## Module Breakdown

### Module 1: Problem Parser (`parser/`)

**Purpose:** Turn a messy competition page into a structured `ProblemSpec` that every downstream module consumes.

**Implementation with Claude Code:**
Claude Code already has web fetch and file reading. The parser is a prompt template + structured output extraction.

```
Files:
  parser/
    parse.py          # Entry point: URL or local path → ProblemSpec
    spec.py           # ProblemSpec dataclass
    extractors/
      kaggle.py       # Kaggle API + page scraping
      hackathon.py    # Generic hackathon (Devpost, etc.)
      puzzle.py       # Math puzzle extraction (Jane Street, Putnam)
      custom.py       # User-provided spec files
```

**ProblemSpec schema:**
```python
@dataclass
class ProblemSpec:
    # Identity
    name: str
    source: str                        # "kaggle" | "hackathon" | "puzzle" | "custom"
    url: str | None

    # Objective
    problem_type: str                  # "classification" | "regression" | "optimization"
                                       # | "combinatorial" | "mathematical" | "systems"
    objective_description: str         # Natural language
    metric: str                        # "RMSE" | "AUC" | "F1" | "custom_score" | etc.
    metric_direction: str              # "minimize" | "maximize"

    # Constraints
    time_limit: datetime | None        # Competition deadline
    submission_limit: int | None       # Max submissions per day
    compute_constraints: str | None    # GPU limits, runtime caps
    rules: list[str]                   # No external data, team size, etc.

    # Data
    data_paths: list[str]              # Local paths to downloaded data
    data_description: str              # Column meanings, relationships
    target_column: str | None          # For tabular ML
    submission_format: str             # Expected output format

    # Evaluation
    eval_script: str | None            # Local evaluation if available
    public_leaderboard: bool
```

**Claude Code task:**
> "Read the competition page at {url}. Download all data files to `data/`. Parse the rules, evaluation metric, submission format, and constraints. Output a ProblemSpec JSON to `problem_spec.json`. If anything is ambiguous, list your assumptions."

---

### Module 2: Strategist (`strategist/`)

**Purpose:** Given a ProblemSpec and the current ScoreHistory, generate a ranked list of hypotheses to try next. This is the brain.

```
Files:
  strategist/
    classify.py       # Problem → strategy family (see taxonomy below)
    hypothesize.py    # Generate next hypotheses given history
    prioritize.py     # Rank by (expected_improvement, cost, risk)
    critique.py       # Red-team current best solution
    playbooks/        # Pre-built strategy templates per problem type
      tabular_ml.md
      computer_vision.md
      nlp.md
      combinatorial.md
      math_puzzle.md
      systems_design.md
```

**Problem taxonomy → Strategy families:**

| Problem Type | Initial Strategy | Mid-game | Endgame |
|---|---|---|---|
| Tabular ML | EDA → baseline XGBoost → feature eng | Stacking, target encoding, NNs | Ensemble top-K, tune thresholds |
| CV | Pretrained ResNet/ViT baseline | Architecture search, augmentation | TTA, ensemble, pseudo-labeling |
| NLP | Fine-tune transformer baseline | Data aug, prompt engineering | Ensemble, post-processing |
| Combinatorial | Greedy/DP baseline → local search | Simulated annealing, genetic alg | Parameter tuning, hybrid |
| Math Puzzle | Brute force small cases → pattern | Prove structure, reduce search | Optimize implementation |
| Systems/Hackathon | MVP → core metric | Feature completeness | Polish, demo prep |

**Hypothesis schema:**
```python
@dataclass
class Hypothesis:
    id: str
    description: str                   # "Add target-encoded categorical features"
    rationale: str                     # Why this should improve score
    expected_improvement: float        # Estimated delta (can be rough)
    estimated_time_minutes: int        # How long to implement + test
    risk: str                          # "low" | "medium" | "high"
    dependencies: list[str]            # Hypothesis IDs this builds on
    strategy_phase: str                # "baseline" | "improve" | "ensemble" | "polish"
    code_sketch: str                   # Pseudocode or key changes
```

**Claude Code task (hypothesis generation):**
> "Here is the ProblemSpec: {spec}. Here is the score history: {history}. The current best score is {best} achieved by approach {approach}. Time remaining: {hours}h. Generate 3-5 hypotheses for improvement, ranked by expected improvement / time cost. For each, provide a concrete code sketch. Be specific — 'try feature engineering' is not a hypothesis; 'compute rolling 7-day mean of column X grouped by user_id' is."

**Claude Code task (critique):**
> "Here is the current best solution code: {code}. Score: {score}. Problem: {spec}. Act as a competition grandmaster reviewing this. What are the 3 biggest weaknesses? What would the winning solution likely do differently? Be concrete and adversarial."

---

### Module 3: Executor (`executor/`)

**Purpose:** Take a Hypothesis, implement it, run it, and return a Result. This is where Claude Code's native capability is most directly useful.

```
Files:
  executor/
    implement.py      # Hypothesis → code changes
    runner.py         # Execute in sandboxed env, capture output
    validate.py       # Check submission format before scoring
    snapshot.py       # Git commit each attempt for rollback
```

**Execution flow:**
1. `git checkout -b hypothesis/{id}` from current best
2. Claude Code implements the hypothesis (writes/modifies code)
3. Run training/solving script
4. Validate output format matches submission spec
5. Score locally (if eval script available) or flag for manual submission
6. Capture: stdout, stderr, runtime, memory usage, score
7. `git add -A && git commit` with structured message

**Claude Code task:**
> "You are on branch `hypothesis/{id}`. Implement this change: {hypothesis.code_sketch}. The current codebase is in `solution/`. Run `python solution/train.py` and report the validation score. If it errors, fix the error and retry up to 3 times. Do not change the submission format."

**Key design decision:** Each hypothesis runs on its own git branch. This gives you:
- Free rollback to any previous state
- Diff visibility (what actually changed per hypothesis)
- Ability to cherry-pick successful changes across branches
- A complete audit trail

---

### Module 4: Score Tracker (`tracker/`)

**Purpose:** Persistent memory across all iterations. The lab notebook.

```
Files:
  tracker/
    db.py             # SQLite storage
    log.py            # Markdown report generation
    compare.py        # Score comparison + regression detection
```

**Schema:**
```sql
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    hypothesis_id TEXT,
    timestamp DATETIME,
    branch TEXT,
    score REAL,
    metric TEXT,
    runtime_seconds REAL,
    memory_mb REAL,
    status TEXT,          -- "success" | "error" | "timeout"
    error_message TEXT,
    code_diff TEXT,       -- git diff from parent
    notes TEXT
);

CREATE TABLE hypotheses (
    id TEXT PRIMARY KEY,
    description TEXT,
    rationale TEXT,
    status TEXT,          -- "pending" | "running" | "accepted" | "rejected" | "error"
    parent_run_id TEXT,
    result_run_id TEXT
);
```

**Auto-generated lab report** (`tracker/report.md`), refreshed after each run:
```markdown
# Competition: {name}
## Best Score: {score} (run {id}, branch {branch})
## Runs: {total} | Accepted: {accepted} | Rejected: {rejected}

### Score Progression
{ascii chart or reference to plot}

### What Worked
- {hypothesis}: {old_score} → {new_score} (+{delta})

### What Didn't Work
- {hypothesis}: {old_score} → {new_score} ({delta})

### Pending Hypotheses
1. {description} (est. +{expected}, ~{minutes}min)
```

---

### Module 5: Loop Controller (`controller/`)

**Purpose:** The meta-policy. Decides what to do next based on score trajectory, time budget, and strategy phase.

```
Files:
  controller/
    loop.py           # Main optimization loop
    policy.py         # Time-aware strategy selection
    budget.py         # Time tracking + estimation
```

**State machine:**
```
INIT → PARSE → BASELINE → IMPROVE → ENSEMBLE → POLISH → SUBMIT
                   ↑          |
                   └──────────┘  (if score regresses or new direction needed)
```

**Time-budget policy:**
```python
def select_phase(time_remaining_hours: float, score_history: list) -> str:
    if not score_history:
        return "baseline"                          # No score yet

    improvement_rate = compute_improvement_rate(score_history, window=5)

    if time_remaining_hours > 24:
        if improvement_rate < threshold:
            return "pivot"                         # Diminishing returns, try new direction
        return "improve"                           # Still gaining, keep pushing
    elif time_remaining_hours > 6:
        return "ensemble"                          # Lock in gains, combine approaches
    elif time_remaining_hours > 2:
        return "polish"                            # Hyperparameter tuning, post-processing
    else:
        return "submit"                            # Ship what you have
```

**The main loop (what Claude Code actually runs):**
```python
def competition_loop(spec: ProblemSpec):
    tracker = ScoreTracker(spec.name)
    time_budget = TimeBudget(spec.time_limit)

    while not time_budget.expired():
        phase = select_phase(time_budget.remaining_hours(), tracker.history())

        if phase == "submit":
            finalize_submission(tracker.best_run())
            break

        # Generate hypotheses conditioned on phase
        hypotheses = strategist.generate(
            spec=spec,
            history=tracker.history(),
            phase=phase,
            time_budget=time_budget.remaining_hours()
        )

        # Execute top hypothesis
        best_hypothesis = hypotheses[0]
        tracker.log_hypothesis(best_hypothesis)

        result = executor.run(best_hypothesis, spec)
        tracker.log_run(result)

        if result.score_improved(tracker.best_score()):
            tracker.accept(result)
            executor.merge_to_main(result.branch)
        else:
            tracker.reject(result)

        # Periodic critique every N runs
        if tracker.total_runs() % 5 == 0:
            critique = strategist.critique(tracker.best_code(), spec)
            tracker.log_critique(critique)

        tracker.refresh_report()
```

---

## Claude Code Session Structure

The agent runs as a series of Claude Code commands. Here's how a session looks:

### Phase 0: Setup
```bash
# Human runs:
claude-code "Initialize a competition workspace for {url}. 
Parse the problem, download data, create the ProblemSpec, 
set up the git repo with the tracker database, 
and generate a baseline strategy."
```

### Phase 1: Baseline
```bash
claude-code "Read problem_spec.json. Implement the simplest 
possible baseline that produces a valid submission. 
Run it, score it, log to tracker. 
This should take <15 minutes of compute."
```

### Phase 2: Iteration Loop
```bash
claude-code "Read the tracker report and problem spec. 
We're in the IMPROVE phase with {X} hours remaining. 
Generate 3 hypotheses, implement the best one, 
run it, log the result. If it improves, merge to main. 
Then generate the next set of hypotheses and repeat. 
Continue for up to 5 iterations or until I interrupt."
```

### Phase 3: Ensemble/Polish
```bash
claude-code "Read the tracker. We have {N} accepted approaches 
on separate branches. Build an ensemble combining the top 3. 
Score it. Then do a final hyperparameter sweep on the ensemble 
weights. Log everything."
```

### Phase 4: Ship
```bash
claude-code "Generate the final submission from the best run. 
Validate format. Write a summary of the approach to APPROACH.md. 
List what we tried, what worked, what didn't."
```

---

## Directory Structure

```
competition-agent/
├── compete.py                # CLI entry point
├── problem_spec.json         # Generated by parser
├── config.yaml               # Time budget, submission limits, etc.
│
├── parser/
│   ├── parse.py
│   ├── spec.py
│   └── extractors/
│       ├── kaggle.py
│       ├── hackathon.py
│       ├── puzzle.py
│       └── custom.py
│
├── strategist/
│   ├── classify.py
│   ├── hypothesize.py
│   ├── prioritize.py
│   ├── critique.py
│   └── playbooks/
│       ├── tabular_ml.md
│       ├── cv.md
│       ├── nlp.md
│       ├── combinatorial.md
│       ├── math_puzzle.md
│       └── systems.md
│
├── executor/
│   ├── implement.py
│   ├── runner.py
│   ├── validate.py
│   └── snapshot.py
│
├── tracker/
│   ├── db.py
│   ├── log.py
│   ├── compare.py
│   └── report.md             # Auto-generated
│
├── controller/
│   ├── loop.py
│   ├── policy.py
│   └── budget.py
│
├── solution/                 # The actual competition code (git-tracked)
│   ├── train.py
│   ├── predict.py
│   ├── features/
│   └── models/
│
├── data/                     # Downloaded competition data
├── submissions/              # Generated submissions
└── .git/                     # Every hypothesis = a branch
```

---

## Build Order (for Claude Code sessions)

### Sprint 1: Scaffold + Tracker (Day 1, ~3 hours)
1. Project init: directory structure, git, virtualenv
2. `ProblemSpec` dataclass + JSON serialization
3. `Hypothesis` and `Run` dataclasses
4. SQLite tracker: create tables, insert/query runs
5. Markdown report generator
6. **Test:** manually insert fake runs, verify report renders

### Sprint 2: Executor (Day 1-2, ~4 hours)
1. Git branch management: create, switch, merge, diff
2. Code runner: subprocess with timeout, stdout/stderr capture
3. Output validator: check submission format against spec
4. Snapshot: auto-commit after each run
5. **Test:** run a trivial Python script, log result to tracker

### Sprint 3: Parser (Day 2, ~3 hours)
1. Kaggle extractor: API for competition metadata + data download
2. Generic extractor: given a URL, use Claude to extract spec fields
3. Custom spec: load from user-provided YAML
4. **Test:** parse a real Kaggle competition end-to-end

### Sprint 4: Strategist (Day 2-3, ~4 hours)
1. Problem classifier: spec → problem type + strategy family
2. Hypothesis generator: prompt templates per problem type
3. Prioritizer: rank by expected improvement / time cost
4. Critique module: adversarial review of current best
5. Playbook loading: inject relevant playbook into prompts
6. **Test:** generate hypotheses for a real Kaggle competition

### Sprint 5: Controller + Loop (Day 3, ~3 hours)
1. Time budget tracker
2. Phase selection policy
3. Main loop: wire everything together
4. CLI entry point with commands: `init`, `run`, `status`, `submit`
5. **Test:** run the full loop on a closed Kaggle competition

### Sprint 6: Playbooks + Polish (Day 3-4, ~3 hours)
1. Write detailed playbooks for each problem type
2. Add ensemble scaffolding
3. Kaggle submission helper (API upload)
4. Error recovery: retry logic, graceful degradation
5. **Test:** end-to-end on 2-3 different competition types

**Total estimate: ~20 hours of focused work, or 4 days at ~5hrs/day.**

---

## What Makes This Different From a Standard Agent

| Dimension | Standard Agent | Competition Agent |
|---|---|---|
| **Loop structure** | Plan → Execute → Done | Parse → Hypothesize → Execute → Score → Accept/Reject → Repeat |
| **Memory** | Conversation context | Persistent SQLite + git history across sessions |
| **Objective** | Task completion | Score maximization under constraints |
| **Strategy** | Single approach | Portfolio of approaches, phase-dependent selection |
| **Self-evaluation** | "Did it work?" | "By how much? Is the trend improving? Should I pivot?" |
| **Time awareness** | None | Time-budget-conditioned strategy selection |
| **Rollback** | Undo last action | Git branches per hypothesis, cherry-pick winners |
| **Self-critique** | None | Periodic adversarial review of best solution |

---

## Open Design Questions

1. **How autonomous should the loop be?** Fully autonomous risks burning submission limits or going down a dead-end path for hours. Recommended: human approves each hypothesis before execution, but the agent generates and ranks them. Progressively loosen as trust builds.

2. **Where does the LLM boundary live?** The strategist is pure LLM. The executor mixes LLM (code generation) with deterministic tooling (running, scoring). The tracker and controller are pure code. Keep this boundary clean.

3. **How to handle competitions with no local eval?** Many Kaggle competitions only score via submission. The agent needs a local proxy metric (cross-validation) and should flag when local and leaderboard scores diverge.

4. **Multi-model support?** For ML competitions, the executor needs to support arbitrary frameworks (sklearn, XGBoost, PyTorch, etc.). The playbooks should specify which tools to reach for, but the executor shouldn't be framework-specific.

5. **How to handle the "novel insight" problem?** The LLM will plateau at known strategies. Build in explicit "stuck" detection: if the last 5 hypotheses all failed, surface a prompt to the human asking for a new direction rather than generating another incremental tweak.
