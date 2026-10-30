"""Deriva un contrato Bearer y metadatos OAuth sin modificar el original."""

import argparse
import copy
import json
from pathlib import Path

import yaml

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def prepare(document):
    result = copy.deepcopy(document)
    schemes = result.get("components", {}).get("securitySchemes", {})
    oauth = {name: value for name, value in schemes.items() if value.get("type") == "oauth2"}
    if len(oauth) > 1:
        raise ValueError("Solo se admite un esquema OAuth2 por SDK")
    scheme = next(iter(oauth), None)
    metadata = {"scheme": scheme, "token_url": None, "scopes": [], "operations": {}}
    declared_scopes = {}
    if scheme:
        flow = oauth[scheme].get("flows", {}).get("clientCredentials")
        if flow is None or len(oauth[scheme]["flows"]) != 1:
            raise ValueError("Se requiere exclusivamente el flujo clientCredentials")
        metadata["token_url"] = flow["tokenUrl"]
        declared_scopes = flow.get("scopes", {})
        schemes[scheme] = {"type": "http", "scheme": "bearer"}

    def convert(requirements):
        converted = copy.deepcopy(requirements)
        for requirement in converted:
            if scheme in requirement:
                for scope in requirement[scheme]:
                    if scope not in declared_scopes:
                        raise ValueError(f"Scope no declarado: {scope}")
                requirement[scheme] = []
        return converted

    if "security" in result:
        result["security"] = convert(document["security"])
    scopes = set()
    for path, path_item in document.get("paths", {}).items():
        if "$ref" in path_item:
            raise ValueError("El contrato debe estar bundled antes de transformar seguridad")
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            if "$ref" in operation:
                raise ValueError("Operaciones con $ref no soportadas; ejecutar bundle primero")
            requirements = operation.get("security", document.get("security", []))
            operation_scopes = sorted({scope for req in requirements for scope in req.get(scheme, [])})
            scopes.update(operation_scopes)
            operation_id = operation["operationId"]
            metadata["operations"][operation_id] = {
                "method": method.upper(), "path": path,
                "security": copy.deepcopy(requirements), "scopes": operation_scopes,
            }
            if "security" in operation:
                result["paths"][path][method]["security"] = convert(requirements)
    metadata["scopes"] = sorted(scopes)
    return result, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()
    result, metadata = prepare(yaml.safe_load(args.source.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(result, sort_keys=False, allow_unicode=True))
    args.metadata.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
