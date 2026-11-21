import io
import json
import os
import re
import secrets
import sqlite3
import shutil
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import requests
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, request, send_file, session

from narration import narrated
from sources import fetch, checked, youtube_id
from editor import refine
from speech import local_transcribe
from engine import parse_srt, platform_copy, rank
from media import captions, probe, render, transcribe, source_levels

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DATA = Path(os.environ.get("AFTERTONE_DATA", ROOT / "data")).resolve()
DATA.mkdir(exist_ok=True, parents=True)
DB = DATA / "studio.sqlite"
app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=512 * 1024**2,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
pool = ThreadPoolExecutor(max_workers=2)
slots = threading.BoundedSemaphore(6)
render_slots = threading.BoundedSemaphore(2)
PLATFORMS = ("YouTube", "Instagram", "LinkedIn")


@contextmanager
def db():
    con = sqlite3.connect(DB, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


with db() as c:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS config(k PRIMARY KEY,v);
    CREATE TABLE IF NOT EXISTS projects(id PRIMARY KEY,owner,title,status,source,clips,rows);
    CREATE TABLE IF NOT EXISTS edits(owner,project,clip,platform,before,after,PRIMARY KEY(owner,project,clip,platform));
    CREATE TABLE IF NOT EXISTS metrics(owner,project,clip,arc,retention,PRIMARY KEY(owner,project,clip));
    CREATE TABLE IF NOT EXISTS calendar(id PRIMARY KEY,owner,project,clip,platform,copy,at REAL,auto INTEGER,status);
    CREATE TABLE IF NOT EXISTS finals(project,clip,PRIMARY KEY(project,clip));
    CREATE TABLE IF NOT EXISTS channels(owner PRIMARY KEY,refresh);
    """)
    c.execute(
        "INSERT OR IGNORE INTO config VALUES('secret',?)", (secrets.token_hex(32),)
    )
    app.secret_key = c.execute("SELECT v FROM config WHERE k='secret'").fetchone()[0]
    c.execute(
        "UPDATE projects SET status='Processing interrupted. Import the recording again.' WHERE clips IS NULL"
    )
    c.execute(
        "UPDATE calendar SET status='Interrupted. Verify your channel before rescheduling.' WHERE status='Uploading'"
    )


def uid():
    return uuid.uuid4().hex


def owner():
    if "owner" not in session:
        session["owner"] = uid()
    return session["owner"]


@app.before_request
def guard():
    if request.method == "POST" and request.headers.get("Origin"):
        if urlsplit(request.headers["Origin"]).netloc != request.host:
            abort(403)


@app.errorhandler(ValueError)
def invalid(e):
    return jsonify(error=str(e)), 400


def project(pid, who):
    with db() as c:
        row = c.execute(
            "SELECT * FROM projects WHERE id=? AND owner=?", (pid, who)
        ).fetchone()
    if not row:
        abort(404)
    return row


def clip_of(p, cid):
    clips = json.loads(p["clips"] or "[]")
    clip = next((x for x in clips if x["id"] == cid), None)
    if clip:
        return clip
    if re.fullmatch(r"[0-9]+(?:-[0-9]+){1,3}", cid):
        with db() as con:
            saved = con.execute(
                "SELECT 1 FROM finals WHERE project=? AND clip=?", (p["id"], cid)
            ).fetchone()
        if saved:
            archived = DATA / p["id"] / (cid + ".json")
            if archived.is_file():
                return json.loads(archived.read_text())
    abort(404)


def memories(who):
    with db() as c:
        edits = [
            dict(x)
            for x in c.execute(
                "SELECT * FROM edits WHERE owner=? ORDER BY rowid DESC LIMIT 100",
                (who,),
            )
        ]
        metrics = {
            str(i): dict(x)
            for i, x in enumerate(
                c.execute("SELECT arc,retention FROM metrics WHERE owner=?", (who,))
            )
        }
    return edits, metrics


def length(value):
    try:
        seconds = int(str(value))
    except (ValueError, TypeError):
        raise ValueError("Enter a whole number of seconds from 30 to 180.")
    if not 30 <= seconds <= 180:
        raise ValueError("Choose a clip length from 30 to 180 seconds.")
    return seconds


def rank_recording(pid, source, rows, metrics, target=30):
    cache = DATA / pid / "levels.json"
    if cache.exists():
        levels = json.loads(cache.read_text())
    else:
        levels = source_levels(source)
        cache.write_text(json.dumps(levels))
    return rank(rows, metrics, levels, target, probe(source)[0])


def insert(who, title, source, rows=None):
    pid = uid()
    (DATA / pid).mkdir()
    clips = rank_recording(pid, source, rows, memories(who)[1]) if rows else None
    with db() as c:
        c.execute(
            "INSERT INTO projects VALUES(?,?,?,?,?,?,?)",
            (
                pid,
                who,
                title,
                "Ready" if clips else "Reading source",
                str(source),
                json.dumps(clips) if clips else None,
                json.dumps(rows),
            ),
        )
    return pid


@app.get("/")
def home():
    return app.send_static_file("index.html")


@app.get("/api/studio")
def studio():
    who = owner()
    with db() as c:
        projects = [
            dict(r)
            for r in c.execute(
                "SELECT id,title,status FROM projects WHERE owner=? ORDER BY rowid DESC",
                (who,),
            )
        ]
        calendar = [
            dict(r)
            for r in c.execute(
                "SELECT calendar.*,projects.title FROM calendar JOIN projects ON projects.id=calendar.project WHERE calendar.owner=? ORDER BY at",
                (who,),
            )
        ]
        linked = bool(
            c.execute("SELECT 1 FROM channels WHERE owner=?", (who,)).fetchone()
        )
    edits, metrics = memories(who)
    return jsonify(
        projects=projects,
        calendar=calendar,
        edits=len(edits),
        examples=[
            {k: e[k] for k in ("platform", "before", "after")} for e in edits[:6]
        ],
        metrics=list(metrics.values()),
        linked=linked,
        films=(ROOT / "exports/cinematic_video.mp4").is_file()
        and (ROOT / "exports/aftertone_short.mp4").is_file(),
        elevenlabs=bool(os.getenv("ELEVENLABS_API_KEY")),
        sarvam=bool(os.getenv("SARVAM_API_KEY")),
        youtube=bool(
            os.getenv("GOOGLE_CLIENT_ID")
            and os.getenv("GOOGLE_CLIENT_SECRET")
            and os.getenv("PUBLIC_URL")
        ),
    )


@app.post("/api/demo")
def demo():
    who = owner()
    brief = (request.get_json(silent=True) or {}).get("source") == "brief"
    name = "brief" if brief else "demo"
    source = ROOT / "static" / (name + ".mp3")
    with db() as c:
        row = c.execute(
            "SELECT id FROM projects WHERE owner=? AND source=?",
            (who, str(source)),
        ).fetchone()
    pid = (
        row[0]
        if row
        else insert(
            who,
            "The editorial brief" if brief else "The Rough Cut",
            source,
            json.loads((ROOT / (name + ".json")).read_text()),
        )
    )
    return jsonify(id=pid)


def import_window(link, start, minutes):
    if not start:
        return None
    if not youtube_id(link):
        raise ValueError("A timed section requires a YouTube video link.")
    if not re.fullmatch(r"(?:[0-9]{1,3}:)?[0-5]?[0-9]:[0-5][0-9]", start):
        raise ValueError("Use HH:MM:SS or MM:SS for the section start.")
    if not re.fullmatch(r"[0-9]{1,2}", minutes) or not 3 <= int(minutes) <= 15:
        raise ValueError("Choose a section length of 3 to 15 minutes.")
    seconds = sum(
        int(part) * 60**i for i, part in enumerate(reversed(start.split(":")))
    )
    return seconds, seconds + int(minutes) * 60


@app.post("/api/import")
def ingest():
    who = owner()
    volume = shutil.disk_usage(DATA)
    used = sum(f.stat().st_size for f in DATA.glob("*/source") if f.is_file())
    limit = int(os.getenv("AFTERTONE_UPLOAD_BUDGET_MB", "4096")) * 1024**2
    incoming = request.content_length or app.config["MAX_CONTENT_LENGTH"]
    if used + incoming > limit or volume.free < incoming + 1024**3:
        return jsonify(error="The studio has reached its upload storage budget."), 507
    media = request.files.get("media")
    srt = request.files.get("srt")
    link = request.form.get("link", "").strip()
    target = length(request.form.get("seconds", 30))
    if link and media:
        raise ValueError("Choose one source.")
    if link:
        checked(link)
        if used + 512 * 1024**2 > limit:
            raise ValueError("The studio has reached its link import budget.")
    elif not media or not media.filename:
        raise ValueError("Paste a source link or choose a recording.")

    window = import_window(
        link,
        request.form.get("window_start", "").strip(),
        request.form.get("window_minutes", "10"),
    )
    rows = (
        parse_srt(srt.read(4_000_000).decode("utf-8-sig"))
        if srt and srt.filename
        else None
    )
    cloud = request.form.get("sarvam") == "on"
    if cloud and not os.getenv("SARVAM_API_KEY"):
        raise ValueError(
            "Set SARVAM_API_KEY in the studio’s .env file and restart to enable Sarvam."
        )
    if rows and len(rows) > 12000:
        raise ValueError("Import up to 12,000 subtitle cues at once.")
    if not slots.acquire(blocking=False):
        return jsonify(error="The import queue is full. Try again shortly."), 429
    try:
        pid = insert(
            who, "Linked recording" if link else Path(media.filename).stem[:150], ""
        )
        src = DATA / pid / "source"
        if media:
            media.save(src)
        lang = request.form.get("language", "unknown")
        if lang not in ("unknown", "hi-IN", "en-IN"):
            lang = "unknown"
        pool.submit(
            process,
            pid,
            who,
            src,
            rows,
            lang,
            cloud,
            link,
            target,
            window,
        )
    except Exception:
        slots.release()
        raise
    return jsonify(id=pid), 202


def process(pid, who, src, rows, lang, cloud, link, target, window=None):
    def progress(s):
        with db() as c:
            c.execute("UPDATE projects SET status=? WHERE id=?", (s, pid))

    try:
        if link:
            progress("Fetching linked recording")
            title = fetch(link, src, window)
            with db() as c:
                c.execute("UPDATE projects SET title=? WHERE id=?", (title, pid))
        duration, _ = probe(src)
        if duration < target:
            raise ValueError(
                f"The source is {duration:.1f}s. Choose a source at least {target}s long."
            )
        if window and duration > window[1] - window[0] + 10:
            raise ValueError(
                "YouTube did not deliver the requested section. Try a different timestamp or recording."
            )
        if duration > 3 * 3600:
            raise ValueError("Import a recording under three hours.")
        if rows is None:
            if cloud:
                rows = transcribe(src, duration, lang, progress)
            else:
                rows = local_transcribe(src, duration, lang, progress, DATA / "models")
        rows = [[a, min(b, duration), t] for a, b, t in rows if a < duration and b > a]
        if not rows:
            raise ValueError("Caption timestamps fall outside the recording.")
        progress("Finding emotional arcs")
        edits, metrics = memories(who)
        clips = rank_recording(pid, src, rows, metrics, target)
        if cloud:
            clips = refine(clips, edits)
        with db() as c:
            c.execute(
                "UPDATE projects SET status='Ready',source=?,clips=?,rows=? WHERE id=?",
                (str(src), json.dumps(clips), json.dumps(rows), pid),
            )
    except Exception as e:
        if link:
            src.unlink(missing_ok=True)
        progress(
            str(e)[:180]
            if isinstance(e, ValueError)
            else "Import failed. Check the recording and transcription service."
        )
    finally:
        slots.release()


@app.get("/api/projects/<pid>")
def detail(pid):
    who = owner()
    p = project(pid, who)
    clips = json.loads(p["clips"] or "[]")
    if clips and clips[0]["id"].count("-") == 1:
        try:
            clips = rank_recording(
                pid, p["source"], json.loads(p["rows"]), memories(who)[1]
            )
            replace_cuts(p, clips)
        except ValueError as error:
            return jsonify(
                id=pid,
                title=p["title"],
                status=str(error),
                clips=[],
                demo=False,
                seconds=30,
            )
    with db() as con:
        finals = {
            r[0] for r in con.execute("SELECT clip FROM finals WHERE project=?", (pid,))
        }
    edits, _ = memories(who)
    saved_clips = [clip for clip in clips if clip["id"] in finals]
    for cid in sorted(finals - {clip["id"] for clip in clips}):
        archived = DATA / pid / (cid + ".json")
        if archived.is_file() and re.fullmatch(r"[0-9]+(?:-[0-9]+){1,3}", cid):
            saved_clips.append(json.loads(archived.read_text()))
    for clip in [*clips, *saved_clips]:
        clip["final"] = clip["id"] in finals
        clip["copy"] = {
            plat: next(
                (
                    e["after"]
                    for e in edits
                    if (e["project"], e["clip"], e["platform"])
                    == (pid, clip["id"], plat)
                ),
                platform_copy(clip, plat, edits),
            )
            for plat in PLATFORMS
        }
    return jsonify(
        id=pid,
        title=p["title"],
        status=p["status"],
        clips=clips,
        saved=saved_clips,
        seconds=round(clips[0]["end"] - clips[0]["start"]) if clips else 30,
        demo=p["source"] == str(ROOT / "static/demo.mp3"),
    )


@app.get("/api/projects/<pid>/source")
def original(pid):
    p = project(pid, owner())
    if not p["source"]:
        abort(404)
    return send_file(p["source"], download_name=p["title"], conditional=True)


@app.post("/api/projects/<pid>/<cid>/edit")
def edit(pid, cid):
    who = owner()
    clip = clip_of(project(pid, who), cid)
    plat = request.json["platform"]
    after = str(request.json["copy"]).strip()[:2000]
    if plat not in PLATFORMS or not after:
        raise ValueError("Choose a platform and enter your copy.")
    before = platform_copy(clip, plat, memories(who)[0])
    with db() as c:
        c.execute(
            "INSERT INTO edits VALUES(?,?,?,?,?,?) ON CONFLICT(owner,project,clip,platform) DO UPDATE SET after=excluded.after",
            (who, pid, cid, plat, before, after),
        )
    return jsonify(ok=True)


@app.post("/api/projects/<pid>/<cid>/metric")
def metric(pid, cid):
    who = owner()
    clip = clip_of(project(pid, who), cid)
    value = float(request.json["retention"])
    if not 0 <= value <= 100:
        raise ValueError("Retention must be between 0 and 100.")
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO metrics VALUES(?,?,?,?,?)",
            (who, pid, cid, clip["arc"], value),
        )
    return jsonify(ok=True)


@app.post("/api/projects/<pid>/rank")
def rerank(pid):
    who = owner()
    p = project(pid, who)
    if not p["clips"]:
        raise ValueError("Wait for the import to finish.")
    prior = json.loads(p["clips"])[0]
    target = length(
        (request.get_json(silent=True) or {}).get(
            "seconds", max(30, round(prior["end"] - prior["start"]))
        )
    )
    clips = rank_recording(
        pid, p["source"], json.loads(p["rows"]), memories(who)[1], target
    )
    replace_cuts(p, clips)
    return jsonify(ok=True)


def replace_cuts(p, clips):
    pid = p["id"]
    # Keep older cuts addressable for scheduled exports, even when rankings change.
    with db() as c:
        for clip in json.loads(p["clips"]):
            path = DATA / pid / (clip["id"] + ".json")
            pending = path.with_suffix("." + uid() + ".tmp")
            pending.write_text(json.dumps(clip))
            pending.replace(path)
        c.execute("UPDATE projects SET clips=? WHERE id=?", (json.dumps(clips), pid))


@app.post("/api/projects/<pid>/<cid>/finalize")
def finalize(pid, cid):
    cut = clip_of(project(pid, owner()), cid)
    if round(cut["end"] - cut["start"], 4) < 30:
        raise ValueError("Refresh the direction list first.")
    with db() as c:
        c.execute("INSERT OR IGNORE INTO finals VALUES(?,?)", (pid, cid))
    return jsonify(ok=True)


def require_final(pid, cid):
    with db() as c:
        if not c.execute(
            "SELECT 1 FROM finals WHERE project=? AND clip=?", (pid, cid)
        ).fetchone():
            raise ValueError("Finalize this direction first.")


@app.get("/api/projects/<pid>/<cid>/export/<kind>")
def export(pid, cid, kind):
    p = project(pid, owner())
    clip = clip_of(p, cid)
    require_final(pid, cid)
    platform = request.args.get("platform", "YouTube")
    if platform not in PLATFORMS:
        abort(400)
    if kind == "srt":
        return send_file(
            io.BytesIO(captions(clip, platform).encode()),
            download_name="aftertone-" + cid + ".srt",
            as_attachment=True,
        )
    if kind != "mp4":
        abort(404)
    with render_slots:
        path = render(Path(p["source"]), clip, DATA / pid, platform)
    return send_file(
        path,
        download_name="aftertone-" + cid + ".mp4",
        as_attachment=request.args.get("download") == "1",
    )


@app.post("/api/projects/<pid>/<cid>/voice")
def voice(pid, cid):
    p = project(pid, owner())
    cut = clip_of(p, cid)
    require_final(pid, cid)
    platform = request.json.get("platform")
    if platform not in PLATFORMS:
        abort(400)
    if not os.getenv("ELEVENLABS_API_KEY"):
        raise ValueError("Configure ElevenLabs to create an alternate voiceover.")
    with render_slots:
        narrated(Path(p["source"]), cut, DATA / pid, platform)
    return jsonify(url=f"/api/projects/{pid}/{cid}/voice/{platform}")


@app.get("/api/projects/<pid>/<cid>/voice/<platform>")
def download_voice(pid, cid, platform):
    p = project(pid, owner())
    clip_of(p, cid)
    if platform not in PLATFORMS:
        abort(400)
    path = DATA / pid / (cid + "-" + platform + "-narrated.mp4")
    if not path.is_file():
        abort(404)
    return send_file(
        path, as_attachment=True, download_name="aftertone-" + cid + "-narrated.mp4"
    )


@app.get("/films/<name>")
def film(name):
    if name not in ("cinematic_video.mp4", "aftertone_short.mp4", "studio_cut.mp4"):
        abort(404)
    path = ROOT / "exports" / name
    if not path.is_file():
        abort(404)
    return send_file(path, conditional=True)


@app.get("/download")
def download():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name in (
            "README.md",
            "requirements.txt",
            "engine.py",
            "media.py",
            "editor.py",
            "speech.py",
            "app.py",
            "sources.py",
            "kinetic.py",
            "narration.py",
            ".env.example",
            "Dockerfile",
            "demo.json",
            "brief.json",
            ".dockerignore",
        ):
            z.write(ROOT / name, "Aftertone/" + name)
        for f in (ROOT / "motion").rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, "Aftertone/" + str(f.relative_to(ROOT)))
        for name in ("cinematic_video.mp4", "aftertone_short.mp4", "studio_cut.mp4"):
            f = ROOT / "exports" / name
            if f.is_file():
                z.write(f, "Aftertone/exports/" + name)
        for f in (ROOT / "static").iterdir():
            if f.is_file():
                z.write(f, "Aftertone/static/" + f.name)
    buffer.seek(0)
    return send_file(buffer, download_name="Aftertone-Studio.zip", as_attachment=True)


@app.get("/youtube/connect")
def connect():
    if not all(
        os.getenv(k) for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "PUBLIC_URL")
    ):
        raise ValueError("Configure YouTube OAuth on the server first.")
    owner()
    session["state"] = secrets.token_urlsafe(32)
    args = dict(
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        redirect_uri=os.environ["PUBLIC_URL"].rstrip("/") + "/youtube/callback",
        response_type="code",
        scope="https://www.googleapis.com/auth/youtube.upload",
        state=session["state"],
        access_type="offline",
        prompt="consent",
    )
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(args))


def google_token(**values):
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data=dict(
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            **values,
        ),
        timeout=30,
    )
    if not r.ok:
        raise ValueError(
            "Google authorization expired or was declined. Reconnect your channel."
        )
    return r.json()


@app.get("/youtube/callback")
def callback():
    expected = session.pop("state", None)
    if not expected or not secrets.compare_digest(
        expected, request.args.get("state", "")
    ):
        abort(403)
    result = google_token(
        code=request.args.get("code", ""),
        redirect_uri=os.environ["PUBLIC_URL"].rstrip("/") + "/youtube/callback",
        grant_type="authorization_code",
    )
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO channels VALUES(?,?)",
            (owner(), result["refresh_token"]),
        )
    return redirect("/")


@app.post("/api/projects/<pid>/<cid>/schedule")
def schedule(pid, cid):
    who = owner()
    clip_of(project(pid, who), cid)
    require_final(pid, cid)
    d = request.json
    at = float(d["at"])
    if (
        not time.time() - 60 < at < time.time() + 366 * 86400
        or d["platform"] not in PLATFORMS
    ):
        raise ValueError("Choose a future date within a year and a valid platform.")
    auto = d.get("auto") is True
    with db() as c:
        if auto and (
            d["platform"] != "YouTube"
            or not c.execute("SELECT 1 FROM channels WHERE owner=?", (who,)).fetchone()
        ):
            raise ValueError("Connect your own YouTube channel to enable publishing.")
        c.execute(
            "INSERT INTO calendar VALUES(?,?,?,?,?,?,?,?,?)",
            (
                uid(),
                who,
                pid,
                cid,
                d["platform"],
                str(d["copy"])[:2000],
                at,
                auto,
                "Scheduled" if auto else "Planned",
            ),
        )
    return jsonify(ok=True)


@app.post("/api/calendar/<item>/cancel")
def cancel(item):
    with db() as c:
        c.execute(
            "UPDATE calendar SET status='Cancelled',auto=0 WHERE id=? AND owner=? AND status IN ('Planned','Scheduled')",
            (item, owner()),
        )
    return jsonify(ok=True)


def publish(row):
    p = project(row["project"], row["owner"])
    directory = DATA / p["id"]
    clip = next((x for x in json.loads(p["clips"]) if x["id"] == row["clip"]), None)
    if not clip:
        clip = json.loads((directory / (row["clip"] + ".json")).read_text())
    with render_slots:
        path = render(Path(p["source"]), clip, directory)
    with db() as c:
        refresh = c.execute(
            "SELECT refresh FROM channels WHERE owner=?", (row["owner"],)
        ).fetchone()[0]
    token = google_token(refresh_token=refresh, grant_type="refresh_token")[
        "access_token"
    ]
    hdr = {"Authorization": "Bearer " + token}
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={
            "uploadType": "resumable",
            "part": "snippet,status",
            "notifySubscribers": "false",
        },
        headers={**hdr, "X-Upload-Content-Type": "video/mp4"},
        json={
            "snippet": {
                "title": (row["copy"].splitlines() or [p["title"]])[0][:100],
                "description": row["copy"],
            },
            "status": {"privacyStatus": "public"},
        },
        timeout=30,
    )
    init.raise_for_status()
    with path.open("rb") as f:
        resp = requests.put(
            init.headers["Location"],
            data=f,
            headers={"Content-Type": "video/mp4"},
            timeout=300,
        )
    resp.raise_for_status()
    return "Uploaded · " + resp.json()["id"]


def worker():
    while True:
        with db() as c:
            row = c.execute(
                "SELECT * FROM calendar WHERE auto=1 AND status='Scheduled' AND at<=? ORDER BY at LIMIT 1",
                (time.time(),),
            ).fetchone()
            if (
                row
                and c.execute(
                    "UPDATE calendar SET status='Uploading' WHERE id=? AND status='Scheduled'",
                    (row["id"],),
                ).rowcount
                == 0
            ):
                row = None
        if row:
            try:
                status = publish(row)
            except Exception:
                status = "Upload failed. Check channel access and verify YouTube Studio before rescheduling."
            with db() as c:
                c.execute(
                    "UPDATE calendar SET status=? WHERE id=?", (status, row["id"])
                )
        else:
            time.sleep(5)


if __name__ == "__main__":
    from waitress import serve

    threading.Thread(target=worker, daemon=True).start()
    serve(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8787")),
        max_request_body_size=512 * 1024**2,
    )
