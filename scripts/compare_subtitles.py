"""
Compare reference (human-made) WebVTT subtitles vs Azure Video Translation output.
Shows timeline differences and text differences per language.

Usage:
  python scripts/compare_subtitles.py --reference-dir <dir> --output-dir <dir>

Layout expected:
  <reference-dir>/<locale>.vtt                          e.g. de-DE.vtt
  <output-dir>/<locale>/subtitles_target_<locale>.vtt   (as written by the API)
"""
import argparse
import re
from pathlib import Path


def parse_webvtt(path: Path) -> list[dict]:
    """Parse WebVTT into list of {start, end, start_ms, end_ms, text}."""
    content = path.read_text(encoding="utf-8")
    cues = []
    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\s*\n(.*?)(?=\n\n|\n\d{2}:\d{2}|\Z)",
        re.DOTALL,
    )

    for m in pattern.finditer(content):
        start, end, text = m.group(1), m.group(2), m.group(3).strip()
        if text:
            cues.append({
                "start": start,
                "end": end,
                "start_ms": ts_to_ms(start),
                "end_ms": ts_to_ms(end),
                "text": text,
            })
    return cues


def ts_to_ms(ts: str) -> int:
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)


def ms_to_ts(ms: int) -> str:
    h = ms // 3600000; ms %= 3600000
    m = ms // 60000; ms %= 60000
    s = ms // 1000; ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def compare_locale(locale: str, reference_vtt: Path, api_vtt: Path):
    """Compare reference vs API subtitles for one language."""
    reference_cues = parse_webvtt(reference_vtt)
    api_cues = parse_webvtt(api_vtt)

    # Merge reference cues into full text (some are split across lines for display)
    reference_full_text = " ".join(c["text"].replace("\n", " ") for c in reference_cues)
    api_full_text = " ".join(c["text"].replace("\n", " ") for c in api_cues)

    # Timeline comparison
    reference_start = reference_cues[0]["start_ms"] if reference_cues else 0
    reference_end = reference_cues[-1]["end_ms"] if reference_cues else 0
    api_start = api_cues[0]["start_ms"] if api_cues else 0
    api_end = api_cues[-1]["end_ms"] if api_cues else 0

    print(f"\n{'='*70}")
    print(f"  {locale}")
    print(f"{'='*70}")
    print(f"  Reference: {len(reference_cues)} cues, {ms_to_ts(reference_start)} → {ms_to_ts(reference_end)}")
    print(f"  API:    {len(api_cues)} cues, {ms_to_ts(api_start)} → {ms_to_ts(api_end)}")
    print(f"  Timeline shift: start {api_start - reference_start:+d}ms, end {api_end - reference_end:+d}ms")

    # Text comparison: find differences
    # Match API cues to reference cues by timing overlap
    text_diffs = []
    for api_cue in api_cues:
        # Find overlapping reference cues
        overlapping = [
            c for c in reference_cues
            if c["start_ms"] < api_cue["end_ms"] and c["end_ms"] > api_cue["start_ms"]
        ]
        if overlapping:
            reference_text = " ".join(c["text"].replace("\n", " ") for c in overlapping)
            api_text = api_cue["text"].replace("\n", " ")
            # Normalize for comparison
            reference_norm = re.sub(r"\s+", " ", reference_text).strip()
            api_norm = re.sub(r"\s+", " ", api_text).strip()
            if reference_norm != api_norm:
                # Check if API text is a substring of reference text (just split differently)
                if api_norm not in reference_norm and reference_norm not in api_norm:
                    text_diffs.append({
                        "time": api_cue["start"],
                        "reference": reference_norm[:80],
                        "api": api_norm[:80],
                    })

    # Show timing differences for first/last few cues
    print(f"\n  --- Timeline per cue (first 5 / last 3) ---")
    show_indices = list(range(min(5, len(api_cues)))) + list(range(max(0, len(api_cues)-3), len(api_cues)))
    show_indices = sorted(set(show_indices))

    for i in show_indices:
        if i >= len(api_cues):
            continue
        ac = api_cues[i]
        # Find matching reference cue by index (approximate)
        if i < len(reference_cues):
            cc = reference_cues[i]
            start_diff = ac["start_ms"] - cc["start_ms"]
            end_diff = ac["end_ms"] - cc["end_ms"]
            print(f"  Cue {i:3d}: reference {cc['start']}-{cc['end']} | api {ac['start']}-{ac['end']} | shift: {start_diff:+d}ms / {end_diff:+d}ms")
        else:
            print(f"  Cue {i:3d}: (no reference cue) | api {ac['start']}-{ac['end']}")

    if text_diffs:
        print(f"\n  --- Text differences ({len(text_diffs)} found) ---")
        for d in text_diffs[:5]:
            print(f"  @{d['time']}:")
            print(f"    REFERENCE: {d['reference']}")
            print(f"    API:    {d['api']}")
        if len(text_diffs) > 5:
            print(f"  ... and {len(text_diffs) - 5} more")
    else:
        print(f"\n  ✅ Text matches (API may split cues differently but content is identical)")

    return {
        "locale": locale,
        "reference_cues": len(reference_cues),
        "api_cues": len(api_cues),
        "text_diffs": len(text_diffs),
        "start_shift_ms": api_start - reference_start,
        "end_shift_ms": api_end - reference_end,
    }


def main():
    parser = argparse.ArgumentParser(description="Compare reference vs API-generated WebVTT subtitles")
    parser.add_argument("--reference-dir", required=True, type=Path, help="Folder with <locale>.vtt reference files")
    parser.add_argument("--output-dir", required=True, type=Path, help="Video Translation output folder (one subfolder per locale)")
    args = parser.parse_args()

    print("=" * 70)
    print("  Subtitle Comparison: Reference vs API Output")
    print("=" * 70)

    results = []
    for reference_vtt in sorted(args.reference_dir.glob("*.vtt")):
        locale = reference_vtt.stem
        api_vtt = args.output_dir / locale / f"subtitles_target_{locale}.vtt"
        if not api_vtt.exists():
            print(f"\n  {locale}: SKIP — API output not found")
            continue

        result = compare_locale(locale, reference_vtt, api_vtt)
        results.append(result)

    # Summary table
    print(f"\n\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Locale':<8} {'Ref':>7} {'API':>5} {'Text Diffs':>10} {'Start Shift':>12} {'End Shift':>12}")
    print(f"  {'-'*8} {'-'*7} {'-'*5} {'-'*10} {'-'*12} {'-'*12}")
    for r in results:
        print(f"  {r['locale']:<8} {r['reference_cues']:>7} {r['api_cues']:>5} {r['text_diffs']:>10} {r['start_shift_ms']:>+10}ms {r['end_shift_ms']:>+10}ms")


if __name__ == "__main__":
    main()
