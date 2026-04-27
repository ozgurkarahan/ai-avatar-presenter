"""UC3 Podcast Library — persists rendered podcasts to Azure Blob Storage.

Blob layout (all inside the existing blob container, prefix `podcast-library/`):

    podcast-library/{job_id}/video.mp4
    podcast-library/{job_id}/audio.mp3
    podcast-library/{job_id}/subtitles.srt
    podcast-library/{job_id}/scorm.zip
    podcast-library/{job_id}/thumb.jpg
    podcast-library/{job_id}/manifest.json      <-- written LAST; presence = published

The manifest is the source of truth. To keep SAS tokens fresh, the manifest
stores only blob names; signed URLs are generated at read time.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

from config import AzureConfig

logger = logging.getLogger(__name__)

LIBRARY_PREFIX = "podcast-library"
MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1


@dataclass
class LibraryFiles:
    """Local paths to files produced by a render job."""
    mp4: Path
    mp3: Path
    srt: Path
    scorm: Optional[Path] = None


class PodcastLibrary:
    """Publishes and lists rendered podcasts in blob storage."""

    def __init__(self, config: AzureConfig) -> None:
        self._config = config
        self._blob: Optional[BlobServiceClient] = None
        self._account_name: Optional[str] = None
        self._credential: Optional[DefaultAzureCredential] = None
        self._udk = None
        self._udk_expiry: Optional[datetime] = None
        self._initialised = False

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    def _ensure_init(self) -> bool:
        if self._initialised:
            return self._blob is not None
        self._initialised = True
        try:
            if self._config.use_managed_identity and self._config.blob_account_name:
                cred = DefaultAzureCredential()
                url = f"https://{self._config.blob_account_name}.blob.core.windows.net"
                self._blob = BlobServiceClient(url, credential=cred)
                self._account_name = self._config.blob_account_name
                self._credential = cred
            elif self._config.blob_connection_string:
                self._blob = BlobServiceClient.from_connection_string(
                    self._config.blob_connection_string
                )
                # Account name is required for SAS minting; extract from connection string
                for part in self._config.blob_connection_string.split(";"):
                    if part.strip().lower().startswith("accountname="):
                        self._account_name = part.strip().split("=", 1)[1]
                        break
            if self._blob:
                cc = self._blob.get_container_client(self._config.blob_container)
                if not cc.exists():
                    cc.create_container()
                logger.info("PodcastLibrary ready (container=%s)", self._config.blob_container)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PodcastLibrary init failed: %s", exc)
            self._blob = None
        return self._blob is not None

    @property
    def available(self) -> bool:
        return self._ensure_init()

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------
    def publish(
        self,
        job_id: str,
        files: LibraryFiles,
        *,
        title: str,
        document_title: str,
        language: str,
        style: str,
        speaker_names: list[str],
        turn_count: int,
        created_at: str,
    ) -> Optional[dict]:
        """Upload assets and manifest to blob storage.

        The manifest is written LAST. If any earlier upload fails, nothing is
        considered published and the caller may retry.
        """
        if not self._ensure_init():
            logger.warning("Library publish skipped: blob not configured")
            return None

        prefix = f"{LIBRARY_PREFIX}/{job_id}"
        try:
            # 1. Probe duration + pick thumbnail timestamp
            duration_sec = _ffprobe_duration(files.mp4)
            thumb_ts = max(0.5, min(3.0, (duration_sec or 0) * 0.25))

            # 2. Extract + upload thumbnail (scaled to 480w JPEG)
            thumb_path = files.mp4.parent / f"{job_id}-thumb.jpg"
            thumb_ok = _extract_thumbnail(files.mp4, thumb_path, ts=thumb_ts)

            if thumb_ok:
                self._upload(f"{prefix}/thumb.jpg", thumb_path.read_bytes(),
                             content_type="image/jpeg")

            # 3. Upload media assets
            self._upload(f"{prefix}/video.mp4", files.mp4.read_bytes(),
                         content_type="video/mp4")
            self._upload(f"{prefix}/audio.mp3", files.mp3.read_bytes(),
                         content_type="audio/mpeg")
            self._upload(f"{prefix}/subtitles.srt", files.srt.read_bytes(),
                         content_type="application/x-subrip")
            scorm_blob: Optional[str] = None
            if files.scorm and files.scorm.exists():
                self._upload(f"{prefix}/scorm.zip", files.scorm.read_bytes(),
                             content_type="application/zip")
                scorm_blob = f"{prefix}/scorm.zip"

            # 4. Finally, write the manifest (presence => published)
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "job_id": job_id,
                "title": title,
                "document_title": document_title,
                "created_at": created_at,
                "duration_sec": duration_sec,
                "language": language,
                "style": style,
                "speaker_names": speaker_names,
                "turn_count": turn_count,
                "video_blob": f"{prefix}/video.mp4",
                "audio_blob": f"{prefix}/audio.mp3",
                "subtitle_blob": f"{prefix}/subtitles.srt",
                "thumbnail_blob": f"{prefix}/thumb.jpg" if thumb_ok else None,
                "scorm_blob": scorm_blob,
            }
            self._upload(
                f"{prefix}/{MANIFEST_NAME}",
                json.dumps(manifest, indent=2).encode("utf-8"),
                content_type="application/json",
            )
            # Clean up temp thumbnail file
            try:
                if thumb_ok:
                    thumb_path.unlink(missing_ok=True)
            except OSError:
                pass

            logger.info("Library published job %s", job_id)
            return manifest
        except Exception as exc:  # noqa: BLE001
            logger.exception("Library publish failed for %s: %s", job_id, exc)
            return None

    def _upload(self, blob_name: str, data: bytes, *, content_type: str) -> None:
        assert self._blob is not None
        client = self._blob.get_blob_client(
            container=self._config.blob_container, blob=blob_name
        )
        client.upload_blob(
            data, overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    # ------------------------------------------------------------------
    # List / get
    # ------------------------------------------------------------------
    def list(self) -> list[dict]:
        """Return manifests for all published items, with a thumbnail SAS only.

        The full-media SAS URLs are generated by `get()` when a user opens
        a specific item — that keeps listing cheap and limits token exposure.
        """
        if not self._ensure_init():
            return []
        assert self._blob is not None
        container = self._blob.get_container_client(self._config.blob_container)
        items: list[dict] = []
        try:
            for blob in container.list_blobs(name_starts_with=f"{LIBRARY_PREFIX}/"):
                if not blob.name.endswith(f"/{MANIFEST_NAME}"):
                    continue
                m = self._read_json_blob(blob.name)
                if not m:
                    continue
                summary = {
                    "job_id": m.get("job_id"),
                    "title": m.get("title"),
                    "document_title": m.get("document_title"),
                    "created_at": m.get("created_at"),
                    "duration_sec": m.get("duration_sec"),
                    "language": m.get("language"),
                    "style": m.get("style"),
                    "speaker_names": m.get("speaker_names", []),
                    "turn_count": m.get("turn_count", 0),
                    "thumbnail_url": self._sas(m.get("thumbnail_blob")),
                }
                items.append(summary)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Library list failed: %s", exc)
            return []
        # newest first
        items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return items

    def get(self, job_id: str) -> Optional[dict]:
        """Return a full item with fresh SAS URLs for mp4/mp3/srt/thumb."""
        if not self._ensure_init():
            return None
        m = self._read_json_blob(f"{LIBRARY_PREFIX}/{job_id}/{MANIFEST_NAME}")
        if not m:
            return None
        m["mp4_url"] = self._sas(m.get("video_blob"))
        m["mp3_url"] = self._sas(m.get("audio_blob"))
        m["srt_url"] = self._sas(m.get("subtitle_blob"))
        m["thumbnail_url"] = self._sas(m.get("thumbnail_blob"))
        m["scorm_url"] = self._sas(m.get("scorm_blob"))
        return m

    def delete(self, job_id: str) -> bool:
        """Delete all blobs for a library item."""
        if not self._ensure_init():
            return False
        assert self._blob is not None
        container = self._blob.get_container_client(self._config.blob_container)
        prefix = f"{LIBRARY_PREFIX}/{job_id}/"
        try:
            for blob in container.list_blobs(name_starts_with=prefix):
                container.delete_blob(blob.name)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Library delete %s failed: %s", job_id, exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _read_json_blob(self, blob_name: str) -> Optional[dict]:
        assert self._blob is not None
        try:
            c = self._blob.get_blob_client(
                container=self._config.blob_container, blob=blob_name
            )
            raw = c.download_blob().readall()
            return json.loads(raw)
        except Exception:
            return None

    def _sas(self, blob_name: Optional[str]) -> Optional[str]:
        """Generate a 24h read-only SAS URL for a blob, or None on failure."""
        if not blob_name or not self._blob or not self._account_name:
            return None
        try:
            client = self._blob.get_blob_client(
                container=self._config.blob_container, blob=blob_name
            )
            now = datetime.now(timezone.utc)
            from datetime import timedelta
            start = now - timedelta(minutes=5)
            expiry = now + timedelta(hours=24)

            if self._credential:
                udk = self._get_udk(start, expiry)
                if not udk:
                    return None
                token = generate_blob_sas(
                    account_name=self._account_name,
                    container_name=self._config.blob_container,
                    blob_name=blob_name,
                    user_delegation_key=udk,
                    permission=BlobSasPermissions(read=True),
                    expiry=expiry, start=start,
                )
            else:
                # Account-key path (connection string with key)
                token = generate_blob_sas(
                    account_name=self._account_name,
                    container_name=self._config.blob_container,
                    blob_name=blob_name,
                    account_key=_account_key_from_conn(self._config.blob_connection_string),
                    permission=BlobSasPermissions(read=True),
                    expiry=expiry, start=start,
                )
            return f"{client.url}?{token}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("SAS failed for %s: %s", blob_name, exc)
            return None

    def _get_udk(self, start: datetime, expiry: datetime):
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        if (self._udk and self._udk_expiry
                and now < self._udk_expiry - timedelta(hours=1)):
            return self._udk
        try:
            self._udk = self._blob.get_user_delegation_key(  # type: ignore[union-attr]
                key_start_time=start, key_expiry_time=expiry,
            )
            self._udk_expiry = expiry
            return self._udk
        except Exception as exc:  # noqa: BLE001
            logger.warning("User delegation key failed: %s", exc)
            return None


# ----------------------------------------------------------------------
# ffmpeg / ffprobe helpers
# ----------------------------------------------------------------------
def _ffprobe_duration(path: Path) -> Optional[float]:
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            stderr=subprocess.STDOUT, timeout=15,
        )
        return float(out.decode().strip())
    except Exception:
        return None


def _extract_thumbnail(mp4: Path, out: Path, *, ts: float) -> bool:
    """Grab a single frame at `ts` seconds, scaled to 480 wide JPEG."""
    if not shutil.which("ffmpeg"):
        return False
    try:
        subprocess.check_call(
            ["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", str(mp4),
             "-vframes", "1", "-vf", "scale=480:-2",
             "-q:v", "4", str(out)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
        return out.exists() and out.stat().st_size > 0
    except Exception:
        return False


def _account_key_from_conn(conn: str) -> str:
    for part in conn.split(";"):
        if part.strip().lower().startswith("accountkey="):
            return part.strip().split("=", 1)[1]
    return ""
