"""
SCORM 1.2 packager service.

Produces a valid SCORM 1.2 ZIP package with an HTML5 media player,
VTT subtitles, and the standard SCORM JS API wrapper.
"""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def _srt_to_vtt(srt_text: str) -> str:
    """Convert SRT subtitle text to WebVTT format via cue-block parsing."""
    text = srt_text.replace("\r\n", "\n")
    blocks = re.split(r"\n{2,}", text.strip())

    vtt_blocks: list[str] = []
    for block in blocks:
        lines = block.split("\n")
        kept: list[str] = []
        for line in lines:
            if re.fullmatch(r"\d+", line.strip()):
                continue
            if "-->" in line:
                kept.append(line.replace(",", "."))
            else:
                kept.append(line)
        if kept:
            vtt_blocks.append("\n".join(kept))

    return "WEBVTT\n\n" + "\n\n".join(vtt_blocks) + "\n"


def _sanitize_id(title: str) -> str:
    """Create an XML-safe identifier from a title."""
    return re.sub(r"[^a-zA-Z0-9-]", "-", title).strip("-") or "scorm-package"


def _build_manifest(title: str, files: list[str]) -> str:
    """Generate a valid SCORM 1.2 imsmanifest.xml."""
    ident = _sanitize_id(title)
    safe_title = escape(title)
    file_elements = "\n        ".join(
        f'<file href="{f}"/>' for f in sorted(files)
    )
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{ident}"
          version="1.0"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                              http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <organizations default="org-{ident}">
    <organization identifier="org-{ident}">
      <title>{safe_title}</title>
      <item identifier="item-{ident}" identifierref="res-{ident}">
        <title>{safe_title}</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="res-{ident}" type="webcontent" adlcp:scormtype="sco" href="index.html">
        {file_elements}
    </resource>
  </resources>
</manifest>
"""


_SCORM_JS = """\
// SCORM 1.2 API wrapper
var _api = null;
var _finished = false;

function findAPI(win) {
    var attempts = 0;
    while (win && !win.API && attempts < 10) {
        if (win.opener && win.opener.API) { return win.opener.API; }
        if (win === win.parent) { break; }
        win = win.parent;
        attempts++;
    }
    return win ? win.API || null : null;
}

function scormInit() {
    _api = findAPI(window);
    if (_api) {
        _api.LMSInitialize("");
        var status = _api.LMSGetValue("cmi.core.lesson_status");
        if (status === "" || status === "not attempted") {
            _api.LMSSetValue("cmi.core.lesson_status", "incomplete");
        }
        _api.LMSCommit("");
    } else {
        console.log("No LMS detected \\u2014 running standalone");
    }
}

function scormComplete() {
    if (_finished) { return; }
    _finished = true;
    if (_api) {
        _api.LMSSetValue("cmi.core.lesson_status", "completed");
        _api.LMSSetValue("cmi.core.score.raw", "100");
        _api.LMSCommit("");
        _api.LMSFinish("");
    }
}

window.addEventListener("beforeunload", function () {
    if (!_finished && _api) {
        _api.LMSFinish("");
    }
});
"""


def _build_index_html(
    title: str,
    media_filename: str,
    language: str,
    is_video: bool,
    poster_filename: str | None,
) -> str:
    """Generate the HTML5 player page."""
    safe_title = escape(title)
    media_tag = "video" if is_video else "audio"
    poster_attr = f' poster="{poster_filename}"' if poster_filename and is_video else ""
    controls = "controls"

    return f"""\
