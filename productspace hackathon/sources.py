"""Public media URLs and canonical YouTube watch links."""

import ipaddress
import re
import socket
import subprocess
import sys
import time
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
                "--socket-timeout",
                "20",
                "--retries",
                "1",
                "-f",
                "best[protocol=https][ext=mp4]/best[protocol=https]/bestaudio[protocol=https]",
                "-o",
                str(path),
                "--print",
                "after_move:title",
                "https://www.youtube.com/watch?v=" + video,
            ],
            capture_output=True,
            text=True,
            timeout=240,
        )
        if result.returncode or not path.exists():
            raise ValueError(
                "YouTube could not supply this recording. Try a public media file link or upload the source."
            )
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
