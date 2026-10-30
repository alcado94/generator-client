# SDK Python modular con OAuth2 Client Credentials

Proyecto de prueba completo: un contrato **OpenAPI 3.0.3** se divide por tags con
**Redocly CLI**, se generan clientes Python síncronos con **OpenAPI Generator +
urllib3** y **Authlib** obtiene y renueva los tokens del proveedor OAuth2.

**Documentación de uso:** [Manual de usuario](MANUAL_USUARIO.md), con instalación,
consumo de SDK, regeneración y un ejemplo paso a paso para crear un nuevo módulo
de Facturación.

## Requisitos

- Python **3.11+**, con `venv` y `pip`.
- Node.js **22.12+** y npm (o una versión LTS posterior compatible con Redocly).
- Java **17+**, para ejecutar OpenAPI Generator.
- Conexión a npm, PyPI y Maven en la primera instalación/generación.

El wrapper npm, Redocly y el generador Java están fijados en `package.json`,
`package-lock.json` y `openapitools.json`. Las dependencias Python declaran rangos
compatibles; para despliegues reproducibles conviene fijarlas en el lock de vuestro
consumidor. El override de `basic-ftp` actualiza la dependencia transitiva del
wrapper a una versión que corrige GHSA-c475-qrg2-pj4r.

## Inicio rápido

Ejecuta desde la raíz del proyecto, en Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -e packages/empresa-sdk-core
npm ci
python scripts/generate.py
python -m pip install \
  -e packages/empresa-sdk-ventas \
  -e packages/empresa-sdk-clientes \
  -e packages/empresa-sdk-productos \
  -e packages/empresa-sdk-sistema \
  -e 'packages/empresa-sdk[all]'
python -m pytest -q
```

Arranca el servidor de demostración:

```bash
uvicorn demo.server:app --host 127.0.0.1 --port 8000
```

En otra terminal, desde la misma raíz:

```bash
source .venv/bin/activate
set -a
source .env.example
set +a
python examples/listar_ventas.py
python examples/crear_venta.py
```

El primer ejemplo devuelve una página con una venta inicial de **2500 céntimos**.
El segundo crea una venta con dos unidades de 1250 céntimos. No requieren leer
ningún archivo de `build/`: los metadatos OAuth están incluidos en el SDK.

## Contrato de prueba

`openapi.yaml` es la fuente de verdad y contiene **15 operaciones**:

| Módulo / tag | Operaciones | Scopes |
| --- | --- | --- |
| Ventas | Listar, crear, obtener, cancelar y consultar líneas | `ventas.read`, `ventas.write` |
| Clientes | Listar, crear, obtener, actualizar y desactivar | `clientes.read`, `clientes.write` |
| Productos | Listar, obtener y actualizar existencias | `productos.read`, `productos.write` |
| Sistema | Salud y versión | Sin autenticación |

El contrato permite probar UUID, fechas, fechas-hora, enumeraciones, modelos
compuestos con `allOf`, cuerpos anidados, mapas de metadatos, campos anulables,
filtros, listas en query, paginación y errores reutilizables. Las referencias a
clientes y productos desde Ventas son identificadores: Ventas no importa sus SDK.
Los importes son enteros en la unidad menor de la moneda.

La seguridad de `obtener_venta` se hereda del contrato global. El resto de
operaciones de negocio declaran sus scopes explícitamente. Las operaciones de
Sistema usan `security: []`.

La demo implementa los endpoints funcionales y errores de validación, autenticación,
autorización, recurso inexistente y conflicto. Los errores `429` del contrato están
reservados para un gateway empresarial y los `503` para indisponibilidad: la demo
no simula rate limiting ni caídas de forma automática.

## Arquitectura y generación

```text
openapi.yaml (OAuth2 clientCredentials)
    │
    ├── Redocly: filtrar por tag + eliminar componentes no usados
    │       └── build/<modulo>.yaml
    │
    ├── prepare_codegen.py: copia para generación
    │       ├── build/<modulo>.codegen.yaml (HTTP Bearer)
    │       └── build/<modulo>.oauth.json (URL, scopes y seguridad original)
    │
    └── OpenAPI Generator (python, urllib3)
            └── packages/empresa-sdk-<modulo>/src/empresa_sdk_<modulo>/
                    ├── api/
                    ├── models/
                    └── oauth.json
```

```bash
npm run lint
python scripts/generate.py
python scripts/generate.py --module ventas
```

`scripts/generate.py` acepta `--module` repetido y regenera únicamente los módulos
indicados. Limpia los destinos que llevan el marcador `.empresa-generated`, para
que desaparezcan modelos y endpoints eliminados del contrato. Si encuentra un
destino sin ese marcador, se detiene. Los directorios generados son desechables;
los cambios propios deben hacerse en el contrato, scripts o core.

La versión Java fijada puede producir estructura plana aunque reciba
`sourceFolder=src`. El script normaliza automáticamente el layout y declara el
empaquetado y las dependencias en `pyproject.toml`. Este postprocesado también
incluye `oauth.json` como recurso del wheel. No modifica la lógica generada del
cliente ni de sus modelos.

La transformación puede ejecutarse por separado:

```bash
python scripts/prepare_codegen.py \
  build/ventas.yaml build/ventas.codegen.yaml build/ventas.oauth.json
```

Preserva el contrato original, vacía los scopes solo en los requisitos Bearer de
la copia y conserva la seguridad original por operación en los metadatos. Rechaza
múltiples esquemas OAuth2, flujos distintos de Client Credentials y scopes no
declarados. Debe recibir un contrato ya bundled, sin referencias de operaciones.

## Autenticación del consumidor

```python
import os
from empresa_sdk_core import (
    ClientCredentialsProvider,
    load_oauth_metadata,
    oauth_configuration,
)
from empresa_sdk_ventas import ApiClient, Configuration
from empresa_sdk_ventas.api.ventas_api import VentasApi