<!DOCTYPE html>
<html lang="{language}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title}</title>
  <script src="scorm.js"></script>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      background: #0f0f23;
      color: #e0e0e0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      flex-direction: column;
      padding: 20px;
    }}
    .player-container {{
      max-width: 960px;
      width: 100%;
      background: #1a1a2e;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    }}
    .player-header {{
      padding: 16px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .player-header h1 {{
      font-size: 1.2rem;
      font-weight: 600;
    }}
    .badges {{
      display: flex;
      gap: 8px;
    }}
    .badge {{
      background: #2d2d5e;
      color: #a0a0ff;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 500;
    }}
    video, audio {{
      width: 100%;
      display: block;
      border-radius: 0;
    }}
    .status-bar {{
      padding: 12px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-top: 1px solid #2d2d5e;
    }}
    .status-indicator {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .status-dot {{
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #ffa500;
    }}
    .status-dot.done {{
      background: #00cc88;
    }}
    .info-section {{
      max-width: 960px;
      width: 100%;
      margin-top: 16px;
      padding: 16px 20px;
      background: #1a1a2e;
      border-radius: 12px;
      font-size: 0.8rem;
      color: #888;
    }}
    .info-section h2 {{
      font-size: 0.9rem;
      margin-bottom: 8px;
      color: #aaa;
    }}
    .info-section ul {{
      list-style: none;
      padding: 0;
    }}
    .info-section li {{
      padding: 2px 0;
    }}
  </style>
</head>
<body onload="scormInit()">
  <div class="player-container">
    <div class="player-header">
      <h1>{safe_title}</h1>
      <div class="badges">
        <span class="badge">SCORM 1.2</span>
        <span class="badge">{escape(language)}</span>
      </div>
    </div>
    <{media_tag} id="player" {controls}{poster_attr}>
      <source src="{media_filename}">
      <track src="subtitles.vtt" kind="subtitles" srclang="{language}" label="Subtitles" default>
    </{media_tag}>
    <div class="status-bar">
      <div class="status-indicator">
        <div class="status-dot" id="statusDot"></div>
        <span id="statusText">En cours...</span>
      </div>
    </div>
  </div>
  <div class="info-section">
    <h2>Package Structure</h2>
    <ul>
      <li>imsmanifest.xml</li>
      <li>index.html</li>
      <li>scorm.js</li>
      <li>subtitles.vtt</li>
      <li>{media_filename}</li>\
{f'{chr(10)}      <li>{poster_filename}</li>' if poster_filename else ''}
    </ul>
  </div>
  <script>
    var media = document.getElementById("player");
    media.addEventListener("ended", function() {{
      scormComplete();
      document.getElementById("statusDot").classList.add("done");
      document.getElementById("statusText").textContent = "Terminé";
    }});
  </script>
</body>
</html>
"""


def build_scorm_package(
    title: str,
    language: str,
    media_path: Path,
    srt_path: Path,
    out_dir: Path,
    thumbnail_path: Path | None = None,
) -> Path:
    """
    Build a SCORM 1.2 ZIP package with an HTML5 player.

    Parameters
    ----------
    title : str
        Human-readable title for the course / SCO.
    language : str
        BCP-47 language code (e.g. ``"fr-FR"``).
    media_path : Path
        Path to the MP4 or MP3 media file.
    srt_path : Path
        Path to the SRT subtitle file.
    out_dir : Path
        Directory where ``scorm.zip`` will be written.
    thumbnail_path : Path | None
        Optional poster image for video packages.

    Returns
    -------
    Path
        Path to the generated ``scorm.zip``.
    """
    os.makedirs(out_dir, exist_ok=True)

    ext = media_path.suffix.lower()
    media_filename = f"media{ext}"
    is_video = ext == ".mp4"

    poster_filename: str | None = None
    if thumbnail_path is not None:
        poster_filename = f"poster{thumbnail_path.suffix.lower()}"

    vtt_content = _srt_to_vtt(srt_path.read_text(encoding="utf-8"))
    index_html = _build_index_html(title, media_filename, language, is_video, poster_filename)

    zip_entries: list[str] = [
        "imsmanifest.xml",
        "index.html",
        "scorm.js",
        "subtitles.vtt",
        media_filename,
    ]
    if poster_filename:
        zip_entries.append(poster_filename)

    manifest = _build_manifest(title, zip_entries)

    zip_path = out_dir / "scorm.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("imsmanifest.xml", manifest)
        zf.writestr("index.html", index_html)
        zf.writestr("scorm.js", _SCORM_JS)
        zf.writestr("subtitles.vtt", vtt_content)
        zf.write(media_path, media_filename)
        if thumbnail_path and poster_filename:
            zf.write(thumbnail_path, poster_filename)

    return zip_path
