import time
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
import requests

from demo.server import CLIENT_ID, PRODUCT_ID, SALE_ID
from empresa_sdk_core import ClientCredentialsProvider, load_oauth_metadata, oauth_configuration
from empresa_sdk_ventas import ApiClient, Configuration, CrearVenta, LineaVenta, CancelacionVenta
from empresa_sdk_ventas.api.ventas_api import VentasApi
from empresa_sdk_ventas.exceptions import ApiException
from empresa_sdk_clientes import ApiClient as ClientApiClient, Configuration as ClientConfiguration, CrearCliente, ActualizarCliente
from empresa_sdk_clientes.api.clientes_api import ClientesApi
from empresa_sdk_productos import ApiClient as ProductApiClient, Configuration as ProductConfiguration, ActualizarExistencias
from empresa_sdk_productos.api.productos_api import ProductosApi
from empresa_sdk_sistema import ApiClient as SystemApiClient, Configuration as SystemConfiguration
from empresa_sdk_sistema.api.sistema_api import SistemaApi


def provider_for(base, scopes, **kwargs):
    return ClientCredentialsProvider(token_url=base + "/oauth/token", client_id="demo-client",
                                     client_secret="demo-secret", scopes=scopes, **kwargs)


@pytest.mark.parametrize("auth_method", ["client_secret_basic", "client_secret_post"])
def test_generated_sales_client_and_real_oauth(live_server, auth_method):
    base, app = live_server
    metadata = load_oauth_metadata("empresa_sdk_ventas")
    with provider_for(base, metadata["scopes"], auth_method=auth_method) as provider:
        config = oauth_configuration(Configuration, provider=provider, host=base + "/v1")
        with ApiClient(config) as client:
            api = VentasApi(client)
            assert api.listar_ventas(page=1, page_size=1).paginacion.total == 1
            assert api.obtener_venta(SALE_ID).total == 2500  # Seguridad heredada.
            body = CrearVenta(cliente_id=CLIENT_ID, moneda="EUR", notas=None,
                              metadatos={"origen": "pytest"},
                              lineas=[LineaVenta(producto_id=PRODUCT_ID, cantidad=3, precio_unitario=1250)])
            key = str(uuid4())
            sale = api.crear_venta(idempotency_key=key, crear_venta=body)
            assert sale.total == 3750
            assert api.crear_venta(idempotency_key=key, crear_venta=body).id == sale.id
            assert len(api.listar_lineas_venta(sale.id)) == 1
            assert api.cancelar_venta(sale.id, CancelacionVenta(motivo="Prueba completada")).estado == "cancelada"
            with pytest.raises(ApiException) as error:
                api.cancelar_venta(sale.id, CancelacionVenta(motivo="Repetida"))
            assert error.value.status == 409
            assert app.state.token_requests == 1


def test_missing_invalid_and_insufficient_tokens(live_server):
    base, _ = live_server
    with ApiClient(Configuration(host=base + "/v1")) as client:
        with pytest.raises(ApiException) as error:
            VentasApi(client).listar_ventas()
        assert error.value.status == 401
    with provider_for(base, ["clientes.read"]) as provider:
        config = oauth_configuration(Configuration, provider=provider, host=base + "/v1")
        with ApiClient(config) as client:
            with pytest.raises(ApiException) as error:
                VentasApi(client).listar_ventas()
            assert error.value.status == 403
    response = requests.get(base + "/v1/ventas", headers={"Authorization": "Bearer invalid"}, timeout=5)
    assert response.status_code == 401


def test_expired_tokens_and_automatic_reacquisition(live_server):
    base, app = live_server
    with provider_for(base, ["ventas.read"]) as provider:
        old_token = provider.get_token()
        time.sleep(2.1)
        assert requests.get(base + "/v1/ventas", headers={"Authorization": f"Bearer {old_token}"}, timeout=5).status_code == 401
        config = oauth_configuration(Configuration, provider=provider, host=base + "/v1")
        with ApiClient(config) as client:
            assert VentasApi(client).listar_ventas().paginacion.total == 1
        assert app.state.token_requests == 2


