# Side-aware evaluation (orientation confound removed)

Train-only radiant coefficient: Elo mean c=+0.089, B-bt mean c=+0.088. Temperature form q=sigmoid(b*logit(p)); b<1 softens.

| variant | log-loss | Brier | intercept a | slope b | ECE |
|---------|-----:|-----:|-----:|-----:|-----:|
| A-elo side-aware | 0.6547 | 0.2310 | +0.422 | 0.486 | 0.0983 |
| B-bt side-aware | 0.6444 | 0.2262 | +0.349 | 0.690 | 0.0933 |
| B-bt side-aware + OOS temp | 0.6500 | 0.2287 | +0.402 | 0.544 | 0.0876 |
| B-bt side-neutral (production) | 0.6518 | 0.2298 | +0.403 | 0.698 | 0.0972 |

**B-bt beats A-elo in 17/23 folds** (side-aware diagnostic, pooled 0.6444 vs 0.6547).

## Two scores, reported separately
- **side-aware DIAGNOSTIC** (actual side known): B-bt log-loss **0.6444**.
- **production-aligned side-neutral** (side unknown, what ships): B-bt log-loss **0.6518**.

## Production-aligned symmetric OOF temperature test (conclusive)
Each OOF side-neutral obs + its (B,A,1-y,1-p) mirror, half weight; zero-intercept temperature fit strictly on prior folds. Removes team-a base-rate confounding.

| symmetric OOF | log-loss | Brier | ECE |
|---|--:|--:|--:|
| identity (b=1) | 0.6518 | 0.2298 | 0.0384 |
| rolling temperature | 0.6573 | 0.2324 | 0.0490 |

## Decision
- symmetric temperature improves OOS (log-loss AND ECE): **False**.
- => **production = identity_side_neutral_bbt** -- identity CONCLUSIVELY frozen (symmetric test failed).
- c=+0.088 rules out radiant-side ADVANTAGE as the main cause of the +0.4 intercept, but
  NOT all orientation effects; team-a ordering / evaluation base-rate remain unresolved.
- Ranking unaffected; B-bt stays the selected rating model.
