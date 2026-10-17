"""Unit tests for the podcast video layout (geometry contract v1).

Pure tests — no ffmpeg needed. They pin the filtergraph produced by
``podcast_compose._build_segment_filter``, the ASS caption placement and
wrapping, slide resolution and the avatar-registry crop rects.
"""
from __future__ import annotations

import inspect
import logging
import re
from pathlib import Path

import pytest

from services import avatar_registry
from services import podcast_compose as pc
from services.podcast_models import Document, Section
from services.podcast_render import ClipManifest, DialogueTurn, RenderRoles, RoleConfig, Script

NAMES = {"interviewer": "Dr. Harry Chen", "expert": "Dr. Lisa Patel"}


def _chains(fc: str) -> list[str]:
    return [c for c in fc.split(";") if c]


def _chain_for(fc: str, out_label: str) -> str:
    matches = [c for c in _chains(fc) if c.endswith(out_label)]
    assert len(matches) == 1, f"expected exactly one chain ending with {out_label}"
    return matches[0]


def _build(**kw) -> str:
    base = dict(
        active_speaker="interviewer",
        total_dur=3.0,
        active=pc.SpeakerVisual(chroma_key=False, crop=(0.3, 0.0, 0.4, 0.5)),
        idle=pc.SpeakerVisual(chroma_key=False, crop=(0.1, 0.0, 0.8, 0.9)),
        names=NAMES,
    )
    base.update(kw)
    return pc._build_segment_filter(**base)


# ---------------------------------------------------------------------------
# Slide region
# ---------------------------------------------------------------------------

def test_slide_is_contained_never_stretched():
    fc = _build()
    slide = _chain_for(fc, "[slide]")
    assert slide.startswith("[0:v]")
    assert "scale=1280:720:force_original_aspect_ratio=decrease" in slide
    assert "pad=1280:720:(ow-iw)/2:(oh-ih)/2" in slide
    assert "setsar=1" in slide
    assert "crop=" not in slide
    assert "scale=1920:810" not in fc and "1920x810" not in fc and "vstack" not in fc
    assert "overlay=x=320:y=360" in fc


def test_canvas_is_full_hd_with_dark_background():
    fc = _build()
    bg = _chain_for(fc, "[bg]")
    assert f"color=c={pc.BG_COLOR}:s=1920x1080" in bg


# ---------------------------------------------------------------------------
# Avatar tiles
# ---------------------------------------------------------------------------

def test_tiles_are_top_left_and_top_right():
    fc = _build(active_speaker="interviewer")
    assert "[av_a]overlay=x=0:y=0" in fc
    assert "[av_i]overlay=x=1360:y=0" in fc
    fc = _build(active_speaker="expert")
    assert "[av_a]overlay=x=1360:y=0" in fc
    assert "[av_i]overlay=x=0:y=0" in fc


@pytest.mark.parametrize("label", ["[av_a]", "[av_i]"])
def test_tile_chain_order_chroma_crop_scale_pad_format(label):
    fc = _build(
        active=pc.SpeakerVisual(chroma_key=True, crop=(0.3, 0.0, 0.4, 0.5)),
        idle=pc.SpeakerVisual(chroma_key=True, crop=(0.1, 0.0, 0.8, 0.9)),
    )
    chain = _chain_for(fc, label)
    i_key = chain.index("chromakey=0x00ff00")
    i_spill = chain.index("despill=")
    i_crop = chain.index("crop=")
    i_scale = chain.index("scale=560:360:force_original_aspect_ratio=decrease")
    i_pad = chain.index("pad=560:360")
    i_fmt = chain.rindex("format=yuva420p")
    assert i_key < i_spill < i_crop < i_scale < i_pad < i_fmt


