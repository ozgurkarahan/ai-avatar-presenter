"""Azure OpenAI clients must refresh Entra ID tokens (no static bearer token).

Regression: cached clients (deck Q&A) were built with a one-off token string;
once it expired every answer failed with 401 (seen in the live E2E as
``qa.error answer_failed`` on the second demo question).
"""
import time

from config import load_config
from services import translation


class _Tok:
    def __init__(self, token: str, expires_on: int) -> None:
        self.token = token
        self.expires_on = expires_on


class _ShortLivedCred:
    """Each token is valid for 60 s, i.e. already inside the refresh window."""

    calls = 0

    def __init__(self, *a, **kw) -> None:
        pass

    def get_token(self, *scopes, **kw):
        type(self).calls += 1
        return _Tok(f"tok-{type(self).calls}", int(time.time()) + 60)

    def get_token_info(self, *scopes, **kw):
        return self.get_token(*scopes, **kw)


def test_managed_identity_client_uses_refreshing_token_provider(monkeypatch):
    monkeypatch.setattr(translation, "DefaultAzureCredential", _ShortLivedCred)
    monkeypatch.setattr(translation, "_token_provider", None)
    _ShortLivedCred.calls = 0
    cfg = load_config()
    cfg.use_managed_identity = True
    cfg.openai_endpoint = "https://example.openai.azure.com/"

    client = translation.get_openai_client(cfg)

    assert client._azure_ad_token is None
    provider = client._azure_ad_token_provider
    assert callable(provider)
    first, second = provider(), provider()
    assert first != second  # near-expiry tokens are re-fetched, never reused
    # One shared credential for every client (token cache survives).
    assert translation.get_openai_client(cfg)._azure_ad_token_provider is provider
