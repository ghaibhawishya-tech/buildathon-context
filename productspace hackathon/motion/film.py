"""Render the Aftertone title film. Run from any directory with the studio venv."""

import argparse
import array
import bisect
import json
import math
import subprocess
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SCRIPT = json.loads((ROOT / "script.json").read_text())
FF = imageio_ffmpeg.get_ffmpeg_exe()
FPS, LENGTH = 60, 36
INK, PAPER, ORANGE, MINT = "#20221f", "#f2efe5", "#fb6540", "#c5d6a3"
FACES = [
    "BarlowCondensed-Black.ttf",
    "DMSerifDisplay-Italic.ttf",
    "IBMPlexMono-Regular.ttf",
]
# Heading, counterline, object, paper, ink, accent.
SCENES = [
    ("ONE HOUR.", "Thirty seconds.", "reels", PAPER, INK, "#cb3e24"),
    ("WHERE", "to begin?", "locator", INK, PAPER, MINT),
    ("TOO LATE.", "The question.", "splice", ORANGE, INK, PAPER),
    ("TOO SOON.", "The answer.", "splice", INK, PAPER, ORANGE),
    ("THE TURN.", "Listen for it.", "groove", MINT, INK, "#9e3122"),
    ("SET THE CUT.", "Thirty seconds.", "window", PAPER, INK, "#bf432b"),
    ("READ IT.", "Line by line.", "proof", INK, PAPER, MINT),
    ("YOUR CUT.", "Your call.", "choose", ORANGE, INK, PAPER),
    ("YOUR VOICE.", "Remembered.", "echo", PAPER, INK, "#c14528"),
    ("AFTERTONE", "The next cut.", "groove", INK, PAPER, ORANGE),
]
STARTS = [0] + [s["start"] for s in SCRIPT[1:]]


def clamp(x):
    return max(0, min(1, x))


def ease(x):
    return 1 - (1 - clamp(x)) ** 3


@lru_cache(maxsize=400)
def face(n, size):
    return ImageFont.truetype(str(ROOT / "fonts" / FACES[n]), max(1, round(size)))


class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.scale = min(w, h) / 540
        self.W, self.H = w / self.scale, h / self.scale
        self.image = Image.new("RGB", (w, h), bg)
        self.d = ImageDraw.Draw(self.image)

    def xy(self, *a):
        return tuple(round(x * self.scale) for x in a)

    def line(self, points, color, width=1):
        self.d.line(
            [self.xy(*p) for p in points],
            fill=color,
            width=max(1, round(width * self.scale)),
            joint="curve",
        )

    def box(self, x, y, w, h, c):
        self.d.rectangle(self.xy(x, y, x + w, y + h), fill=c)

    def disk(self, x, y, r, c, outline=None, width=1):
        self.d.ellipse(
            self.xy(x - r, y - r, x + r, y + r),
            fill=c,
            outline=outline,
            width=max(1, round(width * self.scale)),
        )

    def word(self, x, y, s, size, color, font=0, anchor="lt", fit=None):
        f = face(font, round(size * self.scale))
        if fit and f.getlength(s) > fit * self.scale:
            f = face(font, round(f.size * fit * self.scale / f.getlength(s)))
        self.d.text(self.xy(x, y), s, font=f, fill=color, anchor=anchor)

    def poly(self, points, c):
        self.d.polygon([self.xy(*p) for p in points], fill=c)


def reel(c, x, y, r, angle, ink, bg, accent):
    c.disk(x, y, r, ink)
    for n in range(9, 24, 2):
        c.disk(x, y, r * n / 25, None, bg, 0.65)
    for j in range(3):
        a = angle + j * math.tau / 3
        c.disk(x + math.cos(a) * r * 0.47, y + math.sin(a) * r * 0.47, r * 0.19, bg)
    c.disk(x, y, r * 0.13, accent)
    c.disk(x, y, r * 0.045, bg)


def ticks(c, x, y, w, ink):
    for i in range(41):
        xx = x + w * i / 40
        c.line([(xx, y), (xx, y + (7 if i % 5 == 0 else 3))], ink, 0.7)


