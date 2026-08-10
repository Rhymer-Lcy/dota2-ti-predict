"""Extend the pro-match universe: page /proMatches back to a target date.

The roster-coverage window equals this snapshot's span, so a roster formed before the snapshot start
gets truncated (e.g. Resilience, formed ~April). Pull further back so thin counts reflect real
few-games, not a short window. Overwrites raw/promatches_scan.json (the pro universe used by
roster_coverage.py) and appends a manifest line.

Also writes processed/scan_provenance.json: what this scan established (coverage window, whether it
reached the target start, newest eligible match and its age, row counts, sha). The prediction
pipeline reads that file rather than trusting a CLI flag, so a freshness override has to rest on a
recorded complete scan.

Run:  python -m ti_predict.scan_promatches   (targets 2026-03-01; ~60-100 pages)
"""
import hashlib
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TI = os.path.join(REPO, "data", "ti2026")
RAW, INPUTS, PROC = (os.path.join(TI, d) for d in ("raw", "inputs", "processed"))
BASE = "https://api.opendota.com/api"
UA = {"User-Agent": "dota2-ti-predict/0.1 (scan)"}
NOW = datetime.now(timezone.utc)
TARGET = datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp()
MAX_PAGES = 110


def _get(path):
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
    return json.loads(raw)


SCAN_PROVENANCE = os.path.join(PROC, "scan_provenance.json")


def write_scan_provenance(matches, pages, fetched):
    """Record what the scan actually established, so no later step has to take it on trust.

    The prediction pipeline reads this instead of inferring coverage from a CLI flag: `--allow-stale`
    then means "an old latest match is acceptable BECAUSE a complete scan says so", not "the operator
    asserts there were no games". The two facts are kept apart on purpose:
      coverage_complete    -- the scan reached back to the target start (data coverage freshness);
      latest_match_age_days -- how old the newest eligible professional match is (recency).
    """
    starts = [m["start_time"] for m in matches]
    earliest, latest = min(starts), max(starts)
    now = datetime.now(timezone.utc)
    prov = {
        "scan_completed_at": now.isoformat(timespec="seconds"),
        "scan_source": BASE + "/proMatches",
        "pages_fetched": pages, "records_fetched": fetched,
        "scan_result_rows": len(matches),
        "coverage_start": datetime.fromtimestamp(earliest, timezone.utc).isoformat(),
        "coverage_target_start": datetime.fromtimestamp(TARGET, timezone.utc).isoformat(),
        "coverage_complete": bool(earliest <= TARGET),
        "latest_match_time": datetime.fromtimestamp(latest, timezone.utc).isoformat(),
        "latest_match_age_days": round((now.timestamp() - latest) / 86400.0, 2),
        "scan_sha256": hashlib.sha256(json.dumps(matches).encode()).hexdigest(),
    }
    os.makedirs(PROC, exist_ok=True)
    with open(SCAN_PROVENANCE, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return prov


def main():
    os.makedirs(RAW, exist_ok=True)
    out, less_than, pages, empties = [], None, 0, 0
    while pages < MAX_PAGES:
        page = _get("/proMatches" + (f"?less_than_match_id={less_than}" if less_than else ""))
        if not page:
            # An empty page is usually a transient API hiccup, not the end of history; breaking
            # immediately silently truncates the universe (observed 2026-08-09: scan stopped at
            # 2026-05-17 after 30 pages, shrinking the training window by 2.5 months).
            empties += 1
            if empties > 3:
                break
            time.sleep(3.0)
            continue
        empties = 0
        out.extend(page)
        pages += 1
        less_than = min(m["match_id"] for m in page)
        if min(m.get("start_time", 9e18) for m in page) < TARGET:
            break
        time.sleep(1.1)
    # merge with any existing scan (incremental, coverage never shrinks), de-dup by match_id
    scan_path = os.path.join(RAW, "promatches_scan.json")
    uniq = {}
    if os.path.exists(scan_path):
        with open(scan_path, encoding="utf-8") as fh:
            for m in json.load(fh):
                uniq[m["match_id"]] = m
    prior = len(uniq)
    for m in out:
        uniq[m["match_id"]] = m
    matches = list(uniq.values())
    earliest = min(m["start_time"] for m in matches)
    if earliest > TARGET:
        raise SystemExit(
            f"scan coverage starts {datetime.fromtimestamp(earliest, timezone.utc).date()} but the "
            f"target is {datetime.fromtimestamp(TARGET, timezone.utc).date()}; refusing to write a "
            f"truncated universe (transient API failures? re-run, or restore the prior scan).")
    print(f"merged: {prior} existing + {len(out)} fetched -> {len(matches)} unique")
    payload = json.dumps(matches).encode()
    with open(os.path.join(RAW, "promatches_scan.json"), "wb") as fh:
        fh.write(payload)
    with open(os.path.join(INPUTS, "fetch-manifest.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"endpoint": "proMatches", "key": f"{pages}pages->2026-03",
                             "fetched_at": NOW.isoformat(), "data_cutoff": NOW.isoformat(),
                             "n_records": len(matches),
                             "sha256": hashlib.sha256(payload).hexdigest()}, ensure_ascii=False) + "\n")
    prov = write_scan_provenance(matches, pages, len(out))
    lo = datetime.fromtimestamp(min(m["start_time"] for m in matches), timezone.utc).date()
    hi = datetime.fromtimestamp(max(m["start_time"] for m in matches), timezone.utc).date()
    print(f"pro-universe: {len(matches)} matches over {pages} pages, {lo}..{hi}")
    print(f"scan provenance: coverage_complete={prov['coverage_complete']} "
          f"latest_match={prov['latest_match_time']} "
          f"(age {prov['latest_match_age_days']}d at scan time)")


if __name__ == "__main__":
    main()
