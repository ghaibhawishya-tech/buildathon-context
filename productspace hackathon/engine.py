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
FILLER = re.compile(r"subscribe|promo code|sponsor|link in the description|like and share|सब्सक्राइब", re.I)

@lru_cache(maxsize=8192)
def hits(text, emotion):
    return len(re.findall(CUES[emotion], text, re.I))

@lru_cache(maxsize=8192)
def sentiment(text):
    english = ANALYZER.polarity_scores(text)["compound"]
    return max(-3, min(3, round(2 * english) + hits(text, "Relief") - hits(text, "Tension")))

def parse_srt(raw):
    def seconds(stamp):
        h, m, s = stamp.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    rows = []
    for part in re.split(r"\n\s*\n", raw.strip().replace("\r", "")):
        match = re.search(r"(\d+:\d\d:\d\d[,.]\d+)\s*-->\s*(\d+:\d\d:\d\d[,.]\d+)[^\n]*\n(.+)", part, re.S)
        if match:
            a, b = map(seconds, match.groups()[:2])
            line = re.sub(r"<[^>]*>", "", " ".join(match[3].split()))
            if b > a and line:
                rows.append([a, b, line])
    if not rows:
        raise ValueError("The subtitle file needs timed SRT cues.")
    return sorted(rows)

def rank(rows, feedback):
    candidates = []
    for i, (start, _, _) in enumerate(rows):
        for j in range(i, min(len(rows), i + 90)):
            window = rows[i:j+1]
            duration = window[-1][1] - start
            if duration > 62 or (j > i and rows[j][0] - rows[j-1][1] > 3):
                break
            if duration < min(14, rows[-1][1] - rows[0][0]):
                continue
            lines = [r[2] for r in window]
            whole = " ".join(lines)
            curve = [sentiment(t) for t in lines]
            swing = max(curve) - min(curve)
            change = hits(whole, "Discovery")
            arc = "Reversal" if swing >= 2 else "Realization" if change else "Question" if hits(whole,"Curiosity") else "Reflection"
            outcomes = [v["retention"] for v in feedback.values() if v["arc"] == arc]
            adjustment = sum(v - 50 for v in outcomes) / (len(outcomes)+2) * .32
            detail = bool(re.search(r"\d|because|because of|क्योंकि|इसलिए", whole, re.I))
            payoff = curve[-1] > curve[0] or hits(lines[-1], "Discovery")
            score = (50 + min(swing,3)*6 + min(change,2)*3 + 6*detail + 7*bool(payoff)
                     + 4*bool(hits(lines[0],"Curiosity") or hits(lines[0],"Tension"))
                     - abs(30-duration)*.22 - 18*len(FILLER.findall(whole)) + adjustment)
            reasons = []
            if swing: reasons.append("Emotional range spans %d point%s across the passage." % (swing, "" if swing==1 else "s"))
            if change: reasons.append("The speaker signals a change in understanding.")
            if detail: reasons.append("A concrete number or causal explanation grounds the story.")
            if payoff: reasons.append("The last line resolves or reframes the opening.")
            if outcomes: reasons.append(f"Recorded retention for {arc.lower()} cuts adjusted this score by {adjustment:+.1f}.")
            if not reasons: reasons.append("A continuous thought fits the target editorial length.")
            title = max(lines, key=lambda t: hits(t,"Discovery")*2 + abs(sentiment(t)) + bool(re.search(r"\d",t)))
            candidates.append(dict(id=f"{i}-{j}", start=start, end=window[-1][1], rows=window, arc=arc,
                title=title, score=round(max(1,min(99,score))), reasons=reasons, curve=curve))
    selected=[]
    for c in sorted(candidates,key=lambda c:-c["score"]):
        if all(c["end"]<=s["start"] or c["start"]>=s["end"] for s in selected):
            selected.append(c)
        if len(selected)==8: break
    if not selected and rows:
        raise ValueError("No continuous subtitle passage fits the clip window. Split long cues or reduce gaps.")
    return selected

def platform_copy(c, platform, edits):
    lines = [r[2] for r in c["rows"]]
    samples = [e["after"] for e in edits if e["platform"] == platform]
    lead = c["title"]
    if platform == "YouTube": copy = lead[:95]
    elif platform == "Instagram": copy = lead + "\n\n" + ("#पॉडकास्ट" if re.search("[ऀ-ॿ]",lead) else "#Podcast")
    else: copy = lines[0] + ("\n\n" + lines[-1] if len(lines)>1 else "")
    if samples:
        lengths = sorted(len(s.split()) for s in samples)
        limit = max(3,lengths[len(lengths)//2])
        copy = " ".join(copy.split()[:limit])
        if all("#" not in s for s in samples): copy = re.sub(r"\s*#\S+", "", copy)
        if all(s.islower() for s in samples): copy = copy.lower()
    return copy.strip()
