# Manual de usuario

## 1. Objetivo y conceptos básicos

Esta herramienta genera bibliotecas cliente **Python 3.11+** a partir de un
contrato OpenAPI. Cada módulo funcional se distribuye como un paquete independiente
y utiliza una capa compartida de autenticación OAuth2 Client Credentials.

En este manual, **crear un nuevo cliente** significa generar un nuevo SDK o módulo
Python para consumir una API. Registrar un cliente comercial mediante
`ClientesApi.crear_cliente()` es una operación de negocio diferente.

| Concepto | Significado | Ejemplo |
| --- | --- | --- |
| Contrato | Describe endpoints, modelos y autenticación | `openapi.yaml` |
| Tag | Agrupa operaciones del mismo módulo | `Ventas` |
| Módulo | Nombre utilizado por los scripts | `ventas` |
| Distribución | Nombre usado para instalar con pip | `empresa-sdk-ventas` |
| Paquete Python | Nombre usado en los imports | `empresa_sdk_ventas` |
| Clase API | Agrupa los métodos generados para un tag | `VentasApi` |
| Core | Proveedor de tokens e integración compartida | `empresa-sdk-core` |
| Metapaquete | Instala módulos seleccionados mediante extras | `empresa-sdk[ventas]` |

El recorrido de trabajo es:

```text
Preparar entorno → editar OpenAPI → validar → generar → instalar
                  → probar → construir wheels → distribuir
```

### Qué procedimiento seguir

- **Primera instalación:** sección 2.
- **Probar el proyecto localmente:** sección 3.
- **Usar un SDK desde una aplicación:** sección 4.
- **Regenerar un módulo o añadirle endpoints:** sección 5.
- **Crear un módulo nuevo, como Facturación:** sección 6.
- **Adaptar el proyecto a otra API:** sección 7.
- **Construir, distribuir y actualizar versiones:** sección 8.
- **Resolver problemas:** sección 9.

## 2. Preparación del entorno

### 2.1. Requisitos

Necesitas Python 3.11+, Node.js 22.12+ o una LTS posterior compatible, npm y Java
17+. La primera instalación descarga dependencias de npm, PyPI y Maven.

Comprueba las herramientas:

```bash
python --version
node --version
npm --version
java -version
```

Todos los comandos siguientes se ejecutan desde la raíz del proyecto. Los comandos
de terminal de este manual están escritos para Bash en Linux/macOS. Si utilizas
otro intérprete o Windows, adapta la activación del entorno y la carga de variables.

### 2.2. Instalar las dependencias de desarrollo

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -e packages/empresa-sdk-core
npm ci
```

Si `.venv` ya existe y está preparado, basta con activarlo. La opción `-e` instala
el código local en modo editable. Las herramientas Node se instalan en
`node_modules/`; los scripts utilizan sus ejecutables locales.

### 2.3. Generar e instalar los módulos iniciales

```bash
python scripts/generate.py
python -m pip install \
  -e packages/empresa-sdk-ventas \
  -e packages/empresa-sdk-clientes \
  -e packages/empresa-sdk-productos \
  -e packages/empresa-sdk-sistema \
  -e 'packages/empresa-sdk[all]'
```

La generación valida el contrato, separa las operaciones por tag, adapta la
seguridad para el generador y crea los paquetes en `packages/`.

Instalar únicamente el metapaquete local con `[all]` no indica a pip dónde están
los otros proyectos locales: por eso se pasan también sus directorios en el mismo
comando. Para consumir wheels, consulta la sección 8.

### 2.4. Comprobar la instalación

```bash
python -m pytest -q
python -m pip check
```

Las pruebas arrancan sus propios servidores en puertos libres. No necesitas iniciar
la demo manualmente para ejecutarlas. La versión inicial del proyecto tiene 26
casos de prueba; el número aumentará al incorporar nuevas comprobaciones.

## 3. Primera prueba con la API de demostración

### 3.1. Arrancar el servidor

En una terminal:

```bash
source .venv/bin/activate
uvicorn demo.server:app --host 127.0.0.1 --port 8000
```

Deja este proceso activo. El servicio utiliza:

| Parámetro | Valor local |
| --- | --- |
| URL base de API | `http://127.0.0.1:8000/v1` |
| URL de token | `http://127.0.0.1:8000/oauth/token` |
| Client ID de demostración | `demo-client` |
| Client secret de demostración | `demo-secret` |

