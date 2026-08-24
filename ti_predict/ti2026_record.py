"""The authored half of the TI2026 closure record: incidents, limits, lessons, 2027 actions.

Everything here is written by hand and reviewed. It is kept out of `postmortem.py` on purpose:
that module computes, this one remembers. The computed evaluation and this record are merged into
predictions/ti2026/postmortem/ti2026_postmortem.json.

The incident list includes mistakes that were caught and corrected. That is the point of it. A
postmortem that lists only what went right is a brochure, and a future session cannot tell from a
brochure which of its own instincts to distrust.
"""

# Each incident: what was seen, why it happened, whether a submitted decision depended on it, what
# was done, and - the field that actually pays for itself - the check that would catch it next time.
INCIDENTS = [
    {
        "id": "INC-01",
        "title": "opening bracket seating had no authoritative local provenance",
        "symptom": "the four seeded Main Event pairings entered the model as facts supplied in a "
                   "request, with nothing in the repository able to confirm them",
        "root_cause": "the saved Valve league feed carries the Playoff graph but every Playoff node "
                      "in that snapshot has team_id_1 = team_id_2 = 0, so the feed structurally "
                      "cannot answer who is seated where",
        "load_bearing": True,
        "impact_on_submitted_decision": "none on the numbers - the pairings were correct - but the "
                                        "claim rested on an unverifiable input, which is a "
                                        "provenance defect whether or not the input is right",
        "fix": "archive a first-party client capture, hash it, transcribe it under review, and "
               "derive ti15_results.UBQF from that single transcription so no second seat table "
               "can drift from it",
        "prevention_ti2027": "capture and hash the client bracket the day seating is published, "
                             "before it is needed",
        "check": "ti_predict/seating_evidence.py aborts the run on any hash, byte-count, directory "
                 "or seat mismatch; tests/test_seating_evidence.py pins it",
    },
    {
        "id": "INC-02",
        "title": "first-party client evidence closed the seating gap, and the two sources stayed separate",
        "symptom": "not a defect: recorded because the resolution is the reusable part",
        "root_cause": "n/a",
        "load_bearing": True,
        "impact_on_submitted_decision": "none; the slate was unchanged by the archival",
        "fix": "the capture establishes WHO is seated; the Valve feed independently establishes the "
               "14-node graph and the winner/loser edges. Two questions, two artifacts, no "
               "circularity - and the eight seated organisations must equal the eight survivors "
               "reconstructed from the 44 completed series, which is a real independent check",
        "prevention_ti2027": "keep seating evidence and topology evidence as separate artifacts "
                             "with separate gates",
        "check": "the seating gate plus ti15_results.verify_standings()",
    },
    {
        "id": "INC-03",
        "title": "most current-event timestamps were imputed, not observed",
        "symptom": "only round 1 of the Swiss had a real scheduled_time; rounds 2-6 and the "
                   "Elimination Round were placed on an assumed two-blocks-per-day cadence",
        "root_cause": "no local source recorded actual start times for those series",
        "load_bearing": True,
        "impact_on_submitted_decision": "bounded and reported, not waved away: collapsing every "
                                        "TI15 map onto a single instant moves the block's h90 "
                                        "weight by under 3%, leaves the optimal slate unchanged, "
                                        "and is filed as a sensitivity arm",
        "fix": "label the two provenances separately (official_schedule_feed vs imputed_cadence), "
               "count them in the manifest, and run the collapse arm",
        "prevention_ti2027": "capture an authoritative actual start time for every series as it is "
                             "played; the post-event archive built here shows it is obtainable",
        "check": "the manifest's timestamp_provenance_counts, plus the timestamp sensitivity gate",
    },
    {
        "id": "INC-04",
        "title": "synthetic result rows contaminated the radiant-side coefficient",
        "symptom": "the estimated side coefficient c came out inflated at 0.1056",
        "root_cause": "the 44 TI15 series were expanded with team_a = series winner, a bookkeeping "
                      "orientation with no side meaning. 88 of 109 rows therefore had team_a "
                      "winning by construction, and the side estimator read that as a Radiant "
                      "advantage",
        "load_bearing": True,
        "impact_on_submitted_decision": "c corrected from 0.1056 to 0.0940. Zero change to any "
                                        "strength, zero change to the 14-slot slate - a real bug "
                                        "whose numerical effect happened to be nil",
        "fix": "mark every row with explicit side provenance at construction "
               "(radiant_dire vs none) and restrict est_c to genuinely side-labelled rows",
        "prevention_ti2027": "every observation declares its side provenance; no silent semantic "
                             "overloading of team_a/team_b",
        "check": "ti15_results.side_labelled fails closed on an unmarked row rather than defaulting",
    },
    {
        "id": "INC-05",
        "title": "a diagnostic was described as something stronger than it was",
        "symptom": "an early-to-late diagnostic was written up as a group-stage-to-playoff replay",
        "root_cause": "the corpus has no stage labels, so a group/playoff split could not be "
                      "constructed; the population was in fact dominated by season-long leagues, "
                      "with the top three events carrying about half the evaluation weight",
        "load_bearing": False,
        "impact_on_submitted_decision": "none - the production path used the plain refit either way",
        "fix": "rename the module to sequential_assimilation, downgrade the claim to a "
               "within-league early-to-late diagnostic, and record what was NOT established",
        "prevention_ti2027": "name a diagnostic after what it measures, and record the population "
                             "it was measured on next to the result",
        "check": "the artifact carries is_a_group_to_playoff_replay=false with its reason, and a "
                 "not_established field",
    },
    {
        "id": "INC-06",
        "title": "a candidate set was described as preregistered without a prior artifact",
        "symptom": "the kappa sweep was called preregistered",
        "root_cause": "no timestamped artifact predating the analysis declared that set; a search "
                      "of the history found none",
        "load_bearing": False,
        "impact_on_submitted_decision": "none",
        "fix": "relabelled audit-predeclared, with the provenance of the label recorded",
        "prevention_ti2027": "preregistration means a committed, timestamped artifact written "
                             "before the analysis; anything else gets a weaker word",
        "check": "the artifact stores candidate_set_provenance in plain language",
    },
    {
        "id": "INC-07",
        "title": "finite-sample headline numbers risked reading as exact",
        "symptom": "expected score, regret and per-node flip costs were quoted to a precision the "
                   "1000-draw bootstrap does not support",
        "root_cause": "an exact enumeration (all 2^14 outcomes) wrapped around an approximate "
                      "distribution, and the exactness of the outer step invited over-reading the "
                      "inner one",
        "load_bearing": False,
        "impact_on_submitted_decision": "none",
        "fix": "an explicit approximation block: what is exact given the distribution, what is an "
               "estimate, and an instruction to read the numbers from the JSON rather than prose",
        "prevention_ti2027": "state the approximation boundary next to every headline number",
        "check": "manifest.approximation.read_as_estimates",
    },
    {
        "id": "INC-08",
        "title": "canonical identity and client display names had to be separated",
        "symptom": "the same organisations appear as PARIVISION / TEAM VISION, BetBoom Team / "
                   "BoomBoys, Tundra Esports / Iron Wing / 1w Team depending on the surface",
        "root_cause": "the client, the league feed and third-party databases each use their own "
                      "display convention, and the model needs one stable key",
        "load_bearing": True,
        "impact_on_submitted_decision": "none, because the separation was made before submission: "
                                        "the artifact carries both a canonical pick and the client "
                                        "display name to type into the client",
        "fix": "one alias table resolves every surface name to a canonical organisation, and "
               "nothing is ever matched by name similarity",
        "prevention_ti2027": "keep the alias table; add new surfaces to it explicitly",
        "check": "ti15_results.canon raises on an unknown identity. The post-event archive is a "
                 "further check: two independent sources using different conventions both resolve "
                 "through the same table",
    },
    {
        "id": "INC-09",
        "title": "selection 810 was a genuine decision-theoretic tie",
        "symptom": "the two candidate picks at selection 810 differed by 0.39 expected points out "
                   "of roughly 2288, and a 40,000-draw paired bootstrap could not resolve the sign "
                   "(95% interval about [-127, +121], P(delta>0) = 0.5111)",
        "root_cause": "the underlying series was close to a coin flip and the downstream bracket "
                      "value of the two branches nearly cancelled",
        "load_bearing": True,
        "impact_on_submitted_decision": "the production rule takes the numerical argmax, so Nigma "
                                        "Galaxy was submitted; the artifact records that this is a "
                                        "tie and NOT a demonstration that Nigma was better",
        "fix": "report it as a tie, retain one deterministic client pick, file the paired analysis",
        "prevention_ti2027": "keep the tie language. A tie that is reported as a tie is not a bug "
                             "when it loses",
        "check": "research/slot810_tiebreak_20260816.json carries statistically_separated=false",
    },
    {
        "id": "INC-10",
        "title": "evidence handling needed fail-closed treatment, not best effort",
        "symptom": "early framings would have let the run proceed on unverified seating",
        "root_cause": "the natural default for a missing artifact is to continue with a warning",
        "load_bearing": True,
        "impact_on_submitted_decision": "none; the gate was in place before the filed run",
        "fix": "the gate aborts on any mismatch, and the trust boundary (human review of the "
               "image-to-text step) is written down rather than implied",
        "prevention_ti2027": "every evidence gate aborts; none warns",
        "check": "tests/test_seating_evidence.py drives the failure paths, not just the happy path",
    },
    {
        "id": "INC-11",
        "title": "Fantasy statistic observability was incomplete and found late",
        "symptom": "three official scoring statistics - madstones, watchers taken, lotuses grabbed "
                   "- are not obtainable from any source the project holds",
        "root_cause": "the observability of each official statistic was never enumerated before "
                      "the value model was built on top of them",
        "load_bearing": True,
        "impact_on_submitted_decision": "material and unresolved: the final two-account comparison "
                                        "is decisive on observable data and carries an unbounded "
                                        "unknown term. It closed as PASS_WITH_MATERIAL_UNCERTAINTY",
        "fix": "state the missing terms symbolically, derive the necessary condition for the "
               "conclusion to flip, and refuse to substitute a proxy",
        "prevention_ti2027": "build a full statistic x coefficient x source x observability matrix "
                             "BEFORE any Fantasy optimisation",
        "check": "the Fantasy closure record carries the symbolic equation and the necessary "
                 "condition rather than a filled-in number",
    },
    {
        "id": "INC-12",
        "title": "a probability bound was overclaimed and withdrawn",
        "symptom": "First Blood was described as contributing at most 1/10 for an individual",
        "root_cause": "1/10 is a per-game share across ten players; it is not an upper bound on any "
                      "individual's rate across a period",
        "load_bearing": False,
        "impact_on_submitted_decision": "none; no recommendation depended on it",
        "fix": "withdrawn, with no individual upper bound claimed in its place",
        "prevention_ti2027": "a share is not a bound; check which quantity a ratio is a ratio OF",
        "check": "the withdrawn-claims list in the Fantasy closure record",
    },
    {
        "id": "INC-13",
        "title": "unobservable statistics were extrapolated with an unrelated proxy",
        "symptom": "banner-wide points per scored multiplier unit was used as a per-statistic rate "
                   "estimator for the three unobservable statistics",
        "root_cause": "an aggregate ratio was treated as if it were a rate; the pressure to fill a "
                      "hole in a schema produced a number where there was no measurement",
        "load_bearing": True,
        "impact_on_submitted_decision": "three claims were withdrawn. The conclusion survived, but "
                                        "only after the invalid support was removed",
        "fix": "withdrawn; the unobservable terms remain symbolic and unbounded",
        "prevention_ti2027": "do not replace missing evidence with a proxy. UNKNOWN is a valid "
                             "value and an absence of public data is not an event-rate estimate",
        "check": "the withdrawn-claims list, and the rule that unknown is never written as zero",
    },
    {
        "id": "INC-14",
        "title": "a screenshot transcription was wrong and was caught by re-reading the image",
        "symptom": "a supplied transcription of one banner slot disagreed with the client",
        "root_cause": "hand transcription of a dense UI",
        "load_bearing": True,
        "impact_on_submitted_decision": "caught before it propagated. The decisive check was "
                                        "internal: the supplied version contradicted its own "
                                        "displayed multipliers at four of five slots, while the "
                                        "screenshot version reproduced all five exactly",
        "fix": "re-read the image directly and prefer the screenshot over any transcription",
        "prevention_ti2027": "images outrank transcriptions of them, and a transcription that "
                             "cannot reproduce the displayed derived values is wrong",
        "check": "reproduce every displayed derived quantity from the transcription before using it",
    },
    {
        "id": "INC-15",
        "title": "the scoring functional is now first-party validated",
        "symptom": "not a defect: the strongest positive result of the closure",
        "root_cause": "n/a",
        "load_bearing": True,
        "impact_on_submitted_decision": "the optimiser maximised the right thing. The in-client "
                                        "settlement credits 8 of 14 and the production functional "
                                        "recomputes 8 of 14 node by node, so the objective that "
                                        "16,384 slates were ranked by is the objective the client "
                                        "actually pays",
        "fix": "n/a",
        "prevention_ti2027": "verify the scoring functional against the client BEFORE optimising "
                             "it, rather than discovering afterwards that it was right",
        "check": "tests/test_postmortem.py asserts the recomputation equals the settlement, both "
                 "in aggregate and at all 14 nodes",
    },
    {
        "id": "INC-16",
        "title": "a stated fact about the settlement capture was not in the capture",
        "symptom": "the archival brief stated that the client screenshot displays 8 correct, 6 "
                   "incorrect and +4320 points. The capture shows the 8/14 count and a per-node "
                   "mark on every node; it displays no points figure for that track at all",
        "root_cause": "4320 is a derived quantity - entry 8 of the committed scoring vector - and "
                      "had been carried in prose long enough to be remembered as something seen",
        "load_bearing": True,
        "impact_on_submitted_decision": "none, and the archived conclusion is unchanged: 4320 is "
                                        "correct, but it is DERIVED from the committed scoring "
                                        "vector rather than transcribed from the image. The "
                                        "evidence index records that distinction explicitly",
        "fix": "transcribe only what is visible; mark derived quantities as derived",
        "prevention_ti2027": "before recording a fact as observed, look at the artifact again. A "
                             "number that is right can still have the wrong provenance",
        "check": "the evidence index stores official_points_displayed_by_client = null next to "
                 "official_points_basis explaining the derivation",
    },
    {
        "id": "INC-17",
        "title": "a secondary source reported the wrong series format",
        "symptom": "a news summary rendered the Main Event series as best-of-5 (3-0, 3-2), which "
                   "would have made every archived score wrong",
        "root_cause": "loose secondary reporting",
        "load_bearing": True,
        "impact_on_submitted_decision": "none - caught before archival by cross-checking two "
                                        "hashed sources, both of which give best-of-3 everywhere "
                                        "except the Grand Final",
        "fix": "the archive asserts that each winner's map count equals the clinch number of the "
               "node's declared best-of, so a best-of-5 score at a best-of-3 node fails the build",
        "prevention_ti2027": "corroborate every result fact across independent sources and assert "
                             "format consistency structurally",
        "check": "the outcome build fails closed on a clinch mismatch; sources.json records the "
                 "rejected source and why",
    },
    {
        "id": "INC-19",
        "title": "the friend account's display name is embedded in seven tracked Fantasy state files",
        "symptom": "seven pre-event Fantasy account-state artifacts contain the target account's "
                   "client display name inside the rendered compendium_player_title string, which "
                   "embeds the account name in the title text",
        "root_cause": "the client's title string was transcribed verbatim into the state file. The "
                      "field was captured for its title semantics; nobody noticed it also carries "
                      "an identity",
        "load_bearing": False,
        "impact_on_submitted_decision": "none analytically. It is a privacy defect, not a "
                                        "correctness one, and it is already public: the files were "
                                        "committed and pushed well before the post-event archival",
        "fix": "NOT FIXED, deliberately. Both available remedies are out of scope by instruction "
               "and neither would work: editing the files would mutate frozen pre-event evidence, "
               "and removing them from history would mean rewriting a published branch, which "
               "cannot recall existing clones, forks or caches anyway. Instead the exposure is "
               "registered explicitly - an exact file list, enforced by a test - so it is "
               "documented and bounded rather than hidden, and cannot spread to a new file",
        "prevention_ti2027": "strip or hash any client string that embeds an account name before "
                             "it enters a tracked artifact, and scan for identity at capture time "
                             "rather than at archival time. Transcribe the semantics of a UI "
                             "string, not the string",
        "check": "tests/test_postmortem.py::test_client_identity_does_not_spread_beyond_the_known"
                 "_exposure fails on any new tracked file carrying the name, and also fails if the "
                 "register goes stale",
        "status": "OPEN - operator decision required on whether to act on already-published content",
    },
    {
        "id": "INC-18",
        "title": "the participant pair is not a unique key for a bracket node",
        "symptom": "the first attempt to place the 14 retrieved series onto the 14 nodes failed: "
                   "PARIVISION and Team Spirit played each other twice, at the upper bracket "
                   "semifinal and again in the Grand Final",
        "root_cause": "a double-elimination bracket can rematch any pair; matching on the "
                      "participant set alone is ambiguous by construction",
        "load_bearing": True,
        "impact_on_submitted_decision": "none - the build failed closed with a clear message "
                                        "rather than silently taking the first match",
        "fix": "match on the participant set AND the best-of clinch number, and additionally "
               "assert that every node starts after both of its input nodes",
        "prevention_ti2027": "never key a bracket node on its participants alone",
        "check": "postmortem.reconcile raises when the match is not unique; a test drives it",
    },
]

