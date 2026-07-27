"""
Tests for src/browsercookies.py.

The COM/DPAPI paths that touch a live browser cannot run in CI, so those are
kept behind seams: the pure logic (spec parsing, profile scoring, Netscape
formatting, and the AES-GCM cookie layout) is exercised directly, and the
Chromium key unwrap is monkeypatched.
"""

import os
import sqlite3
import pytest

import src.browsercookies as bc


# ---------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------

@pytest.mark.parametrize("spec, expected", [
    ("firefox", ("firefox", None, "")),
    ("chrome", ("chrome", None, "")),
    ("firefox:C:/path/to/profile", ("firefox", "C:/path/to/profile", "")),
    ("chrome:Profile 1", ("chrome", "Profile 1", "")),
    ("firefox+gnomekeyring", ("firefox", None, "")),
    ("firefox::container", ("firefox", None, "::container")),
    ("firefox:prof::container", ("firefox", "prof", "::container")),
    ("CHROME", ("chrome", None, "")),
])
def test_parse_spec(spec, expected):
    assert bc._parse_spec(spec) == expected


# ---------------------------------------------------------------
# Netscape cookies.txt formatting
# ---------------------------------------------------------------

def test_netscape_line_subdomain_and_secure():
    line = bc._netscape_line(".youtube.com", "SID", "abc", "/", 0, True)
    fields = line.split("\t")
    assert fields == [".youtube.com", "TRUE", "/", "TRUE", "0", "SID", "abc"]


def test_netscape_line_host_only_and_insecure():
    line = bc._netscape_line("accounts.google.com", "X", "y", "/o", 0, False)
    fields = line.split("\t")
    assert fields[0] == "accounts.google.com"
    assert fields[1] == "FALSE"   # not a leading-dot host
    assert fields[3] == "FALSE"   # not secure


def test_netscape_line_expiry_converts_chrome_epoch():
    # 13343068800000000 us since 1601 -> 2024-01-01 in unix seconds.
    line = bc._netscape_line(".x.com", "n", "v", "/", 13343068800000000, True)
    expires = int(line.split("\t")[4])
    assert expires == 13343068800000000 // 1_000_000 - bc._WINDOWS_TO_UNIX_EPOCH
    assert expires > 0


# ---------------------------------------------------------------
# Cookie value decryption layout (v10 / v20) — round-trip with a known key
# ---------------------------------------------------------------

def _encrypt_chrome_value(prefix, key, value_bytes):
    """Build a Chromium encrypted_value blob exactly as the browser stores it."""
    import os as _os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = _os.urandom(12)
    body = value_bytes
    if prefix == b"v20":
        # v20 plaintext is prefixed with a 32-byte domain-bound header.
        body = b"\x00" * 32 + value_bytes
    ct = AESGCM(key).encrypt(nonce, body, None)
    return prefix + nonce + ct


def test_decrypt_v10_roundtrip():
    key = os.urandom(32)
    blob = _encrypt_chrome_value(b"v10", key, b"cookievalue10")
    out = bc._decrypt_cookie_value(blob, {b"v10": key})
    assert out == "cookievalue10"


def test_decrypt_v20_strips_32_byte_prefix():
    key = os.urandom(32)
    blob = _encrypt_chrome_value(b"v20", key, b"cookievalue20")
    out = bc._decrypt_cookie_value(blob, {b"v20": key})
    assert out == "cookievalue20"


def test_decrypt_missing_key_returns_none():
    key = os.urandom(32)
    blob = _encrypt_chrome_value(b"v20", key, b"x")
    assert bc._decrypt_cookie_value(blob, {b"v10": key}) is None


def test_decrypt_wrong_key_returns_none():
    blob = _encrypt_chrome_value(b"v10", os.urandom(32), b"x")
    assert bc._decrypt_cookie_value(blob, {b"v10": os.urandom(32)}) is None


def test_decrypt_empty_returns_none():
    assert bc._decrypt_cookie_value(b"", {}) is None


# ---------------------------------------------------------------
# Firefox profile selection
# ---------------------------------------------------------------

def _make_firefox_profile(root, name, auth_cookie_names):
    prof = root / name
    prof.mkdir(parents=True)
    con = sqlite3.connect(str(prof / "cookies.sqlite"))
    con.execute("CREATE TABLE moz_cookies (name TEXT, host TEXT)")
    for cookie in auth_cookie_names:
        con.execute("INSERT INTO moz_cookies VALUES (?, ?)",
                    (cookie, ".youtube.com"))
    con.commit()
    con.close()
    return prof


def test_firefox_picks_logged_in_profile(tmp_path, monkeypatch):
    root = tmp_path / "Profiles"
    _make_firefox_profile(root, "logged_out.default-release", ["PREF", "VISITOR"])
    signed_in = _make_firefox_profile(
        root, "signed_in.dev-edition", ["SID", "HSID", "SSID", "LOGIN_INFO"])

    monkeypatch.setattr(bc, "_firefox_profiles_dir", lambda: str(tmp_path))
    res = bc._resolve_firefox(None, "")
    assert res.cookies_from_browser == f"firefox:{signed_in}"
    assert res.cookies_file is None


def test_firefox_explicit_profile_is_respected(tmp_path, monkeypatch):
    # Even if a "better" profile exists, an explicit path must be untouched.
    root = tmp_path / "Profiles"
    _make_firefox_profile(root, "signed_in", ["SID", "HSID", "SSID"])
    monkeypatch.setattr(bc, "_firefox_profiles_dir", lambda: str(tmp_path))
    res = bc._resolve_firefox("D:/custom/profile", "")
    assert res.cookies_from_browser == "firefox:D:/custom/profile"


