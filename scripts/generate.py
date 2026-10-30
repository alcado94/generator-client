"""Genera SDK independientes y publica sus metadatos como recursos del wheel."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import shutil

import yaml

from prepare_codegen import prepare

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("ventas", "clientes", "productos", "sistema")


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def package_config(name, version, package):
    return f'''# Generado por scripts/generate.py; no editar manualmente.
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "empresa-sdk-{name}"
version = "{version}"
description = "SDK del módulo {name} de Empresa API"
requires-python = ">=3.11"
dependencies = ["empresa-sdk-core=={version}", "urllib3>=2.1,<3", "python-dateutil>=2.8.2,<3", "pydantic>=2.10,<3", "typing-extensions>=4.7.1"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
{package} = ["oauth.json", "py.typed"]
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", choices=MODULES, action="append", dest="modules")
    args = parser.parse_args()
    version = yaml.safe_load((ROOT / "openapi.yaml").read_text())["info"]["version"]
    run(str(ROOT / "node_modules/.bin/redocly"), "lint", "openapi.yaml")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    for name in args.modules or MODULES:
        spec = build / f"{name}.yaml"
        run(str(ROOT / "node_modules/.bin/redocly"), "bundle", name, "-o", str(spec), "--remove-unused-components")
        codegen, metadata = prepare(yaml.safe_load(spec.read_text()))
        codegen_file = build / f"{name}.codegen.yaml"
        codegen_file.write_text(yaml.safe_dump(codegen, sort_keys=False, allow_unicode=True))
        metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
        (build / f"{name}.oauth.json").write_text(metadata_json)
        package = f"empresa_sdk_{name}"
        output = ROOT / "packages" / f"empresa-sdk-{name}"
        # Un destino limpio evita que sobrevivan modelos eliminados del contrato.
        if output.exists():
            marker = output / ".empresa-generated"
            if not marker.exists():
                sys.exit(f"Destino sin marcador de generación: {output}")
            shutil.rmtree(output)
        output.mkdir(parents=True)
        (output / ".empresa-generated").touch()
        run(str(ROOT / "node_modules/.bin/openapi-generator-cli"), "generate",
            "-i", str(codegen_file), "-g", "python", "-o", str(output),
            "--additional-properties=" + ",".join([
                "library=urllib3", f"packageName={package}", f"projectName=empresa-sdk-{name}",
                f"packageVersion={version}", "sourceFolder=src",
                "disallowAdditionalPropertiesIfNotPresent=false", "hideGenerationTimestamp=true",
            ]), "--global-property", "apiTests=false,modelTests=false")
        source = output / "src" / package
        if not source.exists() and (output / package).is_dir():
            (output / "src").mkdir(exist_ok=True)
            shutil.move(str(output / package), str(source))
        (source / "oauth.json").write_text(metadata_json)
        (output / "pyproject.toml").write_text(package_config(name, version, package))
        # El generador también emite setup.py/setup.cfg; el pyproject anterior es la autoridad.
        for legacy in ("setup.py", "setup.cfg"):
            (output / legacy).unlink(missing_ok=True)
    print("SDK generados. Instalación local y construcción: véase README.md")


if __name__ == "__main__":
    main()