### 3.2. Cargar la configuración y ejecutar ejemplos

En otra terminal:

```bash
source .venv/bin/activate
set -a
source .env.example
set +a
python examples/listar_ventas.py
python examples/crear_venta.py
```

`set -a` exporta las variables del archivo al proceso Python. Los ejemplos no
cargan archivos `.env` automáticamente.

Resultados esperados tras iniciar un servidor nuevo:

1. La consulta devuelve una página con una venta inicial.
2. La creación devuelve una nueva venta con estado `pendiente` y total `2500`.
3. El servidor obtiene tokens mediante `/oauth/token` y los SDK los envían como
   Bearer en las llamadas protegidas.

Los importes se expresan en unidades menores: `2500` corresponde a `25,00 EUR`.
Los datos se guardan en memoria y se reinician al parar el servidor. Para detenerlo,
pulsa `Ctrl+C` en su terminal. Utiliza un único worker para esta demo.

## 4. Usar un SDK desde una aplicación

### 4.1. Elegir los módulos

Una vez disponibles los wheels en `dist/`, instala desde tu aplicación con:

```bash
python -m pip install --find-links /ruta/al/proyecto/dist 'empresa-sdk[ventas]==1.0.0'
```

O selecciona varios módulos:

```bash
python -m pip install --find-links /ruta/al/proyecto/dist 'empresa-sdk[ventas,clientes]==1.0.0'
```

Para todos:

```bash
python -m pip install --find-links /ruta/al/proyecto/dist 'empresa-sdk[all]==1.0.0'
```

Sustituye la ruta por la ubicación real. Estos comandos pueden descargar de PyPI
las dependencias externas. Tras publicar en un registro privado, configura ese
índice y omite `--find-links`.

### 4.2. Configurar el entorno real

```bash
export API_BASE_URL='https://api.empresa.example/v1'
export OAUTH_TOKEN_URL='https://auth.empresa.example/oauth/token'
export OAUTH_CLIENT_ID='identificador-asignado'
export OAUTH_CLIENT_SECRET='secreto-asignado'
```

Son valores de ejemplo que debes sustituir. `API_BASE_URL` incluye el prefijo de
la API, como `/v1`; no incluye `/ventas` ni el endpoint de tokens. Obtén las
credenciales y permisos del administrador de vuestro proveedor OAuth2.

### 4.3. Consultar ventas

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
    auth_method="client_secret_basic",
    timeout=10,
) as provider:
    configuration = oauth_configuration(
        Configuration,
        provider=provider,
        host=os.environ["API_BASE_URL"],
        scheme=metadata["scheme"],
    )
    with ApiClient(configuration) as client:
        api = VentasApi(client)
        pagina = api.listar_ventas(page=1, page_size=20)
        for venta in pagina.items:
            print(venta.id, venta.estado, venta.total)
```

Si tu proveedor requiere el secreto en el cuerpo de la petición, cambia
`auth_method` a `client_secret_post`. El SDK obtiene otro access token antes de
caducar el anterior; no tienes que llamar a un método de renovación.

Reutiliza el proveedor y el `ApiClient` durante el trabajo de tu aplicación para
aprovechar la caché. Cada nuevo proveedor mantiene su propia caché. Los contextos
`with` cierran los recursos al terminar.

Los metadatos del módulo están dentro del paquete instalado. El consumidor no
necesita disponer de `openapi.yaml` ni del directorio `build/`.

### 4.4. Operaciones públicas

Sistema no requiere un proveedor OAuth2:

```python
from empresa_sdk_sistema import ApiClient, Configuration
from empresa_sdk_sistema.api.sistema_api import SistemaApi

