# Combinatorial Optimization Playbook

## Baseline Phase
1. **Greedy construction**: Build solution element by element
2. **Dynamic programming**: If optimal substructure exists
3. **Random sampling**: Generate many random solutions, keep best

## Improve Phase
1. **Local search**: Define neighborhood operators, hill-climb
2. **Simulated annealing**: Good for escaping local optima
3. **Genetic algorithm**: For diverse population of solutions
4. **Problem-specific insights**: Exploit mathematical structure

## Ensemble Phase
1. **Multi-start**: Run best algorithm from different starting points
2. **Algorithm portfolio**: Run multiple algorithms, take best result
3. **Hybrid**: Use exact methods on subproblems

## Polish Phase
1. **Parameter tuning**: Cooling schedule, population size, etc.
2. **Implementation speed**: Profile and optimize hot loops
3. **Time management**: Use all available compute time
