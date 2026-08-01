# AUTHORITATIVE PROJECT CHECKPOINT (frozen)

Preserved before compaction. Do NOT reinterpret, reopen, or silently modify any frozen decision.
On restoration after a compact, restate this briefly and WAIT for the client screenshots; do not
resume modeling work unprompted.

## PROJECT
TI2026 prediction repository. Git history and committed documents are the source of truth. Continue
to obey the commit-message hook: subject <=72 characters and ASCII only.

## DATA / B0 -- CLOSED
- Team identity and roster coverage have been audited and repaired.
- Modeling is roster-centric, not based on a single OpenDota team_id.
- One organization or roster may span multiple source_team_ids.
- Tundra -> 1w, Xtreme, Resilience, PARIVISION and other ID splits have been resolved.
- Training data and canonical identity artifacts are reproducible and committed.
- Do not reopen B0 unless new client inputs expose a concrete contradiction.

## MODELING TRACK -- PARKED, FINAL
- Selected rating model: B-bt.
- B-bt beat A-elo in 17/23 event-frozen rolling folds.
- Reconfirmed by weighting sensitivity, LOEO robustness and side-aware evaluation.
- Production model: identity side-neutral B-bt.
- No Platt or temperature calibration layer is enabled.
- Symmetry-preserving rolling-OOF temperature scaling was tested and rejected.
- Identity is only the best validated production choice among the frozen candidates, not universally
  or theoretically optimal.
- Production-aligned historical metrics: log-loss 0.6518; Brier 0.2298; symmetric-binning ECE 0.0384.
- ECE is auxiliary; log-loss and Brier remain primary.
- 0.6444 is a side-aware diagnostic using actual sides and must not be presented as production
  performance.
- Frozen means the pipeline specification is frozen, not the final TI2026 numerical probabilities.
- No further model selection, parameter search, calibration work or probability output may run
  before client inputs arrive.

## MARKET STATUS
- Historical market-validation gate remains unresolved / not cleared.
- Current client crowd pick percentages cannot clear that gate.
- Crowd share is not a probability, bookmaker odds or calibration input.
- Do not fit a fusion alpha from a current screenshot.
- True bookmaker odds, if later supplied, must be clearly distinguished from crowd pick share and
  official prediction probabilities.

## SIMULATOR
- Mechanics are implemented and internally validated.
- Before any formal tournament output, verify the official TI2026 rules: Swiss pairing rules;
  repeat-match restrictions; special-elimination pairings; main-event seeding; bracket format and
  Bo3/Bo5 rules.
- Do not emit formal advancement or championship probabilities before this rules verification.

## CLIENT INPUTS STILL REQUIRED
Priority input is screenshots from the Dota 2 client, not offshore bookmaker screenshots. Request
complete screenshots showing: (1) every prediction question; (2) all answer options; (3) points or
scoring rules; (4) crowd pick percentages, if displayed; (5) reward tiers and score thresholds;
(6) prediction lock time or countdown.

Classify screenshots field by field as: crowd pick percentage; official prediction probability; true
bookmaker odds; points/reward information; question/option text.

## NEXT EXECUTION ORDER
1. Receive and classify the client screenshots.
2. Extract all questions, options, points, crowd shares, reward thresholds and cutoff times.
3. Verify official tournament rules.
4. At the actual prediction cutoff, refit the frozen B-bt model using all eligible pre-cutoff data.
5. Produce side-neutral model-only probabilities with no calibration layer.
6. Keep model probability and crowd share separate.
7. Use crowd share only in the contest expected-points decision layer.
8. Clearly label outputs as not historically market-validated.
9. Save machine-readable JSON as the fact source and render a human-readable Markdown table.
