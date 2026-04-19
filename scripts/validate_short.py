"""Validate trimmed 63s subtitle files: timing, completeness, no truncated text."""
import re
from pathlib import Path

SHORT_DIR = Path(r"C:\Users\ozgurkarahan\projects\Acme\ai-presenter - Copilot\output\video-translation-short\webvtt")
FULL_DIR = Path(r"C:\Users\ozgurkarahan\projects\Acme\ai-presenter - Copilot\output\webvtt")
MAX_SEC = 63.0


def parse_cues(path):
    content = path.read_text("utf-8")
    cues = []
    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\s*\n(.*?)(?=\n\n|\n\d{2}:\d{2}|\Z)",
        re.DOTALL,
    )
    for m in pattern.finditer(content):
        def to_ms(t):
            h, mi, rest = t.split(":")
            s, ms = rest.split(".")
            return int(h) * 3600000 + int(mi) * 60000 + int(s) * 1000 + int(ms)
        cues.append({
            "start": m.group(1), "end": m.group(2),
            "start_ms": to_ms(m.group(1)), "end_ms": to_ms(m.group(2)),
            "text": m.group(3).strip(),
        })
    return cues


def main():
    print("TIMING VALIDATION — 63s trimmed subtitles")
    print("=" * 100)
    header = f"{'File':50s} {'Cues':>5} {'Last start':>12} {'Last end':>12} {'End(s)':>7} {'Status':>6}"
    print(header)
    print("-" * 100)

    issues = []

    for vtt in sorted(SHORT_DIR.glob("*.vtt")):
        cues = parse_cues(vtt)
        if not cues:
            print(f"{vtt.name:50s} {'0':>5} {'EMPTY':>12} {'':>12} {'':>7} {'BAD':>6}")
            issues.append((vtt.name, "No cues"))
            continue

        last = cues[-1]
        last_end_sec = last["end_ms"] / 1000
        last_start_sec = last["start_ms"] / 1000

        # Check 1: does last cue END extend past 63s?
        extends = last_end_sec > MAX_SEC

        # Check 2: is the last cue text complete vs full version?
        full_vtt = FULL_DIR / vtt.name
        text_cut = False
        if full_vtt.exists():
            full_cues = parse_cues(full_vtt)
            matching = [c for c in full_cues if c["start_ms"] == last["start_ms"]]
            if matching and matching[0]["text"] != last["text"]:
                text_cut = True
                issues.append((vtt.name, f"Last cue text truncated at {last['start']}"))

        # Check 3: is there a cue in the full version that starts before 63s but was dropped?
        missed = False
        if full_vtt.exists():
            full_cues = parse_cues(full_vtt)
            full_before_63 = [c for c in full_cues if c["start_ms"] < MAX_SEC * 1000]
            if len(full_before_63) > len(cues):
                missed = True
                issues.append((vtt.name, f"Missed {len(full_before_63) - len(cues)} cue(s) that start before {MAX_SEC}s"))

        if extends:
            issues.append((vtt.name, f"Last cue ends at {last_end_sec:.1f}s (past {MAX_SEC}s)"))

        status = "OK" if not extends and not text_cut and not missed else "FIX"
        print(f"{vtt.name:50s} {len(cues):>5} {last['start']:>12} {last['end']:>12} {last_end_sec:>7.1f} {status:>6}")

    print()
    if issues:
        print(f"ISSUES ({len(issues)}):")
        for name, issue in issues:
            print(f"  {name}: {issue}")
    else:
        print("All files OK - no issues found")

    # Show last cue text per language
    print()
    print("LAST CUE per language:")
    print("-" * 100)
    for vtt in sorted(SHORT_DIR.glob("*.vtt")):
        cues = parse_cues(vtt)
        if cues:
            last = cues[-1]
            name_short = vtt.name[:45]
            print(f"  {name_short:47s} [{last['start']}-{last['end']}] {last['text'][:50]}")


if __name__ == "__main__":
    main()