KNOWN_LIMITATIONS = [
    "N = 1. Fourteen Main Event series, from one tournament, with heavy team overlap between them. "
    "Nothing here supports a calibration claim or a comparison against an alternative model.",
    "The probabilities recomputed for actually-played matchups are POINT ESTIMATES from the single "
    "frozen serve state. They are not the bootstrap-averaged objects the optimiser maximised, and "
    "the two are not interchangeable.",
    "Most TI15 current-event timestamps remain imputed. The post-event archive has observed times "
    "for the 14 Main Event series only.",
    "No official Fantasy period settlement was captured, so the Fantasy track's realized outcome is "
    "unknown rather than measured.",
    "Three official Fantasy statistics were unobservable from every source held, and no finite "
    "bound on their contribution exists in the verified mechanics.",
    "The identity table maps Iron Wing / 1w Team onto the tracked Tundra Esports lineage. That is a "
    "pre-existing project convention carried forward unchanged here, not a fact re-verified by this "
    "archival phase.",
    "The frozen serve state side-car is reproducible only where the git-ignored rating universe is "
    "present. The evaluation itself reads the tracked side-car and does not need it.",
    "The in-client settlement is first-party but singular: there is one capture, and the trust "
    "boundary is human review of it. The hash proves the bytes have not changed since review; it "
    "cannot prove the review read them correctly.",
    "OPEN, and it needs an operator decision: seven tracked pre-event Fantasy state files carry the "
    "friend account's client display name, and they are already published. See INC-19. The "
    "post-event archive added by this phase is clean and a test now prevents the exposure "
    "spreading, but nothing this phase is permitted to do can un-publish the existing files.",
]

