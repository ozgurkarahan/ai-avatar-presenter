import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from backend directory, then project root
_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / ".env", override=True)
load_dotenv(_backend_dir.parent.parent / ".env")


@dataclass
class AzureConfig:
    speech_endpoint: str
    speech_key: str
    speech_region: str
    speech_resource_id: str
    openai_endpoint: str
    openai_key: str
    openai_chat_deployment: str
    openai_embedding_deployment: str
    libreoffice_path: str = "soffice"
    use_managed_identity: bool = False
    use_local_search: bool = True
    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database: str = "ai-presenter"
    blob_connection_string: str = ""
    blob_container: str = "slide-images"


def load_config() -> AzureConfig:
    """Load configuration from environment variables (.env supported)."""
    return AzureConfig(
        speech_endpoint=os.environ.get("AZURE_SPEECH_ENDPOINT", ""),
        speech_key=os.environ.get("AZURE_SPEECH_KEY", ""),
        speech_region=os.environ.get("AZURE_SPEECH_REGION", "swedencentral"),
        speech_resource_id=os.environ.get("AZURE_SPEECH_RESOURCE_ID", ""),
        openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
        openai_key=os.environ.get("AZURE_OPENAI_KEY", ""),
        openai_chat_deployment=os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1"),
        openai_embedding_deployment=os.environ.get(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
        ),
        libreoffice_path=os.environ.get("LIBREOFFICE_PATH", "soffice"),
        use_managed_identity=os.environ.get("AZURE_USE_MANAGED_IDENTITY", "").lower() == "true",
        use_local_search=os.environ.get("USE_LOCAL_SEARCH", "true").lower() == "true",
        cosmos_endpoint=os.environ.get("AZURE_COSMOS_ENDPOINT", ""),
        cosmos_key=os.environ.get("AZURE_COSMOS_KEY", ""),
        cosmos_database=os.environ.get("AZURE_COSMOS_DATABASE", "ai-presenter"),
        blob_connection_string=os.environ.get("AZURE_BLOB_CONNECTION_STRING", ""),
        blob_container=os.environ.get("AZURE_BLOB_CONTAINER", "slide-images"),
    )
