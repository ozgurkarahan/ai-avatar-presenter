"""Persistence layer: Azure Blob Storage for slide images, Cosmos DB for metadata."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey, exceptions as cosmos_exceptions
from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    ContentSettings,
    generate_blob_sas,
)

from config import AzureConfig

logger = logging.getLogger(__name__)

COSMOS_CONTAINER = "presentations"


class PresentationStore:
    """Manages presentation persistence in Cosmos DB + Blob Storage."""

    def __init__(self, config: AzureConfig) -> None:
        self._config = config
        self._blob_client: BlobServiceClient | None = None
        self._cosmos_db: Any = None
        self._cosmos_container: Any = None
        self._initialised = False
        self._credential: DefaultAzureCredential | None = None
        self._account_name: str | None = None
        self._user_delegation_key = None
        self._delegation_key_expiry: datetime | None = None

    # ------------------------------------------------------------------
    # Lazy init — only connects when first needed
    # ------------------------------------------------------------------

    def _ensure_init(self) -> bool:
        if self._initialised:
            return self._cosmos_container is not None
        self._initialised = True

        credential = DefaultAzureCredential() if self._config.use_managed_identity else None

        # Blob Storage
        try:
            if self._config.use_managed_identity and self._config.blob_account_name:
                # Managed identity: construct client from account name
                account_url = f"https://{self._config.blob_account_name}.blob.core.windows.net"
                self._blob_client = BlobServiceClient(account_url, credential=credential)
                self._account_name = self._config.blob_account_name
                self._credential = credential
            elif self._config.blob_connection_string and not self._config.use_managed_identity:
                self._blob_client = BlobServiceClient.from_connection_string(
                    self._config.blob_connection_string
                )
            elif self._config.blob_connection_string and credential:
                # Extract account URL from connection string, auth via credential
                account_name = _extract_account_name(self._config.blob_connection_string)
                if account_name:
                    account_url = f"https://{account_name}.blob.core.windows.net"
                    self._blob_client = BlobServiceClient(account_url, credential=credential)
                    self._account_name = account_name
                    self._credential = credential

            if self._blob_client:
                container_client = self._blob_client.get_container_client(
                    self._config.blob_container
                )
                if not container_client.exists():
                    container_client.create_container()
                logger.info("Blob Storage initialised (container=%s)", self._config.blob_container)
        except Exception as e:
            logger.warning("Blob Storage init failed (non-blocking): %s", e)
            self._blob_client = None

        # Cosmos DB
        if self._config.cosmos_endpoint:
            try:
                if self._config.cosmos_key:
                    client = CosmosClient(self._config.cosmos_endpoint, self._config.cosmos_key)
                elif credential:
                    client = CosmosClient(self._config.cosmos_endpoint, credential=credential)
                else:
                    client = None

                if client:
                    self._cosmos_db = client.create_database_if_not_exists(self._config.cosmos_database)
                    self._cosmos_container = self._cosmos_db.create_container_if_not_exists(
                        id=COSMOS_CONTAINER,
                        partition_key=PartitionKey(path="/id"),
                    )
                    logger.info("Cosmos DB initialised (db=%s)", self._config.cosmos_database)
            except Exception as e:
                logger.warning("Cosmos DB init failed (non-blocking): %s", e)
                self._cosmos_container = None

        return self._cosmos_container is not None

    @property
    def available(self) -> bool:
        """True only when both Cosmos DB and Blob Storage are reachable (needed for uploads)."""
        return self._ensure_init() and self._blob_client is not None

    @property
    def cosmos_available(self) -> bool:
        """True when Cosmos DB is reachable (sufficient for read operations)."""
        self._ensure_init()
        return self._cosmos_container is not None

    # ------------------------------------------------------------------
    # Blob Storage — slide images
    # ------------------------------------------------------------------

    def upload_slide_image(self, presentation_id: str, slide_index: int, png_bytes: bytes) -> str | None:
        """Upload a slide PNG to blob storage. Returns the blob URL."""
        self._ensure_init()
        if not self._blob_client:
            return None
        blob_name = f"{presentation_id}/{slide_index}.png"
        try:
            blob_client = self._blob_client.get_blob_client(
                container=self._config.blob_container, blob=blob_name
            )
            blob_client.upload_blob(
                png_bytes,
                overwrite=True,
                content_settings=ContentSettings(content_type="image/png"),
            )
            return blob_client.url
        except Exception as e:
            logger.error("Failed to upload slide image %s: %s", blob_name, e)
            return None

    def upload_pptx(self, presentation_id: str, filename: str, pptx_bytes: bytes) -> str | None:
        """Upload the original PPTX file to blob storage. Returns the blob URL."""
        self._ensure_init()
        if not self._blob_client:
            return None
        blob_name = f"{presentation_id}/{filename}"
        try:
            blob_client = self._blob_client.get_blob_client(
                container=self._config.blob_container, blob=blob_name
            )
            blob_client.upload_blob(
                pptx_bytes,
                overwrite=True,
                content_settings=ContentSettings(
                    content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
                ),
            )
            return blob_client.url
        except Exception as e:
            logger.error("Failed to upload PPTX %s: %s", blob_name, e)
            return None

    def get_pptx_url(self, presentation_id: str, filename: str) -> str | None:
        """Get a SAS-signed blob URL for the original PPTX file (read-only, 24h expiry)."""
        self._ensure_init()
        if not self._blob_client:
            return None
        blob_name = f"{presentation_id}/{filename}"
        blob_client = self._blob_client.get_blob_client(
            container=self._config.blob_container, blob=blob_name
        )
        sas_token = self._generate_sas_token(blob_name)
        if sas_token:
            return f"{blob_client.url}?{sas_token}"
        return blob_client.url

    def get_slide_image_url(self, presentation_id: str, slide_index: int) -> str | None:
        """Get a SAS-signed blob URL for a slide image (read-only, 24h expiry)."""
        self._ensure_init()
        if not self._blob_client:
            return None
        blob_name = f"{presentation_id}/{slide_index}.png"
        blob_client = self._blob_client.get_blob_client(
            container=self._config.blob_container, blob=blob_name
        )
        sas_token = self._generate_sas_token(blob_name)
        if sas_token:
            return f"{blob_client.url}?{sas_token}"
        return blob_client.url

    def _generate_sas_token(self, blob_name: str) -> str | None:
        """Generate a read-only SAS token via User Delegation Key (managed identity)."""
        if not self._blob_client or not self._account_name or not self._credential:
            return None
        try:
            now = datetime.now(timezone.utc)
            start = now - timedelta(minutes=5)
            expiry = now + timedelta(hours=24)
            udk = self._get_user_delegation_key(start, expiry)
            if not udk:
                return None
            return generate_blob_sas(
                account_name=self._account_name,
                container_name=self._config.blob_container,
                blob_name=blob_name,
                user_delegation_key=udk,
                permission=BlobSasPermissions(read=True),
                expiry=expiry,
                start=start,
            )
        except Exception as e:
            logger.warning("Failed to generate SAS token for %s: %s", blob_name, e)
            return None

    def _get_user_delegation_key(self, start: datetime, expiry: datetime):
        """Get or reuse a cached User Delegation Key."""
        now = datetime.now(timezone.utc)
        if (
            self._user_delegation_key
            and self._delegation_key_expiry
            and now < self._delegation_key_expiry - timedelta(hours=1)
        ):
            return self._user_delegation_key
        try:
            self._user_delegation_key = self._blob_client.get_user_delegation_key(
                key_start_time=start, key_expiry_time=expiry,
            )
            self._delegation_key_expiry = expiry
            return self._user_delegation_key
        except Exception as e:
            logger.warning("Failed to get user delegation key: %s", e)
            return None

    def download_slide_image(self, presentation_id: str, slide_index: int) -> bytes | None:
        """Download a slide PNG from blob storage."""
        self._ensure_init()
        if not self._blob_client:
            return None
        blob_name = f"{presentation_id}/{slide_index}.png"
        try:
            blob_client = self._blob_client.get_blob_client(
                container=self._config.blob_container, blob=blob_name
            )
            return blob_client.download_blob().readall()
        except Exception as e:
            logger.warning("Failed to download slide image %s: %s", blob_name, e)
            return None

    # ------------------------------------------------------------------
    # Cosmos DB — presentation metadata
    # ------------------------------------------------------------------

    def save_presentation(self, data: dict) -> bool:
        """Save presentation metadata to Cosmos DB. Uses filename as id."""
        self._ensure_init()
        if not self._cosmos_container:
            return False
        try:
            self._cosmos_container.upsert_item(data)
            logger.info("Saved presentation '%s' to Cosmos DB", data.get("id"))
            return True
        except Exception as e:
            logger.error("Failed to save presentation: %s", e)
            return False

    def get_presentation(self, presentation_id: str) -> dict | None:
        """Get presentation metadata by id."""
        self._ensure_init()
        if not self._cosmos_container:
            return None
        try:
            return self._cosmos_container.read_item(
                item=presentation_id, partition_key=presentation_id
            )
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None
        except Exception as e:
            logger.error("Failed to get presentation %s: %s", presentation_id, e)
            return None

    def list_presentations(self) -> list[dict]:
        """List all presentations (id, filename, slide_count)."""
        self._ensure_init()
        if not self._cosmos_container:
            return []
        try:
            query = "SELECT c.id, c.filename, c.slide_count FROM c"
            return list(self._cosmos_container.query_items(
                query=query, enable_cross_partition_query=True
            ))
        except Exception as e:
            logger.error("Failed to list presentations: %s", e)
            return []

    def list_uc1_decks(self) -> list[dict]:
        """List UC1 Learning Hub decks (source='uc1') with metadata."""
        self._ensure_init()
        if not self._cosmos_container:
            return []
        try:
            query = (
                "SELECT c.id, c.filename, c.slide_count, c.language, "
                "c.uploaded_at, c.tags, c.source FROM c WHERE c.source = 'uc1'"
            )
            return list(self._cosmos_container.query_items(
                query=query, enable_cross_partition_query=True
            ))
        except Exception as e:
            logger.error("Failed to list UC1 decks: %s", e)
            return []

    def delete_presentation(self, presentation_id: str) -> bool:
        """Delete a presentation from Cosmos DB."""
        self._ensure_init()
        if not self._cosmos_container:
            return False
        try:
            self._cosmos_container.delete_item(
                item=presentation_id, partition_key=presentation_id
            )
            return True
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return False
        except Exception as e:
            logger.error("Failed to delete presentation %s: %s", presentation_id, e)
            return False

    def delete_slide_images(self, presentation_id: str) -> bool:
        """Delete all slide image blobs for a presentation."""
        self._ensure_init()
        if not self._blob_client:
            return False
        try:
            container_client = self._blob_client.get_container_client(
                self._config.blob_container
            )
            prefix = f"{presentation_id}/"
            blobs = container_client.list_blobs(name_starts_with=prefix)
            for blob in blobs:
                container_client.delete_blob(blob.name)
            logger.info("Deleted blob images for presentation %s", presentation_id)
            return True
        except Exception as e:
            logger.error("Failed to delete slide images for %s: %s", presentation_id, e)
            return False


def _extract_account_name(connection_string: str) -> str | None:
    """Extract AccountName from an Azure Storage connection string."""
    for part in connection_string.split(";"):
        if part.strip().lower().startswith("accountname="):
            return part.strip().split("=", 1)[1]
    return None