REUSABLE_LESSONS = [
    "Verify the scoring functional against the client BEFORE optimising it. TI2026 got this right "
    "and only learned afterwards how much was riding on it.",
    "PICK UNCERTAINTY IS NOT PATH UNCERTAINTY. A tie analysis conditional on a matchup answers "
    "nothing if that matchup never occurs. Selection 810 was analysed to four decimal places as "
    "Nigma versus Liquid; the series actually played there was Liquid versus Falcons.",
    "In a bracket, a wrong pick and a wrong path are different failures. Three of the six misses "
    "were nodes where the selected team was not among the two teams that played. Counting them as "
    "model errors would triple the apparent local error rate.",
    "Node-winner scoring is far more forgiving than exact-path scoring, and that is worth knowing "
    "before choosing an objective: three nodes were credited despite a diverged path.",
    "A tie that is reported as a tie is not a bug when it loses. Selection 810 cost 1080 points and "
    "was still the correct call under the information available.",
    "Make a data structure self-checking rather than merely well-formed: the outcome archive is "
    "re-derived from the bracket graph on every load, so a corrupted entry fails loudly.",
    "Mark chronology in the data, not only in the directory name. A row carrying a post-event "
    "marker is refused by the estimator even if someone reaches past the namespace.",
    "UNKNOWN is a valid value. The most expensive Fantasy error of the year was filling an unknown "
    "with a plausible proxy.",
    "Look at the artifact again before recording that you saw something in it.",
]