def test_chroma_key_is_per_speaker():
    # Active = transparent WebM (no key), idle = green-screen photo (key).
    fc = _build(
        active=pc.SpeakerVisual(chroma_key=False),
        idle=pc.SpeakerVisual(chroma_key=True),
    )
    assert "chromakey" not in _chain_for(fc, "[av_a]")
    assert "chromakey" in _chain_for(fc, "[av_i]")
    # ...and the other way round.
    fc = _build(
        active=pc.SpeakerVisual(chroma_key=True),
        idle=pc.SpeakerVisual(chroma_key=False),
    )
    assert "chromakey" in _chain_for(fc, "[av_a]")
    assert "chromakey" not in _chain_for(fc, "[av_i]")


def test_input_indices_with_slides():
    fc = _build()
    assert _chain_for(fc, "[av_a]").startswith("[1:v]")
    assert _chain_for(fc, "[av_i]").startswith("[2:v]")
    assert _chain_for(fc, "[aout]").startswith("[1:a]")


def test_idle_still_is_dimmed_active_is_not():
    fc = _build()
    assert "colorchannelmixer" in _chain_for(fc, "[av_i]")
    assert "colorchannelmixer" not in _chain_for(fc, "[av_a]")


def test_active_tile_gets_clay_frame():
    fc = _build(active_speaker="expert")
    assert f"drawbox=x=1360:y=0:w=560:h=360:color={pc.ACCENT_COLOR}:t=4" in fc
    assert pc.ACCENT_COLOR.upper() == "#B8461E"
    fc = _build(active_speaker="interviewer")
    assert f"drawbox=x=0:y=0:w=560:h=360:color={pc.ACCENT_COLOR}:t=4" in fc


def test_crop_is_normalized_even_and_clamped():
    f = pc._crop_filter((0.25, 0.1, 0.5, 0.4))
    assert f == (
        "crop=w=trunc(iw*0.5000/2)*2:h=trunc(ih*0.4000/2)*2:"
        "x=trunc(iw*0.2500/2)*2:y=trunc(ih*0.1000/2)*2"
    )
    x, y, w, h = pc._clamp_crop((0.9, -1.0, 0.8, 5.0))
    assert x == 0.9 and y == 0.0
    assert x + w <= 1.0 + 1e-9 and y + h <= 1.0 + 1e-9
    assert pc._clamp_crop("garbage") == avatar_registry.PODCAST_CROP_PREBUILT


def test_no_idle_frame_skips_idle_overlay():
    fc = _build(has_idle=False)
    assert "[av_i]" not in fc
    assert "[2:v]" not in fc


def test_lead_in_pads_video_and_delays_audio():
    fc = _build(lead_in=0.5)
    assert "tpad=start_duration=0.500:start_mode=clone" in _chain_for(fc, "[av_a]")
    assert "adelay=500|500" in fc


def test_labels_in_centre_zone_and_counter_in_gutter():
    fc = _build(slide_counter="2 / 7")
    assert "Dr. Harry Chen" in fc and "Dr. Lisa Patel" in fc
    assert "Interviewer" in fc and "Expert" in fc
    # Label text never drops below the 96 px label zone.
    for y in re.findall(r"drawtext=text='[^']*':x=[^:]+:y=(\d+)", fc):
        assert int(y) < 96 or int(y) >= 1000  # labels, or the gutter counter
    assert "text='2 / 7'" in fc


def test_split_screen_only_layout():
    fc = _build(layout="split_screen_only")
    assert "[slide]" not in fc
    assert _chain_for(fc, "[av_a]").startswith("[0:v]")
    assert _chain_for(fc, "[av_i]").startswith("[1:v]")
    assert _chain_for(fc, "[aout]").startswith("[0:a]")
    assert "scale=960:900:force_original_aspect_ratio=decrease" in fc
    assert "[av_a]overlay=x=0:y=0" in fc and "[av_i]overlay=x=960:y=0" in fc
    for y in re.findall(r"drawtext=text='[^']*':x=[^:]+:y=(\d+)", fc):
        assert 900 <= int(y) < 960


