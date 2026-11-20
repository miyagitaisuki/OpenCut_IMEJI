#!/usr/bin/env python3
"""Upload a rendered lesson to YouTube (unlisted by default).

Standard library only. Needs an OAuth "Desktop app" client JSON from Google Cloud
(YouTube Data API v3 enabled).

  python scripts/publish_youtube.py bai10.youtube.mp4 --client client_secret.json \
      --title "N4 第10課" --markers bai10.markers.json --captions bai10.vtt \
      --playlist "N4 学習" [--thumbnail bai10.thumb.png] [--privacy unlisted|private|public] [--description-file d.txt]

First run opens a browser to authorise; the token is cached in ~/.opencut/youtube_token.json.
Default quota is ~6 uploads/day (1600 units each of 10000).

markers.json: a list (or {"markers": [...]}) of objects with a time in seconds
(`time`, `at`, `start` or `seconds`; `ms` variants also accepted) and a `label`/`title`/`name`.
"""
import argparse, base64, hashlib, http.server, json, os, secrets, sys, threading
import time, urllib.error, urllib.parse, urllib.request, webbrowser

API = "https://www.googleapis.com"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
TOKEN_PATH = os.path.expanduser("~/.opencut/youtube_token.json")


def request(method, url, headers=None, data=None, retries=4):
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            if e.code in (500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            if e.code == 308:  # resumable upload: incomplete
                return 308, dict(e.headers), b""
            sys.exit(f"HTTP {e.code} {url}\n{e.read().decode(errors='replace')}")
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def post_form(url, form):
    body = urllib.parse.urlencode(form).encode()
    _, _, out = request("POST", url, {"Content-Type": "application/x-www-form-urlencoded"}, body)
    return json.loads(out)


def get_token(client_path):
    c = json.load(open(client_path, encoding="utf-8"))
    c = c.get("installed") or c.get("web") or c
    cid, secret = c["client_id"], c["client_secret"]
    if os.path.exists(TOKEN_PATH):
        t = json.load(open(TOKEN_PATH))
        if t.get("refresh_token"):
            r = post_form("https://oauth2.googleapis.com/token", {
                "client_id": cid, "client_secret": secret,
                "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
            return r["access_token"]
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    box = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            box["q"] = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("OK - you can close this tab.".encode())
        def log_message(self, *a): pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Open this URL if the browser does not start:\n" + url)
    webbrowser.open(url)
    threading.Thread(target=srv.handle_request).start()
    while "q" not in box:
        time.sleep(0.2)
    if "code" not in box["q"]:
        sys.exit("Authorisation failed: " + str(box["q"]))
    r = post_form("https://oauth2.googleapis.com/token", {
        "client_id": cid, "client_secret": secret, "code": box["q"]["code"][0],
        "code_verifier": verifier, "redirect_uri": redirect, "grant_type": "authorization_code"})
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    json.dump({"refresh_token": r["refresh_token"]}, open(TOKEN_PATH, "w"))
    try: os.chmod(TOKEN_PATH, 0o600)
    except OSError: pass
    return r["access_token"]


def chapters(path):
    data = json.load(open(path, encoding="utf-8"))
    items = data.get("markers", []) if isinstance(data, dict) else data
    out = []
    for m in items:
        t = next((m[k] for k in ("time", "at", "start", "seconds") if k in m), None)
        if t is None:
            ms = next((m[k] for k in ("ms", "time_ms", "start_ms") if k in m), None)
            t = None if ms is None else ms / 1000
        label = next((m[k] for k in ("label", "title", "name") if m.get(k)), None)
        if t is not None and label:
            out.append((float(t), str(label)))
    out.sort()
    # YouTube needs: first at 0:00, at least 3, each >= 10 s
    if out and out[0][0] > 0:
        out.insert(0, (0.0, "イントロ"))
    else:
        out = [(0.0, out[0][1])] + out[1:] if out else out
    keep = []
    for t, l in out:
        if not keep or t - keep[-1][0] >= 10:
            keep.append((t, l))
    return keep if len(keep) >= 3 else []


def stamp(t):
    t = int(t)
    h, m, s = t // 3600, t % 3600 // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def upload(token, video, meta):
    auth = {"Authorization": f"Bearer {token}"}
    size = os.path.getsize(video)
    _, h, _ = request("POST", f"{API}/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                   {**auth, "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/*"},
                   json.dumps(meta).encode())
    loc = {k.lower(): v for k, v in h.items()}["location"]
    chunk, pos = 8 * 1024 * 1024, 0
    with open(video, "rb") as f:
        while True:
            f.seek(pos)
            data = f.read(chunk)
            end = pos + len(data) - 1
            st, h, out = request("PUT", loc, {"Content-Length": str(len(data)),
                              "Content-Range": f"bytes {pos}-{end}/{size}"}, data)
            if st in (200, 201):
                return json.loads(out)
            rng = {k.lower(): v for k, v in h.items()}.get("range")
            pos = int(rng.split("-")[1]) + 1 if rng else end + 1
            print(f"\r{pos * 100 // size}%", end="", flush=True)


def api(token, method, path, params, body=None, raw=None, ctype=None):
    url = f"{API}{path}?" + urllib.parse.urlencode(params)
    h = {"Authorization": f"Bearer {token}"}
    data = raw
    if body is not None:
        data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    if ctype:
        h["Content-Type"] = ctype
    _, _, out = request(method, url, h, data)
    return json.loads(out) if out else {}


def find_or_create_playlist(token, title, privacy):
    page = None
    while True:
        r = api(token, "GET", "/youtube/v3/playlists",
                {"part": "snippet", "mine": "true", "maxResults": 50, **({"pageToken": page} if page else {})})
        for p in r.get("items", []):
            if p["snippet"]["title"] == title:
                return p["id"]
        page = r.get("nextPageToken")
        if not page:
            break
    r = api(token, "POST", "/youtube/v3/playlists", {"part": "snippet,status"},
            {"snippet": {"title": title}, "status": {"privacyStatus": privacy}})
    return r["id"]


def gate_qc(path):
    """Refuses a real upload unless the lesson's QC report (`lesson_qc.py report --out`) says PASSED.
    A dry run needs no report: it uploads nothing."""
    if not path:
        sys.exit("refusing to upload: no --qc-report. Make one: python scripts/lesson_qc.py report <project.json> --out <file>")
    try:
        report = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as error:
        sys.exit(f"refusing to upload: cannot read the QC report {path}: {error}")
    status = report.get("status")
    if status != "PASSED":
        issues = report.get("issues", [])
        lines = [f"  {i.get('issue_id')} {i.get('type')} {i.get('scene_id', '')}" for i in issues[:10]]
        note = f" (circuit breaker: {report['circuit_reason']})" if report.get("circuit_reason") else ""
        unchecked = f"; not checked: {', '.join(report.get('unchecked', []))}" if report.get("unchecked") else ""
        sys.exit(f"refusing to upload: QC status is {status}{note}{unchecked}\n" + "\n".join(lines))
    print(f"QC passed ({path}); uploading")


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("video")
    a.add_argument("--client", required=True, help="OAuth client JSON")
    a.add_argument("--title", required=True)
    a.add_argument("--description", default="")
    a.add_argument("--description-file")
    a.add_argument("--markers", help="<name>.markers.json -> chapters")
    a.add_argument("--captions", action="append", default=[], help=".vtt/.srt (repeatable)")
    a.add_argument("--caption-lang", default="ja")
    a.add_argument("--thumbnail", help="PNG/JPG (1280x720, < 2 MB); needs a verified channel, a refusal is only a warning")
    a.add_argument("--playlist")
    a.add_argument("--privacy", default="unlisted", choices=["unlisted", "private", "public"])
    a.add_argument("--tags", default="日本語,JLPT")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--qc-report", help="lesson_qc.py report JSON; a real upload needs status PASSED")
    o = a.parse_args()

    desc = open(o.description_file, encoding="utf-8").read() if o.description_file else o.description
    if o.markers:
        ch = chapters(o.markers)
        if ch:
            desc = (desc + "\n\n" if desc else "") + "\n".join(f"{stamp(t)} {l}" for t, l in ch)
        else:
            print("Markers give fewer than 3 usable chapters; skipping chapter list.")
    meta = {"snippet": {"title": o.title[:100], "description": desc, "categoryId": "27",
                        "defaultLanguage": "ja", "tags": [t for t in o.tags.split(",") if t]},
            "status": {"privacyStatus": o.privacy, "selfDeclaredMadeForKids": False}}
    if o.dry_run:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        return
    gate_qc(o.qc_report)
    token = get_token(o.client)
    vid = upload(token, o.video, meta)["id"]
    print(f"\nUploaded: https://youtu.be/{vid} ({o.privacy})")
    for c in o.captions:
        mime = "text/vtt" if c.endswith(".vtt") else "application/x-subrip"
        boundary = secrets.token_hex(8)
        part = json.dumps({"snippet": {"videoId": vid, "language": o.caption_lang, "name": o.caption_lang}})
        body = (f"--{boundary}\r\nContent-Type: application/json\r\n\r\n{part}\r\n"
                f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() + open(c, "rb").read() \
               + f"\r\n--{boundary}--".encode()
        url = f"{API}/upload/youtube/v3/captions?uploadType=multipart&part=snippet"
        request("POST", url, {"Authorization": f"Bearer {token}",
                           "Content-Type": f"multipart/related; boundary={boundary}"}, body)
        print("Caption uploaded:", c)
    if o.thumbnail:
        mime = "image/png" if o.thumbnail.lower().endswith(".png") else "image/jpeg"
        try:
            request("POST", f"{API}/upload/youtube/v3/thumbnails/set?videoId={vid}&uploadType=media",
                    {"Authorization": f"Bearer {token}", "Content-Type": mime}, open(o.thumbnail, "rb").read())
            print("Thumbnail set:", o.thumbnail)
        except SystemExit as error:  # `request` exits on an HTTP error; the upload itself already worked
            print("Thumbnail not set (the channel may need phone verification):", error)
    if o.playlist:
        pid = find_or_create_playlist(token, o.playlist, o.privacy if o.privacy != "public" else "unlisted")
        api(token, "POST", "/youtube/v3/playlistItems", {"part": "snippet"},
            {"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": vid}}})
        print("Added to playlist:", o.playlist)


if __name__ == "__main__":
    main()