TI2027_ACTIONS = [
    {"phase": "PHASE 1", "action": "capture and hash the client scoring vector, the exact scoring "
                                   "semantics, the bracket topology and the opening seating as "
                                   "soon as they exist",
     "why": "TI2026's seating provenance was retrofitted, and its scoring semantics were only "
            "confirmed after the tournament"},
    {"phase": "PHASE 2", "action": "record an observed start time, teams, result, map count, sides "
                                   "and roster for every current-event series as it is played",
     "why": "TI2026 imputed most of its current-event timestamps"},
    {"phase": "PHASE 3", "action": "require an explicit side-provenance declaration on every "
                                   "observation used for side-bias estimation",
     "why": "winner-oriented synthetic rows silently inflated the side coefficient"},
    {"phase": "PHASE 6", "action": "build the full Fantasy observability matrix before any Fantasy "
                                   "optimisation, and resolve or explicitly model every "
                                   "unobservable statistic",
     "why": "three unobservable statistics left the 2026 Fantasy conclusion formally open"},
    {"phase": "PHASE 7", "action": "keep raw client captures in the external private archive with "
                                   "hash-before-move discipline; publish hash plus transcription only",
     "why": "captures are load-bearing evidence and are personally identifying at the same time"},
    {"phase": "PHASE 9", "action": "keep post-event truth in its own namespace behind the "
                                   "chronology guard, and ingest a finished year as history only "
                                   "through the next season's own pipeline",
     "why": "a refit that quietly includes the results it forecast looks excellent and means nothing"},
    {"phase": "RESEARCH", "action": "pre-register in-event sequential assimilation as a hypothesis "
                                    "with a stated metric and decision rule, then test it on events "
                                    "that were not used to design it",
     "why": "the TI2026 post-hoc diagnostic is suggestive at N=14 and cannot promote itself"},
]

