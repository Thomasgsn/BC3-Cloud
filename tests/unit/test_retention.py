"""Cas limites de dates synthétiques identifiées, sans suppression de données."""

from datetime import UTC, datetime, timedelta

import pytest

from rncp_bc3.retention import age_bucket


def test_conservation_boundary_and_future():
    now = datetime(2026, 11, 21, tzinfo=UTC)
    assert age_bucket(now - timedelta(days=7), now, 7) == "past_proposed_retention"
    assert (
        age_bucket(now - timedelta(days=7) + timedelta(microseconds=1), now, 7)
        == "within_proposed_retention"
    )
    assert age_bucket(now + timedelta(seconds=1), now, 7) == "future_timestamp"


def test_ambiguous_dates_and_invalid_duration_refused():
    now = datetime(2026, 11, 21, tzinfo=UTC)
    with pytest.raises(ValueError):
        age_bucket(now.replace(tzinfo=None), now, 7)
    with pytest.raises(ValueError):
        age_bucket(now, now, 0)
