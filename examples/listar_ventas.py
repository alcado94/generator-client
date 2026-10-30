import os

from empresa_sdk_core import ClientCredentialsProvider, load_oauth_metadata, oauth_configuration
from empresa_sdk_ventas import ApiClient, Configuration
from empresa_sdk_ventas.api.ventas_api import VentasApi


def main():
    metadata = load_oauth_metadata("empresa_sdk_ventas")
    with ClientCredentialsProvider(
        token_url=os.getenv("OAUTH_TOKEN_URL", metadata["token_url"]),
        client_id=os.environ["OAUTH_CLIENT_ID"],
        client_secret=os.environ["OAUTH_CLIENT_SECRET"],
        scopes=metadata["scopes"],
    ) as provider:
        configuration = oauth_configuration(Configuration, provider=provider,
                                            scheme=metadata["scheme"],
                                            host=os.getenv("API_BASE_URL", "http://127.0.0.1:8000/v1"))
        with ApiClient(configuration) as client:
            result = VentasApi(client).listar_ventas(page=1, page_size=10)
            print(result.model_dump_json(indent=2, by_alias=True))


if __name__ == "__main__":
    main()