WHAT_WORKED = [
    {"item": "frozen methodology", "assessment":
        "the model, half-life, lambda and scoring form were fixed before the current-event data "
        "arrived and were never reopened. The artifact asserts pipeline identity against the "
        "earlier locked group run, so the freeze is checked rather than promised."},
    {"item": "no leakage", "assessment":
        "the production run recorded network_used=false, odds_used=false and "
        "future_main_event_results_used=false, and those fields remain true and unmodified. No "
        "odds, market probability or crowd pick entered at any point."},
    {"item": "exact enumeration", "assessment":
        "because a coherent 14-slot slate IS one of the 2^14 outcomes, the candidate set equals the "
        "outcome space and the optimisation is exact rather than sampled. All 16,384 slates were "
        "scored against all 16,384 outcomes."},
    {"item": "the objective", "assessment":
        "VALIDATED. Maximising expected official score under node-winner semantics is exactly what "
        "the client settled. The recomputation reproduces the client's 8/14 node by node."},
    {"item": "uncertainty integration", "assessment":
        "expected score is linear in the outcome distribution, so averaging the distribution over "
        "bootstrap draws and then optimising is exact rather than an approximation of an average."},
    {"item": "series-blocked resampling", "assessment":
        "whole series were resampled, never individual maps, so a Bo3 could not masquerade as three "
        "independent observations."},
    {"item": "fail-closed verification", "assessment":
        "the topology is read from the saved Valve feed and the seating from a hashed capture, and "
        "either one failing aborts the run. Neither was ever hand-entered at the point of use."},
    {"item": "independent audit", "assessment":
        "six successive scoped audits each found a real defect. Two of them (the side-provenance "
        "bug and the cutoff dated after its own run) were genuine correctness issues that no test "
        "was catching."},
    {"item": "tie handling", "assessment":
        "the one near-tie was named as a tie, priced with a paired bootstrap, and submitted by a "
        "deterministic rule rather than dressed up as a judgement."},
    {"item": "immutable artifacts", "assessment":
        "the submitted slate is byte-identical to what it was before this postmortem, and the "
        "postmortem asserts that."},
    {"item": "expected score vs expected correct", "assessment":
        "kept distinct throughout. The two optima differed at exactly one node, which is precisely "
        "the kind of difference that gets lost when the two objectives are conflated."},
    {"item": "private evidence hashing", "assessment":
        "every raw capture is committed to by hash without publishing the image, and every "
        "rename/move was proved byte-preserving."},
    {"item": "Fantasy decomposition", "assessment":
        "banner, coach title and team deployment effects were attributed separately and reconciled "
        "under one estimator, so the headline difference is explained rather than asserted."},
]

