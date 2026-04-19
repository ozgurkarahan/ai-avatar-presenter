"""
Convert SRT subtitle files to clean WebVTT format for Azure Video Translation API.

The API expects WebVTT with:
- "WEBVTT" header
- Dot-decimal timestamps (00:00:08.920, not 00:00:08,920)
- No cue numbers
- Blank lines between cues

Usage:
  python scripts/convert_srt.py input.srt [output.vtt]
  python scripts/convert_srt.py --dir <folder>  # convert all SRTs in folder
"""

import re
import sys
from pathlib import Path


def srt_to_webvtt(srt_text: str) -> str:
    """Convert SRT content to clean WebVTT format."""
    lines = srt_text.strip().replace('\r\n', '\n').split('\n')
    output = ['WEBVTT', '']

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip cue numbers (lines that are just digits)
        if re.match(r'^\d+$', line):
            i += 1
            continue

        # Timestamp line: convert commas to dots
        ts_match = re.match(
            r'(\d{2}:\d{2}:\d{2}),(\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}),(\d{3})',
            line
        )
        if ts_match:
            timestamp = f'{ts_match.group(1)}.{ts_match.group(2)} --> {ts_match.group(3)}.{ts_match.group(4)}'
            output.append(timestamp)
            i += 1

            # Collect subtitle text lines until blank line or end
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            output.append('\n'.join(text_lines))
            output.append('')  # blank line between cues
            continue

        i += 1

    # Ensure trailing newline
    result = '\n'.join(output).rstrip() + '\n'

    # Fix timestamp issues (may need 2 passes: first pass fixes and removes,
    # second pass catches issues created by removals)
    result = _fix_overlaps(result)
    result = _fix_overlaps(result)

    return result


def _fix_overlaps(vtt_text: str) -> str:
    """Fix overlapping, negative-duration, and backward-jumping cue timestamps."""
    lines = vtt_text.split('\n')
    ts_pattern = re.compile(r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})')

    def to_ms(t: str) -> int:
        h, m, rest = t.split(':')
        s, ms = rest.split('.')
        return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)

    def from_ms(ms: int) -> str:
        h = ms // 3600000
        ms %= 3600000
        m = ms // 60000
        ms %= 60000
        s = ms // 1000
        ms %= 1000
        return f'{h:02d}:{m:02d}:{s:02d}.{ms:03d}'

    # Collect all timestamp line indices and their values
    ts_lines = []
    for i, line in enumerate(lines):
        m = ts_pattern.match(line)
        if m:
            ts_lines.append([i, to_ms(m.group(1)), to_ms(m.group(2))])

    total_fixed = 0

    # Pass 1: Fix negative-duration cues (end < start)
    # Common causes: SRT typo (wrong hour/minute), or slightly swapped boundaries
    for j in range(len(ts_lines)):
        idx = ts_lines[j][0]
        curr_start = ts_lines[j][1]
        curr_end = ts_lines[j][2]

        if curr_end <= curr_start:
            # Strategy: look at neighboring cues to infer correct end time
            # If next cue starts at or near our bad end time, the end is likely
            # missing a minute/hour component
            next_start = ts_lines[j + 1][1] if j + 1 < len(ts_lines) else None

            # Try adding 1-minute increments to end time to see if it fits
            fixed_end = False
            for add_min in range(1, 10):
                candidate = curr_end + add_min * 60000
                if candidate > curr_start:
                    # Verify it doesn't overshoot next cue
                    if next_start is None or candidate <= next_start:
                        ts_lines[j][2] = candidate
                        lines[idx] = f'{from_ms(curr_start)} --> {from_ms(candidate)}'
                        fixed_end = True
                        total_fixed += 1
                        break

            # If minute fix didn't work, use next cue's start if valid, else +2s
            if not fixed_end:
                if next_start and next_start > curr_start:
                    new_end = next_start
                else:
                    new_end = curr_start + 2000
                ts_lines[j][2] = new_end
                lines[idx] = f'{from_ms(curr_start)} --> {from_ms(new_end)}'
                total_fixed += 1

    # Pass 2: Fix backward-jumping starts (cue start before previous cue's start)
    for j in range(1, len(ts_lines)):
        prev_start = ts_lines[j - 1][1]
        curr_start = ts_lines[j][1]
        curr_end = ts_lines[j][2]
        idx = ts_lines[j][0]

        if curr_start < prev_start - 5000:
            for add_min in range(1, 10):
                candidate_start = curr_start + add_min * 60000
                candidate_end = curr_end + add_min * 60000
                if candidate_start >= prev_start:
                    ts_lines[j][1] = candidate_start
                    ts_lines[j][2] = candidate_end
                    lines[idx] = f'{from_ms(candidate_start)} --> {from_ms(candidate_end)}'
                    total_fixed += 1
                    break

    # Pass 3: Fix remaining overlaps
    for j in range(1, len(ts_lines)):
        prev_end = ts_lines[j - 1][2]
        curr_start = ts_lines[j][1]
        idx_prev = ts_lines[j - 1][0]

        if curr_start < prev_end:
            ts_lines[j - 1][2] = curr_start
            lines[idx_prev] = f'{from_ms(ts_lines[j-1][1])} --> {from_ms(curr_start)}'
            total_fixed += 1

    # Pass 4: Remove any remaining negative-duration cues (unfixable SRT errors)
    # These are cues where end <= start even after all fix attempts
    remove_indices = set()
    for j in range(len(ts_lines)):
        if ts_lines[j][2] <= ts_lines[j][1]:
            idx = ts_lines[j][0]
            # Remove the timestamp line and the following text line(s) until blank
            remove_indices.add(idx)
            k = idx + 1
            while k < len(lines) and lines[k].strip():
                remove_indices.add(k)
                k += 1
            if k < len(lines):
                remove_indices.add(k)  # remove blank line too
            total_fixed += 1

    if remove_indices:
        lines = [l for i, l in enumerate(lines) if i not in remove_indices]

    if total_fixed:
        print(f'    ⚠ Fixed {total_fixed} timestamp issue(s)')

    return '\n'.join(lines)


