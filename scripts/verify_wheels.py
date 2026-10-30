"""Prueba los extras ventas y all en entornos virtuales limpios usando dist/."""

import argparse
from pathlib import Path
import subprocess
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extras", nargs="+", choices=("ventas", "all"), default=["ventas", "all"])
    args = parser.parse_args()
    if not (ROOT / "dist" / "empresa_sdk-1.0.0-py3-none-any.whl").exists():
        parser.error("Primero ejecuta python scripts/build_packages.py")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    for extra in args.extras:
        with tempfile.TemporaryDirectory(prefix=f"verify-{extra}-", dir=build) as directory:
            venv.EnvBuilder(with_pip=True).create(directory)
            python = str(Path(directory) / "bin" / "python")
            subprocess.run([python, "-m", "pip", "install", "--find-links", str(ROOT / "dist"),
                            f"empresa-sdk[{extra}]==1.0.0"], check=True)
            code = '''
import importlib.util
from empresa_sdk_core import load_oauth_metadata
from empresa_sdk_ventas import ApiClient, Configuration
assert load_oauth_metadata("empresa_sdk_ventas")["scopes"] == ["ventas.read", "ventas.write"]
'''
            for module in ("clientes", "productos", "sistema"):
                code += f'assert (importlib.util.find_spec("empresa_sdk_{module}") is not None) == {extra == "all"}\n'
            subprocess.run([python, "-c", code], cwd=directory, check=True)
            print(f"Instalación verificada: empresa-sdk[{extra}]")


if __name__ == "__main__":
    main()
