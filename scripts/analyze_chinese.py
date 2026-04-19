"""Analyze Chinese (zh-CN) timing gaps vs German (de-DE) and the original English source."""
import re
import json
from pathlib import Path

OUTPUT = Path(r"C:\Users\ozgurkarahan\projects\Acme\ai-presenter - Copilot\output\video-translation")


def parse_metadata(path: Path) -> list[dict]:
    content = path.read_text("utf-8")
    blocks = re.split(r"\n(?=\d{2}:\d{2}:\d{2}\.\d{3}\s*-->)", content)
    entries = []
    for block in blocks:
        ts = re.match(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})", block)
        if not ts:
            continue
        jm = re.search(r"\{.*\}", block, re.DOTALL)
        if not jm:
            continue
        try:
            data = json.loads(jm.group())
        except json.JSONDecodeError:
            continue

        def to_ms(t):
            h, m, rest = t.split(":")
            s, ms = rest.split(".")
            return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)

        entries.append({
            "start": ts.group(1),
            "end": ts.group(2),
            "start_ms": to_ms(ts.group(1)),
            "end_ms": to_ms(ts.group(2)),
            "dur_ms": to_ms(ts.group(2)) - to_ms(ts.group(1)),
            "src": data.get("sourceLocaleText", ""),
            "tgt": data.get("translatedText", ""),
        })
    return entries


def analyze():
    zh = parse_metadata(OUTPUT / "zh-CN" / "metadata_zh-CN.vtt")
    de = parse_metadata(OUTPUT / "de-DE" / "metadata_de-DE.vtt")
    es = parse_metadata(OUTPUT / "es-ES" / "metadata_es-ES.vtt")

    print("CHINESE (zh-CN) — Segment Duration & Gap Analysis")
    print("Compared against German (de-DE) and Spanish (es-ES)")
    print("=" * 100)
    print()

    long_gaps = []
    short_segments = []
    total_zh_speech = 0
    total_de_speech = 0
    total_zh_gap = 0

    for i in range(len(zh)):
        zh_dur = zh[i]["dur_ms"] / 1000
        total_zh_speech += zh_dur

        de_dur = de[i]["dur_ms"] / 1000 if i < len(de) else 0
        total_de_speech += de_dur

        # Gap before this segment
        if i > 0:
            zh_gap = (zh[i]["start_ms"] - zh[i - 1]["end_ms"]) / 1000
        else:
            zh_gap = zh[i]["start_ms"] / 1000

        de_gap = 0
        if i > 0 and i < len(de):
            de_gap = (de[i]["start_ms"] - de[i - 1]["end_ms"]) / 1000

        total_zh_gap += max(0, zh_gap)

        # Ratio: how much shorter is Chinese compared to German?
        ratio = zh_dur / de_dur if de_dur > 0 else 0

        # Flag long gaps (silent moments with gestures)
        if zh_gap > 2.0:
            long_gaps.append({
                "idx": i, "at": zh[i]["start"], "gap": zh_gap,
                "de_gap": de_gap, "src": zh[i]["src"][:60],
            })

        # Flag segments much shorter than German
        if ratio < 0.5 and de_dur > 1.5:
            short_segments.append({
                "idx": i, "at": zh[i]["start"],
                "zh_dur": zh_dur, "de_dur": de_dur, "ratio": ratio,
                "src": zh[i]["src"][:60], "tgt": zh[i]["tgt"][:40],
            })

    # Summary
    print(f"Total segments:      {len(zh)}")
    print(f"ZH speech time:      {total_zh_speech:.1f}s")
    print(f"DE speech time:      {total_de_speech:.1f}s")
    print(f"ZH gap time:         {total_zh_gap:.1f}s")
    print(f"Video duration:      ~408s")
    print(f"ZH speech ratio:     {total_zh_speech / 408 * 100:.0f}%")
    print(f"DE speech ratio:     {total_de_speech / 408 * 100:.0f}%")
    print(f"ZH/DE duration ratio: {total_zh_speech / total_de_speech:.2f}x")
    print()

    # Long gaps
    print(f"LONG GAPS (>2s) — silent moments where gestures play without voice")
    print(f"{'#':>3} {'At':>12} {'ZH gap':>7} {'DE gap':>7} {'Extra':>7} Source text")
    print("-" * 100)
    for g in long_gaps:
        extra = g["gap"] - g["de_gap"]
        flag = " *** PROBLEM" if extra > 1.5 else ""
        print(f"{g['idx']:3d} {g['at']:>12} {g['gap']:7.2f} {g['de_gap']:7.2f} {extra:>+7.2f} {g['src']}{flag}")

    print()
    print(f"SEGMENTS MUCH SHORTER THAN GERMAN (ratio < 0.5)")
    print(f"{'#':>3} {'At':>12} {'ZH dur':>7} {'DE dur':>7} {'Ratio':>6} ZH text")
    print("-" * 100)
    for s in short_segments:
        print(f"{s['idx']:3d} {s['at']:>12} {s['zh_dur']:7.2f} {s['de_dur']:7.2f} {s['ratio']:6.2f} {s['tgt']}")

    print()
    # Per-segment comparison for first 20 and last 5
    print("DETAILED TIMING (first 20 segments)")
    print(f"{'#':>3} {'ZH start':>12} {'ZH end':>12} {'ZH dur':>6} {'DE dur':>6} {'Gap':>5} {'Ratio':>5} Source")
    print("-" * 100)
    for i in range(min(20, len(zh))):
        zh_dur = zh[i]["dur_ms"] / 1000
        de_dur = de[i]["dur_ms"] / 1000 if i < len(de) else 0
        ratio = zh_dur / de_dur if de_dur > 0 else 0
        gap = (zh[i]["start_ms"] - zh[i - 1]["end_ms"]) / 1000 if i > 0 else 0
        flag = ""
        if gap > 2.0:
            flag = " <-- GAP"
        if ratio < 0.5 and de_dur > 1.5:
            flag += " <-- SHORT"
        print(f"{i:3d} {zh[i]['start']:>12} {zh[i]['end']:>12} {zh_dur:6.2f} {de_dur:6.2f} {gap:5.2f} {ratio:5.2f} {zh[i]['src'][:40]}{flag}")


if __name__ == "__main__":
    analyze()
