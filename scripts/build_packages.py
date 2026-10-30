"""Construye los seis wheels en dist/ para publicación o instalación local."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("core", "ventas", "clientes", "productos", "sistema", "")


def main():
    for name in PACKAGES:
        package = ROOT / "packages" / (f"empresa-sdk-{name}" if name else "empresa-sdk")
        if not (package / "pyproject.toml").is_file():
            sys.exit(f"Paquete ausente: {package}. Ejecuta scripts/generate.py primero.")
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(ROOT / "dist"), str(package)],
                       cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