with ApiClient(Configuration(host="http://127.0.0.1:8000/v1")) as client:
    print(SistemaApi(client).obtener_salud().estado)
```

### 4.5. Consultar métodos y tratar errores

La documentación generada está en:

```text
packages/empresa-sdk-ventas/docs/VentasApi.md
packages/empresa-sdk-ventas/docs/Venta.md
packages/empresa-sdk-clientes/docs/ClientesApi.md
```

Cada módulo contiene su propia carpeta `docs/`. Consulta sus firmas antes de
llamar a una operación nueva: los nombres dependen de los tags y `operationId`.

```python
from empresa_sdk_ventas.exceptions import ApiException

# Dentro del contexto donde ya has creado api:
try:
    venta = api.obtener_venta("33333333-3333-4333-8333-333333333333")
except ApiException as error:
    print("Estado HTTP:", error.status)
    print("Respuesta:", error.body)
```

Los errores al obtener tokens se originan en Authlib o en el proveedor compartido,
antes de la llamada de negocio. No son necesariamente `ApiException`.
Para mostrar un modelo completo utiliza `model_dump_json(indent=2)`: el método
generado `to_json()` omite campos `readOnly` al serializar solicitudes.

## 5. Regenerar clientes existentes o añadir operaciones

### 5.1. Regenerar sin cambiar el contrato

```bash
python scripts/generate.py --module ventas
```

Para varios módulos:

```bash
python scripts/generate.py --module ventas --module clientes
```

Para todos los módulos registrados:

```bash
python scripts/generate.py
```

`--module` acepta los nombres presentes en `MODULES` de `scripts/generate.py`.
No existe actualmente una opción `--input`: el contrato de entrada es el archivo
`openapi.yaml` de la raíz.

**La regeneración sustituye por completo el directorio generado del módulo.**
Guarda las personalizaciones en el contrato, en los scripts o en una capa propia.
Si el destino existe pero no tiene `.empresa-generated`, la herramienta se detiene.
Revisa su contenido antes de decidir cómo conservarlo o moverlo.

### 5.2. Añadir un endpoint a un módulo ya registrado

1. Añade la ruta y el método HTTP bajo `paths` en `openapi.yaml`.
2. Utiliza el tag exacto del módulo; por ejemplo, `tags: [Ventas]`.
3. Define un `operationId` único y estable, preferiblemente en `snake_case`.
4. Declara parámetros, cuerpos y respuestas con esquemas completos.
5. Declara `security` con los scopes apropiados; añade los scopes nuevos al flujo
   `clientCredentials` si es necesario. Para una operación pública, usa `security: []`.
6. Ejecuta la validación y regenera el módulo.
7. Reinstala el paquete si cambian dependencias o metadatos y verifica la operación
   contra una API que la implemente.

```bash
npm run lint
python scripts/generate.py --module ventas
python -m pip install -e packages/empresa-sdk-ventas
```

Si añades operaciones al contrato de la demo, implementa también esas rutas en
`demo/server.py` y actualiza las pruebas que cuentan operaciones o llaman a todas
las rutas. El generador produce código cliente, no implementaciones de servidor.

## 6. Crear un nuevo cliente modular: ejemplo Facturación

El registro de módulos es explícito en la versión actual. Añadir un tag al contrato
no basta para que los scripts descubran automáticamente el módulo.

El ejemplo siguiente crea un SDK con una operación de consulta. Los fragmentos se
integran en las secciones existentes de los archivos; **no crees claves YAML o
tablas TOML duplicadas**.

### Paso 1. Elegir los nombres

| Elemento | Nombre |
| --- | --- |
| Tag | `Facturacion` |
| Nombre de módulo | `facturacion` |
| Distribución | `empresa-sdk-facturacion` |
| Paquete importable | `empresa_sdk_facturacion` |
| Clase API esperada | `FacturacionApi` |
| Scope | `facturacion.read` |

Usa nombres sencillos y sin espacios para el módulo. La capitalización de los
tags debe coincidir con el filtro de Redocly. Un único tag funcional por operación
facilita mantener separados los SDK.

### Paso 2. Ampliar `openapi.yaml`

Añade a la lista superior `tags`:

```yaml
- name: Facturacion
  description: Consulta de facturas emitidas.
