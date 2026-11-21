"""Convert replay-chat messages into small, anonymous reaction summaries."""

import csv
import io
import json
import math
import re
from collections import Counter, defaultdict
from statistics import median

BUCKET_SECONDS = 5
DEFAULT_TERMS = (
    "lol",
    "lmao",
    "lmfao",
    "pog",
    "poggers",
    "clutch",
    "wtf",
    "gg",
    "😂",
    "💀",
    "🤣",
)
MAX_CHAT_BYTES = 16 * 1024**2


def youtube_messages(text):
    for line in text.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        replay = obj.get("replayChatItemAction", {})
        if replay:
            seconds = float(replay.get("videoOffsetTimeMsec", "nan")) / 1000
            for action in replay.get("actions", []):
                renderer = (
                    action.get("addChatItemAction", {})
                    .get("item", {})
                    .get("liveChatTextMessageRenderer", {})
                )
                if not renderer:
                    continue
                runs = renderer.get("message", {}).get("runs", [])
                message = " ".join(
                    run.get("text")
                    or (run.get("emoji", {}).get("shortcuts") or [""])[0]
                    for run in runs
                )
                yield (
                    seconds,
                    message,
                    renderer.get("authorExternalChannelId"),
                    renderer.get("id"),
                )
        elif "seconds" in obj and "text" in obj:
            yield (
                float(obj["seconds"]),
                str(obj["text"]),
                obj.get("author"),
                obj.get("id"),
            )


def csv_messages(text):
    rows = csv.DictReader(io.StringIO(text))
    if not {"seconds", "text"} <= set(rows.fieldnames or []):
        raise ValueError("Use a chat CSV with seconds and text columns.")
    for row in rows:
        yield float(row["seconds"]), row["text"], row.get("author"), row.get("id")


def chat_peaks(raw, filename, custom_terms="", offset=0, end=None):
    if len(raw) > MAX_CHAT_BYTES:
        raise ValueError(
            "Chat files can be up to 16 MiB. Trim the export to the section you want."
        )
    terms = tuple(
        dict.fromkeys(
            (
                *DEFAULT_TERMS,
                *(
                    word.strip().casefold()
                    for word in custom_terms[:360].split(",")
                    if word.strip() and len(word.strip()) <= 30
                ),
            )
        )
    )
    pattern = re.compile(
        r"(?<!\w)(?:"
        + "|".join(map(re.escape, sorted(terms, key=len, reverse=True)))
        + r")(?!\w)"
    )
    bins = defaultdict(Counter)
    authors = defaultdict(set)
    seen = set()
    try:
        text = raw.decode("utf-8-sig")
        messages = (
            csv_messages(text)
            if filename.lower().endswith(".csv")
            else youtube_messages(text)
        )
        usable = 0
        for seconds, message, author, message_id in messages:
            if (
                not math.isfinite(seconds)
                or seconds < offset
                or (end is not None and seconds >= end)
                or not message
            ):
                continue
            bucket = int((seconds - offset) // BUCKET_SECONDS) * BUCKET_SECONDS
            if message_id and message_id in seen:
                continue
            if message_id:
                seen.add(message_id)
            if author and author in authors[bucket]:
                continue
            if author:
                authors[bucket].add(author)
            usable += 1
            bins[bucket]["messages"] += 1
            for term in set(pattern.findall(message[:500].casefold())):
                bins[bucket][term] += 1
    except (AttributeError, TypeError, UnicodeError, ValueError) as error:
        raise ValueError(
            "Could not read the chat. Use YouTube replay JSONL or a CSV with seconds and text."
        ) from error
    if not usable:
        raise ValueError(
            "No timed chat messages fell inside the selected recording or section."
        )
    baseline = median(bucket["messages"] for bucket in bins.values())
    peaks = []
    for timestamp, counts in bins.items():
        volume = counts.pop("messages")
        reactions = max(counts.values(), default=0)
        if volume >= max(3, baseline * 1.7) or reactions >= 3:
            peaks.append(
                dict(
                    at=timestamp + BUCKET_SECONDS / 2,
                    count=volume,
                    terms=[term for term, count in counts.most_common(3) if count >= 2],
                    strength=min(
                        18,
                        5
                        + 5 * math.log2(1 + volume / max(1, baseline))
                        + min(4, reactions),
                    ),
                )
            )
    # Collapse adjacent buckets so a single outburst doesn't dominate the shortlist.
    spaced = []
    for peak in sorted(peaks, key=lambda p: (-p["strength"], p["at"])):
        if all(abs(peak["at"] - other["at"]) >= 15 for other in spaced):
            spaced.append(peak)
            if len(spaced) == 80:
                break
    return sorted(spaced, key=lambda p: p["at"])
