"""Fast tests on a tiny fixture repo. Regex backend only: no model downloads."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from filegate import config, policy
from filegate.cost import file_cost
from filegate.evaluate import evaluate
from filegate.facts import get, risk
from filegate.inventory import scan

REPO = Path(__file__).parent / "fixtures" / "repo"


@pytest.fixture(scope="module")
def decisions():
    cfg = config.load()
    backend = get(cfg)
    return {d["path"]: d for d in (policy.route(f, cfg, backend) for f in scan(REPO, cfg["models_dir"]))}


def test_every_file_gets_a_route_and_reason(decisions):
    assert decisions
    for d in decisions.values():
        assert d["route"] in {"excluded", "skip", "cheap", "full"}
        assert d["reason"]
        assert "text" not in d  # file content never leaves the process


@pytest.mark.parametrize("path,route", [
    ("node_modules/lib/index.js", "excluded"),
    ("styles/plain.scss", "cheap"),            # stylesheet, no imports -> low risk
    ("docs/guide.md", "cheap"),
    ("LICENSE", "cheap"),
    ("server/app.py", "full"),                 # production code
    (".github/workflows/ci.yml", "full"),      # CI is always scanned
    ("tests/test_auth.py", "full"),            # test that exercises auth
    ("tests/test_math.py", "cheap"),           # test with no risky facts
    ("config/builder.yml", "full"),            # config that defines hooks/scripts
    ("config/plain.yaml", "cheap"),
    ("src/api/users.js", "full"),              # JS that calls the network
    ("src/components/Raw.js", "full"),         # JS that sets innerHTML
    ("src/components/Button.jsx", "cheap"),    # UI-only component
])
def test_routes(decisions, path, route):
    assert decisions[path]["route"] == route, decisions[path]


def test_skip_mode():
    cfg = config.load()
    cfg["policy"]["low_risk_route"] = "skip"
    backend = get(cfg)
    ds = {d["path"]: d for d in (policy.route(f, cfg, backend) for f in scan(REPO, cfg["models_dir"]))}
    assert ds["styles/plain.scss"]["route"] == "skip"


def test_discount_fact_lowers_risk():
    facts = {"ui_only": {"role": "discount"}, "network": {}}
    assert risk({"ui_only": 1.0, "network": 0.8}, facts) == pytest.approx(0.4)
    assert risk({"ui_only": 0.0, "network": 0.8}, facts) == pytest.approx(0.8)


def test_cost_routes():
    c = config.load()["cost"]
    f = {"bytes": 4000}
    full, cheap = file_cost(f, "full", c), file_cost(f, "cheap", c)
    assert full == pytest.approx((3000 + 1000) * 5 / 1e6 + 1000 * 25 / 1e6)
    assert cheap < full and file_cost(f, "skip", c) == 0


def test_evaluate_counts_findings_by_any_file(decisions):
    cfg = config.load()
    findings = [("f1", ["server/app.py", "tests/test_math.py"]),   # caught via the prod file
                ("f2", ["styles/plain.scss"]),                    # only on the cheap route
                ("f3", ["does/not/exist.py"])]
    r = evaluate(list(decisions.values()), findings, cfg)
    assert r["caught_by_full_model"] == 1
    assert r["caught_by_full_or_cheap"] == 2
    assert r["findings_with_unknown_files"] == 1
    assert 0 < r["saved_pct"] < 100


def test_cli_scan_writes_jsonl(tmp_path):
    from filegate.cli import main
    out = tmp_path / "d.jsonl"
    main(["scan", str(REPO), "--out", str(out)])
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert {r["path"] for r in rows} >= {"server/app.py", "styles/plain.scss"}