def art(c, x, y, w, h, kind, t, u, cols, idx):
    bg, ink, a = cols
    # Procedural tape deck; all geometry lives in one coordinate system.
    s = min(w / 405, h / 240)
    cx = x + w / 2
    cy = y + h / 2

    def pt(X, Y):
        return cx + X * s, cy + Y * s

    def line(points, col, width=1):
        c.line([pt(*p) for p in points], col, width * s)

    def box(X, Y, W, H, col):
        c.box(*pt(X, Y), W * s, H * s, col)

    def lbl(X, Y, txt, col=ink, size=9):
        c.word(*pt(X, Y), txt, size * s, col, 2)

    def tape(Y, lo=-170, hi=170):
        for k in range(int(lo), int(hi), 4):
            amp = (
                0.22 + 0.78 * abs(math.sin(k * 0.029 + 0.7) * math.cos(k * 0.057))
            ) * (15 + 6 * math.sin(k * 0.08 + t * 2))
            line([(k, Y - amp), (k, Y + amp)], ink, 2.2)

    if kind == "reels":
        line([(-112, 55), (-78, 81), (100, 81), (123, 45)], ink, 3)
        reel(c, *pt(-85, 0), 79 * s, t * 0.78, ink, bg, a)
        reel(c, *pt(83, 0), 70 * s, -t * 0.87, ink, bg, a)
        for j in range(9):
            box(-90 + ((j * 23 + t * 36) % 178), 78, 9, 4, a)
        lbl(-155, 96, "SOURCE / 60 MIN")
        lbl(48, 96, "EDIT / 00:30")
    elif kind in ("locator", "window", "splice"):
        offset = math.sin(t * 0.9) * 12 if kind == "locator" else 0
        tape(0)
        ticks(c, *pt(-170, 38), 340 * s, ink)
        l = (-125 + 70 * ease(u / 0.8) if idx == 2 else -110) + offset
        r = (140 - 75 * ease(u / 0.8) if idx == 3 else 95) + offset
        for k, d in ((l, 1), (r, -1)):
            line([(k + 12 * d, -44), (k, -44), (k, 47), (k + 12 * d, 47)], a, 4)
        pointer = l + (r - l) * ((t * 0.28) % 1)
        line([(pointer, -57), (pointer, 34)], a, 1.5)
        c.poly([pt(pointer - 4, -59), pt(pointer + 4, -59), pt(pointer, -52)], a)
        lbl(-169, -80, "SOURCE IN")
        lbl(81, 70, "SOURCE OUT")
        if kind == "splice":
            lbl(-170, 83, "QUESTION  /  PAYOFF", ink, 12)
    elif kind in ("proof", "choose", "echo"):
        labels = {
            "proof": ["Opening line", "The turn", "Closing line"],
            "choose": ["Direction A", "Direction B", "Final cut"],
            "echo": ["First draft", "Creator edit", "Next draft"],
        }[kind]
        for j, txt in enumerate(labels):
            xx = -160 + 22 * (1 - ease((u - j * 0.09) / 0.6))
            yy = -63 + j * 55
            active = min(2, int(u * 1.8)) == j
            box(xx, yy, 320, 43, a if active else ink)
            c.word(
                *pt(xx + 12, yy + 10),
                txt,
                22 * s,
                bg if not active else (INK if a != INK else PAPER),
                1,
            )
            for k in range(13):
                box(
                    xx + 224 + k * 5,
                    yy + 19 - (k % 4) * 2,
                    2,
                    6 + (k % 4) * 4,
                    bg if not active else INK,
                )
    else:
        # Radial record grooves open into a visible wedge at the emotional turn.
        reel(c, *pt(0, 0), 96 * s, t * 0.37, ink, bg, a)
        angle = -1.52 + 0.42 * math.sin(t * 0.9)
        line(
            [(160, -85), (116, -80), (math.cos(angle) * 56, math.sin(angle) * 56)], a, 5
        )
        c.disk(*pt(160, -85), 8 * s, a)
        lbl(-175, 105, "PLAYHEAD")
        lbl(92, 105, "AFTERTONE")


