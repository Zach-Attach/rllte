# Performance Comparison of Multiple Algorithms

## Download Data
Suppose we want to evaluate algorithm performance on the [Procgen](https://github.com/openai/procgen) benchmark. First, download the data from 
[rllte-hub](https://hub.rllte.dev/):
``` py title="example.py"
# load packages
from rllte.evaluation import Performance, Comparison, min_max_normalize
from rllte.evaluation import *
from rllte.hub.datasets import Procgen, Atari
import numpy as np
# load scores
procgen = Procgen()
procgen_scores = procgen.load_scores()
print(procgen_scores.keys())
# PPO-Normalized scores
ppo_norm_scores = dict()
MIN_SCORES = np.zeros_like(procgen_scores['PPO'])
MAX_SCORES = np.mean(procgen_scores['PPO'], axis=0)
for algo in procgen_scores.keys():
    ppo_norm_scores[algo] = min_max_normalize(procgen_scores[algo],
                                              min_scores=MIN_SCORES,
                                              max_scores=MAX_SCORES)

# Output:
# dict_keys(['PPG', 'MixReg', 'PPO', 'IDAAC', 'PLR', 'UCB-DrAC'])
```
For each algorithm, this will return a `NdArray` of size (`10` x `16`) where scores[n][m] represent the score on run `n` of task `m`.

## Performance Comparison
`Comparison` module allows you to compare the performance between two algorithms:
``` py title="example.py"
comp = Comparison(scores_x=ppo_norm_scores['PPG'],
                  scores_y=ppo_norm_scores['PPO'],
                  get_ci=True)
comp.compute_poi()

# Output:
# Computing confidence interval for PoI...
# (0.8153125, array([[0.779375  ], [0.85000781]]))
```
This indicates the overall probability of imporvement of `PPG` over `PPO` is `0.8153125`.

Available metrics:

|Metric|Remark|
|:-|:-|
|`.compute_poi`|Compute the overall probability of imporvement of algorithm `X` over `Y`.|