```

Añade al mapa `paths`:

```yaml
/facturas:
  get:
    tags: [Facturacion]
    operationId: listar_facturas
    summary: Consultar las facturas emitidas
    security:
      - EmpresaOAuth: [facturacion.read]
    responses:
      '200':
        description: Facturas encontradas
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ListaFacturas'
      '401':
        $ref: '#/components/responses/Unauthorized'
      '403':
        $ref: '#/components/responses/Forbidden'
```

Añade dentro de `components.schemas`:

```yaml
Factura:
  type: object
  required: [id, cliente_id, total, moneda]
  properties:
    id:
      type: string
      format: uuid
    cliente_id:
      type: string
      format: uuid
    total:
      type: integer
      format: int64
      minimum: 0
    moneda:
      type: string
      enum: [EUR, USD, GBP]
ListaFacturas:
  type: object
  required: [items]
  properties:
    items:
      type: array
      items:
        $ref: '#/components/schemas/Factura'
```

Añade al mapa existente
`components.securitySchemes.EmpresaOAuth.flows.clientCredentials.scopes`:

```yaml
facturacion.read: Consultar facturas
```

Declara expresamente la seguridad de la nueva operación: de lo contrario heredará
`ventas.read`, que es el requisito global del contrato de ejemplo.

### Paso 3. Registrar el filtro en `redocly.yaml`

Añade una entrada bajo `apis` al mismo nivel que `ventas` y `clientes`:

```yaml
facturacion:
  root: ./openapi.yaml
  decorators:
    filter-in:
      applyTo: Operation
      property: tags
      value: [Facturacion]
```

### Paso 4. Registrar el módulo en el generador

En `scripts/generate.py`, amplía la tupla:

```python
MODULES = ("ventas", "clientes", "productos", "sistema", "facturacion")
```

Los nombres de distribución, paquete y destino se calculan automáticamente a
partir de `facturacion`. No necesitas copiar un SDK existente.

### Paso 5. Incorporarlo al metapaquete y a la construcción

En `packages/empresa-sdk/pyproject.toml`, dentro de
`[project.optional-dependencies]`, añade el extra y amplía el extra `all` existente:

```toml
facturacion = ["empresa-sdk-facturacion==1.0.0"]
all = [
    "empresa-sdk-ventas==1.0.0",
    "empresa-sdk-clientes==1.0.0",
    "empresa-sdk-productos==1.0.0",
    "empresa-sdk-sistema==1.0.0",
    "empresa-sdk-facturacion==1.0.0",
]
```

En `scripts/build_packages.py`, actualiza:

```python
PACKAGES = ("core", "ventas", "clientes", "productos", "sistema", "facturacion", "")
```

Se construirán siete distribuciones. Conserva la cadena vacía final: representa
el metapaquete `empresa-sdk`.

Añade también a `.gitignore`:

```gitignore
packages/empresa-sdk-facturacion/
```

### Paso 6. Generar e instalar

```bash
npm run lint
python scripts/generate.py --module facturacion
python -m pip install -e packages/empresa-sdk-facturacion -e 'packages/empresa-sdk[all]'
```

Este comando de instalación presupone que ya instalaste los cuatro módulos
iniciales según la sección 2. Si empiezas desde cero, genera todos y pasa también
sus directorios a pip.

Comprueba estos resultados:

```text
build/facturacion.yaml
build/facturacion.codegen.yaml
build/facturacion.oauth.json
packages/empresa-sdk-facturacion/src/empresa_sdk_facturacion/
packages/empresa-sdk-facturacion/docs/FacturacionApi.md
```

Los metadatos OAuth del nuevo módulo deben contener únicamente
`facturacion.read`, porque esa es la única autorización utilizada por sus
operaciones. Declarar otros scopes en el contrato no los añade automáticamente
al conjunto solicitado por el módulo.

### Paso 7. Conectar la API o ampliar la demo

Para usar un servidor real, asegúrate de que implemente `GET /v1/facturas` y de que
el proveedor OAuth2 permita solicitar `facturacion.read` con tus credenciales.

Para probarlo localmente con la demo:

1. Añade `facturacion.read` al conjunto `SCOPES` de `demo/server.py`, después de su
   declaración actual:

   ```python
   SCOPES.add("facturacion.read")
   ```

2. Dentro de `create_app()`, antes de `return app`, añade:

   ```python
   @app.get("/v1/facturas", dependencies=[require("facturacion.read")])
   def list_invoices():
       return {"items": []}
   ```

3. Reinicia el servidor. Una lista vacía es una respuesta válida del nuevo contrato.

Añadir una ruta al OpenAPI no crea la implementación del servidor ni registra el
scope en un proveedor externo.

### Paso 8. Consumir el cliente generado

Con las variables de la sección 3 o 4 cargadas:

```python
import os

