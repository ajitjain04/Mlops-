import math

import pytest

from adaptivephish.features.url_features import (
    FEATURE_NAMES,
    extract_features,
    extract_features_df,
    feature_schema,
)


def test_schema_order_and_keys():
    f = extract_features("https://example.com/")
    assert tuple(f) == FEATURE_NAMES
    assert len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)
    assert feature_schema()["feature_names"] == list(FEATURE_NAMES)


def test_basic_https_url():
    u = "https://login.secure-pay.example.com:8443/a/b/c?x=1&y=2#frag"
    f = extract_features(u)
    assert f["parse_ok"] == 1
    assert f["is_https"] == 1
    assert f["url_len"] == len(u)
    assert f["host_len"] == len("login.secure-pay.example.com")
    assert f["path_len"] == len("/a/b/c")
    assert f["query_len"] == len("x=1&y=2")
    assert f["fragment_len"] == len("frag")
    assert f["n_params"] == 2
    assert f["path_depth"] == 3
    assert f["n_subdomains"] == 2
    assert f["host_has_port"] == 1
    assert f["host_n_hyphens"] == 1
    assert f["tld_len"] == 3
    assert f["host_longest_label"] == len("secure-pay")
    assert f["host_is_ip"] == 0


def test_http_and_scheme_less():
    assert extract_features("http://example.com")["is_https"] == 0
    f = extract_features("example.com/path")
    assert f["parse_ok"] == 1
    assert f["host_len"] == len("example.com")
    assert f["is_https"] == 0


def test_ipv4_and_ipv6_hosts():
    v4 = extract_features("http://192.168.1.10/login")
    assert v4["host_is_ip"] == 1 and v4["n_subdomains"] == 0 and v4["tld_len"] == 0
    v6 = extract_features("http://[2001:db8::1]:8080/x")
    assert v6["host_is_ip"] == 1 and v6["host_has_port"] == 1 and v6["parse_ok"] == 1


def test_userinfo_and_at_symbol():
    f = extract_features("http://paypal.com@evil.example.net/x")
    assert f["has_userinfo"] == 1 and f["has_at_symbol"] == 1
    assert f["host_len"] == len("evil.example.net")


def test_idn_and_punycode():
    assert extract_features("https://bücher.example/")["host_is_idn"] == 1
    assert extract_features("https://xn--bcher-kva.example/")["host_is_idn"] == 1
    assert extract_features("https://example.com/")["host_is_idn"] == 0


def test_percent_encoding_not_decoded():
    f = extract_features("https://example.com/a%20b%2Fc")
    assert f["n_percent_encoded"] == 2
    assert f["path_len"] == len("/a%20b%2Fc")


@pytest.mark.parametrize(
    "bad", [None, "", "   ", 123, "http://[::1", "http://host:notaport/", "http://[bad]/"]
)
def test_malformed_never_raises(bad):
    f = extract_features(bad)
    assert tuple(f) == FEATURE_NAMES
    assert all(math.isfinite(v) for v in f.values())


def test_invalid_port_marks_parse_failed():
    f = extract_features("http://example.com:99999999/")
    assert f["parse_ok"] == 0 and f["url_len"] > 0


def test_very_long_url_is_ok():
    f = extract_features("https://example.com/" + "a" * 20000)
    assert f["url_len"] == 20020 and f["parse_ok"] == 1


def test_ratios_and_entropy_bounds():
    f = extract_features("https://a1b2c3.example.com/12345")
    assert 0 <= f["digit_ratio"] <= 1 and 0 <= f["letter_ratio"] <= 1
    assert f["digit_ratio"] + f["letter_ratio"] <= 1
    assert extract_features("aaaa")["url_entropy"] == 0
    assert extract_features("abcd")["url_entropy"] == pytest.approx(2.0)


def test_deterministic_and_df_matches_dict():
    urls = ["https://a.com/x?y=1", "http://1.2.3.4/", None, "x"]
    df = extract_features_df(urls)
    assert list(df.columns) == list(FEATURE_NAMES)
    assert df.shape == (4, len(FEATURE_NAMES))
    assert df.iloc[0].to_dict() == extract_features(urls[0])
    assert extract_features_df(urls).equals(df)
