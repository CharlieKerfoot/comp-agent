from __future__ import annotations

from comp_agent.models import ProblemSpec

# Problem type -> strategy family mapping
STRATEGY_FAMILIES = {
    "classification": "tabular_ml",
    "regression": "tabular_ml",
    "optimization": "combinatorial",
    "combinatorial": "combinatorial",
    "mathematical": "math_puzzle",
    "systems": "systems",
}

# Strategy phases per family
PHASE_STRATEGIES = {
    "tabular_ml": {
        "baseline": [
            "Build EDA notebook to understand data distributions",
            "Train baseline XGBoost with default parameters",
            "Implement k-fold cross-validation pipeline",
        ],
        "improve": [
            "Feature engineering: interaction terms, aggregations, encodings",
            "Try gradient boosting variants: LightGBM, CatBoost",
            "Target encoding for high-cardinality categoricals",
            "Neural network approach with tabular embeddings",
        ],
        "ensemble": [
            "Stack top 3 models with a meta-learner",
            "Blend predictions with optimized weights",
            "Out-of-fold predictions for stacking",
        ],
        "polish": [
            "Hyperparameter tuning with Optuna",
            "Threshold optimization for classification",
            "Post-processing rules based on domain knowledge",
        ],
    },
    "combinatorial": {
        "baseline": [
            "Implement greedy solution",
            "Try dynamic programming if structure allows",
            "Brute force small cases to understand patterns",
        ],
        "improve": [
            "Local search with neighborhood operators",
            "Simulated annealing",
            "Genetic algorithm approach",
            "Constraint programming formulation",
        ],
        "ensemble": [
            "Run multiple algorithms, take best per-instance",
            "Combine solutions from different approaches",
        ],
        "polish": [
            "Parameter tuning for metaheuristics",
            "Hybrid: exact methods on subproblems",
            "Implementation optimization for speed",
        ],
    },
    "math_puzzle": {
        "baseline": [
            "Brute force small cases to find patterns",
            "Formalize the problem mathematically",
            "Implement exhaustive search for small inputs",
        ],
        "improve": [
            "Prove structural properties to reduce search space",
            "Dynamic programming or memoization",
            "Mathematical insight: symmetry, invariants",
        ],
        "ensemble": [
            "Cross-validate approaches on different input sizes",
        ],
        "polish": [
            "Optimize implementation for speed",
            "Verify edge cases",
        ],
    },
    "systems": {
        "baseline": [
            "Build minimum viable prototype",
            "Implement core scoring metric first",
        ],
        "improve": [
            "Add features from judging criteria",
            "Improve UX and presentation",
            "Performance optimization",
        ],
        "ensemble": [
            "Combine best features from different approaches",
        ],
        "polish": [
            "Demo preparation",
            "Documentation and README",
            "Edge case handling",
        ],
    },
}


def classify_problem(spec: ProblemSpec) -> str:
    return STRATEGY_FAMILIES.get(spec.problem_type, "tabular_ml")


def get_phase_strategies(family: str, phase: str) -> list[str]:
    family_strategies = PHASE_STRATEGIES.get(family, PHASE_STRATEGIES["tabular_ml"])
    return family_strategies.get(phase, family_strategies.get("improve", []))
