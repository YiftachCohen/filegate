"""Excludes and risk levels. Deterministic, every decision has a readable reason.

Levels (lower = safer to skip):
  0 license/meta, vendored          1 docs, styles without imports, generated/minified
  2 config/data, text-like unknowns 3 test code, generated code, unknown types
  4 type/content mismatch, test code with dangerous calls, config with script
  5 production code, templates, CI/infra, anything with a possible secret
"""
from __future__ import annotations

import re

CI_INFRA = re.compile(
    r"(^|/)(\.github/(workflows|actions)/|\.gitlab-ci|\.circleci/|Jenkinsfile|azure-pipelines|\.buildkite/|bitbucket-pipelines"
    r"|Dockerfile|docker-compose|Containerfile|\.?helm/|charts/|k8s/|kubernetes/|deploy/|terraform/|Makefile$)"
    r"|\.(tf|tfvars|hcl|bicep|nix)$", re.I)
TEMPLATE_EXT = {".html", ".htm", ".php", ".phtml", ".twig", ".erb", ".ejs", ".hbs", ".handlebars", ".mustache",
                ".jinja", ".jinja2", ".j2", ".tpl", ".vue", ".svelte", ".astro", ".jsp", ".aspx", ".cshtml", ".razor",
                ".liquid", ".njk", ".pug"}
STYLE_EXT = {".css", ".scss", ".sass", ".less", ".styl", ".pcss"}
CONFIG_EXT = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".plist", ".properties", ".env", ".editorconfig"}
PROSE_EXT = {".md", ".markdown", ".rst", ".txt", ".adoc", ".asciidoc", ".org", ".rdoc", ".textile"}
JS_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
LOW_NAMES = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS|CONTRIBUTORS|CHANGELOG|CHANGES|HISTORY|CODEOWNERS|\.gitignore|\.gitattributes|\.prettierrc|\.eslintignore|\.dockerignore)([.\w-]*)$", re.I)
GENERATED_PATH = re.compile(r"\.pb\.(go|cc|h|swift)$|_pb2(_grpc)?\.pyi?$|\.g\.dart$|\.freezed\.dart$|[._-]generated\.|(^|/)(generated|__generated__|gen)/|\.designer\.cs$", re.I)
TEXTY_LABELS = {"txt", "csv", "json", "xml", "markdown", "ini", "yaml", "toml", "rst", "tsv", "jsonl", "srt"}
CODE_LABELS = {"python", "shell", "javascript", "typescript", "php", "ruby", "perl", "powershell", "batch", "lua",
               "go", "rust", "c", "cpp", "cs", "java", "kotlin", "scala", "swift", "vba", "groovy", "dart"}


def excluded(f: dict, ex: dict) -> str | None:
    """Reason if the file is on the exclude list (or binary), else None."""
    p = f["path"]
    if f["binary"] or not f.get("magika_text", True):
        return "binary"
    parts = p.split("/")[:-1]
    for d in ex.get("dirs", []):
        if d in parts:
            return f"excluded dir {d}/"
    name = p.rsplit("/", 1)[-1]
    if name in set(ex.get("names", [])):
        return "lockfile/excluded name"
    if f["ext"] in set(ex.get("extensions", [])) or p.endswith(tuple(ex.get("suffixes", []))):
        return f"excluded type {f['ext'] or name}"
    return None


def level(f: dict) -> tuple[int, str]:
    p, ext, lt = f["path"], f["ext"], f["ltype"]
    script, url = f.get("script"), f.get("remote_url")
    generated = bool(GENERATED_PATH.search(p))
    minified = f.get("avg_line", 0) > 300

    if f.get("secret"):
        return 5, "possible secret"
    if CI_INFRA.search(p):
        return 5, "CI/CD or infra"
    if ext in TEMPLATE_EXT:
        return 5, "template/markup that renders"
    code = lt == "programming" or (not f["lang"] and f.get("magika") in CODE_LABELS) or ext in JS_EXT
    if code and not f["test_path"] and not generated and not minified:
        return 5, f"code ({f['lang'] or f.get('magika')})"
    if lt in ("data", "prose", "") and f.get("magika") in CODE_LABELS and f.get("magika_group") == "code":
        return 4, f"type says {lt or 'unknown'}, content looks like {f['magika']}"
    if code and f.get("exec_like"):
        return 4, "test/generated code with dangerous calls"
    if code:
        return 3, "test code" if f["test_path"] else "generated/minified code"
    if ext in CONFIG_EXT or lt == "data":
        return (4, "config/data with script") if script else (2, "config/data" + (" with URLs" if url else ""))
    if ext in STYLE_EXT:
        return (2, "stylesheet with imports/url()") if (f.get("style_import") or script) else (1, "stylesheet, no imports")
    if LOW_NAMES.search(p):
        return 0, "license/changelog/meta"
    if f["vendored"] and not p.startswith(".github/"):
        return 0, "vendored"
    if ext in PROSE_EXT or f["docs"] or lt == "prose":
        return (2, "docs with script") if script else (1, "docs/prose")
    if minified or generated:
        return 1, "generated/minified"
    m = f.get("magika", "")
    if m in TEXTY_LABELS:
        return 2, f"unknown ext, content looks like {m}"
    if f.get("magika_group") == "code":
        return 4, f"unknown ext, content looks like {m}"
    return 3, f"unknown type ({m})"


def kind(f: dict, lvl: int, why: str) -> str | None:
    """Which fact set decides this file, or None if rules alone decide it."""
    if "test" in why:
        return "test"
    if lvl == 5:
        return "js" if f["ext"] in JS_EXT and why.startswith("code") and not f["path"].endswith(".d.ts") else None
    if 2 <= lvl <= 4:
        return "config"
    return None
