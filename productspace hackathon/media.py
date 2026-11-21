import os
import re
import subprocess
import tempfile
from pathlib import Path
import imageio_ffmpeg
import requests

FF = imageio_ffmpeg.get_ffmpeg_exe()
INPUT_FLAGS = [
    "-protocol_whitelist",
    "file,pipe",
    "-format_whitelist",
    "mov,matroska,webm,mp3,wav,aiff,flac,ogg,aac,avi,mpegts,mpeg,asf",
]


def run(args, timeout=600):
    result = subprocess.run(
        [FF, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise ValueError("The media processor could not read or encode this file.")
    return result


def probe(path):
    result = subprocess.run(
        [FF, "-hide_banner", *INPUT_FLAGS, "-i", str(path)],
        capture_output=True,
        timeout=30,
    )
    info = result.stderr.decode(errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    if not m or "Audio:" not in info and "Video:" not in info:
        raise ValueError("Choose a playable video or podcast recording.")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), "Video:" in info


def transcribe(path, duration, lang, progress):
    key = os.getenv("SARVAM_API_KEY")
    if not key:
        raise ValueError("Add a timed SRT or configure Sarvam transcription.")
    rows = []
    with tempfile.TemporaryDirectory(dir=path.parent) as temp:
        wav = Path(temp) / "part.wav"
        for start in range(0, int(duration + 0.999), 25):
            progress(f"Transcribing {int(100 * start / duration)}%")
            run(
                [
                    "-ss",
                    start,
                    *INPUT_FLAGS,
                    "-i",
                    path,
                    "-t",
                    25,
                    "-vn",
                    "-ar",
                    16000,
                    "-ac",
                    1,
                    wav,
                ]
            )
            with wav.open("rb") as f:
                resp = requests.post(
                    "https://api.sarvam.ai/speech-to-text",
                    headers={"api-subscription-key": key},
                    files={"file": ("part.wav", f, "audio/wav")},
                    data={
                        "model": "saaras:v3",
                        "with_timestamps": "true",
                        "language_code": lang,
                    },
                    timeout=90,
                )
            if not resp.ok:
                raise ValueError(
                    f"Sarvam returned HTTP {resp.status_code}. Check the server key and quota."
                )
            data = resp.json()
            stamps = data.get("timestamps") or {}
            parts = list(
                zip(
                    stamps.get("start_time_seconds", []),
                    stamps.get("end_time_seconds", []),
                    stamps.get("words", []),
                )
            )
            if not parts and data.get("transcript"):
                parts = [(0, min(25, duration - start), data["transcript"])]
            rows.extend(
                [start + a, min(duration, start + b), t]
                for a, b, t in parts
                if b > a and t.strip()
            )
    if not rows:
        raise ValueError("No speech was detected.")
    return rows


def source_levels(path):
    # Equal 200 ms bins, before any export normalization or subtitle processing.
    filters = "aresample=8000,asetnsamples=n=1600,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-"
    result = subprocess.run(
        [
            FF,
            "-nostdin",
            "-loglevel",
            "error",
            *INPUT_FLAGS,
            "-i",
            str(path),
            "-vn",
            "-af",
            filters,
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        timeout=600,
    )
    return [
        max(-70, min(0, float(v)))
        for v in re.findall(rb"RMS_level=(-?[\d.]+|-inf)", result.stdout)
    ]


def captions(clip, platform="YouTube"):
    def stamp(s):
        ms = round(max(0, s) * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    # Interpolate within a supplied phrase when word timestamps are unavailable.
    width = {"YouTube": 7, "Instagram": 5, "LinkedIn": 12}[platform]
    cues = []
    for start, end, text in clip["rows"]:
        words = text.split()
        for i in range(0, len(words), width):
            stop = min(len(words), i + width)
            cues.append(
                (
                    start + (end - start) * i / len(words),
                    start + (end - start) * stop / len(words),
                    " ".join(words[i:stop]),
                )
            )
    return (
        "\n\n".join(
            f"{i + 1}\n{stamp(a - clip['start'])} --> {stamp(b - clip['start'])}\n{text}"
            for i, (a, b, text) in enumerate(cues)
        )
        + "\n"
    )


def render(source, clip, directory, platform="YouTube"):
    if round(clip["end"] - clip["start"], 4) < 30:
        raise ValueError("Every generated clip must be at least 30 seconds.")
    out = directory / (clip["id"] + "-" + platform + ".mp4")
    if out.exists():
        return out
    _, video = probe(source)
    with tempfile.TemporaryDirectory(dir=directory) as d:
        temp = Path(d)
        sub = temp / "captions.srt"
        sub.write_text(captions(clip, platform))
        inputs = ["-ss", clip["start"], *INPUT_FLAGS, "-i", source]
        if video:
            vf = "[0:v]scale=540:960:force_original_aspect_ratio=decrease,pad=540:960:(ow-iw)/2:(oh-ih)/2:color=0x181920,setsar=1"
        else:
            inputs += ["-loop", "1", "-i", Path(__file__).parent / "static/cover.jpg"]
            vf = "[1:v]scale=540:960:force_original_aspect_ratio=increase,crop=540:960,setsar=1"
        # Relative filter path keeps spaces and punctuation in the workspace path harmless.
        args = [
            FF,
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            *map(str, inputs),
            "-t",
            str(clip["end"] - clip["start"]),
            "-filter_complex",
            vf
            + ",subtitles=captions.srt:force_style='FontSize=13,Alignment=2,MarginV=34,Outline=2'[v]",
            "-map",
            "[v]",
            "-map",
            "0:a?",
            "-r",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "cut.mp4",
        ]
        p = subprocess.run(args, cwd=temp, capture_output=True, timeout=600)
        if p.returncode:
            raise ValueError(
                "Export failed. Check that FFmpeg supports libass subtitles and H.264."
            )
        (temp / "cut.mp4").replace(out)
    return out