def test_unknown_layout_falls_back_to_default():
    assert pc.get_layout("nope").name == "split_screen_with_slides"
    assert pc.get_layout(None).name == "split_screen_with_slides"


def test_compose_podcast_layout_parameter_default():
    sig = inspect.signature(pc.compose_podcast)
    assert sig.parameters["layout"].default == "split_screen_with_slides"


# ---------------------------------------------------------------------------
# Per-speaker visuals from clips + registry
# ---------------------------------------------------------------------------

def _roles(int_avatar="harry", exp_avatar="lisa") -> RenderRoles:
    return RenderRoles(
        interviewer=RoleConfig(display_name="A", avatar=int_avatar, voice="x"),
        expert=RoleConfig(display_name="B", avatar=exp_avatar, voice="y"),
    )


def test_speaker_visual_uses_each_speakers_own_chroma_flag():
    avatar_registry.reload(
        '[{"id":"photo_female","character":"c","gender":"female","kind":"photo"}]'
    )
    clips = [
        ClipManifest(turn_idx=0, speaker="interviewer", blob_url="a.mp4",
                     chroma_key=True, avatar_id="photo_female"),
        ClipManifest(turn_idx=1, speaker="expert", blob_url="b.webm",
                     chroma_key=False, avatar_id="lisa"),
    ]
    roles = _roles("photo_female", "lisa")
    iv = pc._speaker_visual(roles, "interviewer", clips)
    ex = pc._speaker_visual(roles, "expert", clips)
    assert iv.chroma_key is True and ex.chroma_key is False
    assert iv.crop == avatar_registry.PODCAST_CROP_PHOTO
    assert ex.crop == avatar_registry.podcast_crop_for(avatar_registry.get("lisa"))


def test_speaker_visual_unknown_avatar_uses_kind_from_clip():
    clips = [ClipManifest(turn_idx=0, speaker="interviewer", blob_url="a.mp4",
                          chroma_key=True, avatar_id="not_registered")]
    v = pc._speaker_visual(_roles("not_registered"), "interviewer", clips)
    assert v.chroma_key is True and v.crop == avatar_registry.PODCAST_CROP_PHOTO


# ---------------------------------------------------------------------------
# Avatar registry crop rects
# ---------------------------------------------------------------------------

def test_registry_podcast_crop_fallbacks_and_overrides():
    avatar_registry.reload(
        '[{"id":"p1","character":"c","kind":"photo"},'
        '{"id":"p2","character":"c","kind":"photo","podcast_crop":[0.1,0.2,0.5,0.6]},'
        '{"id":"v1","character":"c","kind":"video"},'
        '{"id":"bad","character":"c","kind":"video","podcast_crop":[2,2,2,"x"]}]'
    )
    assert avatar_registry.podcast_crop_for(avatar_registry.get("p1")) == avatar_registry.PODCAST_CROP_PHOTO
    assert avatar_registry.podcast_crop_for(avatar_registry.get("p2")) == (0.1, 0.2, 0.5, 0.6)
    assert avatar_registry.podcast_crop_for(avatar_registry.get("v1")) == avatar_registry.PODCAST_CROP_PREBUILT
    assert avatar_registry.get("bad").podcast_crop is None
    assert avatar_registry.podcast_crop_for(avatar_registry.get("harry")) == avatar_registry.PODCAST_CROP_PREBUILT
    lisa = avatar_registry.podcast_crop_for(avatar_registry.get("lisa"))
    assert lisa != avatar_registry.PODCAST_CROP_PREBUILT
    for x, y, w, h in (lisa, avatar_registry.PODCAST_CROP_PREBUILT, avatar_registry.PODCAST_CROP_PHOTO):
        assert 0 <= x and 0 <= y and x + w <= 1.0 and y + h <= 1.0


