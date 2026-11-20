"""Tests for the SQLite job store and the stage input-hash cache in lesson_jobs.py (standard library only)."""
from __future__ import annotations

import json
import sys
import tempfile
import time
import types
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lesson_jobs  # noqa: E402


def new_job(job_id: str, status: str = "queued") -> dict:
    now = time.time()
    return {"id": job_id, "status": status, "spec": {"name": "x"}, "created": now, "updated": now,
            "stages": {s: {"status": "pending"} for s in lesson_jobs.STAGES}, "outputs": {}, "error": None}


class StoreRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = lesson_jobs.Store(Path(self.tmp.name))

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_save_and_get_keep_shape(self):
        job = new_job("j1")
        job["stages"]["tts"] = {"status": "done", "input_hash": "abc", "exit_code": 0}
        job["outputs"]["final"] = "a.mp4"
        self.store.save(job)
        got = self.store.get("j1")
        self.assertEqual(got["status"], "queued")
        self.assertEqual(got["outputs"], {"final": "a.mp4"})
        self.assertEqual(got["stages"]["tts"]["input_hash"], "abc")
        self.assertEqual(list(got["stages"]), list(lesson_jobs.STAGES))

    def test_save_updates_in_place(self):
        job = new_job("j2")
        self.store.save(job)
        job["status"] = "failed"
        job["error"] = "boom"
        self.store.save(job)
        self.assertEqual([j["id"] for j in self.store.all()], ["j2"])
        self.assertEqual(self.store.get("j2")["error"], "boom")

    def test_all_is_newest_first(self):
        old = new_job("old")
        old["created"] = 1.0
        self.store.save(old)
        self.store.save(new_job("new"))
        self.assertEqual([j["id"] for j in self.store.all()], ["new", "old"])

    def test_running_jobs_are_failed_on_restart(self):
        self.store.save(new_job("r1", status="running"))
        self.store.db.close()
        reopened = lesson_jobs.Store(Path(self.tmp.name))
        self.store = reopened
        self.assertEqual(reopened.get("r1")["status"], "failed")
        self.assertIn("stopped", reopened.get("r1")["error"])

    def test_missing_job_is_none(self):
        self.assertIsNone(self.store.get("nope"))


class StageCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = lesson_jobs.Store(Path(self.tmp.name))
        self.runner = types.SimpleNamespace(store=self.store, _log=lambda *a: None)
        self.cached = lambda job, stage, key, outputs: lesson_jobs.Runner._cached(self.runner, job, stage, key, outputs)
        self.out = Path(self.tmp.name) / "final.mp4"
        self.out.write_bytes(b"video")

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def done_job(self, key: str) -> dict:
        job = new_job("c1", status="failed")
        job["stages"]["mix"] = {"status": "done", "input_hash": key}
        return job

    def test_hit_when_hash_and_output_match(self):
        job = self.done_job("k")
        self.assertTrue(self.cached(job, "mix", "k", [self.out]))
        self.assertTrue(job["stages"]["mix"]["cached"])

    def test_miss_when_inputs_changed(self):
        self.assertFalse(self.cached(self.done_job("k"), "mix", "other", [self.out]))

    def test_miss_when_output_removed(self):
        self.out.unlink()
        self.assertFalse(self.cached(self.done_job("k"), "mix", "k", [self.out]))

    def test_miss_when_previous_stage_failed(self):
        job = self.done_job("k")
        job["stages"]["mix"]["status"] = "failed"
        self.assertFalse(self.cached(job, "mix", "k", [self.out]))

    def test_no_key_never_hits(self):
        job = self.done_job(None)
        job["stages"]["mix"]["input_hash"] = None
        self.assertFalse(self.cached(job, "mix", None, [self.out]))


class Hashing(unittest.TestCase):
    def test_hash_files_tracks_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.txt"
            f.write_text("one", encoding="utf-8")
            first = lesson_jobs._hash_files(f)
            self.assertEqual(first, lesson_jobs._hash_files(f))
            f.write_text("two", encoding="utf-8")
            self.assertNotEqual(first, lesson_jobs._hash_files(f))

    def test_missing_file_is_stable(self):
        p = Path("no-such-file-for-test.txt")
        self.assertEqual(lesson_jobs._hash_files(p), lesson_jobs._hash_files(p))

    def test_hash_text_depends_on_every_part(self):
        self.assertNotEqual(lesson_jobs._hash_text("a", {"x": 1}), lesson_jobs._hash_text("a", {"x": 2}))
        self.assertEqual(lesson_jobs._hash_text("a", {"x": 1, "y": 2}), lesson_jobs._hash_text("a", {"y": 2, "x": 1}))


