from __future__ import annotations

from .festival import list_upcoming_events


def upcoming_festival(request):
    """
    Adds upcoming festival/occasion/event items from dataset to every page.
    Dataset is loaded from settings.NW_DATA_DIR (not hard-coded).
    """
    events = list_upcoming_events(limit=5)
    return {
        "upcoming_events": events,
        "upcoming_festival": events[0] if events else None,
    }

