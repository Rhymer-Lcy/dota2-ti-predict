# Side-aware evaluation (orientation confound removed)

Train-only radiant coefficient: Elo mean c=+0.089, B-bt mean c=+0.088. Temperature form q=sigmoid(b*logit(p)); b<1 softens.

| variant | log-loss | Brier | intercept a | slope b | ECE |
|---------|-----:|-----:|-----:|-----:|-----:|
| A-elo side-aware | 0.6547 | 0.2310 | +0.422 | 0.486 | 0.0983 |
| B-bt side-aware | 0.6444 | 0.2262 | +0.349 | 0.690 | 0.0933 |
| B-bt side-aware + OOS temp | 0.6500 | 0.2287 | +0.402 | 0.544 | 0.0876 |
| B-bt side-neutral (production) | 0.6518 | 0.2298 | +0.403 | 0.698 | 0.0972 |

**B-bt beats A-elo (side-aware) in 17/23 folds** on log-loss (pooled 0.6444 vs 0.6547).
Production temperature (all-OOF fit) b=1.1188 (sharpens).

## Decision
- Symmetric temperature improves OOS log-loss AND ECE over side-aware B-bt: **False**.
- => **production = identity** (freeze at identity side-neutral B-bt; no calibration layer).
- Ranking unaffected; B-bt remains the primary candidate.