def test_registry_normalize_crop_clamps():
    assert avatar_registry._normalize_crop([0.9, 0.9, 0.5, 0.5]) == (0.9, 0.9, 0.1, 0.1)
    assert avatar_registry._normalize_crop([1, 2, 3]) is None
    assert avatar_registry._normalize_crop(None) is None


def test_public_catalog_does_not_expose_crop():
    for item in avatar_registry.public_catalog():
        assert "podcast_crop" not in item


# ---------------------------------------------------------------------------
# Captions (ASS) and SRT
# ---------------------------------------------------------------------------

LONG = (
    "Context engineering keeps every model request grounded for as long as "
    "possible, which means designing every agent for retrieval, citation and "
    "review rather than guesswork. Supercalifragilisticexpialidocious-retrieval-provenance-identifiers "
    "make that traceable."
)


def _ass_for(text: str, layout: str, tmp_path: Path) -> str:
    turns = [DialogueTurn(idx=0, speaker="expert", text=text, slide_idx=0)]
    clips = [ClipManifest(turn_idx=0, speaker="expert", blob_url="x.webm")]
    out = tmp_path / "subs.ass"
    pc._write_ass(out, clips, [12.0], {t.idx: t for t in turns}, _roles(),
                  offset=2.0, layout=layout)
    return out.read_text(encoding="utf-8")


def _dialogue_lines(ass: str) -> list[str]:
    return [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]


def _plain_lines(dialogue: str) -> list[str]:
    text = dialogue.split(",", 9)[9]
    text = re.sub(r"\{[^}]*\}", "", text)
    return text.split("\\N")


def test_ass_captions_confined_to_centre_zone(tmp_path):
    ass = _ass_for(LONG, "split_screen_with_slides", tmp_path)
    assert "PlayResX: 1920" in ass and "PlayResY: 1080" in ass
    style = next(ln for ln in ass.splitlines() if ln.startswith("Style: Karaoke"))
    fields = style.split(",")
    # Alignment 5 (middle-centre), MarginL = MarginR = 580 → 760 px wide.
    assert fields[18] == "5" and fields[19] == "580" and fields[20] == "580"
    dialogues = _dialogue_lines(ass)
    assert len(dialogues) >= 3
    for d in dialogues:
        assert "{\\an5\\pos(960,228)}" in d
        lines = _plain_lines(d)
        assert 1 <= len(lines) <= 3
        for line in lines:
            assert len(line) <= 40, line
    # All words survive (minus ASS-unsafe characters) and karaoke tags remain.
    words = " ".join(" ".join(_plain_lines(d)) for d in dialogues).split()
    assert "Context" in words and "traceable." in words
    assert "\\k" in dialogues[0]


def test_ass_captions_keep_offset(tmp_path):
    ass = _ass_for("Hello there.", "split_screen_with_slides", tmp_path)
    d = _dialogue_lines(ass)
    assert d[0].startswith("Dialogue: 0,0:00:02.00,0:00:14.00,Karaoke")


def test_ass_split_screen_only_zone(tmp_path):
    ass = _ass_for(LONG, "split_screen_only", tmp_path)
    for d in _dialogue_lines(ass):
        assert "{\\an5\\pos(960,1020)}" in d
        assert len(_plain_lines(d)) <= 2


def test_wrap_is_balanced_and_bounded():
    words = "The agent loop is basically read the goal, call a tool, and then check the result".split()
    lines = pc._wrap_words(words, 40)
    assert len(lines) == 2 or all(len(ln) > 1 for ln in lines)
    assert all(len(" ".join(ln)) <= 40 for ln in lines)
    long_word = ["x" * 95]
    assert all(len(" ".join(ln)) <= 40 for ln in pc._wrap_words(long_word, 40))


