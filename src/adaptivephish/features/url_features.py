"""Shared URL-only feature extraction.

One implementation used by training, evaluation, drift analysis, retraining and the API.
Only the URL string is inspected; nothing is fetched and no HTML is used.

Parsing policy (documented because it affects every feature):
- The raw string is stripped of surrounding whitespace but otherwise preserved: no
  percent-decoding, no case folding of path/query, no punycode conversion. Length and
  character-count features therefore see the URL exactly as given.
- The host is taken from urllib's parser, which lowercases it and strips brackets from
  IPv6 literals and any userinfo/port. A scheme-less input ("example.com/a") is parsed as if
  it started with "//".
- Internationalized hosts are kept as given; `host_is_idn` flags non-ASCII or "xn--" labels.
- IPv4/IPv6 literals are detected with `ipaddress`. Decimal/hex/octal-encoded IPv4 hosts
  are NOT detected.
- Subdomain count is a heuristic (labels minus two, floor 0) without a public-suffix list,
  so "a.b.example.co.uk" counts 3 although only 2 are real subdomains.
- Anything that cannot be parsed yields `parse_ok = 0` and zeros for host/path/query
  features; the function never raises on str/None input.
"""

from __future__ import annotations

import ipaddress
import math
import re
from collections import Counter
from collections.abc import Iterable
from urllib.parse import urlsplit

import pandas as pd

FEATURE_VERSION = "1.0.0"

FEATURE_NAMES: tuple[str, ...] = (
    "url_len",
    "host_len",
    "path_len",
    "query_len",
    "fragment_len",
    "n_dots",
    "n_hyphens",
    "n_digits",
    "n_special_chars",
    "n_params",
    "n_subdomains",
    "path_depth",
    "n_percent_encoded",
    "is_https",
    "host_is_ip",
    "host_has_port",
    "has_userinfo",
    "has_at_symbol",
    "host_is_idn",
    "host_n_hyphens",
    "host_n_digits",
    "host_longest_label",
    "tld_len",
    "digit_ratio",
    "letter_ratio",
    "host_digit_ratio",
    "url_entropy",
    "host_entropy",
    "parse_ok",
)

# PhreshPhish benign URLs contain no query string or fragment at all (0 of ~47k in the
# subset) while ~17% of phishing URLs do, so these features separate the classes through
# a dataset collection artifact rather than phishing behaviour. They are still computed
# (the API must accept any URL) but models should be evaluated with and without them.
DATASET_ARTIFACT_FEATURES: tuple[str, ...] = ("query_len", "fragment_len", "n_params")

# Characters counted by n_special_chars: anything not alphanumeric and not one of the
# structural characters already counted separately (. - / : ?).
_STRUCTURAL = set(".-/:?")
_PCT = re.compile(r"%[0-9A-Fa-f]{2}")


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _empty() -> dict[str, float]:
    return dict.fromkeys(FEATURE_NAMES, 0.0)


def extract_features(url: str | None) -> dict[str, float]:
    """Return the feature dict for one URL, keys in FEATURE_NAMES order."""
    feats = _empty()
    if url is None or not isinstance(url, str):
        return feats
    raw = url.strip()
    feats["url_len"] = float(len(raw))
    if not raw:
        return feats

    n = len(raw)
    digits = sum(ch.isdigit() for ch in raw)
    letters = sum(ch.isalpha() for ch in raw)
    feats["n_dots"] = float(raw.count("."))
    feats["n_hyphens"] = float(raw.count("-"))
    feats["n_digits"] = float(digits)
    feats["n_special_chars"] = float(
        sum(not ch.isalnum() and ch not in _STRUCTURAL for ch in raw)
    )
    feats["n_percent_encoded"] = float(len(_PCT.findall(raw)))
    feats["has_at_symbol"] = float("@" in raw)
    feats["digit_ratio"] = digits / n
    feats["letter_ratio"] = letters / n
    feats["url_entropy"] = _entropy(raw)

    try:
        parts = urlsplit(raw if "://" in raw else "//" + raw)
        host = parts.hostname or ""
        port = parts.port  # may raise ValueError for an invalid port
    except ValueError:
        return feats

    feats["parse_ok"] = 1.0
    feats["is_https"] = float(parts.scheme.lower() == "https")
    feats["host_len"] = float(len(host))
    feats["path_len"] = float(len(parts.path))
    feats["query_len"] = float(len(parts.query))
    feats["fragment_len"] = float(len(parts.fragment))
    feats["n_params"] = float(len([p for p in parts.query.split("&") if p]))
    feats["path_depth"] = float(len([p for p in parts.path.split("/") if p]))
    feats["host_has_port"] = float(port is not None)
    feats["has_userinfo"] = float("@" in parts.netloc)

    is_ip = _is_ip(host)
    feats["host_is_ip"] = float(is_ip)
    labels = [lb for lb in host.split(".") if lb] if host and not is_ip else []
    feats["n_subdomains"] = float(max(len(labels) - 2, 0))
    feats["host_longest_label"] = float(max((len(lb) for lb in labels), default=0))
    feats["tld_len"] = float(len(labels[-1])) if len(labels) > 1 else 0.0
    feats["host_is_idn"] = float(
        any(ord(ch) > 127 for ch in host) or any(lb.startswith("xn--") for lb in labels)
    )
    feats["host_n_hyphens"] = float(host.count("-"))
    host_digits = sum(ch.isdigit() for ch in host)
    feats["host_n_digits"] = float(host_digits)
    feats["host_digit_ratio"] = host_digits / len(host) if host else 0.0
    feats["host_entropy"] = _entropy(host)
    return feats


def extract_features_df(urls: Iterable[str | None]) -> pd.DataFrame:
    """Feature matrix with columns exactly FEATURE_NAMES (float64), one row per URL."""
    rows = [extract_features(u) for u in urls]
    return pd.DataFrame(rows, columns=list(FEATURE_NAMES), dtype="float64")


def feature_schema() -> dict[str, object]:
    """Schema recorded with trained models and checked at serving time."""
    return {"feature_version": FEATURE_VERSION, "feature_names": list(FEATURE_NAMES)}
