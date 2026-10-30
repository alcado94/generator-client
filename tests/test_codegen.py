import copy
import importlib
from pathlib import Path

from openapi_spec_validator import validate
import pytest
import yaml

from empresa_sdk_core import load_oauth_metadata
from scripts.prepare_codegen import HTTP_METHODS, prepare

ROOT = Path(__file__).resolve().parents[1]


def test_transform_preserves_original_and_security_semantics():
    original = yaml.safe_load((ROOT / "openapi.yaml").read_text())
    before = copy.deepcopy(original)
    derived, metadata = prepare(original)
    validate(original)
    validate(derived)
    assert original == before
    assert derived["security"] == [{"EmpresaOAuth": []}]
    assert derived["paths"]["/salud"]["get"]["security"] == []
    assert "security" not in derived["paths"]["/ventas/{venta_id}"]["get"]
    assert metadata["operations"]["obtener_venta"]["scopes"] == ["ventas.read"]
    assert metadata["operations"]["obtener_salud"]["security"] == []
    assert len(metadata["operations"]) == 15


@pytest.mark.parametrize("module,count", [("ventas", 5), ("clientes", 5), ("productos", 3), ("sistema", 2)])
def test_modules_are_valid_and_isolated(module, count):
    path = ROOT / "build" / f"{module}.yaml"
    assert path.exists(), "Ejecutar python scripts/generate.py antes de las pruebas"
    document = yaml.safe_load(path.read_text())
    validate(document)
    validate(yaml.safe_load((ROOT / "build" / f"{module}.codegen.yaml").read_text()))
    operations = [op for item in document["paths"].values() for method, op in item.items() if method in HTTP_METHODS]
    assert len(operations) == count
    assert all(op["tags"] == [module.capitalize()] for op in operations)
    package = importlib.import_module(f"empresa_sdk_{module}")
    api_path = Path(package.__file__).parent / "api"
    assert {p.stem for p in api_path.glob("*_api.py")} == {f"{module}_api"}
    if module != "ventas":
        assert not (Path(package.__file__).parent / "models" / "venta.py").exists()
    metadata = load_oauth_metadata(package.__name__)
    assert metadata["scopes"] == ([] if module == "sistema" else [f"{module}.read", f"{module}.write"])


@pytest.mark.parametrize("case", ["multiple", "flow", "scope"])
def test_unsupported_contracts_fail_clearly(case):
    document = yaml.safe_load((ROOT / "openapi.yaml").read_text())
    scheme = document["components"]["securitySchemes"]["EmpresaOAuth"]
    if case == "multiple":
        document["components"]["securitySchemes"]["OtherOAuth"] = copy.deepcopy(scheme)
    elif case == "flow":
        scheme["flows"] = {"password": scheme["flows"]["clientCredentials"]}
    else:
        document["paths"]["/ventas"]["get"]["security"] = [{"EmpresaOAuth": ["unknown"]}]
    with pytest.raises(ValueError):
        prepare(document)