def test_public_operations_do_not_request_tokens(live_server):
    base, app = live_server

    class FailingProvider:
        def get_token(self):
            pytest.fail("Un endpoint público no debe solicitar un token")

    config = oauth_configuration(SystemConfiguration, provider=FailingProvider(), host=base + "/v1")
    with SystemApiClient(config) as client:
        api = SistemaApi(client)
        assert api.obtener_salud().estado == "ok"
        assert api.obtener_version().version == "1.0.0"
    assert app.state.token_requests == 0


def test_clients_and_products_generated_sdks(live_server):
    base, _ = live_server
    with provider_for(base, ["clientes.read", "clientes.write", "productos.read", "productos.write"]) as provider:
        config = oauth_configuration(ClientConfiguration, provider=provider, host=base + "/v1")
        with ClientApiClient(config) as client:
            api = ClientesApi(client)
            assert api.listar_clientes(q="demo", activo=True).paginacion.total == 1
            created = api.crear_cliente(CrearCliente(nombre="Nuevo", email="nuevo@example.org", fecha_alta="2026-10-30"))
            assert api.obtener_cliente(created.id).nombre == "Nuevo"
            assert api.actualizar_cliente(created.id, ActualizarCliente(nombre="Actualizado")).nombre == "Actualizado"
            assert api.desactivar_cliente(created.id) is None
            assert api.obtener_cliente(created.id).activo is False
        config = oauth_configuration(ProductConfiguration, provider=provider, host=base + "/v1")
        with ProductApiClient(config) as client:
            api = ProductosApi(client)
            assert api.listar_productos(categoria="hardware", etiquetas=["demo", "oficina"]).paginacion.total == 1
            assert api.obtener_producto(PRODUCT_ID).sku == "DEMO-001"
            assert api.actualizar_existencias(PRODUCT_ID, ActualizarExistencias(existencias=7)).existencias == 7


def test_demo_business_and_validation_errors(live_server):
    base, _ = live_server
    with provider_for(base, ["ventas.read", "ventas.write", "clientes.write"]) as provider:
        headers = {"Authorization": "Bearer " + provider.get_token()}
        assert requests.get(base + "/v1/ventas?page=0", headers=headers, timeout=5).status_code == 422
        assert requests.get(base + f"/v1/ventas/{uuid4()}", headers=headers, timeout=5).status_code == 404
        payload = {"cliente_id": CLIENT_ID, "moneda": "EUR", "lineas": [
            {"producto_id": PRODUCT_ID, "cantidad": 1, "precio_unitario": 1250}]}
        headers["Idempotency-Key"] = "test-conflict"
        assert requests.post(base + "/v1/ventas", json=payload, headers=headers, timeout=5).status_code == 201
        payload["lineas"][0]["cantidad"] = 2
        assert requests.post(base + "/v1/ventas", json=payload, headers=headers, timeout=5).status_code == 409
        payload["lineas"] = []
        assert requests.post(base + "/v1/ventas", json=payload, headers=headers, timeout=5).status_code == 422
        assert requests.patch(base + f"/v1/clientes/{CLIENT_ID}", json={}, headers=headers, timeout=5).status_code == 422


def test_oauth_errors(live_server):
    base, _ = live_server
    url = base + "/oauth/token"
    assert requests.post(url, data={"grant_type": "client_credentials"}, timeout=5).status_code == 401
    result = requests.post(url, auth=("demo-client", "demo-secret"),
                           data={"grant_type": "client_credentials", "scope": "unknown"}, timeout=5)
    assert result.status_code == 400
    assert result.json()["error"] == "invalid_scope"


@pytest.mark.parametrize("example", ["listar_ventas.py", "crear_venta.py"])
def test_documented_examples(live_server, example):
    base, _ = live_server
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, OAUTH_CLIENT_ID="demo-client", OAUTH_CLIENT_SECRET="demo-secret",
               OAUTH_TOKEN_URL=base + "/oauth/token", API_BASE_URL=base + "/v1")
    result = subprocess.run([sys.executable, str(root / "examples" / example)], env=env,
                            check=True, capture_output=True, text=True, timeout=15)
    payload = json.loads(result.stdout)
    if example == "listar_ventas.py":
        assert payload["paginacion"]["total"] == 1
    else:
        assert payload["total"] == 2500
