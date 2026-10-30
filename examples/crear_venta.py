import os
from uuid import uuid4

from empresa_sdk_core import ClientCredentialsProvider, load_oauth_metadata, oauth_configuration
from empresa_sdk_ventas import ApiClient, Configuration, CrearVenta, LineaVenta
from empresa_sdk_ventas.api.ventas_api import VentasApi


def main():
    metadata = load_oauth_metadata("empresa_sdk_ventas")
    with ClientCredentialsProvider(
        token_url=os.getenv("OAUTH_TOKEN_URL", metadata["token_url"]),
        client_id=os.environ["OAUTH_CLIENT_ID"],
        client_secret=os.environ["OAUTH_CLIENT_SECRET"], scopes=metadata["scopes"],
    ) as provider:
        configuration = oauth_configuration(Configuration, provider=provider,
                                            host=os.getenv("API_BASE_URL", "http://127.0.0.1:8000/v1"),
                                            scheme=metadata["scheme"])
        with ApiClient(configuration) as client:
            result = VentasApi(client).crear_venta(
                idempotency_key=str(uuid4()),
                crear_venta=CrearVenta(
                    cliente_id="11111111-1111-4111-8111-111111111111", moneda="EUR",
                    lineas=[LineaVenta(producto_id="22222222-2222-4222-8222-222222222222",
                                       cantidad=2, precio_unitario=1250)],
                ),
            )
            # to_json() del generador omite readOnly para serializar peticiones.
            print(result.model_dump_json(indent=2, by_alias=True))


if __name__ == "__main__":
    main()