from empresa_sdk_core import ClientCredentialsProvider, load_oauth_metadata, oauth_configuration
from empresa_sdk_facturacion import ApiClient, Configuration
from empresa_sdk_facturacion.api.facturacion_api import FacturacionApi

metadata = load_oauth_metadata("empresa_sdk_facturacion")

with ClientCredentialsProvider(
    token_url=os.environ["OAUTH_TOKEN_URL"],
    client_id=os.environ["OAUTH_CLIENT_ID"],
    client_secret=os.environ["OAUTH_CLIENT_SECRET"],
    scopes=metadata["scopes"],
) as provider:
    configuration = oauth_configuration(
        Configuration,
        provider=provider,
        host=os.environ["API_BASE_URL"],
        scheme=metadata["scheme"],
    )
    with ApiClient(configuration) as client:
        resultado = FacturacionApi(client).listar_facturas()
        print(resultado.model_dump_json(indent=2))
```

### Paso 9. Ampliar las comprobaciones

Las pruebas actuales contienen valores explícitos del contrato inicial. Actualiza:

| Archivo | Cambio para este ejemplo |
| --- | --- |
| `tests/test_codegen.py` | El total pasa de 15 a 16 operaciones; añade `("facturacion", 1)` a los módulos parametrizados |
| `tests/test_codegen.py` | Ajusta la expectativa de scopes para Facturación a `["facturacion.read"]`, sin `.write` |
| `tests/test_packaging.py` | Incluye Facturación en los módulos construidos y en los módulos con `oauth.json`; adapta su expectativa de scopes |
| `tests/test_packaging.py` | Incluye Facturación en las comprobaciones de independencia entre paquetes y verifica su extra |
| `scripts/verify_wheels.py` | Añade `facturacion` al bucle de módulos que deben existir para `all` y estar ausentes para `ventas` |

`tests/test_demo_contract.py` recorre las operaciones del contrato: necesitará que
la ruta de la demo y el scope del paso 7 estén implementados. Para este GET sin
cuerpo no hace falta añadir un payload al mapa de solicitudes de esa prueba.
Añade además una prueba de integración del nuevo SDK, incluyendo `403` cuando el
token no tenga `facturacion.read`.

Después ejecuta:

```bash
python scripts/generate.py
python -m pytest -q
python scripts/build_packages.py
python scripts/verify_wheels.py
```

### Paso 10. Distribuir

Publica las distribuciones nuevas junto con el metapaquete actualizado. Desde otro
entorno, la instalación selectiva será:

```bash
python -m pip install --find-links /ruta/al/proyecto/dist 'empresa-sdk[facturacion]==1.0.0'
```

La versión `1.0.0` de estos ejemplos corresponde al laboratorio. Si ya has
publicado esa versión, prepara una versión nueva siguiendo la sección 8.3.

## 7. Generar clientes para otra API

### 7.1. Preparar el contrato

Trabaja sobre una copia del proyecto y coloca el contrato de la nueva API en
`openapi.yaml`. La ruta de entrada actual es fija. Para un contrato con varios
archivos, conserva las rutas de sus referencias para que Redocly pueda resolverlas
al hacer bundle.

Comprueba que el contrato:

- Utilice OpenAPI 3.0.3 para este flujo de trabajo.
- Asigne tags funcionales y `operationId` únicos.
- Declare el esquema OAuth2 con el flujo `clientCredentials`, su `tokenUrl` y sus scopes.
- Especifique correctamente la seguridad global y las excepciones por operación.
- Defina respuestas y modelos suficientes para generar tipos útiles.

La capa actual admite un esquema OAuth2 por SDK y exclusivamente Client Credentials
para ese esquema. El token se solicita con la unión de los scopes de las operaciones
del módulo. Si vuestra API requiere otros flujos o selección de tokens por
operación, hay que ampliar la capa de autenticación.

### 7.2. Alinear la configuración

1. Crea una entrada Redocly por módulo.
2. Actualiza `MODULES` en el generador.
3. Actualiza `PACKAGES` en el constructor de wheels.
4. Ajusta los extras del metapaquete y las dependencias del core.
5. Adapta las pruebas y ejemplos al nuevo contrato; las pruebas existentes usan
   identificadores, rutas y modelos de la demo Empresa.
6. Valida, genera e instala siguiendo las secciones anteriores.

Los prefijos `empresa-sdk-` y `empresa_sdk_` están definidos en los scripts y en el
empaquetado; no se obtienen del título del contrato. Si necesitas otra marca o
familia de paquetes, actualiza también los nombres de distribución, imports,
recursos y dependencias relacionados.

## 8. Construcción, distribución y versiones

### 8.1. Construir y verificar wheels

```bash
python scripts/build_packages.py
python scripts/verify_wheels.py
```

El primer comando construye los paquetes registrados en `PACKAGES` y los deja en
`dist/`. Necesita que esos SDK ya estén generados. El segundo crea entornos
virtuales temporales y comprueba los extras `ventas` y `all`.

También puedes verificar uno solo:

```bash
python scripts/verify_wheels.py --extras ventas
python scripts/verify_wheels.py --extras all
```

Este verificador está especializado en la estructura de Empresa. Al sustituir los
módulos o cambiar la versión debes adaptarlo antes de usarlo como comprobación de
publicación.

### 8.2. Distribuir los paquetes

Entrega los wheels generados o súbelos al registro Python privado con el mecanismo
de publicación de vuestra organización. Publica el core, los módulos necesarios y
el metapaquete de versiones compatibles. El proyecto construye los artefactos;
no incluye un comando propio de publicación ni credenciales del registro.

Tras configurar el índice privado en pip, el consumidor podrá ejecutar:

```bash
python -m pip install 'empresa-sdk[ventas]==1.0.0'
```

La instalación del SDK no necesita Node, Java, Redocly ni el contrato OpenAPI.
Estas herramientas se utilizan en la generación, no en la aplicación consumidora.

### 8.3. Preparar una versión nueva

En la estructura actual todos los módulos generados comparten `info.version` y
requieren el core de esa misma versión exacta. Para pasar, por ejemplo, a `1.1.0`:

1. Cambia `info.version` en `openapi.yaml`.
2. Cambia la versión de `packages/empresa-sdk-core/pyproject.toml`.
3. Cambia la versión, dependencia del core y versiones de todos los extras en
   `packages/empresa-sdk/pyproject.toml`.
4. Actualiza las referencias fijas a `1.0.0` en `scripts/verify_wheels.py` y las
   expectativas de dependencias en `tests/test_packaging.py`.
5. Mantén coherentes la versión del workspace y la información de versión de la
   demo si forman parte de esa entrega; no controlan la versión del SDK generado.
6. Regenera **todos** los módulos, reinstala core y módulos en el entorno de
   desarrollo y vuelve a ejecutar las pruebas.
7. Construye los nuevos wheels, verifica la instalación y publica los artefactos
   correspondientes a esa entrega.

No edites los `pyproject.toml` de los módulos generados para cambiar versiones:
se vuelven a escribir en cada generación. `dist/` puede conservar wheels de
versiones anteriores; selecciona los artefactos de la versión que vas a distribuir.

## 9. Resolución de problemas

| Síntoma | Comprobación o acción |
| --- | --- |
| `python` no encuentra paquetes | Activa `.venv` y utiliza `python -m pip` para instalar con el mismo intérprete |
| No existe el ejecutable local de Redocly | Ejecuta `npm ci` en la raíz |
| Falla la descarga del generador | Comprueba acceso a Maven, configuración de red y proxy del entorno |
| Java no se encuentra | Instala Java 17+ y comprueba `java -version` |
| `--module facturacion` no se acepta | Añade el nombre a `MODULES` en `scripts/generate.py` |
| Redocly no encuentra el módulo | Añade la entrada correspondiente bajo `apis` en `redocly.yaml` |
| El bundle no contiene las operaciones esperadas | Revisa coincidencia exacta entre los tags de las operaciones y el filtro |
| «Destino sin marcador de generación» | Inspecciona y conserva el contenido existente antes de moverlo o resolver el conflicto |
| `ModuleNotFoundError: empresa_sdk_...` | Genera el módulo e instala su directorio o wheel; generar no instala |
| pip no encuentra `empresa-sdk-core==...` | Ofrece el wheel del core con `--find-links`, instala su proyecto local o configura el índice privado |
| Faltan `OAUTH_CLIENT_ID` u otras variables | Exporta las variables; los ejemplos no leen `.env` por sí solos |
| El endpoint de tokens responde `invalid_client` | Comprueba credenciales y si requiere `client_secret_basic` o `client_secret_post` |
| El endpoint de tokens responde `invalid_scope` | Revisa scopes declarados, metadatos generados y permisos del cliente OAuth2 |
| La API responde `401` | Comprueba token, URL y proveedor; el SDK no reintenta automáticamente una operación tras un `401` |
| La API responde `403` | El token no tiene los permisos requeridos por la operación |
| La API responde `404` | Comprueba host, prefijo `/v1`, ruta y existencia del recurso |
| Un endpoint nuevo no funciona en la demo | Implementa la ruta en `demo/server.py` y reinicia el proceso |
| La API responde `422` | Revisa el cuerpo o los parámetros frente al contrato y el detalle del error |
| El token no se puede cachear | El proveedor debe devolver un `expires_in` positivo y finito y un token de tipo Bearer |
| No aparecen `id` o `total` al imprimir | Usa `model_dump_json()` o accede a los atributos, en lugar de `to_json()` |
| Fallan las pruebas al cambiar el contrato | Revisa conteos, scopes, casos de prueba y rutas de demo dependientes del contrato inicial |

## 10. Referencia rápida de archivos y comandos

| Archivo o directorio | Cuándo modificarlo |
| --- | --- |
| `openapi.yaml` | Al añadir o cambiar operaciones, modelos, scopes o versión |
| `redocly.yaml` | Al añadir o cambiar filtros de módulos |
| `scripts/generate.py` | Al registrar módulos o cambiar convenciones de generación |
| `scripts/build_packages.py` | Al cambiar las distribuciones que se construyen |
| `scripts/verify_wheels.py` | Al cambiar módulos o versión verificados |
| `packages/empresa-sdk/pyproject.toml` | Al cambiar extras y dependencias del metapaquete |
| `packages/empresa-sdk-core/` | Al modificar la capa compartida de autenticación |
| `demo/server.py` | Al añadir comportamiento a la API local o scopes del emisor demo |
| `tests/` | Al incorporar nuevos contratos, módulos o casos de comportamiento |
| `build/` | Artefactos intermedios; se regeneran |
| `packages/empresa-sdk-<modulo>/` | Código generado; se sustituye al regenerar |
| `dist/` | Wheels construidos para distribución |

```bash
# Validar el contrato
npm run lint

# Generar un módulo
python scripts/generate.py --module ventas

# Generar todos los módulos registrados
python scripts/generate.py

# Ejecutar las pruebas
python -m pytest -q

# Construir las distribuciones
python scripts/build_packages.py

# Comprobar instalaciones limpias
python scripts/verify_wheels.py
```
