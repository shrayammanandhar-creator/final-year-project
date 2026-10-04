from __future__ import annotations

import json
from dataclasses import dataclass
from django.utils.text import slugify
from datetime import date, datetime
from pathlib import Path
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class UpcomingEvent:
    name: str
    kind: str  # festival | occasion | event
    on: date
    slug: str
    image_url: str | None = None
    discount_percent: int | None = None

    @property
    def days_left(self) -> int:
        return (self.on - date.today()).days

    @property
    def query_kind(self) -> str:
        if self.kind == "event":
            return "event"
        if self.kind == "occasion":
            return "occasion"
        return "festival"


def _load_events() -> list[dict[str, Any]]:
    """
    Expected JSON structure (placeholder):
    [
      {"name": "Dashain", "kind": "festival", "date_ad": "2026-10-19"},
      {"name": "Teej", "kind": "festival", "date_ad": "2026-09-08"}
    ]
    """
    data_dir = Path(getattr(settings, "NW_DATA_DIR", Path(settings.BASE_DIR) / "datasets"))
    path = data_dir / "events_ad.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def list_upcoming_events(*, today: date | None = None, limit: int = 3) -> list[UpcomingEvent]:
    """
    Returns the next N upcoming festival/occasion/event items based on dataset-provided AD dates.
    """
    if today is None:
        today = date.today()

    candidates: list[UpcomingEvent] = []
    for row in _load_events():
        name = str(row.get("name", "")).strip()
        kind = str(row.get("kind", "festival")).strip().lower() or "festival"
        date_ad = str(row.get("date_ad", "")).strip()
        if not name or not date_ad:
            continue
        try:
            on = datetime.strptime(date_ad, "%Y-%m-%d").date()
        except ValueError:
            continue
        if on >= today:
            if slugify(name) == "loktantrik-diwas":
                continue
            tag_slug = str(row.get("tag_slug") or "").strip()
            image_url = str(row.get("image_url") or "").strip() or None
            discount = row.get("discount_percent")
            try:
                discount_percent = int(discount) if discount is not None else None
            except Exception:
                discount_percent = None
            candidates.append(
                UpcomingEvent(
                    name=name,
                    kind=kind,
                    on=on,
                    slug=tag_slug or slugify(name),
                    image_url=image_url,
                    discount_percent=discount_percent,
                )
            )

    candidates.sort(key=lambda e: e.on)
    return candidates[: max(0, int(limit))]

def get_upcoming_festival(today: date | None = None) -> UpcomingEvent | None:
    events = list_upcoming_events(today=today, limit=1)
    return events[0] if events else None
