"""Expected LLM cost of scanning one file on a given route."""
from __future__ import annotations


def tokens(f: dict, c: dict) -> float:
    return min(f["bytes"] / c["bytes_per_token"], c["max_file_tokens"])


def file_cost(f: dict, route: str, c: dict) -> float:
    if route not in ("full", "cheap"):
        return 0.0
    p = c[route]
    return ((c["overhead_tokens"] + tokens(f, c)) * p["input_per_mtok"] + c["output_tokens"] * p["output_per_mtok"]) / 1e6
