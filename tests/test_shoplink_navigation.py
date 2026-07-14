from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_JS = (ROOT / "app" / "web" / "client.js").read_text(encoding="utf-8")
CLIENT_HTML = (ROOT / "app" / "web" / "client.html").read_text(encoding="utf-8")


def function_source(name: str) -> str:
    marker = f"function {name}("
    start = CLIENT_JS.index(marker)
    end = CLIENT_JS.find("\n  function ", start + len(marker))
    return CLIENT_JS[start : end if end >= 0 else len(CLIENT_JS)]


def test_shoplink_catalog_code_does_not_claim_every_shoplink_submodule():
    source = function_source("cxIsShoplinkCode026K")

    assert 'normalized.includes("shoplink")' not in source


def test_shoplink_submodule_active_navigation_prefers_exact_codes():
    functions = {
        "cxSlProActiveCode026L": "cxIsShoplinkProductsCode026L",
        "cxSlCarActiveCode026M": "cxIsShoplinkOrdersCode026M",
        "cxSlCliActiveCode026N": "cxIsShoplinkClientsCode026N",
        "cxSlCamActiveCode026O": "cxIsShoplinkCampaignsCode026O",
    }

    for function_name, exact_matcher in functions.items():
        source = function_source(function_name)
        exact_position = source.index(f"modules.find((item) => {exact_matcher}")
        fuzzy_position = source.index("|| modules.find(")
        assert exact_position < fuzzy_position


def test_shoplink_fuzzy_detectors_respect_explicit_sibling_codes():
    functions = [
        "cxIsShoplinkModule026K",
        "cxIsShoplinkProductsModule026L",
        "cxIsShoplinkOrdersModule026M",
        "cxIsShoplinkClientsModule026N",
        "cxIsShoplinkCampaignsModule026O",
    ]

    for function_name in functions:
        assert "cxShoplinkExactModuleKind032B" in function_source(function_name)


def test_shoplink_navigation_cache_version_is_updated():
    assert "032B_SHOPLINK_STRICT_ROUTING" in CLIENT_HTML
