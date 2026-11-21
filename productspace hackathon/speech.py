"""Offline transcription with English and Hindi Vosk acoustic models."""

import functools
import hashlib
import json
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path
import requests
from vosk import KaldiRecognizer, Model, SetLogLevel

from media import FF, INPUT_FLAGS

MODELS = {"en-IN": "vosk-model-small-en-us-0.15", "hi-IN": "vosk-model-small-hi-0.22"}
model_lock = threading.Lock()
SetLogLevel(-1)


@functools.lru_cache(maxsize=2)
def model_for(language, directory):
    name = MODELS.get(language, MODELS["en-IN"])
    folder = directory / name
    with model_lock:
        if not (folder / "am/final.mdl").is_file():
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=directory) as work:
                archive = Path(work) / "model.zip"
                with requests.get(
                    "https://alphacephei.com/vosk/models/" + name + ".zip",
                    stream=True,
                    timeout=(15, 100),
                ) as resp:
                    resp.raise_for_status()
                    with archive.open("wb") as out:
                        for chunk in resp.iter_content(512 * 1024):
                            out.write(chunk)
                checksums = {
                    "vosk-model-small-en-us-0.15": "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498",
                    "vosk-model-small-hi-0.22": "7c50a10866889f0ac21d912c20537a055a597ed09fc1d3e5bcd798f9f0017e48",
                }
                with archive.open("rb") as stream:
                    if (
                        hashlib.file_digest(stream, "sha256").hexdigest()
                        != checksums[name]
                    ):
                        raise ValueError(
                            "Speech model download was incomplete. Retry the import."
                        )
                with zipfile.ZipFile(archive) as z:
                    for path in z.namelist():
                        if (
                            not (Path(work) / path)
                            .resolve()
                            .is_relative_to(Path(work).resolve() / name)
                        ):
                            raise ValueError("Unexpected model archive.")
                    z.extractall(work)
                (Path(work) / name).replace(folder)
        return Model(str(folder))


def local_transcribe(path, duration, lang, progress, models):
    progress("Transcribing · preparing offline speech model")
    recognizer = KaldiRecognizer(model_for(lang, models), 16000)
    recognizer.SetWords(True)
    cues = []

    def append(result):
        words = result.get("result", [])
        group = []
        for word in words:
            if group and (word["start"] - group[-1]["end"] > 0.65 or len(group) >= 15):
                cues.append(
                    [
                        group[0]["start"],
                        group[-1]["end"],
                        " ".join(w["word"] for w in group),
                    ]
                )
                group = []
            group.append(word)
        if group:
            cues.append(
                [
                    group[0]["start"],
                    group[-1]["end"],
                    " ".join(w["word"] for w in group),
                ]
            )

    args = [
        FF,
        "-nostdin",
        "-loglevel",
        "error",
        *INPUT_FLAGS,
        "-i",
        str(path),
        "-vn",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "s16le",
        "pipe:1",
    ]
    read = 0
    with subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    ) as decoder:
        try:
            while chunk := decoder.stdout.read(64000):
                if recognizer.AcceptWaveform(chunk):
                    append(json.loads(recognizer.Result()))
                read += len(chunk)
                if read % 320000 == 0:
                    progress(
                        f"Transcribing · {min(99, int(100 * read / (32000 * duration)))}%"
                    )
            append(json.loads(recognizer.FinalResult()))
        finally:
            decoder.stdout.close()
            if decoder.poll() is None:
                decoder.terminate()
    if not cues:
        raise ValueError("No speech was detected. Try a timed SRT or another language.")
    return cues
