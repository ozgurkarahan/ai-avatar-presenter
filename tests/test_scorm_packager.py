"""Tests for the SCORM 1.2 packager service."""

from __future__ import annotations

import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from demos.backend.services.scorm_packager import build_scorm_package, _srt_to_vtt

SAMPLE_SRT = """\
1\r
00:00:01,000 --> 00:00:04,500\r
Welcome to the safety\r
training module.\r
\r
2\r
00:00:05,000 --> 00:00:08,200\r
Please follow all instructions carefully.\r
\r
3\r
00:00:09,100 --> 00:00:12,750\r
Let's get started.\r
"""


def _make_srt(directory: Path) -> Path:
    srt = directory / "subtitles.srt"
    srt.write_text(SAMPLE_SRT, encoding="utf-8")
    return srt


def _make_media(directory: Path, name: str = "video.mp4") -> Path:
    media = directory / name
    media.write_bytes(b"\x00" * 64)
    return media


def _make_thumbnail(directory: Path, ext: str = ".jpg") -> Path:
    thumb = directory / f"thumb{ext}"
    thumb.write_bytes(b"\xff\xd8\xff" + b"\x00" * 32)
    return thumb


# ---------- Test 1: MP4 video package ----------


def test_scorm_package_mp4():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        mp4 = _make_media(tmp_path, "video.mp4")
        srt = _make_srt(tmp_path)
        out = tmp_path / "output"

        result = build_scorm_package(
            title="Safety Training",
            language="fr-FR",
            media_path=mp4,
            srt_path=srt,
            out_dir=out,
        )

        assert result.exists()
        assert zipfile.is_zipfile(result)

        with zipfile.ZipFile(result) as zf:
            names = set(zf.namelist())
            expected = {"imsmanifest.xml", "index.html", "scorm.js", "subtitles.vtt", "media.mp4"}
            assert names == expected
            # manifest at ZIP root (no directory prefix)
            assert "imsmanifest.xml" in names


# ---------- Test 2: MP3 audio package ----------


def test_scorm_package_mp3():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        mp3 = _make_media(tmp_path, "audio.mp3")
        srt = _make_srt(tmp_path)
        out = tmp_path / "output"

        result = build_scorm_package(
            title="Podcast Episode",
            language="en-US",
            media_path=mp3,
            srt_path=srt,
            out_dir=out,
        )

        with zipfile.ZipFile(result) as zf:
            names = set(zf.namelist())
            assert "media.mp3" in names
            assert "media.mp4" not in names

            html = zf.read("index.html").decode()
            assert "<audio" in html
            assert "<video" not in html


# ---------- Test 3: Package with thumbnail ----------


def test_scorm_package_with_thumbnail():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        mp4 = _make_media(tmp_path, "video.mp4")
        srt = _make_srt(tmp_path)
        thumb = _make_thumbnail(tmp_path, ".jpg")
        out = tmp_path / "output"

        result = build_scorm_package(
            title="Training",
            language="fr-FR",
            media_path=mp4,
            srt_path=srt,
            out_dir=out,
            thumbnail_path=thumb,
        )

        with zipfile.ZipFile(result) as zf:
            names = set(zf.namelist())
            assert "poster.jpg" in names

            html = zf.read("index.html").decode()
            assert 'poster="poster.jpg"' in html


# ---------- Test 4: Manifest structure ----------


def test_manifest_structure():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        mp4 = _make_media(tmp_path)
        srt = _make_srt(tmp_path)
        out = tmp_path / "output"

        result = build_scorm_package(
            title="Manifest Test",
            language="en",
            media_path=mp4,
            srt_path=srt,
            out_dir=out,
        )

        with zipfile.ZipFile(result) as zf:
            zip_entries = set(zf.namelist())
            manifest_xml = zf.read("imsmanifest.xml").decode()

        ns = {
            "ims": "http://www.imsproject.org/xsd/imscp_rootv1p1p2",
            "adlcp": "http://www.adlnet.org/xsd/adlcp_rootv1p2",
        }
        root = ET.fromstring(manifest_xml)

        # Namespaces present
        assert "imsproject.org" in root.tag or root.tag.endswith("manifest")
        assert "adlcp" in manifest_xml

        # Organization
        orgs = root.find("ims:organizations", ns)
        assert orgs is not None
        assert "default" in orgs.attrib

        org = orgs.find("ims:organization", ns)
        assert org is not None

        # Item → identifierref matches resource identifier
        item = org.find(".//ims:item", ns)
        assert item is not None
        item_ref = item.attrib["identifierref"]

        resources = root.find("ims:resources", ns)
        resource = resources.find("ims:resource", ns)
        assert resource is not None
        assert resource.attrib["identifier"] == item_ref
        assert resource.attrib["type"] == "webcontent"
        assert resource.attrib[f"{{{ns['adlcp']}}}scormtype"] == "sco"
        assert resource.attrib["href"] == "index.html"

        # All <file href="..."> must match ZIP entries and be relative
        file_hrefs = {f.attrib["href"] for f in resource.findall("ims:file", ns)}
        for href in file_hrefs:
            assert "\\" not in href, f"Backslash in href: {href}"
            assert not href.startswith("/"), f"Absolute href: {href}"
            assert href in zip_entries, f"{href} not found in ZIP"


# ---------- Test 5: scorm.js status guard ----------


def test_scorm_js_status_guard():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        mp4 = _make_media(tmp_path)
        srt = _make_srt(tmp_path)
        out = tmp_path / "output"

        result = build_scorm_package(
            title="JS Test",
            language="en",
            media_path=mp4,
            srt_path=srt,
            out_dir=out,
        )

        with zipfile.ZipFile(result) as zf:
            js = zf.read("scorm.js").decode()

        # Must read status before setting it
        assert "cmi.core.lesson_status" in js
        assert "LMSGetValue" in js
        assert "not attempted" in js
        assert "_finished" in js


# ---------- Test 6: SRT → VTT conversion ----------


def test_srt_to_vtt_conversion():
    result = _srt_to_vtt(SAMPLE_SRT)

    assert result.startswith("WEBVTT")
    # No commas in timestamps
    for line in result.split("\n"):
        if "-->" in line:
            assert "," not in line
    # No bare cue numbers (lines that are only digits)
    for line in result.split("\n"):
        stripped = line.strip()
        if stripped and stripped.isdigit():
            pytest.fail(f"Bare cue number found: {stripped!r}")
    # Multiline text preserved
    assert "safety" in result
    assert "training module." in result


# ---------- Test 7: Special chars in title ----------


def test_title_with_special_chars():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        mp4 = _make_media(tmp_path)
        srt = _make_srt(tmp_path)
        out = tmp_path / "output"

        result = build_scorm_package(
            title='Test <>&"\' chars',
            language="en",
            media_path=mp4,
            srt_path=srt,
            out_dir=out,
        )

        with zipfile.ZipFile(result) as zf:
            manifest_xml = zf.read("imsmanifest.xml").decode()

        # Must be parseable (well-formed XML)
        ET.fromstring(manifest_xml)


# ---------- Test 8: Media filename with spaces ----------


def test_media_filename_with_spaces():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        mp4 = _make_media(tmp_path, "my video file.mp4")
        srt = _make_srt(tmp_path)
        out = tmp_path / "output"

        result = build_scorm_package(
            title="Spaces Test",
            language="en",
            media_path=mp4,
            srt_path=srt,
            out_dir=out,
        )

        with zipfile.ZipFile(result) as zf:
            names = set(zf.namelist())
            assert "media.mp4" in names
            assert "my video file.mp4" not in names
