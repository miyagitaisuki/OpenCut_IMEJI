"""Tests for the YouTube quota ledger (standard library only)."""
from __future__ import annotations

import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import youtube_quota  # noqa: E402


class Costs(unittest.TestCase):
    def test_upload_units_follow_the_cost_table(self):
        self.assertEqual(youtube_quota.upload_units(), 1600)
        self.assertEqual(youtube_quota.upload_units(captions=2, thumbnail=True, playlist=True),
                         1600 + 800 + 50 + 100)


class Ledger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = youtube_quota.Ledger(Path(self.tmp.name) / "quota.json", limit=3300)
        self.now = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_books_until_the_limit(self):
        self.assertTrue(self.ledger.spend(1600, "a", "upload", now=self.now))
        self.assertTrue(self.ledger.spend(1600, "b", "upload", now=self.now))
        self.assertFalse(self.ledger.spend(1600, "c", "upload", now=self.now))  # would pass 3300
        self.assertEqual(self.ledger.used(youtube_quota.pacific_day(self.now)), 3200)

    def test_a_new_pacific_day_starts_empty(self):
        self.ledger.spend(1600, "a", "upload", now=self.now)
        tomorrow = self.now + dt.timedelta(days=1)
        self.assertEqual(self.ledger.used(youtube_quota.pacific_day(tomorrow)), 0)

    def test_reset_is_next_midnight_pacific(self):
        reset = youtube_quota.next_reset(self.now)
        local = reset.astimezone(youtube_quota.PACIFIC)
        self.assertEqual((local.hour, local.minute), (0, 0))
        self.assertGreater(reset, self.now)
        self.assertLessEqual(reset - self.now, dt.timedelta(days=1))


if __name__ == "__main__":
    unittest.main()
