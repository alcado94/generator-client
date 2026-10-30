import json
import math
import threading
import time
from importlib.resources import files

from authlib.integrations.requests_client import OAuth2Session


class ClientCredentialsProvider:
    """Caché de tokens por proveedor. Repetir el grant sustituye al refresh_token."""

    def __init__(self, *, token_url, client_id, client_secret, scopes=(),
                 auth_method="client_secret_basic", timeout=10, leeway=30):
        if auth_method not in {"client_secret_basic", "client_secret_post"}:
            raise ValueError("Método de autenticación no soportado")
        if not token_url or not client_id or not client_secret:
            raise ValueError("Se requieren token_url, client_id y client_secret")
        if timeout <= 0 or leeway < 0:
            raise ValueError("timeout debe ser positivo y leeway no negativo")
        self.token_url = token_url
        self.timeout = timeout
        self.leeway = leeway
        self.scopes = tuple(sorted(set(scopes)))
        self._session = OAuth2Session(client_id, client_secret, scope=" ".join(self.scopes),
                                     token_endpoint_auth_method=auth_method)
        self._lock = threading.Lock()
        self._token = None
        self._deadline = 0
        self._closed = False

    def get_token(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("Proveedor cerrado")
            if self._token is not None and time.monotonic() < self._deadline:
                return self._token
            # Limpiar el token anterior evita que Authlib lo envíe al solicitar otro.
            self._session.token = None
            started = time.monotonic()
            token = self._session.fetch_token(self.token_url, grant_type="client_credentials",
                                              timeout=self.timeout)
            lifetime = float(token.get("expires_in", 0))
            if not math.isfinite(lifetime) or lifetime <= 0:
                raise ValueError("El proveedor debe devolver expires_in positivo y finito")
            if str(token.get("token_type", "")).lower() != "bearer":
                raise ValueError("Se requiere un token de tipo Bearer")
            access_token = token.get("access_token")
            if not isinstance(access_token, str) or not access_token or any(c in access_token for c in "\r\n"):
                raise ValueError("access_token no válido")
            granted = token.get("scope")
            if granted is not None and not set(self.scopes).issubset(granted.split()):
                raise ValueError("El proveedor no ha concedido todos los scopes solicitados")
            # Incluso con tokens cortos, reservar como máximo el 10% de su vida.
            self._deadline = started + lifetime - min(self.leeway, lifetime * 0.1)
            self._token = access_token
            return access_token

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                self._token = None
                self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def load_oauth_metadata(package):
    """Carga oauth.json incluido en el wheel del módulo, sin depender de build/."""
    return json.loads(files(package).joinpath("oauth.json").read_text(encoding="utf-8"))


def oauth_configuration(configuration_cls, *, provider, host, scheme="EmpresaOAuth"):
    """Solicita tokens solo cuando ApiClient aplica un requisito de seguridad.

    auth_settings() se evalúa también para endpoints públicos en el generador.
    El diccionario perezoso evita pedir tokens hasta acceder al esquema concreto.
    """
    class LazyAuthSettings(dict):
        def get(self, key, default=None):
            return self[key] if key in self else default

        def __getitem__(self, key):
            value = super().__getitem__(key)
            if key == scheme:
                return {"type": "bearer", "in": "header", "key": "Authorization",
                        "value": "Bearer " + provider.get_token()}
            return value

    class OAuthConfiguration(configuration_cls):
        def auth_settings(self):
            settings = LazyAuthSettings(super().auth_settings())
            settings[scheme] = None
            return settings

    return OAuthConfiguration(host=host)