DOES_NOT_PROVE = [
    "One tournament does not validate calibration. Fourteen correlated series cannot distinguish a "
    "well-calibrated model from a poorly calibrated one.",
    "8 realized correct against about 5.1 expected does not show the model will outperform again. "
    "The model's own pre-event distribution gave a 19.5% chance of scoring at least this well, so "
    "the result sits inside the forecast rather than contradicting it.",
    "4320 realized against about 2288 expected does not justify retuning anything. Expected score "
    "is an average over a distribution the realization was drawn from.",
    "Team Spirit winning does not justify a shorter half-life, a form term, or any other parameter "
    "change. A team the model put fifth of eight won; that is what a 7.9% event looks like when it "
    "happens.",
    "The post-hoc sequential-assimilation diagnostic does not validate sequential assimilation. It "
    "was chosen after the outcome, scored on 14 non-independent series, and has no interval that "
    "would be honest to quote.",
    "Unknown Fantasy statistics must never be silently treated as zero. Exclusion from an estimator "
    "and a true value of zero are different claims.",
    "An absence of public data is not an event-rate estimate.",
    "One year's scoring semantics do not carry to the next. The 2027 client must be re-verified "
    "before its objective is optimised, however stable the format looks.",
    "The optimiser comparators cannot be ranked on this realization. The max-expected-correct slate "
    "scored 1080 more points, from a 0.39-point expected-score difference - noise, resolved by one "
    "coin flip.",
]
