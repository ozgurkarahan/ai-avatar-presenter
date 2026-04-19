"""
Compare client-provided SRT subtitles vs API-generated output subtitles.
Shows timeline differences and text differences per language.
"""
import re
from pathlib import Path

OUTPUT_DIR = Path(r"C:\Users\ozgurkarahan\projects\Acme\ai-presenter - Copilot\output\video-translation")
CLIENT_VTT_DIR = Path(r"C:\Users\ozgurkarahan\projects\Acme\ai-presenter - Copilot\output\webvtt")

LANGUAGES = {
    "ar-SA": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_ARABIC.vtt",
    "zh-CN": "CSG_EHS DAY2026_BenoitBazin_InternalUseOnlyCHINESE.vtt",
    "cs-CZ": "Czech_CSG_2026_EHS DAY_Message_from_Benoit_Bazin_CZECH.vtt",
    "de-DE": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_GERMAN.vtt",
    "it-IT": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_ITALIAN.vtt",
    "pl-PL": "2026 International EHS DAY - POLISH.vtt",
    "pt-BR": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_PORTUGUES-BRAZIL.vtt",
    "ro-RO": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_ROMANIEN.vtt",
    "es-ES": "CSG_2026_EHS_DAY_Message_from_Benoit_Bazin_Spanish_SPAIN.vtt",
    "th-TH": "CSG_EHS DAY2026_BenoitBazin_Thai_InternalUseOnly (1).vtt",
    "tr-TR": "BB_EHS_MesajınızVar_TIURKISH_altyazı (1).vtt",
    "vi-VN": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_VIETNAM.vtt",
}


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


def compare_locale(locale: str, client_vtt: Path, api_vtt: Path):
    """Compare client vs API subtitles for one language."""
    client_cues = parse_webvtt(client_vtt)
    api_cues = parse_webvtt(api_vtt)

    # Merge client cues into full text (some are split across lines for display)
    client_full_text = " ".join(c["text"].replace("\n", " ") for c in client_cues)
    api_full_text = " ".join(c["text"].replace("\n", " ") for c in api_cues)

    # Timeline comparison
    client_start = client_cues[0]["start_ms"] if client_cues else 0
    client_end = client_cues[-1]["end_ms"] if client_cues else 0
    api_start = api_cues[0]["start_ms"] if api_cues else 0
    api_end = api_cues[-1]["end_ms"] if api_cues else 0

    print(f"\n{'='*70}")
    print(f"  {locale}")
    print(f"{'='*70}")
    print(f"  Client: {len(client_cues)} cues, {ms_to_ts(client_start)} → {ms_to_ts(client_end)}")
    print(f"  API:    {len(api_cues)} cues, {ms_to_ts(api_start)} → {ms_to_ts(api_end)}")
    print(f"  Timeline shift: start {api_start - client_start:+d}ms, end {api_end - client_end:+d}ms")

    # Text comparison: find differences
    # Match API cues to client cues by timing overlap
    text_diffs = []
    for api_cue in api_cues:
        # Find overlapping client cues
        overlapping = [
            c for c in client_cues
            if c["start_ms"] < api_cue["end_ms"] and c["end_ms"] > api_cue["start_ms"]
        ]
        if overlapping:
            client_text = " ".join(c["text"].replace("\n", " ") for c in overlapping)
            api_text = api_cue["text"].replace("\n", " ")
            # Normalize for comparison
            client_norm = re.sub(r"\s+", " ", client_text).strip()
            api_norm = re.sub(r"\s+", " ", api_text).strip()
            if client_norm != api_norm:
                # Check if API text is a substring of client text (just split differently)
                if api_norm not in client_norm and client_norm not in api_norm:
                    text_diffs.append({
                        "time": api_cue["start"],
                        "client": client_norm[:80],
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
        # Find matching client cue by index (approximate)
        if i < len(client_cues):
            cc = client_cues[i]
            start_diff = ac["start_ms"] - cc["start_ms"]
            end_diff = ac["end_ms"] - cc["end_ms"]
            print(f"  Cue {i:3d}: client {cc['start']}-{cc['end']} | api {ac['start']}-{ac['end']} | shift: {start_diff:+d}ms / {end_diff:+d}ms")
        else:
            print(f"  Cue {i:3d}: (no client cue) | api {ac['start']}-{ac['end']}")

    if text_diffs:
        print(f"\n  --- Text differences ({len(text_diffs)} found) ---")
        for d in text_diffs[:5]:
            print(f"  @{d['time']}:")
            print(f"    CLIENT: {d['client']}")
            print(f"    API:    {d['api']}")
        if len(text_diffs) > 5:
            print(f"  ... and {len(text_diffs) - 5} more")
    else:
        print(f"\n  ✅ Text matches (API may split cues differently but content is identical)")

    return {
        "locale": locale,
        "client_cues": len(client_cues),
        "api_cues": len(api_cues),
        "text_diffs": len(text_diffs),
        "start_shift_ms": api_start - client_start,
        "end_shift_ms": api_end - client_end,
    }


def main():
    print("=" * 70)
    print("  Subtitle Comparison: Client SRT vs API Output")
    print("=" * 70)

    results = []
    for locale, vtt_name in sorted(LANGUAGES.items()):
        client_vtt = CLIENT_VTT_DIR / vtt_name
        api_vtt = OUTPUT_DIR / locale / f"subtitles_target_{locale}.vtt"

        if not client_vtt.exists():
            print(f"\n  {locale}: SKIP — client VTT not found: {vtt_name}")
            continue
        if not api_vtt.exists():
            print(f"\n  {locale}: SKIP — API output not found")
            continue

        result = compare_locale(locale, client_vtt, api_vtt)
        results.append(result)

    # Summary table
    print(f"\n\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Locale':<8} {'Client':>7} {'API':>5} {'Text Diffs':>10} {'Start Shift':>12} {'End Shift':>12}")
    print(f"  {'-'*8} {'-'*7} {'-'*5} {'-'*10} {'-'*12} {'-'*12}")
    for r in results:
        print(f"  {r['locale']:<8} {r['client_cues']:>7} {r['api_cues']:>5} {r['text_diffs']:>10} {r['start_shift_ms']:>+10}ms {r['end_shift_ms']:>+10}ms")


if __name__ == "__main__":
    main()
