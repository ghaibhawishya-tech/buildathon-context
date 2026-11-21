"""Render a 30-second studio cut using the same pipeline as a creator export."""

import json
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from engine import rank
from media import probe, render


def main():
    assets = PROJECT / "motion"
    rows = [
        [s["start"], s["end"], s["line"]]
        for s in json.loads((assets / "script.json").read_text())
    ]
    source = assets / "jessica.mp3"
    chosen = rank(rows, {}, source_duration=probe(source)[0])[0]
    target = PROJECT / "exports"
    target.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target) as temp:
        output = render(source, chosen, Path(temp), "Instagram")
        shutil.copyfile(output, target / "studio_cut.mp4")


if __name__ == "__main__":
    main()
