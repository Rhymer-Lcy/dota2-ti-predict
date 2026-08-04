"""Official-constant sanity: capacities, scoring tables, frozen production half-life."""
from ti_predict.contest_rules import (BUCKETS, CAPACITY, GROUP_SCORE, MAIN_EVENT_SCORE,
                                      PRODUCTION_HALF_LIFE_DAYS)


def test_buckets_and_capacity():
    assert len(BUCKETS) == 6
    assert set(CAPACITY) == set(BUCKETS)
    assert sum(CAPACITY.values()) == 16
    assert CAPACITY == {"4-0": 1, "4-1": 2, "decider_win": 5, "decider_loss": 5, "1-4": 2, "0-4": 1}


def test_group_score_table():
    assert set(GROUP_SCORE) == set(range(17))
    assert GROUP_SCORE[0] == 0 and GROUP_SCORE[16] == 12000
    vals = [GROUP_SCORE[k] for k in range(17)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))          # non-decreasing


def test_main_event_score_table():
    assert set(MAIN_EVENT_SCORE) == set(range(15))
    assert MAIN_EVENT_SCORE[14] == 12000


def test_production_half_life_frozen():
    assert PRODUCTION_HALF_LIFE_DAYS == 90