class StagedBuild(unittest.TestCase):
    """Runs Runner._build with a fake `_run` (no textts, Remotion or FFmpeg): checks which stages run."""

    class FakeRunner(lesson_jobs.Runner):
        def __init__(self, store, engine):
            self.store = store
            self.queue = lesson_jobs.queue.Queue()
            self.current = {}
            self.cancelled = set()
            self.engine = list(engine)  # one scenes-stage engine result per pass
            self.calls: list[str] = []
            self.quota = lesson_jobs.youtube_quota.Ledger(Path(tempfile.gettempdir()) / f"quota-test-{uuid.uuid4().hex}.json")

        def _log(self, job_id, text):
            pass

        def _qc_report(self, job, out, name):
            (out / f"{name}.qc-report.json").write_text("{}", encoding="utf-8")

        def _run(self, job, stage, cmd, key=None):
            self.calls.append(stage)
            job["stages"][stage] = {"status": "running", "started": 0, "input_hash": key}
            self.store.save(job)
            text = ""
            out = lesson_jobs.LESSONS / job["spec"]["name"]
            name = job["spec"]["name"]
            if stage == "tts":
                (out / f"{name}.tts.json").write_text("{}", encoding="utf-8")
            elif stage == "scenes":
                (out / f"{name}.project.json").write_text("{}", encoding="utf-8")
                engine = self.engine.pop(0) if self.engine else {"retry": False, "ok": True}
                text = json.dumps({"stage": "scenes", "retry": engine["retry"],
                                   "qc": {"engine": {"ok": engine["ok"], "retry": engine["retry"]}}})
            elif stage == "render":
                # New bytes each render, so the mix stage cannot reuse an older video.
                (out / f"{name}.mp4").write_text(uuid.uuid4().hex, encoding="utf-8")
            elif stage == "mix":
                Path(cmd[cmd.index("-o") + 1]).write_text("final", encoding="utf-8")
            job["stages"][stage].update(status="done", exit_code=0)
            self.store.save(job)
            return text

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_lessons = lesson_jobs.LESSONS
        lesson_jobs.LESSONS = Path(self.tmp.name) / "lessons"
        self.store = lesson_jobs.Store(Path(self.tmp.name) / "jobs")

    def tearDown(self):
        self.store.db.close()
        lesson_jobs.LESSONS = self.old_lessons
        self.tmp.cleanup()

    def make(self, engine=()):
        spec = lesson_jobs.validate({"script": "[1] 日本語 // Tiếng Việt", "name": "lesson1"})
        job = new_job("b1")
        job["spec"] = spec
        self.store.save(job)
        return self.FakeRunner(self.store, engine), job

    def build(self, runner, job_id):
        job = self.store.get(job_id)
        runner._build(job)
        return self.store.get(job_id)

    def test_fresh_job_runs_every_stage(self):
        runner, _ = self.make()
        job = self.build(runner, "b1")
        self.assertEqual(runner.calls, ["tts", "scenes", "render", "mix", "qc", "publish"])
        self.assertEqual(job["status"], "awaiting_approval")

    def test_unchanged_rebuild_reuses_stages(self):
        runner, _ = self.make()
        self.build(runner, "b1")
        runner.calls.clear()
        self.build(runner, "b1")
        self.assertEqual(runner.calls, ["publish"])  # the dry-run publish always runs

    def test_edited_script_reruns_voice_and_scenes_but_scenes_keep_claude_out(self):
        runner, job = self.make()
        self.build(runner, "b1")
        job = self.store.get("b1")
        job["spec"]["script"] = "[1] 日本語を変えた // Tiếng Việt khác"
        self.store.save(job)
        runner.calls.clear()
        self.build(runner, "b1")
        self.assertEqual(runner.calls[:3], ["tts", "scenes", "render"])

    def test_engine_taught_readings_voices_again(self):
        runner, _ = self.make(engine=[{"retry": True, "ok": False}, {"retry": False, "ok": True}])
        job = self.build(runner, "b1")
        self.assertEqual(runner.calls[:4], ["tts", "scenes", "tts", "scenes"])
        self.assertEqual(job["status"], "awaiting_approval")

    def test_lines_still_failing_go_to_quarantine_and_accept_finishes(self):
        runner, _ = self.make(engine=[{"retry": True, "ok": False}, {"retry": False, "ok": False}])
        job = self.build(runner, "b1")
        self.assertEqual(job["status"], "quarantine")
        self.assertNotIn("render", runner.calls)
        job = self.store.get("b1")
        self.assertEqual(job["status"], "quarantine")
        runner.accept("b1")
        runner.calls.clear()
        runner._finish(self.store.get("b1"))
        self.assertEqual(runner.calls, ["mix", "qc", "publish"])
        self.assertEqual(self.store.get("b1")["status"], "awaiting_approval")

    def test_force_retry_reruns_every_stage(self):
        runner, _ = self.make()
        self.build(runner, "b1")
        job = self.store.get("b1")
        job["status"] = "failed"
        self.store.save(job)
        runner.retry("b1", force=True)
        runner.queue.get()  # the queued build entry; this test runs the build itself
        runner.calls.clear()
        self.build(runner, "b1")
        self.assertEqual(runner.calls, ["tts", "scenes", "render", "mix", "qc", "publish"])


if __name__ == "__main__":
    unittest.main()
