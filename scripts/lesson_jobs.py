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
  POST /jobs/<id>/publish    upload to YouTube (job must be `awaiting_approval`)
  GET  /health

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

State lives in lessons/_jobs/<id>/ (job.json, job.log), so jobs survive a restart; a job that was
running when the server stopped is marked failed.

Environment: LESSON_JOBS_PORT (default 8790), plus what the steps need (QBANK_URL, TEXTTS_URL,
OPENCUT_BIN, ANTHROPIC_API_KEY for auto scenes).

  python scripts/lesson_jobs.py serve [--port 8790]
  curl -X POST localhost:8790/jobs -d '{"questions":[7323],"name":"q7323"}'
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
LESSONS = REPO / "lessons"
JOBS_DIR = LESSONS / "_jobs"
DEFAULT_MASCOT = "apps/intro/public/avatars/chibi"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
STAGES = ("build", "mix", "qc", "publish")


class JobError(RuntimeError):
    pass


class Store:
    """Jobs in memory, mirrored to lessons/_jobs/<id>/job.json."""

    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}
        root.mkdir(parents=True, exist_ok=True)
        for path in root.glob("*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if job.get("status") in ("running", "publishing"):
                job["status"] = "failed"
                job["error"] = "the server stopped while this job was running"
                self._write(job)
            self.jobs[job["id"]] = job

    def _write(self, job: dict) -> None:
        folder = self.root / job["id"]
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "job.json.tmp"
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(folder / "job.json")

    def save(self, job: dict) -> None:
        with self.lock:
            job["updated"] = time.time()
            self.jobs[job["id"]] = job
            self._write(job)

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return json.loads(json.dumps(job)) if job else None

    def all(self) -> list[dict]:
        with self.lock:
            return sorted((dict(j) for j in self.jobs.values()), key=lambda j: j["created"], reverse=True)

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
        for job in reversed(store.all()):
            if job["status"] == "queued":
                self.queue.put(("build", job["id"]))
        threading.Thread(target=self._loop, daemon=True).start()

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
        job["spec"]["publish"] = {**job["spec"]["publish"], **overrides, "client": client}
        job["status"] = "queued_publish"
        self.store.save(job)
        self.queue.put(("publish", job_id))
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
        if job["status"] in ("queued", "awaiting_approval", "queued_publish"):
            job["status"] = "cancelled"
            self.store.save(job)
        return job

    # -- worker --------------------------------------------------------------------------------

    def _loop(self) -> None:
        while True:
            kind, job_id = self.queue.get()
            job = self.store.get(job_id)
            if not job or job_id in self.cancelled or job["status"] == "cancelled":
                continue
            try:
                if kind == "build":
                    self._build(job)
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

    def _run(self, job: dict, stage: str, cmd: list[str]) -> str:
        """Runs one step, streams its output to job.log, returns stdout; raises when it fails."""
        job["stages"][stage] = {"status": "running", "started": time.time()}
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
        return [sys.executable, str(SCRIPTS / script), *args]

    def _build(self, job: dict) -> None:
        spec = job["spec"]
        out = LESSONS / spec["name"]
        out.mkdir(parents=True, exist_ok=True)
        name = spec["name"]
        job["status"] = "running"
        job["outputs"]["folder"] = str(out)
        self.store.save(job)

        cmd = self._py("opencut_ptc.py", "lesson", "--out", str(out), "--name", name, "--title", spec["title"])
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
            if spec["karaoke"]:
                cmd.append("--karaoke")
        if spec["level"]:
            cmd += ["--level", spec["level"]]
        if spec["mascot"]:
            cmd += ["--mascot", spec["mascot"]]
        if spec["burn_subtitles"]:
            cmd.append("--burn-subtitles")
        cmd.append("--dry-run" if spec["dry_run"] else "--render")

        stdout = self._run(job, "build", cmd)
        report = _last_json(stdout)
        job["outputs"]["build"] = report
        if spec["dry_run"]:
            for s in ("mix", "qc", "publish"):
                job["stages"][s]["status"] = "skipped"
            job["status"] = "done"
            self.store.save(job)
            return
        video = (report or {}).get("video")
        if not video or not Path(video).exists():
            raise JobError("build finished without a video; see qc.json in the lesson folder")
        if (report.get("qc") or {}).get("engine", {}).get("ok") is False:
            job["outputs"]["warnings"] = ["engine QC still finds suspect lines after the rebuilds; see qc.json"]

        final = out / f"{name}.final.mp4"
        markers = out / f"{name}.markers.json"
        mix = self._py("lesson_audio.py", "mix", video, "-o", str(final))
        if markers.exists():
            mix += ["--markers", str(markers)]
        if spec["bgm"]:
            mix += ["--bgm", spec["bgm"]]
        self._run(job, "mix", mix)
        job["outputs"]["final"] = str(final)

        self._run(job, "qc", self._py("lesson_qc.py", "video", str(final)))
        self._qc_report(job, out, name)

        self._run(job, "publish", self._publish_cmd(job, dry_run=True))
        job["stages"]["publish"]["status"] = "dry_run"
        job["status"] = "awaiting_approval"
        self.store.save(job)
        self._log(job["id"], f"\n>>> watch {final}, then POST /jobs/{job['id']}/publish to upload")

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
        if dry_run:
            cmd.append("--dry-run")
        else:
            cmd += ["--qc-report", str(out / f"{name}.qc-report.json")]
        return cmd

    def _publish(self, job: dict) -> None:
        job["status"] = "publishing"
        self.store.save(job)
        stdout = self._run(job, "publish", self._publish_cmd(job, dry_run=False))
        found = re.search(r"https://youtu\.be/\S+", stdout)
        job["outputs"]["youtube"] = found.group(0) if found else None
        job["status"] = "done"
        self.store.save(job)


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
    args = parser.parse_args(argv)
    store = Store(JOBS_DIR)
    runner = Runner(store)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, runner))
    print(f"lesson jobs on http://{args.host}:{args.port} (state in {JOBS_DIR})", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
