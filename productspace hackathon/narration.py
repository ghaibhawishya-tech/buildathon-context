"""Make a timed replacement voice track from the finalized transcript."""

import base64
import os
import tempfile
import threading
from pathlib import Path
import requests
from media import run, render

GENERATION = threading.Lock()


def narrated(source, cut, directory, platform):
    voice = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
    track = directory / (cut["id"] + "-voice.m4a")
    output = directory / (cut["id"] + "-" + platform + "-narrated.mp4")
    with GENERATION:
        if output.exists():
            return output
        original = render(source, cut, directory, platform)
        with tempfile.TemporaryDirectory(dir=directory) as work:
            tmp = Path(work)
            if not track.exists():
                key = os.getenv("ELEVENLABS_API_KEY")
                if not key:
                    raise ValueError(
                        "Configure an ElevenLabs key to generate a new voiceover."
                    )
                script = " ".join(r[2] for r in cut["rows"])
                res = requests.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
                    headers={"xi-api-key": key},
                    json={"text": script, "model_id": "eleven_multilingual_v2"},
                    timeout=100,
                )
                if not res.ok:
                    raise ValueError(
                        f"ElevenLabs returned HTTP {res.status_code}. Check the key and available credits."
                    )
                data = res.json()
                alignment = data.get("alignment") or {}
                if "".join(alignment.get("characters", [])) != script:
                    raise ValueError(
                        "ElevenLabs returned a different transcript alignment."
                    )
                starts = alignment["character_start_times_seconds"]
                ends = alignment["character_end_times_seconds"]
                audio = tmp / "speech.mp3"
                audio.write_bytes(base64.b64decode(data["audio_base64"], validate=True))
                cursor = 0
                pieces = []
                for idx, (a, b, line) in enumerate(cut["rows"]):
                    first, last = starts[cursor], ends[cursor + len(line) - 1]
                    ratio = (last - first) / (b - a)
                    if ratio <= 0:
                        raise ValueError("Invalid voice alignment.")
                    speeds = []
                    while ratio < 0.5:
                        speeds.append("atempo=0.5")
                        ratio *= 2
                    speeds.append(f"atempo={ratio:.6f}")
                    delay = round((a - cut["start"]) * 1000)
                    pieces.append(
                        f"[0:a]atrim=start={first}:end={last},asetpts=PTS-STARTPTS,"
                        + ",".join(speeds)
                        + f",adelay={delay}:all=1[a{idx}]"
                    )
                    cursor += len(line) + 1
                mix = (
                    "".join(f"[a{i}]" for i in range(len(pieces)))
                    + f"amix=inputs={len(pieces)}:normalize=0,apad[out]"
                )
                run(
                    [
                        "-i",
                        audio,
                        "-filter_complex",
                        ";".join(pieces + [mix]),
                        "-map",
                        "[out]",
                        "-t",
                        cut["end"] - cut["start"],
                        "-c:a",
                        "aac",
                        tmp / "track.m4a",
                    ]
                )
                (tmp / "track.m4a").replace(track)
            run(
                [
                    "-i",
                    original,
                    "-i",
                    track,
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    tmp / "cut.mp4",
                ]
            )
            (tmp / "cut.mp4").replace(output)
    return output
