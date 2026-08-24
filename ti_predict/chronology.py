"""The chronology boundary: pre-event evidence must never be contaminated by post-event truth.

TI2026 is finished, so the repository now holds two kinds of fact that look alike and are not:

  PRE-EVENT   what was known before the bracket locked. The frozen fit, the submitted slate, the
              seating evidence, the Fantasy deployment. This is the historical record of a forecast
              and is immutable.
  POST-EVENT  what actually happened. Realized winners, scores, the client's settlement, every
              number in the postmortem. This was observed AFTER the prediction was submitted.

Mixing them is the one failure that would silently destroy the value of the whole archive: a model
refit that quietly includes the results it was supposed to predict looks excellent and means
nothing. The separation is therefore enforced three ways, not asserted once in prose:

  1. namespace     post-event files live only under the directories named in POST_EVENT_DIRS;
  2. marker        every post-event document carries post_event_only / observed_after_prediction /
                   valid_production_input, and `assert_production_document` refuses them;
  3. funnel        `assert_production_rows` sits on the single path by which observations reach the
                   frozen estimator, so a post-event row cannot be trained on even if someone
                   reaches past the other two.

All three fail closed: on doubt they raise, they never warn and continue.
"""
import os

# Post-event namespaces, repository-relative and POSIX-style. Anything under these paths is truth
# observed after the fact and is never a production input.
POST_EVENT_DIRS = (
    "data/ti2026/outcomes",
    "predictions/ti2026/postmortem",
)

# Pre-event namespaces, kept for documentation and for the structural test that pins the contract.
PRE_EVENT_DIRS = (
    "data/ti2026/inputs",
    "predictions/ti2026/group-stage",
    "predictions/ti2026/playoffs",
    "predictions/ti2026/fantasy",
)

# Document-level markers. A document carrying any of these in the stated sense is post-event.
POST_EVENT_MARKERS = ("post_event_only", "observed_after_prediction")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rel(path):
    """`path` relative to the repository root, POSIX-style. Absolute foreign paths pass through."""
    try:
        rel = os.path.relpath(os.path.abspath(path), REPO)
    except ValueError:            # different drive on Windows
        return os.path.abspath(path).replace("\\", "/")
    return rel.replace("\\", "/")


def is_post_event_path(path):
    """True if `path` lives inside a post-event namespace."""
    rel = _rel(path)
    return any(rel == d or rel.startswith(d + "/") for d in POST_EVENT_DIRS)


def assert_production_input(path, why="a production input"):
    """Refuse a post-event file where a production input is expected."""
    if is_post_event_path(path):
        raise SystemExit(
            f"chronology violation: {_rel(path)} is post-event truth and was offered as {why}.\n"
            "Files under " + ", ".join(POST_EVENT_DIRS) + " record what happened AFTER the TI2026 "
            "prediction was submitted. Feeding them back into a TI2026 fit would be leakage: the "
            "model would be scored on data it had been given. When TI2026 is used as history in a "
            "later season, ingest it through that season's own historical-data pipeline instead.")
    return path


def is_post_event_document(doc):
    """True if a loaded JSON document declares itself post-event."""
    if not isinstance(doc, dict):
        return False
    if any(bool(doc.get(m)) for m in POST_EVENT_MARKERS):
        return True
    return doc.get("phase") == "post_event"


def assert_production_document(doc, why="a production input"):
    """Refuse a loaded document that declares itself post-event or non-production."""
    if is_post_event_document(doc) or doc.get("valid_production_input") is False:
        raise SystemExit(
            f"chronology violation: a document marked post-event was offered as {why}. "
            "It declares post_event_only/observed_after_prediction or "
            "valid_production_input=false and must not enter a TI2026 fit.")
    return doc


def assert_production_rows(rows, why="the frozen estimator"):
    """Refuse observation rows carrying a post-event marker.

    This guards the funnel rather than the file: rows reach the estimator as plain dicts, long after
    any path is visible, so the marker travels with the observation itself.
    """
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("phase") == "post_event" or any(bool(r.get(m)) for m in POST_EVENT_MARKERS):
            raise SystemExit(
                f"chronology violation: a row marked post-event reached {why}. "
                f"Offending row: { {k: r[k] for k in list(r)[:6]} }. "
                "Main Event results are not training data for the prediction that forecast them.")
    return rows


def stamp_post_event(doc):
    """Stamp the standard post-event header onto a document being written to the archive."""
    doc.setdefault("phase", "post_event")
    doc["post_event_only"] = True
    doc["observed_after_prediction"] = True
    doc["valid_production_input"] = False
    return doc


def main():
    print("post-event namespaces (never a production input):")
    for d in POST_EVENT_DIRS:
        print("  " + d)
    print("pre-event namespaces (immutable historical evidence):")
    for d in PRE_EVENT_DIRS:
        print("  " + d)


if __name__ == "__main__":
    main()
