#!/usr/bin/env python3
"""Job queue for lesson videos: an HTTP server that builds lessons one at a time (standard library only).

A job takes QBank questions (or a QBank chapter) or a raw lesson script and runs, in order:

  1. build    `opencut_ptc.py lesson ... --render`: textts (voice + QC listen-back) ->
              `opencut import-textts` -> scenes (`opencut_scenes.py` when no visuals are given,
              `--visuals auto`) -> `lesson_qc` engine check (rebuilds once if it taught textts
              new readings) -> `opencut render`
  2. mix      `lesson_audio.py mix`: music, chapter chimes, -16 LUFS
  3. qc       `lesson_qc.py video`: size, length, audio
  4. publish  `publish_youtube.py --dry-run` only. The real upload waits for a person:
              `POST /jobs/<id>/publish` after watching `<name>.final.mp4`.

Endpoints (JSON in and out; listens on 127.0.0.1 only):
  POST /jobs                 create a job, returns {"id", "status": "queued"}
  GET  /jobs                 every job, newest first
  GET  /jobs/<id>            one job (stages, outputs, error)
  GET  /jobs/<id>/log        the job's log (text)
  POST /jobs/<id>/cancel     drop a queued job or stop a running one
  POST /jobs/<id>/retry      requeue a failed, cancelled or quarantined job; body {"force": true} reruns every stage
  POST /jobs/<id>/accept     a quarantined job, reviewed by a person: continue to mix, QC and the publish check
  POST /jobs/<id>/publish    upload to YouTube (job must be `awaiting_approval`)
  GET  /health
  GET  /dashboard            the queue page (scripts/lesson_dashboard.html)

POST /jobs body, one source:
  {"questions": [7323, 7514]}                       QBank question ids
  {"chapter": 193, "limit": 5}                      QBank chapter
  {"script": "## Mở bài\\n[1] ... // ...", "visuals": {...}}   raw script (`soan-bai-video` format);
                                                    no "visuals" -> Claude writes the scenes
  {"script_path": "lessons/minna-05/minna-05.script.vi.txt"}   a script already on disk
plus options: "name" (folder under lessons/, required with "script"), "title", "level" (N5..N1),
"karaoke" (default true with a script), "mascot" (default apps/intro/public/avatars/chibi with a script),
"burn_subtitles", "bgm", "dry_run" (stop after writing the textts script),
"publish": {"title", "description", "playlist", "privacy" (default unlisted), "tags"}.

POST /jobs/<id>/publish body: {"client": "path/to/oauth-client.json"} (or $YOUTUBE_CLIENT); may override
any "publish" field. The OAuth consent opens in a browser the first time.

State lives in lessons/_jobs/jobs.db (SQLite, WAL) and each job's log in lessons/_jobs/<id>/job.log, so
jobs survive a restart; a job that was running when the server stopped is marked failed. Each stage stores
an input hash: a retry (or a rebuild after a small edit) skips a stage whose inputs did not change.

Environment: LESSON_JOBS_PORT (default 8790), plus what the steps need (QBANK_URL, TEXTTS_URL,
OPENCUT_BIN, ANTHROPIC_API_KEY for auto scenes).

  python scripts/lesson_jobs.py serve [--port 8790]
  curl -X POST localhost:8790/jobs -d '{"questions":[7323],"name":"q7323"}'
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so `youtube_quota` imports when run from elsewhere
import youtube_quota  # noqa: E402
import pron_review  # noqa: E402

FROZEN = bool(getattr(sys, "frozen", False))  # the one-file exe (PyInstaller)
# The repo: OPENCUT_REPO, else the folder the exe sits in (the exe is in the repo root or dist/), else the
# parent of scripts/.
REPO = Path(os.environ["OPENCUT_REPO"]).resolve() if os.environ.get("OPENCUT_REPO") else (
    Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent)
SCRIPTS = REPO / "scripts"
LESSONS = REPO / "lessons"
JOBS_DIR = LESSONS / "_jobs"
DEFAULT_MASCOT = "apps/intro/public/avatars/chibi"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
STAGES = ("tts", "scenes", "render", "mix", "qc", "publish")


class JobError(RuntimeError):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id      TEXT PRIMARY KEY,
    status  TEXT NOT NULL,
    spec    TEXT NOT NULL,
    outputs TEXT NOT NULL,
    error   TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS stages (
    job_id     TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    stage      TEXT NOT NULL,
    status     TEXT NOT NULL,
    input_hash TEXT,
    info       TEXT NOT NULL,
    PRIMARY KEY (job_id, stage)
);
"""