def test_srt_output_unchanged_format(tmp_path):
    turns = [
        DialogueTurn(idx=0, speaker="interviewer", text="Hello and welcome.", slide_idx=0),
        DialogueTurn(idx=1, speaker="expert", text="Glad to be here.", slide_idx=0),
    ]
    clips = [ClipManifest(turn_idx=t.idx, speaker=t.speaker, blob_url="x") for t in turns]
    roles = RenderRoles(
        interviewer=RoleConfig(display_name="Ann", avatar="lisa", voice="x"),
        expert=RoleConfig(display_name="Bob", avatar="harry", voice="y"),
    )
    out = tmp_path / "f.srt"
    pc._write_srt(out, clips, [1.5, 2.0], {t.idx: t for t in turns}, roles, offset=2.0)
    assert out.read_text(encoding="utf-8") == (
        "1\n00:00:02,000 --> 00:00:03,500\nAnn: Hello and welcome.\n\n"
        "2\n00:00:03,500 --> 00:00:05,500\nBob: Glad to be here.\n"
    )


# ---------------------------------------------------------------------------
# Slide resolution
# ---------------------------------------------------------------------------

def test_resolve_slides_counters_and_missing_fallback(tmp_path, caplog):
    s0 = tmp_path / "s0.png"
    s0.write_bytes(b"png")
    doc = Document(id="d", title="T", sections=[Section(heading="h", text="t")],
                   slide_images=[str(s0), str(tmp_path / "missing.png"), ""],
                   source_kind="pptx")
    script = Script(id="s", document_id="d", turns=[
        DialogueTurn(idx=0, speaker="interviewer", text="a", slide_idx=0),
        DialogueTurn(idx=1, speaker="expert", text="b", slide_idx=1),
        DialogueTurn(idx=2, speaker="expert", text="c", slide_idx=2),
        DialogueTurn(idx=3, speaker="expert", text="d", slide_idx=99),
    ])
    with caplog.at_level(logging.WARNING, logger="services.podcast_compose"):
        res = pc._resolve_slides(doc, script, tmp_path)
    assert res[0] == (s0, "1 / 3")
    assert res[1] == (None, None)
    assert res[2] == (None, None)
    assert res[3] == (None, None)  # clamped to the last (empty) slide
    assert "slide 2 image missing" in caplog.text


def test_resolve_slides_without_document():
    script = Script(id="s", document_id="d", turns=[
        DialogueTurn(idx=0, speaker="interviewer", text="a", slide_idx=0),
    ])
    assert pc._resolve_slides(None, script, Path(".")) == {0: (None, None)}


# ---------------------------------------------------------------------------
# Ingest rendering parity (LibreOffice path + index-aligned slide images)
# ---------------------------------------------------------------------------

def test_ingest_pptx_forwards_libreoffice_path_and_aligns_images(tmp_path, monkeypatch, caplog):
    from services import podcast_ingest, pptx_parser

    seen = {}

    def fake_parse(file_bytes, filename, libreoffice_path="soffice"):
        seen["lo"] = libreoffice_path
        slides = [pptx_parser.SlideData(index=i, title=f"T{i}", body="b", notes="") for i in range(3)]
        # Renderer skipped slide 2 (index 1).
        return pptx_parser.PresentationData(
            id="abcdef0123", filename=filename, slide_count=3, slides=slides,
            slide_images=[(0, b"png0"), (2, b"png2")],
        )

    monkeypatch.setattr(pptx_parser, "parse_pptx", fake_parse)
    src = tmp_path / "deck.pptx"
    src.write_bytes(b"pptx")
    with caplog.at_level(logging.WARNING, logger="services.podcast_ingest"):
        doc = podcast_ingest.ingest_file(src, libreoffice_path=r"C:\LO\soffice.exe")
    assert seen["lo"] == r"C:\LO\soffice.exe"
    assert len(doc.slide_images) == 3
    assert doc.slide_images[1] == ""
    assert Path(doc.slide_images[0]).read_bytes() == b"png0"
    assert Path(doc.slide_images[2]).read_bytes() == b"png2"
    assert "slide(s) [2]" in caplog.text

    podcast_ingest.ingest_pptx(src)
    assert seen["lo"] == "soffice"