def caption(c, t, ink, a):
    row = SCRIPT[max(0, bisect.bisect_right(STARTS, t) - 1)]
    words = row["words"]
    active = max(0, bisect.bisect_right([p[1] for p in words], t) - 1)
    group = words[(active // 5) * 5 : (active // 5 + 1) * 5]
    size = 16 if c.H > c.W else 14
    f = face(2, round(size * c.scale))
    widths = [f.getlength(w) / c.scale for w, _ in group]
    gap = 7
    x = (c.W - sum(widths) - gap * (len(group) - 1)) / 2
    for j, ((w, _), width) in enumerate(zip(group, widths)):
        c.word(x, c.H - 52, w, size, ink, 2)
        if j == active % 5:
            c.box(x, c.H - 29, width, 2, a)
        x += width + gap


def frame(t, w, h):
    i = max(0, bisect.bisect_right(STARTS, t) - 1)
    u = t - STARTS[i]
    head, sub, kind, bg, ink, a = SCENES[i]
    c = Canvas(w, h, bg)
    portrait = h > w
    m = 32
    c.line([(m, 40), (c.W - m, 40)], ink, 0.7)
    c.word(m, 20, "AFTERTONE   /   EDITORIAL FILM", 9, ink, 2)
    c.word(
        c.W - m,
        20,
        f"TAKE 02   /   {int(t):02d}:{int(t * FPS) % FPS:02d}",
        9,
        ink,
        2,
        "rt",
    )
    if portrait:
        tx, ty, tw = m, 145, c.W - 2 * m
        ax, ay, aw, ah = m, 408, tw, 305
    else:
        tx, ty, tw = m, 150, c.W * 0.49 - m
        ax, ay, aw, ah = c.W * 0.52, 110, c.W * 0.45, 280
    c.word(
        tx,
        ty - 34,
        f"{i + 1:02d}   /   {['THE SOURCE', 'ENTRY POINT', 'THE SETUP', 'THE PAYOFF', 'LISTEN', 'SELECT', 'EVIDENCE', 'DECISION', 'MEMORY', 'AFTERTONE'][i]}",
        11,
        a,
        2,
    )
    # Staggered glyphs settle on a shared baseline.
    font = face(0, round((128 if portrait else 112) * c.scale))
    if font.getlength(head) > tw * c.scale:
        font = face(0, int(font.size * tw * c.scale / font.getlength(head)))
    for k, ch in enumerate(head):
        p = ease((u - k * 0.026) / 0.34)
        x = tx + font.getlength(head[:k]) / c.scale
        if p > 0:
            c.d.text(c.xy(x, ty + (1 - p) * 31), ch, font=font, fill=ink, anchor="lt")
    c.word(
        tx + (1 - ease((u - 0.14) / 0.5)) * 20,
        ty + (115 if portrait else 105),
        sub,
        54 if portrait else 47,
        a,
        1,
        fit=tw,
    )
    art(c, ax, ay, aw, ah, kind, t, u, (bg, ink, a), i)
    base = c.H - 120
    ticks(c, m, base, c.W - 2 * m, ink)
    c.box(m, base - 6, (c.W - 2 * m) * t / LENGTH, 3, a)
    caption(c, t, ink, a)
    # A tape splice briefly wipes across each cut.
    if i and u < 0.16:
        c.box(c.W * ease(u / 0.16), 0, c.W * 0.08 * (1 - u / 0.16), c.H, a)
    return c.image


def sound(path):
    # Original quiet splice clicks; leave the narrator's pace and breaths intact.
    rate = 24000
    buf = array.array("h", [0]) * (LENGTH * rate)
    for t in STARTS[1:]:
        for j in range(int(0.09 * rate)):
            t0 = j / rate
            idx = int(t * rate) + j
            buf[idx] = int(
                720
                * math.exp(-62 * t0)
                * math.sin(math.tau * (310 * t0 + 1100 * t0 * t0))
            )
    with wave.open(str(path), "wb") as f:
        f.setparams((1, 2, rate, 0, "NONE", ""))
        f.writeframes(buf.tobytes())


def render(out, portrait):
    w, h = (1080, 1920) if portrait else (1920, 1080)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as d:
        clicks = Path(d) / "mix.wav"
        sound(clicks)
        tmp = Path(d) / "final.mp4"
        cmd = [
            FF,
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(FPS),
            "-i",
            "pipe:0",
            "-i",
            str(ROOT / "jessica.mp3"),
            "-i",
            str(clicks),
            "-filter_complex",
            "[1:a][2:a]amix=inputs=2:normalize=0,alimiter=limit=0.96[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-threads",
            "4",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(tmp),
        ]
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as enc:
            for n in range(FPS * LENGTH):
                enc.stdin.write(frame(n / FPS, w, h).tobytes())
            enc.stdin.close()
            if enc.wait():
                raise RuntimeError("FFmpeg failed to encode the film")
        tmp.replace(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--portrait", action="store_true")
    args = parser.parse_args()
    render(args.out, args.portrait)