class Store:
    """Jobs in SQLite (WAL) at lessons/_jobs/jobs.db: one row per job, one per stage. get() and all()
    return the dict shape the HTTP API serves. Each job's log stays a plain file (job.log)."""

    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.RLock()
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "jobs.db", check_same_thread=False, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        for path in root.glob("*/job.json"):  # jobs written before the SQLite store
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if self.get(job["id"]) is None:
                self.save(job)
        for job in self.all():
            if job["status"] in ("running", "publishing"):
                job["status"] = "failed"
                job["error"] = "the server stopped while this job was running"
                self.save(job)

    def save(self, job: dict) -> None:
        with self.lock, self.db:
            job["updated"] = time.time()
            self.db.execute(
                "INSERT INTO jobs (id, status, spec, outputs, error, created, updated) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, spec=excluded.spec, "
                "outputs=excluded.outputs, error=excluded.error, updated=excluded.updated",
                (job["id"], job["status"], json.dumps(job["spec"], ensure_ascii=False),
                 json.dumps(job["outputs"], ensure_ascii=False), job.get("error"), job["created"], job["updated"]),
            )
            for stage, info in job["stages"].items():
                self.db.execute(
                    "INSERT INTO stages (job_id, stage, status, input_hash, info) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(job_id, stage) DO UPDATE SET status=excluded.status, "
                    "input_hash=excluded.input_hash, info=excluded.info",
                    (job["id"], stage, info.get("status", "pending"), info.get("input_hash"),
                     json.dumps(info, ensure_ascii=False)),
                )

    def _row(self, job_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT id, status, spec, outputs, error, created, updated FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        found = {s: json.loads(info) for s, info in
                 self.db.execute("SELECT stage, info FROM stages WHERE job_id=?", (job_id,))}
        return {"id": row[0], "status": row[1], "spec": json.loads(row[2]), "outputs": json.loads(row[3]),
                "error": row[4], "created": row[5], "updated": row[6],
                "stages": {s: found[s] for s in STAGES if s in found}}

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            return self._row(job_id)

    def all(self) -> list[dict]:
        with self.lock:
            ids = [r[0] for r in self.db.execute("SELECT id FROM jobs ORDER BY created DESC")]
            return [self._row(i) for i in ids]

    def log_path(self, job_id: str) -> Path:
        return self.root / job_id / "job.log"


def validate(body: dict) -> dict:
    """Checks a POST /jobs body and returns the job's spec."""
    if not isinstance(body, dict):
        raise JobError("the body must be a JSON object")
    sources = [k for k in ("questions", "chapter", "script", "script_path") if body.get(k) not in (None, "", [])]
    if len(sources) != 1:
        raise JobError("give exactly one of: questions, chapter, script, script_path")
    source = sources[0]
    spec = {"source": source}
    if source == "questions":
        ids = body["questions"]
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            raise JobError("questions must be a list of integer ids")
        spec["questions"] = ids
    elif source == "chapter":
        if not isinstance(body["chapter"], int):
            raise JobError("chapter must be an integer id")
        spec["chapter"] = body["chapter"]
        spec["limit"] = int(body.get("limit") or 0)
    elif source == "script":
        if not isinstance(body["script"], str) or "//" not in body["script"]:
            raise JobError("script must be text in the `[1] 日本語 // Tiếng Việt` format")
        spec["script"] = body["script"]
        if body.get("visuals") is not None and not isinstance(body["visuals"], (dict, list)):
            raise JobError("visuals must be the JSON of a visuals file")
        spec["visuals"] = body.get("visuals")
    else:
        path = (REPO / body["script_path"]).resolve()
        if LESSONS.resolve() not in path.parents and (REPO / "apps").resolve() not in path.parents:
            raise JobError("script_path must be under lessons/ or apps/")
        if not path.is_file():
            raise JobError(f"no such script: {body['script_path']}")
        spec["script_path"] = str(path)

    name = body.get("name")
    if name is None:
        if source == "script":
            raise JobError("name is required with script")
        name = (Path(spec["script_path"]).name.split(".")[0] if source == "script_path"
                else f"ch{spec['chapter']}" if source == "chapter" else "q" + "-".join(map(str, spec["questions"][:3])))
    if not isinstance(name, str) or not NAME_RE.match(name) or name.startswith("_"):
        raise JobError("name: letters, digits, . _ - only (max 64)")
    spec["name"] = name
    scripted = source in ("script", "script_path")
    level = body.get("level")
    if level is not None and level not in ("N5", "N4", "N3", "N2", "N1"):
        raise JobError("level must be N5..N1")
    spec.update({
        "title": body.get("title") or name,
        "level": level,
        "karaoke": bool(body.get("karaoke", scripted)),
        "mascot": body.get("mascot", DEFAULT_MASCOT if scripted else None),
        "burn_subtitles": bool(body.get("burn_subtitles", not scripted)),
        "bgm": body.get("bgm"),
        "dry_run": bool(body.get("dry_run")),
        "publish": body.get("publish") or {},
    })
    if not isinstance(spec["publish"], dict):
        raise JobError("publish must be an object")
    return spec


class Runner:
    """One worker thread: lessons are built one after another (textts, AivisSpeech and the renderer
    are each a single local resource)."""

    def __init__(self, store: Store):
        self.store = store
        self.queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.current: dict[str, subprocess.Popen] = {}
        self.cancelled: set[str] = set()
        self.quota = youtube_quota.Ledger()
        waiting = {"queued": "build", "queued_finish": "finish", "queued_publish": "publish"}
        for job in reversed(store.all()):
            if job["status"] in waiting:
                self.queue.put((waiting[job["status"]], job["id"]))
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._scheduler, daemon=True).start()

    def submit(self, spec: dict) -> dict:
        now = time.time()
        job = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6], "status": "queued", "spec": spec,
               "created": now, "updated": now, "stages": {s: {"status": "pending"} for s in STAGES},
               "outputs": {}, "error": None}
        self.store.save(job)
        self.queue.put(("build", job["id"]))
        return job

    def approve_publish(self, job_id: str, overrides: dict) -> dict:
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] != "awaiting_approval":
            raise JobError(f"job is {job['status']}, not awaiting_approval")
        client = overrides.pop("client", None) or os.environ.get("YOUTUBE_CLIENT")
        if not client or not Path(client).is_file():
            raise JobError("give client (OAuth client JSON path) or set $YOUTUBE_CLIENT")
        if overrides.get("publish_at"):
            try:
                dt.datetime.fromisoformat(overrides["publish_at"])
            except (TypeError, ValueError) as error:
                raise JobError("publish_at must be an ISO 8601 time, e.g. 2026-11-25T09:00:00+09:00") from error
        job["spec"]["publish"] = {**job["spec"]["publish"], **overrides, "client": client}
        job["status"] = "queued_publish"
        self.store.save(job)
        self.queue.put(("publish", job_id))
        return job

    def teach(self, job_id: str, body: dict) -> dict:
        """Teaches textts one reading (word -> kana) for a reviewed line. The job is not rebuilt here: the reviewer
        asks for a retry, and the voice stage then runs again (its key includes the taught readings)."""
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        try:
            pron_review.teach(body.get("word", ""), body.get("reading", ""))
        except pron_review.ReviewError as error:
            raise JobError(str(error)) from error
        job["outputs"].setdefault("readings_taught", []).append(
            {"word": body["word"].strip(), "reading": body["reading"].strip()})
        job["outputs"]["readings_taught"] = job["outputs"]["readings_taught"][-200:]
        self.store.save(job)
        return job

    def accept(self, job_id: str) -> dict:
        """A person reviewed a quarantined job and accepts it: mix, QC and the publish dry run follow."""
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] != "quarantine":
            raise JobError(f"job is {job['status']}, not quarantine")
        job["status"] = "queued_finish"
        self.store.save(job)
        self.queue.put(("finish", job_id))
        return job

    def cancel(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] in ("done", "failed", "cancelled"):
            raise JobError(f"job is already {job['status']}")
        self.cancelled.add(job_id)
        proc = self.current.get(job_id)
        if proc and proc.poll() is None:
            proc.terminate()
        if job["status"] in ("queued", "awaiting_approval", "queued_publish", "queued_finish", "quarantine", "waiting_quota"):
            job["status"] = "cancelled"
            self.store.save(job)
        return job

    def retry(self, job_id: str, force: bool = False) -> dict:
        """Requeues a failed, cancelled or quarantined job. Stages that finished ("done") keep their result and
        _cached() skips them when their inputs still match; force=True reruns every stage."""
        job = self.store.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] not in ("failed", "cancelled", "quarantine"):
            raise JobError(f"job is {job['status']}; only failed, cancelled or quarantined jobs can be retried")
        self.cancelled.discard(job_id)
        for stage, info in job["stages"].items():
            if force or info.get("status") != "done":
                job["stages"][stage] = {"status": "pending"}
        job.update(status="queued", error=None)
        self.store.save(job)
        self.queue.put(("build", job_id))
        return job

    # -- worker --------------------------------------------------------------------------------

    def _scheduler(self) -> None:
        """Puts jobs that waited for the YouTube quota back in the queue once the quota has reset."""
        while True:
            time.sleep(60)
            now = dt.datetime.now(dt.timezone.utc)
            for job in self.store.all():
                if job["status"] != "waiting_quota":
                    continue
                if now >= dt.datetime.fromisoformat(job["outputs"]["quota_retry_after"]):
                    job["status"] = "queued_publish"
                    self.store.save(job)
                    self.queue.put(("publish", job["id"]))

    def _loop(self) -> None:
        while True:
            kind, job_id = self.queue.get()
            job = self.store.get(job_id)
            # A stale queue entry (cancelled, or requeued by retry) must not run a job twice.
            expected = {"build": "queued", "finish": "queued_finish", "publish": "queued_publish"}[kind]
            if not job or job_id in self.cancelled or job["status"] != expected:
                continue
            try:
                if kind == "build":
                    self._build(job)
                elif kind == "finish":
                    self._finish(job)
                else:
                    self._publish(job)
            except Exception as error:  # noqa: BLE001 - a job's failure must not stop the worker
                job = self.store.get(job_id) or job
                for stage in job["stages"].values():
                    if stage["status"] == "running":
                        stage["status"] = "failed"
                job["status"] = "cancelled" if job_id in self.cancelled else "failed"
                job["error"] = str(error)
                self.store.save(job)
                self._log(job_id, f"!! {job['status']}: {error}")

    def _log(self, job_id: str, text: str) -> None:
        with self.store.log_path(job_id).open("a", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")

    def _cached(self, job: dict, stage: str, key: str | None, outputs: list) -> bool:
        """True when the stage finished before with the same input hash and its outputs still exist."""
        prev = job["stages"].get(stage) or {}
        if key is None or prev.get("status") != "done" or prev.get("input_hash") != key:
            return False
        if not all(Path(p).exists() for p in outputs):
            return False
        job["stages"][stage] = {**prev, "cached": True}
        self.store.save(job)
        self._log(job["id"], f"\n=== {stage}: inputs unchanged, reusing the previous result")
        return True

    def _run(self, job: dict, stage: str, cmd: list[str], key: str | None = None) -> str:
        """Runs one step, streams its output to job.log, returns stdout; raises when it fails."""
        job["stages"][stage] = {"status": "running", "started": time.time(), "input_hash": key}
        self.store.save(job)
        self._log(job["id"], f"\n=== {stage}: {' '.join(cmd)}")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", env=env)
        self.current[job["id"]] = proc
        lines: list[str] = []
        assert proc.stdout
        for line in proc.stdout:
            lines.append(line)
            self._log(job["id"], line)
        code = proc.wait()
        self.current.pop(job["id"], None)
        if job["id"] in self.cancelled:
            raise JobError("cancelled")
        info = job["stages"][stage]
        info.update(finished=time.time(), exit_code=code, status="done" if code == 0 else "failed")
        self.store.save(job)
        if code != 0:
            tail = "".join(lines[-15:]).strip()
            raise JobError(f"{stage} failed (exit {code}): {tail[-1500:]}")
        return "".join(lines)

    def _py(self, script: str, *args: str) -> list[str]:
        # The exe cannot run the scripts itself: they need a Python interpreter (OPENCUT_PYTHON, else `python`).
        python = os.environ.get("OPENCUT_PYTHON") or ("python" if FROZEN else sys.executable)
        return [python, str(SCRIPTS / script), *args]

    def _lesson_args(self, spec: dict, out: Path) -> tuple[list[str], list[Path] | None]:
        """The options every stage of a job gets (the stage flag is added per call). Returns the command and,
        for a script source, the files whose bytes decide whether a stage can be reused."""
        name = spec["name"]
        cmd = self._py("opencut_ptc.py", "lesson", "--out", str(out), "--name", name, "--title", spec["title"])
        inputs: list[Path] | None = None
        if spec["source"] == "questions":
            for qid in spec["questions"]:
                cmd += ["--question", str(qid)]
        elif spec["source"] == "chapter":
            cmd += ["--chapter", str(spec["chapter"])]
            if spec["limit"]:
                cmd += ["--limit", str(spec["limit"])]
        else:
            if spec["source"] == "script":
                script_path = out / f"{name}.script.vi.txt"
                script_path.write_text(spec["script"].replace("\r\n", "\n"), encoding="utf-8")
                visuals = out / f"{name}.visuals.json"
                if spec["visuals"] is not None:
                    visuals.write_text(json.dumps(spec["visuals"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            else:
                script_path = Path(spec["script_path"])
                visuals = script_path.with_name(re.sub(r"\.script(\.vi)?\.txt$|\.txt$", "", script_path.name) + ".visuals.json")
            cmd += ["--script", str(script_path)]
            # No scenes file: Claude writes one from the imported cues (opencut_scenes.py).
            cmd += ["--visuals", str(visuals) if visuals.exists() else "auto"]
            inputs = [script_path, visuals]
            if spec["karaoke"]:
                cmd.append("--karaoke")
        if spec["level"]:
            cmd += ["--level", spec["level"]]
        if spec["mascot"]:
            cmd += ["--mascot", spec["mascot"]]
        if spec["burn_subtitles"]:
            cmd.append("--burn-subtitles")
        return cmd, inputs

    def _build(self, job: dict) -> None:
        """Stages tts -> scenes -> render. A stage whose inputs did not change is reused (_cached). When the
        engine check taught textts new readings, the voice is made again (up to 2 passes); if lines still
        fail, the job goes to QUARANTINE instead of publishing review."""
        spec = job["spec"]
        out = LESSONS / spec["name"]
        out.mkdir(parents=True, exist_ok=True)
        name = spec["name"]
        job["status"] = "running"
        job["outputs"]["folder"] = str(out)
        self.store.save(job)

        base, inputs = self._lesson_args(spec, out)
        voices = REPO / "scripts" / "lesson_voices.json"
        state = out / f"{name}.tts.json"
        project = out / f"{name}.project.json"
        video = out / f"{name}.mp4"
        job["outputs"]["video"] = str(video)

        if spec["dry_run"]:
            self._run(job, "tts", base + ["--stage", "tts", "--dry-run"])
            for s in ("scenes", "render", "mix", "qc", "publish"):
                job["stages"][s]["status"] = "skipped"
            job["status"] = "done"
            self.store.save(job)
            return

        taught = job["outputs"].get("readings_taught") or []
        tts_key = _hash_text(name, spec["title"], spec["level"], taught, _hash_files(*inputs, voices)) if inputs else None
        attempts = 2
        ran_tts = False
        engine_ok: bool | None = None
        for attempt in range(1, attempts + 1):
            # A second pass is a real voice pass: the cached result of the first one is not valid any more.
            key = None if (attempt > 1 or ran_tts) else tts_key
            if not self._cached(job, "tts", key, [state]):
                self._run(job, "tts", base + ["--stage", "tts"], key=key)
                ran_tts = True
            scenes_key = _hash_text(tts_key, spec["mascot"], spec["karaoke"], _hash_files(inputs[1])) if tts_key else None
            # After a fresh voice pass the scenes are drawn again (cue times may have moved).
            ran_scenes = ran_tts or not self._cached(job, "scenes", scenes_key, [project])
            if ran_scenes:
                try:
                    report = _last_json(self._run(job, "scenes", base + ["--stage", "scenes"], key=scenes_key)) or {}
                except JobError as error:
                    if job["stages"]["scenes"].get("exit_code") != 3:  # 3: the scenes need a person
                        raise
                    job["status"] = "quarantine"
                    job["error"] = f"the scenes need review: {error}"
                    self.store.save(job)
                    self._log(job["id"], f"\n!! quarantine: {job['error']}")
                    return
                job["outputs"]["scenes"] = report
                self.store.save(job)
            else:
                report = job["outputs"].get("scenes") or {}
            engine_ok = ((report.get("qc") or {}).get("engine") or {}).get("ok")
            if not report.get("retry"):
                break
            if attempt < attempts:
                self._log(job["id"], "\n>>> the engine check taught textts new readings: voicing the lesson again")
                ran_tts = False  # next pass re-voices
        if engine_ok is False:
            job["status"] = "quarantine"
            job["error"] = ("engine QC still finds lines the reader cannot say right after the rebuilds (see "
                            "qc.json). Fix the script or readings, then POST /jobs/<id>/retry {\"force\": true}; "
                            "or POST /jobs/<id>/accept to continue to review")
            self.store.save(job)
            self._log(job["id"], f"\n!! quarantine: {job['error']}")
            return

        render_key = _hash_text(scenes_key, _hash_files(project), spec["burn_subtitles"]) if scenes_key else None
        if ran_scenes or not self._cached(job, "render", render_key, [video]):
            stdout = self._run(job, "render", base + ["--stage", "render"], key=render_key)
            job["outputs"]["render"] = _last_json(stdout)
        if not video.exists():
            raise JobError("render finished without a video; see qc.json in the lesson folder")
        self._finish(job)

    def _finish(self, job: dict) -> None:
        """Stages mix -> qc -> publish (dry run), then the job waits for a person to approve the upload."""
        spec = job["spec"]
        name = spec["name"]
        out = LESSONS / name
        job["status"] = "running"
        self.store.save(job)
        video = Path(job["outputs"]["video"])
        final = out / f"{name}.final.mp4"
        markers = out / f"{name}.markers.json"

        mix_key = _hash_text(_hash_files(video, markers), spec["bgm"])
        if not self._cached(job, "mix", mix_key, [final]):
            mix = self._py("lesson_audio.py", "mix", str(video), "-o", str(final))
            if markers.exists():
                mix += ["--markers", str(markers)]
            if spec["bgm"]:
                mix += ["--bgm", spec["bgm"]]
            self._run(job, "mix", mix, key=mix_key)
        job["outputs"]["final"] = str(final)

        qc_key = _hash_files(final)
        if not self._cached(job, "qc", qc_key, [out / f"{name}.qc-report.json"]):
            self._run(job, "qc", self._py("lesson_qc.py", "video", str(final)), key=qc_key)
            self._qc_report(job, out, name)

        self._thumbnail(job, out, name)
        self._run(job, "publish", self._publish_cmd(job, dry_run=True))
        job["stages"]["publish"]["status"] = "dry_run"
        job["status"] = "awaiting_approval"
        self.store.save(job)
        self._log(job["id"], f"\n>>> watch {final}, then POST /jobs/{job['id']}/publish to upload")

    def _thumbnail(self, job: dict, out: Path, name: str) -> None:
        """The 1280x720 thumbnail (Remotion renderStill, `lesson.ts thumbnail`) for the upload. A failure only
        leaves the video without a thumbnail: it is recorded as a warning, the job goes on."""
        spec = job["spec"]
        meta = out / f"{name}.thumb.json"
        png = out / f"{name}.thumb.png"
        meta.write_text(json.dumps({"title": spec["title"], "subtitle": "", "badge": spec.get("level") or "",
                                    "tag": "", "pose": "avatars/chibi/pose_a01.png"}, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        node = os.environ.get("OPENCUT_NODE", "node")
        done = subprocess.run([node, "scripts/lesson.ts", "thumbnail", str(meta), "-o", str(png)],
                              cwd=REPO / "apps" / "intro", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace")
        self._log(job["id"], f"\n=== thumbnail\n{done.stdout[-1500:]}")
        if done.returncode != 0 or not png.exists():
            job["outputs"].setdefault("warnings", []).append("thumbnail not rendered; publish without it")

    def _qc_report(self, job: dict, out: Path, name: str) -> None:
        """The full QC (voice, pronunciation, layout) as a report file. It does not fail the job: the
        status is recorded, and the publish step refuses unless it is PASSED."""
        report_path = out / f"{name}.qc-report.json"
        cmd = self._py("lesson_qc.py", "report", str(out / f"{name}.project.json"), "--out", str(report_path))
        if (out / f"{name}.words.json").exists():
            cmd += ["--words", str(out / f"{name}.words.json")]
        if (out / "stills").is_dir():
            cmd += ["--stills", str(out / "stills")]
        done = subprocess.run(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace")
        self._log(job["id"], f"\n=== qc report: {' '.join(cmd)}\n{done.stdout}")
        status = "UNKNOWN"
        if report_path.exists():
            status = json.loads(report_path.read_text(encoding="utf-8")).get("status", status)
        job["outputs"]["qc_status"] = status
        job["outputs"]["qc_report"] = str(report_path)
        if status != "PASSED":
            job["outputs"].setdefault("warnings", []).append(
                f"QC status {status}: publishing is blocked until it is PASSED (see {report_path.name})")

    def _publish_cmd(self, job: dict, dry_run: bool) -> list[str]:
        spec, out, name = job["spec"], LESSONS / job["spec"]["name"], job["spec"]["name"]
        pub = spec["publish"]
        cmd = self._py("publish_youtube.py", job["outputs"]["final"], "--title", pub.get("title") or spec["title"],
                       "--privacy", pub.get("privacy", "unlisted"),
                       "--client", pub.get("client") or "-")
        if pub.get("description"):
            cmd += ["--description", pub["description"]]
        if pub.get("playlist"):
            cmd += ["--playlist", pub["playlist"]]
        if pub.get("tags"):
            cmd += ["--tags", pub["tags"]]
        for path, flag in ((out / f"{name}.markers.json", "--markers"), (out / f"{name}.thumb.png", "--thumbnail")):
            if path.exists():
                cmd += [flag, str(path)]
        for srt in sorted((out / "textts").glob("*.srt")) if (out / "textts").exists() else []:
            cmd += ["--captions", str(srt)]
            break
        if pub.get("publish_at"):
            cmd += ["--publish-at", pub["publish_at"]]
        if dry_run:
            cmd.append("--dry-run")
        else:
            cmd += ["--qc-report", str(out / f"{name}.qc-report.json")]
        return cmd

    def _publish_units(self, job: dict) -> int:
        """Quota the upload needs: the video, the first subtitle file, the thumbnail, the playlist."""
        spec, out = job["spec"], LESSONS / job["spec"]["name"]
        name = spec["name"]
        srt = (sorted((out / "textts").glob("*.srt")) or [None])[0] if (out / "textts").exists() else None
        return youtube_quota.upload_units(captions=1 if srt else 0,
                                          thumbnail=(out / f"{name}.thumb.png").exists(),
                                          playlist=bool(spec["publish"].get("playlist")))

    def _publish(self, job: dict) -> None:
        """Uploads. The daily YouTube quota is booked first; when it does not cover the upload the job waits
        (waiting_quota) until the quota resets at midnight Pacific time."""
        if not self.quota.spend(self._publish_units(job), job["id"], "upload"):
            job["status"] = "waiting_quota"
            job["outputs"]["quota_retry_after"] = youtube_quota.next_reset().isoformat()
            self.store.save(job)
            self._log(job["id"], f"\n>>> YouTube quota is used up today; retry after {job['outputs']['quota_retry_after']}")
            return
        job["status"] = "publishing"
        self.store.save(job)
        stdout = self._run(job, "publish", self._publish_cmd(job, dry_run=False))
        found = re.search(r"https://youtu\.be/\S+", stdout)
        job["outputs"]["youtube"] = found.group(0) if found else None
        job["status"] = "done"
        self.store.save(job)


def _hash_files(*paths) -> str:
    """sha256 of the files' bytes (a missing file counts as missing): a stage's input hash."""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path).encode("utf-8") + b"\0")
        if path and Path(path).is_file():
            with Path(path).open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    digest.update(chunk)
        else:
            digest.update(b"<missing>")
    return digest.hexdigest()


def _hash_text(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _last_json(text: str) -> dict | None:
    """opencut_ptc prints its report as the last JSON object of its output."""
    start = text.rfind("\n{")
    start = 0 if text.startswith("{") and start < 0 else start + 1
    while start >= 0:
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            start = text.rfind("\n{", 0, start - 1)
            if start < 0:
                return None
            start += 1
    return None


def make_handler(store: Store, runner: Runner):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter than the default
            sys.stderr.write(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}\n")

        def _send(self, code: int, payload, content_type: str = "application/json") -> None:
            data = (json.dumps(payload, ensure_ascii=False, indent=2) if content_type == "application/json"
                    else payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 2_000_000:
                raise JobError("body too large")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                return json.loads(raw.decode("utf-8") or "{}")
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise JobError(f"invalid JSON: {error}") from error

        def do_GET(self):
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if parts in ([], ["dashboard"]):
                return self._send(200, (SCRIPTS / "lesson_dashboard.html").read_text(encoding="utf-8"), "text/html")
            if parts == ["health"]:
                return self._send(200, {"ok": True, "queued": runner.queue.qsize()})
            if parts == ["jobs"]:
                return self._send(200, store.all())
            if len(parts) >= 2 and parts[0] == "jobs":
                job = store.get(parts[1])
                if not job:
                    return self._send(404, {"error": "no such job"})
                if len(parts) == 2:
                    return self._send(200, job)
                if parts[2:] == ["review"]:
                    folder = LESSONS / job["spec"]["name"]
                    return self._send(200, {"lines": pron_review.flagged(folder, job["spec"]["name"]),
                                            "taught": job["outputs"].get("readings_taught") or []})
                if len(parts) == 4 and parts[2] == "clip":
                    try:
                        audio = pron_review.clip(LESSONS / job["spec"]["name"], job["spec"]["name"], parts[3])
                    except pron_review.ReviewError as error:
                        return self._send(400, {"error": str(error)})
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/mpeg")
                    self.send_header("Content-Length", str(len(audio)))
                    self.end_headers()
                    self.wfile.write(audio)
                    return
                if parts[2:] == ["log"]:
                    log = store.log_path(parts[1])
                    return self._send(200, log.read_text(encoding="utf-8") if log.exists() else "", "text/plain")
            self._send(404, {"error": "not found"})

        def do_POST(self):
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            try:
                body = self._body()
                if parts == ["jobs"]:
                    return self._send(201, runner.submit(validate(body)))
                if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "cancel":
                    return self._send(200, runner.cancel(parts[1]))
                if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "retry":
                    return self._send(202, runner.retry(parts[1], force=bool(body.get("force"))))
                if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "readings":
                    return self._send(202, runner.teach(parts[1], body))
                if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "accept":
                    return self._send(202, runner.accept(parts[1]))
                if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "publish":
                    return self._send(202, runner.approve_publish(parts[1], dict(body)))
                self._send(404, {"error": "not found"})
            except KeyError:
                self._send(404, {"error": "no such job"})
            except JobError as error:
                self._send(400, {"error": str(error)})

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the job server")
    serve.add_argument("--port", type=int, default=int(os.environ.get("LESSON_JOBS_PORT", "8790")))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--open", action="store_true", default=FROZEN,
                       help="Open the dashboard in the browser (default for the exe)")
    args = parser.parse_args(argv if argv is not None else (sys.argv[1:] or ["serve"]))  # no command: serve
    store = Store(JOBS_DIR)
    runner = Runner(store)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, runner))
    url = f"http://{args.host}:{args.port}"
    print(f"lesson jobs on {url} (state in {JOBS_DIR})", file=sys.stderr)
    print(f"dashboard: {url}/dashboard   (Ctrl+C stops the server)", file=sys.stderr)
    if args.open:
        import webbrowser
        threading.Timer(1.0, webbrowser.open, args=[f"{url}/dashboard"]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
