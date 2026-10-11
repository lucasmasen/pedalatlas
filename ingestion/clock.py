"""Fixed atlas date so freshness checks stay reproducible."""

from datetime import date, datetime

# Hackathon reference date. Freshness is measured against this clock, not the
# wall clock, so a demo run does not change classification as time passes.
ATLAS_TODAY = date(2026, 10, 11)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None
