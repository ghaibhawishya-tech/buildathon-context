"""Public media URLs and canonical YouTube watch links."""

import ipaddress
import json
import re
import socket
import subprocess
import sys
import time
import tempfile
import shutil
from media import FF
from urllib.parse import urljoin, urlsplit, parse_qs, unquote
from pathlib import Path

MAX_BYTES = 512 * 1024**2


def youtube_id(url):
    parsed = urlsplit(url)
    host = parsed.hostname
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        return None
    video = (
        parsed.path[1:]
        if host == "youtu.be"
        else parse_qs(parsed.query).get("v", [""])[0]
    )
    if parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
        video = parsed.path.split("/")[2]
    if not re.fullmatch(r"[a-zA-Z0-9_-]{11}", video):
        raise ValueError("Paste a single YouTube video link.")
    return video


def checked(url):
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.port not in (None, 443)
    ):
        raise ValueError("Use a public HTTPS video or podcast link.")
    return p


def youtube_failure(details):
    details = details.casefold()
    if any(
        phrase in details
        for phrase in ("max-filesize", "larger than the maximum", "max filesize")
    ):
        return "This YouTube download exceeds Aftertone’s 512 MiB limit. Try a shorter recording or upload a smaller copy."
    if any(
        phrase in details
        for phrase in (
            "confirm you’re not a bot",
            "confirm you're not a bot",
            "sign in",
            "private video",
            "members-only",
            "age-restricted",
        )
    ):
        return "YouTube requires sign-in or restricted access for this download. Try another public video or upload your copy."
    if any(
        phrase in details
        for phrase in (
            "does not pass filter",
            "does not pass the filter",
            "is_live",
            "live event will begin",
            "live stream is offline",
        )
    ):
        return "Choose a finished YouTube recording no longer than three hours."
    if any(
        phrase in details
        for phrase in (
            "video unavailable",
            "has been removed",
            "not made this video available",
        )
    ):
        return "This video is unavailable to the studio. Try another public video or upload your copy."
    if any(
        phrase in details
        for phrase in (
            "timed out",
            "connection reset",
            "temporarily unavailable",
            "http error 429",
        )
    ):
        return "The YouTube download was interrupted. Try the link again or upload your copy."
    if (
        "requested format is not available" in details
        or "challenge solving failed" in details
    ):
        return "YouTube did not provide a playable download for this link. Try another public video or upload your copy."
    return "The YouTube download failed. Try another public video or upload your copy."


def fetch_youtube(video, path):
    with tempfile.TemporaryDirectory(dir=path.parent) as work:
        root = Path(work).resolve()
        encoder = root / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        try:
            encoder.symlink_to(FF)
        except OSError:
            shutil.copy2(FF, encoder)
        receipt = root / "download.json"
        runtime = ["--js-runtimes", "node"] if shutil.which("node") else []
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--ignore-config",
            "--no-playlist",
            "--no-cache-dir",
            "--no-part",
            "--no-quiet",
            "--no-progress",
            "--max-filesize",
            str(MAX_BYTES),
            "--match-filters",
            "duration <= 10800 & !is_live",
            "--socket-timeout",
            "20",
            "--retries",
            "1",
            *runtime,
            "--ffmpeg-location",
            str(encoder),
            "--merge-output-format",
            "mp4",
            "-S",
            "res:480",
            "-f",
            "bestvideo[height<=720][ext=mp4][protocol=https]+bestaudio[ext=m4a][protocol=https]/best[height<=720][protocol=https]/bestvideo[height<=720][protocol=https]+bestaudio[protocol=https]",
            "-o",
            str(root / "recording.%(ext)s"),
            "--print-to-file",
            'after_move:{"title":%(title)j,"path":%(filepath)j}',
            str(receipt),
            "https://www.youtube.com/watch?v=" + video,
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            raise ValueError(
                "The YouTube download took too long. Try a shorter recording or upload your copy."
            ) from None
        if result.returncode or not receipt.is_file():
            raise ValueError(youtube_failure(result.stderr + "\n" + result.stdout))
        info = json.loads(receipt.read_text())
        downloaded = Path(info["path"])
        if downloaded.parent != root or not downloaded.is_file():
            raise ValueError("The YouTube download did not produce a playable file.")
        if downloaded.stat().st_size > MAX_BYTES:
            raise ValueError(youtube_failure("max-filesize"))
        downloaded.replace(path)
        return str(info["title"])[:150]


def fetch(url, path):
    checked(url)
    video = youtube_id(url)
    if video:
        return fetch_youtube(video, path)
    deadline = time.monotonic() + 240
    for _ in range(6):
        parsed = checked(url)
        host = parsed.hostname.encode("idna").decode()
        ips = {
            ipaddress.ip_address(row[4][0])
            for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
        if (
            not ips
            or any(
                not ip.is_global
                or ip.is_multicast
                or ip.ipv4_mapped
                and not ip.ipv4_mapped.is_global
                for ip in ips
                if isinstance(ip, ipaddress.IPv6Address)
            )
            or any(not ip.is_global or ip.is_multicast for ip in ips)
        ):
            raise ValueError("Choose a publicly reachable media file.")
        ip = min(ips, key=lambda a: a.version)
        pin = f"[{ip}]" if ip.version == 6 else str(ip)
        args = [
            "curl",
            "--disable",
            "--noproxy",
            "*",
            "--silent",
            "--show-error",
            "--globoff",
            "--proto",
            "=https",
            "--resolve",
            f"{host}:443:{pin}",
            "--max-filesize",
            str(MAX_BYTES),
            "--max-time",
            str(max(1, int(deadline - time.monotonic()))),
            "--output",
            str(path),
            "--write-out",
            "%{http_code}\n%{redirect_url}\n%{content_type}",
            "--",
            url,
        ]
        p = subprocess.run(args, capture_output=True, text=True, timeout=245)
        if p.returncode:
            raise ValueError(
                "Download failed. Check the link, file size and access permissions."
            )
        status, redirect, mime = p.stdout.split("\n", 2)
        if status.startswith("3") and redirect:
            url = urljoin(url, redirect)
            continue
        if not status.startswith("2") or "text/html" in mime:
            raise ValueError(
                "That page does not serve media. Paste the direct audio/video URL or a YouTube watch link."
            )
        return Path(unquote(parsed.path)).stem[:150] or "Linked recording"
    raise ValueError("This link redirected too many times.")
