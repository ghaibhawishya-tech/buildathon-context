from bisect import bisect_left, bisect_right
from functools import lru_cache
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ANALYZER = SentimentIntensityAnalyzer()
import re


CUES = {
    "Tension": "afraid|fear|scared|terrified|failed|failure|lost|stuck|panic|struggled|डर|असफल|हार|डरा|darr",
    "Relief": "finally|relief|worked|saved|solved|free|proud|trust|peace|जीत|सुकून|खुशी|भरोसा|jeet",
    "Discovery": "realized|realised|learned|discovered|instead|turns out|लेकिन|समझ|पता चला|सीखा|lekin",
    "Curiosity": r"\?|why|what if|how come|क्यों|कैसे|kyun",
}
FILLER = re.compile(
    r"subscribe|promo code|sponsor|link in the description|like and share|सब्सक्राइब",
    re.I,
)


@lru_cache(maxsize=8192)
def hits(text, emotion):
    return len(re.findall(CUES[emotion], text, re.I))


@lru_cache(maxsize=8192)
def sentiment(text):
    english = ANALYZER.polarity_scores(text)["compound"]
    return max(
        -3, min(3, round(2 * english) + hits(text, "Relief") - hits(text, "Tension"))
    )


def parse_srt(raw):
    def seconds(stamp):
        h, m, s = stamp.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    rows = []
    for part in re.split(r"\n\s*\n", raw.strip().replace("\r", "")):
        match = re.search(
            r"(\d+:\d\d:\d\d[,.]\d+)\s*-->\s*(\d+:\d\d:\d\d[,.]\d+)[^\n]*\n(.+)",
            part,
            re.S,
        )
        if match:
            a, b = map(seconds, match.groups()[:2])
            line = re.sub(r"<[^>]*>", "", " ".join(match[3].split()))
            if b > a and line:
                rows.append([a, b, line])
    if not rows:
        raise ValueError("The subtitle file needs timed SRT cues.")
    return sorted(rows)


