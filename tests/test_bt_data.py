"""B-bt data path: 16-team strength mapping. Requires the gitignored processed universe; skipped on
a clean clone without local data (see docs/lockday-runbook.md for how to regenerate it)."""
import os

import pytest

from ti_predict.predict_ti15 import UNIVERSE_CSV, bt_strengths_for, load_teams, parse_cutoff

pytestmark = pytest.mark.skipif(not os.path.exists(UNIVERSE_CSV),
                                reason="processed universe_maps.csv not present (gitignored)")


def test_bt_maps_all_16_teams():
    teams = load_teams()
    cut_ts, _ = parse_cutoff("2026-08-01T00:00:00Z")
    strengths, c, n_train, uni_rows, uni_max = bt_strengths_for(teams, cut_ts)
    assert set(strengths) == {t["team"] for t in teams}         # all 16 mapped by organization name
    assert n_train > 0 and uni_rows >= n_train
    assert isinstance(c, float)
