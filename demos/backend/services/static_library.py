"""UC2 Static Video Library — publish rendered videos to Azure Blob Storage.

Blob layout (same container as UC3, prefix `static-videos/`):

    static-videos/{job_id}/thumb.jpg
    static-videos/{job_id}/video.mp4
    static-videos/{job_id}/audio.mp3
    static-videos/{job_id}/subtitles.srt
    static-videos/{job_id}/scorm.zip
    static-videos/{job_id}/manifest.json   <-- written LAST (publish flag)

Manifest holds blob names only — SAS tokens are minted at read time from
either a user delegation key (AAD) or account key (connection string).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

from config import AzureConfig

log = logging.getLogger(__name__)

LIBRARY_PREFIX = "static-videos"
MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1


@dataclass
class StaticLibraryFiles:
    mp4: Path
    mp3: Path
    srt: Path
    thumb: Optional[Path] = None
    scorm: Optional[Path] = None


class StaticVideoLibrary:
    """Publishes and lists rendered static-presenter videos in blob storage."""

    def __init__(self, config: AzureConfig) -> None:
        self._config = config
        self._blob: Optional[BlobServiceClient] = None
        self._account_name: Optional[str] = None
        self._credential: Optional[DefaultAzureCredential] = None
        self._udk = None
        self._udk_expiry: Optional[datetime] = None
        self._initialised = False

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
                for part in self._config.blob_connection_string.split(";"):
                    if part.strip().lower().startswith("accountname="):
                        self._account_name = part.strip().split("=", 1)[1]
                        break
            if self._blob:
                cc = self._blob.get_container_client(self._config.blob_container)
                if not cc.exists():
                    cc.create_container()
                log.info("StaticVideoLibrary ready (container=%s)", self._config.blob_container)
        except Exception as exc:  # noqa: BLE001
            log.warning("StaticVideoLibrary init failed: %s", exc)
            self._blob = None
        return self._blob is not None

    @property
    def available(self) -> bool:
        return self._ensure_init()

    # ------------------------------------------------------------------
    def publish(
        self,
        job_id: str,
        files: StaticLibraryFiles,
        *,
        title: str,
        document_title: str,
        language: str,
        voice: str,
        slide_count: int,
        duration_sec: Optional[float],
        created_at: str,
    ) -> Optional[dict]:
        if not self._ensure_init():
            log.warning("Library publish skipped: blob not configured")
            return None

        prefix = f"{LIBRARY_PREFIX}/{job_id}"
        try:
            thumb_blob: Optional[str] = None
            if files.thumb and files.thumb.exists():
                self._upload(f"{prefix}/thumb.jpg", files.thumb.read_bytes(),
                             content_type="image/jpeg")
                thumb_blob = f"{prefix}/thumb.jpg"

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

            manifest = {
                "schema_version": SCHEMA_VERSION,
                "job_id": job_id,
                "title": title,
                "document_title": document_title,
                "created_at": created_at,
                "duration_sec": duration_sec,
                "language": language,
                "voice": voice,
                "slide_count": slide_count,
                "video_blob": f"{prefix}/video.mp4",
                "audio_blob": f"{prefix}/audio.mp3",
                "subtitle_blob": f"{prefix}/subtitles.srt",
                "thumbnail_blob": thumb_blob,
                "scorm_blob": scorm_blob,
            }
            # Manifest LAST — its presence is the publish flag.
            self._upload(
                f"{prefix}/{MANIFEST_NAME}",
                json.dumps(manifest, indent=2).encode("utf-8"),
                content_type="application/json",
            )
            log.info("Static library published job %s", job_id)
            return manifest
        except Exception as exc:  # noqa: BLE001
            log.exception("Static library publish failed for %s: %s", job_id, exc)
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
    def list(self) -> list[dict]:
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
                items.append({
                    "job_id": m.get("job_id"),
                    "title": m.get("title"),
                    "document_title": m.get("document_title", ""),
                    "created_at": m.get("created_at"),
                    "duration_sec": m.get("duration_sec"),
                    "language": m.get("language", "en-US"),
                    "voice": m.get("voice", ""),
                    "slide_count": m.get("slide_count", 0),
                    "thumbnail_url": self._sas(m.get("thumbnail_blob")),
                })
        except Exception as exc:  # noqa: BLE001
            log.warning("Static library list failed: %s", exc)
            return []
        items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return items

    def get(self, job_id: str) -> Optional[dict]:
        if not self._ensure_init():
            return None
        m = self._read_json_blob(f"{LIBRARY_PREFIX}/{job_id}/{MANIFEST_NAME}")
        if not m:
            return None
        m["video_url"] = self._sas(m.get("video_blob"))
        m["audio_url"] = self._sas(m.get("audio_blob"))
        m["srt_url"] = self._sas(m.get("subtitle_blob"))
        m["thumbnail_url"] = self._sas(m.get("thumbnail_blob"))
        m["scorm_url"] = self._sas(m.get("scorm_blob"))
        return m

    def delete(self, job_id: str) -> bool:
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
            log.warning("Static library delete %s failed: %s", job_id, exc)
            return False

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
        if not blob_name or not self._blob or not self._account_name:
            return None
        try:
            client = self._blob.get_blob_client(
                container=self._config.blob_container, blob=blob_name
            )
            now = datetime.now(timezone.utc)
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
            log.warning("SAS failed for %s: %s", blob_name, exc)
            return None

    def _get_udk(self, start: datetime, expiry: datetime):
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
            log.warning("User delegation key failed: %s", exc)
            return None


def _account_key_from_conn(conn: str) -> str:
    for part in (conn or "").split(";"):
        if part.strip().lower().startswith("accountkey="):
            return part.strip().split("=", 1)[1]
    return ""
