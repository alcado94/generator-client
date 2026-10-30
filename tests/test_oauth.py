from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from empresa_sdk_core import ClientCredentialsProvider
import empresa_sdk_core.oauth as oauth


def test_concurrent_cache_and_early_renewal(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(oauth, "time", SimpleNamespace(monotonic=lambda: now[0]))
    calls = []
    with ClientCredentialsProvider(token_url="https://auth.empresa.example/token", client_id="id",
                                   client_secret="secret", scopes=["ventas.read"]) as provider:
        def fetch(*args, **kwargs):
            calls.append(kwargs)
            return {"access_token": f"token-{len(calls)}", "token_type": "Bearer", "expires_in": 100,
                    "scope": "ventas.read"}
        monkeypatch.setattr(provider._session, "fetch_token", fetch)
        with ThreadPoolExecutor(max_workers=16) as pool:
            assert set(pool.map(lambda _: provider.get_token(), range(100))) == {"token-1"}
        now[0] = 189
        assert provider.get_token() == "token-1"
        now[0] = 191
        assert provider.get_token() == "token-2"
        assert len(calls) == 2
        assert calls[0]["grant_type"] == "client_credentials"
        assert calls[0]["timeout"] == 10
    with pytest.raises(RuntimeError, match="cerrado"):
        provider.get_token()


@pytest.mark.parametrize("changes", [
    {"expires_in": 0}, {"expires_in": "nan"}, {"token_type": "MAC"},
    {"access_token": "bad\r\ntoken"}, {"scope": "clientes.read"},
])
def test_invalid_token_responses_are_not_cached(monkeypatch, changes):
    response = {"access_token": "abc", "token_type": "Bearer", "expires_in": 60, "scope": "ventas.read"}
    response.update(changes)
    with ClientCredentialsProvider(token_url="https://auth.empresa.example/token", client_id="id",
                                   client_secret="secret", scopes=["ventas.read"]) as provider:
        monkeypatch.setattr(provider._session, "fetch_token", lambda *a, **kw: response)
        with pytest.raises(ValueError):
            provider.get_token()
        assert provider._token is None
