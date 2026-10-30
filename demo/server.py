"""API de laboratorio en memoria. Ejecutar con uvicorn demo.server:app."""

import base64
from datetime import date, datetime, timezone
import secrets
import threading
import time
from typing import Annotated, Literal
from urllib.parse import unquote
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, model_validator

CLIENT_ID = "11111111-1111-4111-8111-111111111111"
PRODUCT_ID = "22222222-2222-4222-8222-222222222222"
SALE_ID = "33333333-3333-4333-8333-333333333333"
SCOPES = {f"{module}.{action}" for module in ("ventas", "clientes", "productos") for action in ("read", "write")}
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Category = Literal["hardware", "software", "servicios"]
SaleStatus = Literal["pendiente", "confirmada", "cancelada"]


class Address(BaseModel):
    calle: str = Field(min_length=1, max_length=200)
    ciudad: str = Field(min_length=1, max_length=100)
    codigo_postal: str = Field(min_length=1, max_length=20)
    pais: str = Field(pattern=r"^[A-Z]{2}$")


class NewClient(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    email: EmailStr = Field(max_length=254)
    fecha_alta: date
    direccion: Address | None = None
    telefono: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def validate_address(self):
        if "direccion" in self.model_fields_set and self.direccion is None:
            raise ValueError("direccion puede omitirse, pero no admite null")
        return self


class ClientPatch(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = Field(default=None, max_length=254)
    direccion: Address | None = None
    telefono: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Se requiere al menos un campo")
        if any(getattr(self, name) is None for name in self.model_fields_set - {"telefono"}):
            raise ValueError("Solo telefono admite null")
        return self


class SaleLine(BaseModel):
    producto_id: UUID
    cantidad: int = Field(ge=1, le=10000)
    precio_unitario: int = Field(ge=0)


class NewSale(BaseModel):
    cliente_id: UUID
    moneda: Literal["EUR", "USD", "GBP"]
    lineas: list[SaleLine] = Field(min_length=1, max_length=100)
    notas: str | None = Field(default=None, max_length=1000)
    metadatos: dict[str, str] = Field(default_factory=dict)


class Cancellation(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


class Stock(BaseModel):
    existencias: int = Field(ge=0, le=1000000)


def fail(status, code, detail):
    raise HTTPException(status, {"codigo": code, "detalle": detail},
                        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None)


def create_app(*, token_lifetime=120):
    app = FastAPI(title="Empresa API demo", version="1.0.0")
    lock = threading.RLock()
    tokens = {}
    idempotency = {}
    clients = {CLIENT_ID: {"id": CLIENT_ID, "nombre": "Cliente Demo", "email": "demo@empresa.example",
                           "fecha_alta": "2026-10-30", "activo": True}}
    products = {PRODUCT_ID: {"id": PRODUCT_ID, "sku": "DEMO-001", "nombre": "Teclado de prueba",
                             "categoria": "hardware", "precio": 1250, "moneda": "EUR",
                             "existencias": 100, "etiquetas": ["demo", "oficina"]}}
    sales = {SALE_ID: {"id": SALE_ID, "cliente_id": CLIENT_ID, "moneda": "EUR", "estado": "pendiente",
                       "lineas": [{"producto_id": PRODUCT_ID, "cantidad": 2, "precio_unitario": 1250}],
                       "total": 2500, "creada_en": "2026-10-30T10:00:00Z"}}
    app.state.token_requests = 0

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        content = exc.detail if isinstance(exc.detail, dict) else {"codigo": "http_error", "detalle": str(exc.detail)}
        return JSONResponse(content, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"codigo": "validation_error", "detalle": "Datos no válidos",
                             "errores": [f"{e['loc']}: {e['msg']}" for e in exc.errors()]}, status_code=422)

    def require(scope):
        def check(authorization: Annotated[str | None, Header()] = None):
            bearer = authorization.removeprefix("Bearer ") if authorization else ""
            with lock:
                token = tokens.get(bearer)
                if token is None or token["expires_at"] <= time.monotonic():
                    fail(401, "unauthorized", "Token ausente o caducado")
                if scope not in token["scopes"]:
                    fail(403, "insufficient_scope", f"Scope requerido: {scope}")
        return Depends(check)

    def find(collection, key):
        if str(key) not in collection:
            fail(404, "not_found", "Recurso no encontrado")
        return collection[str(key)]

    def page_result(items, page, page_size):
        items = list(items)
        return {"items": items[(page - 1) * page_size:page * page_size],
                "paginacion": {"page": page, "page_size": page_size, "total": len(items)}}

    def unique_email(email, exclude=None):
        if any(c["email"].lower() == email.lower() and c["id"] != exclude for c in clients.values()):
            fail(409, "duplicate_email", "El email ya está registrado")

    @app.post("/oauth/token")
    async def issue_token(request: Request):
        form = await request.form()
        client_id, secret = form.get("client_id", ""), form.get("client_secret", "")
        auth = request.headers.get("authorization", "")
        if auth.startswith("Basic "):
            try:
                raw_id, raw_secret = base64.b64decode(auth[6:], validate=True).decode().split(":", 1)
                client_id, secret = unquote(raw_id), unquote(raw_secret)
            except (ValueError, UnicodeDecodeError):
                return JSONResponse({"error": "invalid_client"}, status_code=401)
        if not (secrets.compare_digest(str(client_id), "demo-client") and
                secrets.compare_digest(str(secret), "demo-secret")):
            return JSONResponse({"error": "invalid_client"}, status_code=401,
                                headers={"WWW-Authenticate": "Basic"})
        if form.get("grant_type") != "client_credentials":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
        scopes = set(str(form.get("scope", "")).split())
        if not scopes.issubset(SCOPES):
            return JSONResponse({"error": "invalid_scope"}, status_code=400)
        token = secrets.token_urlsafe(32)
        with lock:
            tokens[token] = {"scopes": scopes, "expires_at": time.monotonic() + token_lifetime}
            app.state.token_requests += 1
        return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": token_lifetime,
                             "scope": " ".join(sorted(scopes))},
                            headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

    @app.get("/v1/salud")
    def health():
        return {"estado": "ok"}

    @app.get("/v1/version")
    def version():
        return {"version": "1.0.0", "servicio": "empresa-api-demo"}

    @app.get("/v1/clientes", dependencies=[require("clientes.read")])
    def list_clients(page: Page = 1, page_size: PageSize = 20,
                     q: Annotated[str | None, Query(max_length=100)] = None, activo: bool | None = None):
        with lock:
            return page_result((c for c in clients.values() if
                                (q is None or q.lower() in c["nombre"].lower()) and
                                (activo is None or c["activo"] == activo)), page, page_size)

    @app.post("/v1/clientes", status_code=201, dependencies=[require("clientes.write")])
    def new_client(body: NewClient):
        with lock:
            unique_email(str(body.email))
            value = body.model_dump(mode="json", exclude_unset=True)
            value.update(id=str(uuid4()), activo=True)
            clients[value["id"]] = value
            return value

    @app.get("/v1/clientes/{cliente_id}", dependencies=[require("clientes.read")])
    def get_client(cliente_id: UUID):
        with lock:
            return find(clients, cliente_id)

    @app.patch("/v1/clientes/{cliente_id}", dependencies=[require("clientes.write")])
    def patch_client(cliente_id: UUID, body: ClientPatch):
        with lock:
            value = find(clients, cliente_id)
            if body.email is not None:
                unique_email(str(body.email), str(cliente_id))
            value.update(body.model_dump(mode="json", exclude_unset=True))
            return value

    @app.delete("/v1/clientes/{cliente_id}", status_code=204, dependencies=[require("clientes.write")])
    def deactivate_client(cliente_id: UUID):
        with lock:
            find(clients, cliente_id)["activo"] = False
        return Response(status_code=204)

    @app.get("/v1/productos", dependencies=[require("productos.read")])
    def list_products(page: Page = 1, page_size: PageSize = 20, categoria: Category | None = None,
                      etiquetas: Annotated[list[Annotated[str, Field(max_length=40)]] | None,
                                           Query(max_length=10)] = None):
        with lock:
            return page_result((p for p in products.values() if
                                (categoria is None or p["categoria"] == categoria) and
                                set(etiquetas or []).issubset(p["etiquetas"])), page, page_size)

    @app.get("/v1/productos/{producto_id}", dependencies=[require("productos.read")])
    def get_product(producto_id: UUID):
        with lock:
            return find(products, producto_id)

    @app.put("/v1/productos/{producto_id}/existencias", dependencies=[require("productos.write")])
    def stock(producto_id: UUID, body: Stock):
        with lock:
            value = find(products, producto_id)
            value["existencias"] = body.existencias
            return value

    @app.get("/v1/ventas", dependencies=[require("ventas.read")])
    def list_sales(page: Page = 1, page_size: PageSize = 20, estado: SaleStatus | None = None,
                   cliente_id: UUID | None = None, desde: datetime | None = None):
        with lock:
            if desde is not None and desde.tzinfo is None:
                fail(422, "validation_error", "desde debe incluir zona horaria")
            return page_result((s for s in sales.values() if
                                (estado is None or s["estado"] == estado) and
                                (cliente_id is None or s["cliente_id"] == str(cliente_id)) and
                                (desde is None or datetime.fromisoformat(s["creada_en"].replace("Z", "+00:00")) >= desde)),
                               page, page_size)

    @app.post("/v1/ventas", status_code=201, dependencies=[require("ventas.write")])
    def new_sale(body: NewSale, response: Response,
                 idempotency_key: Annotated[str, Header(min_length=1, max_length=128)]):
        payload = body.model_dump(mode="json", exclude_unset=True)
        with lock:
            if idempotency_key in idempotency:
                previous, sale_id = idempotency[idempotency_key]
                if previous != payload:
                    fail(409, "idempotency_conflict", "Clave reutilizada con otro cuerpo")
                response.headers["Location"] = f"/v1/ventas/{sale_id}"
                return sales[sale_id]
            client = find(clients, body.cliente_id)
            if not client["activo"]:
                fail(409, "inactive_client", "Cliente desactivado")
            for line in body.lineas:
                find(products, line.producto_id)
            value = dict(payload, id=str(uuid4()), estado="pendiente",
                         total=sum(line.cantidad * line.precio_unitario for line in body.lineas),
                         creada_en=datetime.now(timezone.utc).isoformat())
            sales[value["id"]] = value
            idempotency[idempotency_key] = (payload, value["id"])
            response.headers["Location"] = f"/v1/ventas/{value['id']}"
            return value

    @app.get("/v1/ventas/{venta_id}", dependencies=[require("ventas.read")])
    def get_sale(venta_id: UUID):
        with lock:
            return find(sales, venta_id)

    @app.get("/v1/ventas/{venta_id}/lineas", dependencies=[require("ventas.read")])
    def lines(venta_id: UUID):
        with lock:
            return find(sales, venta_id)["lineas"]

    @app.post("/v1/ventas/{venta_id}/cancelacion", dependencies=[require("ventas.write")])
    def cancel(venta_id: UUID, body: Cancellation):
        with lock:
            value = find(sales, venta_id)
            if value["estado"] != "pendiente":
                fail(409, "invalid_state", "Solo pueden cancelarse ventas pendientes")
            value.update(estado="cancelada", motivo_cancelacion=body.motivo)
            return value

    return app


app = create_app()
