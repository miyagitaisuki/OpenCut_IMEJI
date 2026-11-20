#!/usr/bin/env python3
"""YouTube Data API quota ledger for lesson uploads (standard library only).

The project's quota is 10,000 units a day and resets at midnight Pacific time. Costs (Google's table):
videos.insert 1600, captions.insert 400, thumbnails.set 50, playlists.insert 50, playlistItems.insert 50.
The ledger is a JSON file (lessons/_jobs/quota.json, written atomically) keyed by the Pacific date.

  python scripts/youtube_quota.py status              today's usage
  python scripts/youtube_quota.py upload-units --captions 2 --thumbnail --playlist "N4"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import threading
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = REPO / "lessons" / "_jobs" / "quota.json"
DAILY_LIMIT = int(os.environ.get("YOUTUBE_QUOTA_DAILY", "10000"))
PACIFIC = ZoneInfo("America/Los_Angeles")
COST = {"videos.insert": 1600, "captions.insert": 400, "thumbnails.set": 50,
        "playlists.insert": 50, "playlistItems.insert": 50}


def upload_units(captions: int = 0, thumbnail: bool = False, playlist: bool = False) -> int:
    """Units one lesson upload needs (playlist: at most one playlist create plus one item insert)."""
    units = COST["videos.insert"] + captions * COST["captions.insert"]
    if thumbnail:
        units += COST["thumbnails.set"]
    if playlist:
        units += COST["playlists.insert"] + COST["playlistItems.insert"]
    return units


def pacific_day(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    return now.astimezone(PACIFIC).date().isoformat()


def next_reset(now: dt.datetime | None = None) -> dt.datetime:
    """The next midnight Pacific, as an aware UTC datetime."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(PACIFIC)
    midnight = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(0), tzinfo=PACIFIC)
    return midnight.astimezone(dt.timezone.utc)


class Ledger:
    def __init__(self, path: Path = DEFAULT_LEDGER, limit: int = DAILY_LIMIT):
        self.path = path
        self.limit = limit
        self.lock = threading.Lock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def used(self, day: str | None = None) -> int:
        day = day or pacific_day()
        with self.lock:
            return int(self._load().get(day, {}).get("units", 0))

    def remaining(self, day: str | None = None) -> int:
        return self.limit - self.used(day)

    def spend(self, units: int, job_id: str, action: str, now: dt.datetime | None = None) -> bool:
        """Books `units` against today if they fit under the limit. False (nothing booked) otherwise."""
        day = pacific_day(now)
        with self.lock:
            data = self._load()
            entry = data.setdefault(day, {"units": 0, "uses": []})
            if entry["units"] + units > self.limit:
                return False
            entry["units"] += units
            entry["uses"].append({"job": job_id, "action": action, "units": units})
            self._write(data)
            return True
