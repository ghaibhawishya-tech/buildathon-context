"""Generate portable libass motion captions from a finalized cut."""

import re


def clock(seconds):
    ticks = round(max(0, seconds) * 100)
    return f"{ticks // 360000}:{ticks // 6000 % 60:02}:{ticks // 100 % 60:02}.{ticks % 100:02}"


def literal(word):
    return word.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def titles(clip, platform, audio_only=False):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 540
PlayResY: 960
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cut,Barlow Condensed Black,40,&H0098D9FF,&H00FFFFFF,&H001C211E,&H601C211E,0,0,0,0,100,100,0,0,1,2.8,1,2,36,36,160,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    duration = clip["end"] - clip["start"]
    events = []
    if audio_only:
        label = literal("AFTERTONE    /    " + clip["arc"].upper())
        events.append(
            f"Dialogue: 0,0:00:00.00,{clock(duration)},Cut,,0,0,0,,"
            + r"{\an7\pos(38,430)\fs20\fsp2\bord0}"
            + label
        )

    for a, b, text in clip["rows"]:
        words = text.split()
        width = {"YouTube": 5, "Instagram": 4, "LinkedIn": 7}[platform]
        for pos in range(0, len(words), width):
            group = words[pos : pos + width]
            start = a - clip["start"] + (b - a) * pos / len(words)
            end = a - clip["start"] + (b - a) * (pos + len(group)) / len(words)
            lengths = [max(1, len(w)) for w in group]
            total = sum(lengths)
            elapsed = 0
            content = []
            for w, weight in zip(group, lengths):
                prev = round((end - start) * 100 * elapsed / total)
                elapsed += weight
                dt = round((end - start) * 100 * elapsed / total) - prev
                content.append(r"{\kf" + str(dt) + "}" + literal(w))
            font = r"\fnNoto Sans Devanagari\fs31" if re.search("[ऀ-ॿ]", text) else ""
            if audio_only:
                font += r"\fs50" if font else r"\fs65"
            entry = r"{\an2\move(270,818,270,801,0,135)\fad(45,55)" + font + "}"
            if audio_only:
                entry = entry.replace("270,818,270,801", "270,668,270,652")
            events.append(
                f"Dialogue: 0,{clock(start)},{clock(end)},Cut,,0,0,0,,{entry}"
                + " ".join(content)
            )
    return header + "\n".join(events) + "\n"