def test_firefox_no_login_warns_and_falls_back(tmp_path, monkeypatch):
    root = tmp_path / "Profiles"
    _make_firefox_profile(root, "logged_out", ["PREF"])
    monkeypatch.setattr(bc, "_firefox_profiles_dir", lambda: str(tmp_path))
    res = bc._resolve_firefox(None, "")
    assert res.cookies_from_browser == "firefox"
    assert any("No signed-in Firefox profile" in m for m in res.messages)


# ---------------------------------------------------------------
# resolve(): unknown browsers pass through, failures never raise
# ---------------------------------------------------------------

def test_resolve_unknown_browser_passthrough():
    res = bc.resolve("safari")
    assert res.cookies_from_browser == "safari"
    assert res.cookies_file is None


def test_resolve_firefox_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(bc, "_resolve_firefox", boom)
    res = bc.resolve("firefox")
    assert res.cookies_from_browser == "firefox"
    assert any("failed" in m for m in res.messages)


def test_resolve_chromium_failure_falls_back(monkeypatch):
    def boom(*a, **k):
        raise bc.BrowserCookieError("browser is open")
    monkeypatch.setattr(bc, "_resolve_chromium", boom)
    res = bc.resolve("chrome")
    assert res.cookies_from_browser == "chrome"
    assert any("Could not read chrome cookies" in m for m in res.messages)


# ---------------------------------------------------------------
# Chromium extraction end-to-end, with the key unwrap stubbed out
# ---------------------------------------------------------------

# ---------------------------------------------------------------
# Firefox expiry normalization + export
# ---------------------------------------------------------------

@pytest.mark.parametrize("stored, expected", [
    (0, 0),                       # session cookie
    (2_000_000_000, 2_000_000_000),   # already seconds (year 2033)
    (1_813_904_683_609, 1_813_904_683),   # milliseconds -> seconds
    (1_780_666_375_328_000, 1_780_666_375),  # microseconds -> seconds
])
def test_firefox_expiry_seconds(stored, expected):
    assert bc._firefox_expiry_seconds(stored) == expected


def _make_firefox_cookie_db(path, cookies):
    """cookies: list of (host, name, value, path, expiry, isSecure)."""
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT, "
                "path TEXT, expiry INTEGER, isSecure INTEGER)")
    con.executemany("INSERT INTO moz_cookies (host,name,value,path,expiry,isSecure) "
                    "VALUES (?,?,?,?,?,?)", cookies)
    con.commit()
    con.close()


def test_export_firefox_writes_netscape(tmp_path):
    prof = tmp_path / "prof"
    prof.mkdir()
    _make_firefox_cookie_db(prof / "cookies.sqlite", [
        (".youtube.com", "SID", "abc", "/", 1_813_904_683_609, 1),
        ("accounts.google.com", "X", "y", "/o", 0, 0),
    ])
    out = tmp_path / "cookies.txt"
    n = bc._export_firefox(str(prof), str(out))
    assert n == 2
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Netscape HTTP Cookie File"
    sid = [l for l in lines if "\tSID\t" in l][0].split("\t")
    assert sid == [".youtube.com", "TRUE", "/", "TRUE", "1813904683", "SID", "abc"]
    other = [l for l in lines if "\tX\t" in l][0].split("\t")
    assert other[1] == "FALSE" and other[3] == "FALSE" and other[4] == "0"


def test_export_to_file_explicit_firefox_profile(tmp_path):
    prof = tmp_path / "prof"
    prof.mkdir()
    _make_firefox_cookie_db(prof / "cookies.sqlite",
                            [(".youtube.com", "SID", "v", "/", 0, 1)])
    out = tmp_path / "out.txt"
    assert bc.export_to_file(f"firefox:{prof}", str(out)) == 1
    assert "SID" in out.read_text(encoding="utf-8")


def test_export_to_file_unsupported_browser_raises(tmp_path):
    with pytest.raises(bc.BrowserCookieError):
        bc.export_to_file("safari", str(tmp_path / "x.txt"))


@pytest.mark.skipif(os.name != "nt", reason="Chromium extraction is Windows-only")
def test_chromium_extracts_and_writes_cookies_txt(tmp_path, monkeypatch):
    key = os.urandom(32)
    user_data = tmp_path / "User Data"
    prof_net = user_data / "Default" / "Network"
    prof_net.mkdir(parents=True)

    # A cookie store with one v20-encrypted YouTube cookie.
    db = prof_net / "Cookies"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, "
                "encrypted_value BLOB, path TEXT, expires_utc INTEGER, is_secure INTEGER)")
    con.execute("INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?)",
                (".youtube.com", "SID",
                 _encrypt_chrome_value(b"v20", key, b"secretsid"),
                 "/", 0, 1))
    con.commit()
    con.close()

    monkeypatch.setattr(bc, "_chromium_user_data_dir", lambda b: str(user_data))
    monkeypatch.setattr(bc, "_load_master_keys", lambda udd, b: {b"v20": key})

    res = bc._resolve_chromium("chrome", "Default", "")
    try:
        assert res.cookies_file and os.path.exists(res.cookies_file)
        content = open(res.cookies_file, encoding="utf-8").read()
        assert "# Netscape HTTP Cookie File" in content
        assert "\tSID\tsecretsid" in content
        assert ".youtube.com" in content
    finally:
        res.cleanup()
    assert not os.path.exists(res.cookies_file)  # cleanup removed the temp dir
