"""Contrasta las respuestas del servidor con el contrato mantenido, no con su OpenAPI automático."""

from pathlib import Path

from openapi_schema_validator import OAS30ReadValidator
import requests
import yaml

from demo.server import CLIENT_ID, PRODUCT_ID, SALE_ID, SCOPES


def test_all_demo_operations_match_response_contract(live_server):
    base, _ = live_server
    document = yaml.safe_load((Path(__file__).resolve().parents[1] / "openapi.yaml").read_text())

    def resolve(value):
        while "$ref" in value:
            target = document
            for part in value["$ref"][2:].split("/"):
                target = target[part]
            value = target
        return value

    with requests.Session() as client:
        token = client.post(base + "/oauth/token", auth=("demo-client", "demo-secret"), timeout=5,
                            data={"grant_type": "client_credentials", "scope": " ".join(SCOPES)}).json()["access_token"]
        headers = {"Authorization": "Bearer " + token, "Idempotency-Key": "contract-test"}
        sale_payload = {"cliente_id": CLIENT_ID, "moneda": "EUR", "lineas": [
            {"producto_id": PRODUCT_ID, "cantidad": 2, "precio_unitario": 1250}]}
        bodies = {
            "crear_venta": sale_payload,
            "cancelar_venta": {"motivo": "Prueba de contrato"},
            "crear_cliente": {"nombre": "Contrato", "email": "contrato@example.org", "fecha_alta": "2026-10-30"},
            "actualizar_cliente": {"telefono": None},
            "actualizar_existencias": {"existencias": 50},
        }
        ids = {"venta_id": SALE_ID, "cliente_id": CLIENT_ID, "producto_id": PRODUCT_ID}
        for path, path_item in document["paths"].items():
            for method, operation in path_item.items():
                if method == "parameters":
                    continue
                body = bodies.get(operation["operationId"])
                response = client.request(method, base + "/v1" + path.format(**ids), headers=headers, timeout=5,
                                          **({"json": body} if body is not None else {}))
                assert response.status_code < 300, (operation["operationId"], response.text)
                response_spec = resolve(operation["responses"][str(response.status_code)])
                if "content" in response_spec:
                    schema = response_spec["content"]["application/json"]["schema"]
                    # Mantener los componentes en la raíz resuelve los $ref locales.
                    schema = dict(schema, components=document["components"])
                    OAS30ReadValidator(schema).validate(response.json())
                else:
                    assert response.content == b""