def rank(rows, feedback, levels=(), target=30, source_duration=None, reactions=()):
    duration_available = source_duration if source_duration is not None else rows[-1][1]
    if duration_available < target:
        raise ValueError(
            f"This recording is {duration_available:.1f}s. Choose a recording at least {target}s long."
        )
    starts = [r[0] for r in rows]
    # Median voiced RMS keeps long quiet tails from dominating the delivery signal.
    loudness = []
    for a, b, _ in rows:
        voiced = sorted(v for v in levels[int(a * 5) : int(b * 5) + 1] if v > -55)
        loudness.append(voiced[len(voiced) // 2] if voiced else None)
    candidates = []
    anchors = {
        max(0, min(t, duration_available - target))
        for a, b, _ in rows
        for t in (a, b - target)
    }
    lead = min(30, max(20, target - 15))
    reactions = [peak for peak in reactions if peak["at"] < duration_available]
    reaction_times = [peak["at"] for peak in reactions]
    anchors.update(
        max(0, min(peak["at"] - lead, duration_available - target))
        for peak in reactions
    )
    ends = []
    for _, b, _ in rows:
        ends.append(max(b, ends[-1] if ends else 0))
    for start in sorted(anchors):
        i = bisect_right(ends, start)
        end = start + target
        j = bisect_left(starts, end) - 1
        if j < i:
            continue
        window = []
        for a, b, text in rows[i : j + 1]:
            left, right = max(start, a), min(end, b)
            if right <= left:
                continue
            words = text.split()
            first = int(len(words) * (left - a) / (b - a))
            last = max(first + 1, round(len(words) * (right - a) / (b - a)))
            window.append([left, right, " ".join(words[first:last])])
        if not window:
            continue
        duration = target
        lines = [r[2] for r in window]
        whole = " ".join(lines)
        curve = [sentiment(t) for t in lines]
        swing = max(curve) - min(curve)
        change = hits(whole, "Discovery")
        arc = (
            "Reversal"
            if swing >= 2
            else "Realization"
            if change
            else "Question"
            if hits(whole, "Curiosity")
            else "Reflection"
        )
        outcomes = [v["retention"] for v in feedback.values() if v["arc"] == arc]
        adjustment = sum(v - 50 for v in outcomes) / (len(outcomes) + 2) * 0.32
        detail = bool(re.search(r"\d|because|because of|क्योंकि|इसलिए", whole, re.I))
        payoff = curve[-1] > curve[0] or hits(lines[-1], "Discovery")
        spoken = [v for v in loudness[i : j + 1] if v is not None]
        dynamics = max(spoken) - min(spoken) if spoken else 0
        unfinished = bool(
            re.search(
                r"(?:^|\s)(?:the|and|because|to|my|of|a|कि|और|लेकिन)$",
                lines[-1],
                re.I,
            )
        )
        clean_end = (
            j + 1 == len(rows)
            or rows[j + 1][0] - rows[j][1] > 0.32
            or bool(re.search(r"[.!?।]$", lines[-1]))
        )
        nearby = reactions[
            bisect_left(reaction_times, start + 4) : bisect_left(
                reaction_times, end - 4
            )
        ]
        reaction = max(
            nearby,
            key=lambda peak: (
                peak["strength"]
                * (1 - min(0.7, abs(peak["at"] - start - lead) / target))
            ),
            default=None,
        )
        chat_bonus = (
            reaction["strength"]
            * (1 - min(0.7, abs(reaction["at"] - start - lead) / target))
            if reaction
            else 0
        )
        score = (
            50
            + min(swing, 3) * 6
            + min(change, 2) * 3
            + 6 * detail
            + 7 * bool(payoff)
            + 4 * bool(hits(lines[0], "Curiosity") or hits(lines[0], "Tension"))
            - max(0, duration - sum(b - a for a, b, _ in window)) * 0.65
            - 18 * len(FILLER.findall(whole))
            + min(4, dynamics * 0.35)
            + 3 * clean_end
            - 11 * (start > rows[i][0] + 0.08)
            - 15 * (end < rows[j][1] - 0.08)
            - 13 * unfinished
            + adjustment
            + chat_bonus
        )

        reasons = []
        if reaction:
            timestamp = int(reaction["at"])
            terms = ", ".join(reaction["terms"])
            reasons.append(
                f"Chat reacted near {timestamp // 60}:{timestamp % 60:02d} with {reaction['count']} messages in 5 seconds"
                + (f" and repeated {terms}." if terms else ".")
            )
        if swing:
            low = lines[curve.index(min(curve))].split(". ")[0][:120]
            high = lines[curve.index(max(curve))].split(". ")[0][:120]
            reasons.append(f"Emotional low: “{low}”. Emotional high: “{high}”.")
        if dynamics >= 4:
            reasons.append(
                f"Typical voice level varies by {dynamics:.0f} dB across these lines, adding a change in delivery."
            )
        if change:
            reasons.append("The speaker signals a change in understanding.")
        if detail:
            reasons.append("A concrete number or causal explanation grounds the story.")
        if payoff:
            reasons.append("The last line resolves or reframes the opening.")
        if outcomes:
            reasons.append(
                f"Recorded retention for {arc.lower()} cuts adjusted this score by {adjustment:+.1f}."
            )
        if not reasons:
            reasons.append("A continuous thought fits the target editorial length.")
        clauses = [
            phrase.strip()
            for line in lines
            for phrase in re.split(
                r"(?<=[.!?।])\s+|,\s+|\s+(?=लेकिन|but then|then I realized)", line
            )
            if len(phrase.split()) >= 3
        ]
        title = max(
            clauses or lines,
            key=lambda t: (
                hits(t, "Discovery") * 2 + abs(sentiment(t)) + bool(re.search(r"\d", t))
            ),
        )
        candidates.append(
            dict(
                id=f"{i}-{j}-{target}-{round(start * 1000)}",
                start=start,
                end=end,
                rows=window,
                arc=arc,
                title=title
                if len(title.split()) <= 18
                else " ".join(title.split()[:16]) + "…",
                score=round(max(1, min(99, score))),
                reasons=reasons,
                curve=curve,
                chat=reaction,
                waveform=[
                    round(
                        max(
                            levels[
                                int((start + duration * k / 20) * 5) : max(
                                    int((start + duration * k / 20) * 5) + 1,
                                    int((start + duration * (k + 1) / 20) * 5),
                                )
                            ],
                            default=-70,
                        ),
                        1,
                    )
                    for k in range(20)
                ]
                if levels
                else [],
            ),
        )
    selected = []
    for c in sorted(candidates, key=lambda c: -c["score"]):
        if all(
            min(c["end"], s["end"]) - max(c["start"], s["start"]) <= target * 0.3
            for s in selected
        ):
            selected.append(c)
        if len(selected) == 5:
            break
    if not selected and rows:
        raise ValueError(
            "No continuous subtitle passage fits the clip window. Split long cues or reduce gaps."
        )
    return selected


def platform_copy(c, platform, edits):
    lines = [r[2] for r in c["rows"]]
    samples = [e["after"] for e in edits if e["platform"] == platform]
    lead = c["title"]
    if platform == "YouTube":
        copy = lead[:95]
    elif platform == "Instagram":
        copy = lead + "\n\n" + ("#पॉडकास्ट" if re.search("[ऀ-ॿ]", lead) else "#Podcast")
    else:
        copy = lines[0] + ("\n\n" + lines[-1] if len(lines) > 1 else "")
    copy = c.get("drafts", {}).get(platform, copy)
    if samples:
        lengths = sorted(len(s.split()) for s in samples)
        limit = max(3, lengths[len(lengths) // 2])
        copy = " ".join(copy.split()[:limit])
        if all("#" not in s for s in samples):
            copy = re.sub(r"\s*#\S+", "", copy)
        if all(s.islower() for s in samples):
            copy = copy.lower()
    return copy.strip()
