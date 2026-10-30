"""OAuth2 Client Credentials independiente de los clientes generados."""

from .oauth import ClientCredentialsProvider, load_oauth_metadata, oauth_configuration

__all__ = ["ClientCredentialsProvider", "load_oauth_metadata", "oauth_configuration"]
