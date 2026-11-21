"""Public media URLs and canonical YouTube watch links."""

import ipaddress
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


def fetch(url, path):
    checked(url)
    video = youtube_id(url)
    if video:
        with tempfile.TemporaryDirectory(dir=path.parent) as work:
            root = Path(work).resolve()
            encoder = root / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
            try:
                encoder.symlink_to(FF)
            except OSError:
                shutil.copy2(FF, encoder)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "yt_dlp",
                    "--ignore-config",
                    "--no-playlist",
                    "--no-cache-dir",
                    "--no-part",
                    "--max-filesize",
                    "512M",
                    "--match-filters",
                    "duration <= 10800 & !is_live",
                    "--socket-timeout",
                    "20",
                    "--retries",
                    "1",
                    "--ffmpeg-location",
                    str(encoder),
                    "--merge-output-format",
                    "mp4",
                    "-f",
                    "best[height<=720][protocol=https]/bestvideo[height<=720][ext=mp4][protocol=https]+bestaudio[ext=m4a][protocol=https]/bestvideo[height<=720]+bestaudio",
                    "-o",
                    str(root / "recording.%(ext)s"),
                    "--print",
                    "after_move:title",
                    "https://www.youtube.com/watch?v=" + video,
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            files = [
                f
                for f in root.glob("recording.*")
                if f.name.count(".") == 1 and f.stat().st_size <= MAX_BYTES
            ]
            if result.returncode or len(files) != 1:
                raise ValueError(
                    "YouTube could not supply this recording within the size limit. Try a direct media link or upload the file."
                )
            files[0].replace(path)
            return (
                result.stdout.strip().splitlines()[-1][:150]
                if result.stdout.strip()
                else "YouTube recording"
            )
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
