"""Walk a local checkout and compute per-file features. No network, no content written out.

Features: size, binary, Magika content type, linguist language/type/vendored/docs
(if `filegate fetch-models` stored linguist's data in models_dir), test path, and
cheap content signals. The file head is kept in memory (`text`) for the fact
backends and dropped before anything is written.
"""
from __future__ import annotations

import os, re, subprocess
from pathlib import Path

HEAD_BYTES = 256 * 1024
TEXT_BYTES = 8 * 1024   # what fact backends and the head see

SIG = {
    "remote_url": re.compile(rb"\b(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}", re.I),
    "script": re.compile(rb"<script\b|\bon[a-z]+\s*=\s*[\"']|javascript:", re.I),
    "secret": re.compile(rb"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*[\"'][^\"'\s]{6,}", re.I),
    "exec_like": re.compile(rb"\b(?:eval|exec|system|popen|subprocess|child_process|Runtime\.getRuntime|shell_exec|passthru|deserializ|unserialize|pickle\.loads|yaml\.load|innerHTML|dangerouslySetInnerHTML)\b"),
    "style_import": re.compile(rb"@(?:import|use|forward)\b|url\s*\(", re.I),
    "code_import": re.compile(rb"^\s*(?:import\s|from\s+\S+\s+import|require\s*\(|#include\s|using\s+[A-Z]|use\s+[\w:\\]+;|package\s+\w)", re.M),
}
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|specs|testdata|fixtures?|e2e|cypress|mocks?)(/|$)|(_test|\.test|\.spec|_spec|Test)\.[a-z]+$", re.I)


class Linguist:
    """Extension/filename -> (language, type), vendored and documentation path rules."""

    def __init__(self, models_dir: str | None):
        self.by_ext, self.by_name, self.vendored, self.docs = {}, {}, None, None
        d = Path(models_dir or "") / "linguist"
        if not (d / "languages.yml").exists():
            return
        import yaml
        langs = yaml.safe_load((d / "languages.yml").read_text())
        for lang, x in langs.items():
            for e in x.get("extensions") or []:
                self.by_ext.setdefault(e.lower(), (lang, x.get("type", "")))
            for f in x.get("filenames") or []:
                self.by_name.setdefault(f, (lang, x.get("type", "")))
        self.vendored = re.compile("|".join(f"(?:{r})" for r in yaml.safe_load((d / "vendor.yml").read_text())))
        self.docs = re.compile("|".join(f"(?:{r})" for r in yaml.safe_load((d / "documentation.yml").read_text())))

    def lang(self, path: str) -> tuple[str, str]:
        name = os.path.basename(path)
        if name in self.by_name:
            return self.by_name[name]
        parts = name.lower().split(".")
        for i in range(1, len(parts)):
            e = "." + ".".join(parts[i:])
            if e in self.by_ext:
                return self.by_ext[e]
        return ("", "")


def list_files(root: Path) -> list[str]:
    """git ls-files when it's a git checkout (respects .gitignore), else a plain walk."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
        files = [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]
        if files:
            return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    files = []
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        files += [os.path.relpath(os.path.join(d, n), root) for n in names]
    return files


def features(path: str, data: bytes, magika, ling: Linguist, size: int | None = None) -> dict:
    head = data[:HEAD_BYTES]
    binary = b"\x00" in head[:8192]
    lang, ltype = ling.lang(path)
    f = {
        "path": path.replace(os.sep, "/"),
        "ext": os.path.splitext(path)[1].lower(),
        "bytes": len(data) if size is None else size,
        "binary": binary,
        "lang": lang,
        "ltype": ltype,
        "vendored": bool(ling.vendored and ling.vendored.search(path)),
        "docs": bool(ling.docs and ling.docs.search(path)),
        "test_path": bool(TEST_PATH.search(path)),
    }
    try:
        r = magika.identify_bytes(data[: 1 << 20]).output
        f["magika"], f["magika_group"], f["magika_text"] = r.label, r.group, r.is_text
    except Exception:
        f["magika"], f["magika_group"], f["magika_text"] = "unknown", "", not binary
    if not binary:
        lines = head.split(b"\n")
        f["avg_line"] = len(head) / max(len(lines), 1)
        for k, rx in SIG.items():
            f[k] = bool(rx.search(head))
        f["text"] = data[:TEXT_BYTES].decode("utf-8", "replace")
    return f


def scan(root: str | Path, models_dir: str | None = None):
    """Yield feature dicts for every file in the checkout."""
    from magika import Magika
    root = Path(root)
    mg, ling = Magika(), Linguist(models_dir)
    for rel in list_files(root):
        p = root / rel
        if not p.is_file() or p.is_symlink():
            continue
        try:
            size = p.stat().st_size
            with open(p, "rb") as fh:
                data = fh.read(1 << 20)   # never more than 1 MB in memory per file
        except OSError:
            continue
        yield features(rel, data, mg, ling, size)