metadata = load_oauth_metadata("empresa_sdk_ventas")
with ClientCredentialsProvider(
    token_url=os.environ["OAUTH_TOKEN_URL"],
    client_id=os.environ["OAUTH_CLIENT_ID"],
    client_secret=os.environ["OAUTH_CLIENT_SECRET"],
    scopes=metadata["scopes"],
    auth_method="client_secret_basic",  # o client_secret_post
    timeout=10,
) as provider:
    config = oauth_configuration(
        Configuration,
        provider=provider,
        host=os.environ["API_BASE_URL"],
        scheme=metadata["scheme"],
    )
    with ApiClient(config) as client:
        print(VentasApi(client).listar_ventas().model_dump_json(indent=2))
```

El proveedor comparte un token en memoria bajo bloqueo. Calcula una caducidad
monótona usando `expires_in`, reservando un margen de hasta 30 segundos o el 10 %
de la vida del token. Solicita otro token con `client_credentials` cuando termina
esa ventana. Comprueba el tipo Bearer, la caducidad y los scopes concedidos cuando
el servidor los devuelve. No usa `refresh_token`.

La configuración evalúa la autenticación de forma perezosa: un endpoint público
no obtiene tokens ni envía el Bearer. El proveedor se cierra después del cliente.

Los ejemplos muestran las respuestas con `model_dump_json()` de Pydantic. El
método `to_json()` del generador está orientado a solicitudes y omite campos
`readOnly`, como el identificador y el total de la venta.

El alcance inicial utiliza **un proveedor y la unión de los scopes del módulo**.
Si el servidor exige un token distinto por operación, será necesario ampliar la
selección del proveedor a partir de la seguridad conservada en los metadatos.
Los errores HTTP se propagan como las excepciones del SDK; no hay reintentos
automáticos de operaciones después de un `401` ni caché de tokens entre procesos.

## Servidor demo

- API: `http://127.0.0.1:8000/v1`.
- Token: `http://127.0.0.1:8000/oauth/token`.
- Credenciales del laboratorio: `demo-client` / `demo-secret`.
- Cliente inicial: `11111111-1111-4111-8111-111111111111`.
- Producto inicial: `22222222-2222-4222-8222-222222222222`.
- Venta inicial: `33333333-3333-4333-8333-333333333333`.

Acepta ambos métodos de autenticación de cliente y emite tokens opacos de 120
segundos. Los datos, tokens y claves de idempotencia se guardan en memoria y se
reinician con el proceso. Ejecuta una sola instancia/worker para esta demo.
El importe y las líneas de una venta no afectan al stock del catálogo.

Para un entorno real cambia `API_BASE_URL` y `OAUTH_TOKEN_URL` y configura las
credenciales del proveedor. Actualiza también los servidores y el `tokenUrl` del
contrato publicado. `.env.example` no se carga automáticamente desde Python.

## Wheels e instalación selectiva

```bash
python scripts/build_packages.py
```

Produce seis distribuciones en `dist/`: core, cuatro módulos y metapaquete.
En un entorno limpio puedes instalar:

```bash
pip install --find-links dist 'empresa-sdk[ventas]==1.0.0'
pip install --find-links dist 'empresa-sdk[all]==1.0.0'
```

También hay extras `clientes`, `productos` y `sistema`. Para varios módulos:

```bash
pip install --find-links dist 'empresa-sdk[ventas,clientes]==1.0.0'
```

`ventas` instala core y Ventas, sin los endpoints ni paquetes de los demás módulos.
Compruébalo automáticamente en dos entornos virtuales nuevos:

```bash
python scripts/verify_wheels.py
```

Una vez publicados los seis wheels en vuestro índice privado, los consumidores
pueden usar `pip install 'empresa-sdk[ventas]'` o `pip install 'empresa-sdk[all]'`
con ese índice configurado. Al cambiar la versión, mantén sincronizados
`info.version`, core, metapaquete y las dependencias exactas de sus extras. La
versión de los módulos generados se obtiene de `info.version`.

## Pruebas

```bash
python -m pytest -q
python scripts/build_packages.py
python scripts/verify_wheels.py
```

Las pruebas necesitan los cuatro módulos generados e instalados. Validan el
contrato original y los derivados, aislamiento modular, transformación de
seguridad, concurrencia y renovación del proveedor, contenido de los wheels y
llamadas a **un servidor TCP local real** con Authlib y urllib3. Cubren las 15
operaciones, ambos métodos de autenticación, expiración real, endpoints públicos,
errores `401`/`403`, validaciones y conflictos de idempotencia/estado.

La prueba de empaquetado construye wheels en un directorio temporal con aislamiento
de build, por lo que puede necesitar acceso a PyPI. `verify_wheels.py` instala las
dependencias en entornos limpios y también puede acceder a PyPI.

## Estructura mantenida

```text
openapi.yaml                   Contrato completo
redocly.yaml                   Filtrado por tags
scripts/prepare_codegen.py     Derivación Bearer y extracción de metadatos
scripts/generate.py            Generación y empaquetado de los módulos
scripts/build_packages.py      Construcción de wheels
scripts/verify_wheels.py       Instalación selectiva en entornos limpios
packages/empresa-sdk-core/     Proveedor Authlib y configuración compartida
packages/empresa-sdk/          Metapaquete con extras
demo/                         API y emisor OAuth2 de laboratorio
examples/                     Consumo de los SDK generados
tests/                        Pruebas unitarias, de contrato e integración
```
