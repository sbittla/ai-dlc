Kappa intervals: 95% percentile bootstrap over answers (2,000 resamples, seed 7), not Wilson.

| Judge | Split | Answers | Accuracy | Cohen's kappa (95%) | Humans' kappa | TP | FP | FN | TN | False-pass rate |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| judge-v1 | calibration | 60 | 78.3% | 0.57 (0.36 to 0.77) | 0.83 | 27 | 10 | 3 | 20 | 33.3% |
| judge-v2 | calibration | 60 | 91.7% | 0.83 (0.69 to 0.97) | 0.83 | 28 | 3 | 2 | 27 | 10.0% |
| judge-v1 | heldout | 120 | 79.2% | 0.58 (0.43 to 0.72) | 0.82 | 55 | 20 | 5 | 40 | 33.3% |
| judge-v2 | heldout | 120 | 93.3% | 0.87 (0.77 to 0.95) | 0.82 | 55 | 3 | 5 | 57 | 5.0% |
