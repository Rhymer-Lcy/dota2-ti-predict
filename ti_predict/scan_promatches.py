"""Extend the pro-match universe: page /proMatches back to a target date.

The roster-coverage window equals this snapshot's span, so a roster formed before the snapshot start
gets truncated (e.g. Resilience, formed ~April). Pull further back so thin counts reflect real
few-games, not a short window. Overwrites raw/promatches_scan.json (the pro universe used by
roster_coverage.py) and appends a manifest line.

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
RAW, INPUTS = os.path.join(TI, "raw"), os.path.join(TI, "inputs")
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


def main():
    os.makedirs(RAW, exist_ok=True)
    out, less_than, pages = [], None, 0
    while pages < MAX_PAGES:
        page = _get("/proMatches" + (f"?less_than_match_id={less_than}" if less_than else ""))
        if not page:
            break
        out.extend(page)
        pages += 1
        less_than = min(m["match_id"] for m in page)
        if min(m.get("start_time", 9e18) for m in page) < TARGET:
            break
        time.sleep(1.1)
    # de-dup by match_id
    uniq = {m["match_id"]: m for m in out}
    matches = list(uniq.values())
    payload = json.dumps(matches).encode()
    with open(os.path.join(RAW, "promatches_scan.json"), "wb") as fh:
        fh.write(payload)
    with open(os.path.join(INPUTS, "fetch-manifest.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"endpoint": "proMatches", "key": f"{pages}pages->2026-03",
                             "fetched_at": NOW.isoformat(), "data_cutoff": NOW.isoformat(),
                             "n_records": len(matches),
                             "sha256": hashlib.sha256(payload).hexdigest()}, ensure_ascii=False) + "\n")
    lo = datetime.fromtimestamp(min(m["start_time"] for m in matches), timezone.utc).date()
    hi = datetime.fromtimestamp(max(m["start_time"] for m in matches), timezone.utc).date()
    print(f"pro-universe: {len(matches)} matches over {pages} pages, {lo}..{hi}")


if __name__ == "__main__":
    main()