def convert_file(srt_path: Path, vtt_path: Path | None = None) -> Path:
    """Convert a single SRT file to WebVTT."""
    if vtt_path is None:
        vtt_path = srt_path.with_suffix('.vtt')

    srt_text = srt_path.read_text(encoding='utf-8-sig')  # handle BOM
    vtt_text = srt_to_webvtt(srt_text)
    vtt_path.write_text(vtt_text, encoding='utf-8')
    return vtt_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert SRT to WebVTT')
    parser.add_argument('input', nargs='?', help='SRT file path')
    parser.add_argument('output', nargs='?', help='Output VTT path (default: same name .vtt)')
    parser.add_argument('--dir', help='Convert all SRT files in directory')
    parser.add_argument('--outdir', help='Output directory (default: same as input)')
    parser.add_argument('--trim', type=float, default=None, help='Trim to first N seconds')
    args = parser.parse_args()

    if args.dir:
        src_dir = Path(args.dir)
        out_dir = Path(args.outdir) if args.outdir else src_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        for srt in sorted(src_dir.glob('*.srt')):
            vtt_path = out_dir / srt.with_suffix('.vtt').name
            convert_file(srt, vtt_path)

            if args.trim:
                trim_webvtt(vtt_path, args.trim)

            print(f'  ✓ {srt.name} → {vtt_path.name}')
    elif args.input:
        srt_path = Path(args.input)
        vtt_path = Path(args.output) if args.output else None
        result = convert_file(srt_path, vtt_path)

        if args.trim:
            trim_webvtt(result, args.trim)

        print(f'  ✓ {srt_path.name} → {result.name}')
    else:
        parser.print_help()
        sys.exit(1)


def trim_webvtt(vtt_path: Path, max_seconds: float):
    """Trim a WebVTT file to keep only cues starting before max_seconds."""
    content = vtt_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    output = ['WEBVTT', '']
    skip = False

    for line in lines[2:]:  # skip WEBVTT header
        m = re.match(r'(\d{2}):(\d{2}):(\d{2})\.\d{3}\s*-->', line)
        if m:
            secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            if secs >= max_seconds:
                break
            skip = False
        if not skip:
            output.append(line)

    vtt_path.write_text('\n'.join(output).rstrip() + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
