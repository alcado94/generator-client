import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile


def test_wheels_include_metadata_and_independent_dependencies(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for module in ("core", "ventas", "clientes", "productos", "sistema", ""):
        name = f"empresa-sdk-{module}" if module else "empresa-sdk"
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path),
                        str(root / "packages" / name)], check=True, capture_output=True, text=True)
        wheel = next(tmp_path.glob(name.replace("-", "_") + "-*.whl"))
        with ZipFile(wheel) as archive:
            metadata = archive.read(next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))).decode()
            assert "Requires-Python: >=3.11" in metadata
            if module in ("ventas", "clientes", "productos", "sistema"):
                oauth = json.loads(archive.read(f"empresa_sdk_{module}/oauth.json"))
                assert oauth["scopes"] == ([] if module == "sistema" else [f"{module}.read", f"{module}.write"])
                assert "Requires-Dist: empresa-sdk-core==1.0.0" in metadata
                assert all(f"Requires-Dist: empresa-sdk-{other}" not in metadata
                           for other in ("ventas", "clientes", "productos", "sistema"))
            elif not module:
                assert 'Requires-Dist: empresa-sdk-ventas==1.0.0; extra == "ventas"' in metadata
                assert 'Requires-Dist: empresa-sdk-clientes==1.0.0; extra == "all"' in metadata
