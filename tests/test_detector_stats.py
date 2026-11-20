# =============================================================================
# SentinelFlow - Detector statistics
# =============================================================================
"""``DetectorStats`` backs the detector's terminal dashboard."""

from __future__ import annotations

from datetime import timezone

from sentinelflow.processor.detector.types import DetectorStats


def test_start_time_is_utc_aware():
    assert DetectorStats().start_time.tzinfo is timezone.utc


def test_uptime_works_on_a_fresh_instance():
    # The dashboard reads uptime on its first render; a naive start time made it raise.
    uptime = DetectorStats().uptime_seconds
    assert 0 <= uptime < 5
