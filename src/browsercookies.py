"""
Make ``--cookies-from-browser`` actually authenticate on Windows.

yt-dlp's own browser-cookie support has three gaps that make it silently fail to
log in on a normal Windows setup:

1. **Firefox picks the wrong profile.** yt-dlp selects the profile marked default
   in ``profiles.ini``. That is often *not* the profile you are signed into
   YouTube on, so extraction "succeeds" but authenticates nobody. We instead pick
   the profile that actually holds Google/YouTube login cookies.

2. **Chrome/Edge cookies are App-Bound Encrypted (v20).** Since Chrome 127 the
   cookie key is wrapped by the browser's elevation service and can only be
   unwrapped by asking that service (the ``IElevator`` COM interface). yt-dlp on
   Windows only understands the older v10/DPAPI scheme, so on a current Chrome it
   decrypts nothing. We call the elevator ourselves.

3. **The cookie DB is locked while the browser runs.** We copy it out of the way
   first, and if the browser holds it exclusively we say so plainly instead of
   emitting an opaque error.

The public entry point is :func:`resolve`. Given a browser spec such as
``"chrome"`` or ``"firefox:C:\\path\\to\\profile"`` it returns a
:class:`Resolution` telling the caller either a refined ``--cookies-from-browser``
spec (Firefox, best profile) or a freshly written Netscape ``cookies.txt``
(Chromium, decrypted here) to hand to yt-dlp via ``--cookies``.

Everything Windows/Chromium-specific degrades gracefully: on any other platform,
or if decryption is not possible (browser open, no elevation service), we fall
back to yt-dlp's native handling and explain why.
"""

import os
import sys
import glob
import json
import base64
import shutil
import sqlite3
import tempfile
import configparser

# Cookie names that only exist once you are signed in to a Google/YouTube
# account. Their mere presence (the name column is never encrypted) is enough to
# tell a logged-in profile from a logged-out one, without decrypting anything.
_AUTH_COOKIE_NAMES = frozenset({
    "SID", "HSID", "SSID", "APISID", "SAPISID", "LOGIN_INFO",
    "__Secure-1PSID", "__Secure-3PSID", "__Secure-1PAPISID", "__Secure-3PAPISID",
})

# Netscape cookies.txt epoch conversion: Chrome stores expiry as microseconds
# since 1601-01-01, cookies.txt wants seconds since the Unix epoch.
_WINDOWS_TO_UNIX_EPOCH = 11644473600


class BrowserCookieError(Exception):
    """Raised when cookies cannot be extracted (locked DB, no elevator, ...)."""


class Resolution:
    """
    The outcome of :func:`resolve`.

    Exactly one of ``cookies_from_browser`` / ``cookies_file`` is meaningful; the
    caller passes whichever is set through to yt-dlp. ``messages`` are lines worth
    showing the user. ``cleanup`` removes any temp files that were written.
    """

    def __init__(self, cookies_from_browser=None, cookies_file=None,
                 messages=None, cleanup=None):
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file
        self.messages = messages or []
        self._cleanup = cleanup

    def cleanup(self):
        if self._cleanup:
            self._cleanup()


# Browsers whose cookie store uses the Chromium format (SQLite + os_crypt).
# Each entry: (user-data dir relative to a base env var, base env var).
_CHROMIUM_BROWSERS = {
    "chrome":   (("Google", "Chrome", "User Data"), "LOCALAPPDATA"),
    "chromium": (("Chromium", "User Data"), "LOCALAPPDATA"),
    "edge":     (("Microsoft", "Edge", "User Data"), "LOCALAPPDATA"),
    "brave":    (("BraveSoftware", "Brave-Browser", "User Data"), "LOCALAPPDATA"),
    "vivaldi":  (("Vivaldi", "User Data"), "LOCALAPPDATA"),
}

# Per-brand elevation-service COM identity used to unwrap the App-Bound key.
# CLSID is the coclass; the IIDs are tried in order — Chromium ships a base
# IElevator plus brand-specific subclasses, and different builds expose
# different ones. These are the long-stable published values.
_ELEVATOR_COM = {
    "chrome": {
        "clsid": "{708860E0-F641-4611-8895-7D867DD3675B}",
        "iids": ["{463ABECF-410D-407F-8AF5-0DF35A005CC8}",   # IElevatorChrome
                 "{A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C}"],  # IElevator (base)
    },
    "edge": {
        "clsid": "{1FCBE96C-1697-43AF-9140-2897C7C69767}",
        "iids": ["{C9C2B807-7731-4F34-81B7-44FF7779522B}",   # IElevatorEdge
                 "{A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C}"],
    },
    "brave": {
        "clsid": "{576B31AF-6369-4B6B-8560-E4B203A97A8B}",
        "iids": ["{F396861E-0C8E-4C71-8256-2FAE6D759CE9}",   # IElevatorBrave
                 "{A949CB4E-C4F9-44C4-B213-6BF8AA9AC69C}"],
    },
}

# When the App-Bound key carries protection level >= PATH_VALIDATION, the
# elevation service verifies the *caller* is the browser and reports its own
# failure in the interface facility (0x8004Axxx). No ordinary user-space tool
# can satisfy that check — that is exactly what App-Bound Encryption is for — so
# it is surfaced as a distinct, non-misleading error rather than "key failed".
def _is_elevator_refusal(hr: int) -> bool:
    return (hr & 0xFFFF0000) == 0x80040000 and 0xA000 <= (hr & 0xFFFF) <= 0xAFFF


# --------------------------------------------------------------------------
# Spec parsing
# --------------------------------------------------------------------------

def _parse_spec(spec: str):
    """
    Split a yt-dlp browser spec into (browser, profile, remainder).

    Format is ``BROWSER[+KEYRING][:PROFILE][::CONTAINER]``. We only care about
    the browser name and an explicit profile; anything after ``::`` is preserved
    verbatim so a refined Firefox spec keeps container selectors intact.
    """
    remainder = ""
    if "::" in spec:
        spec, remainder = spec.split("::", 1)
        remainder = "::" + remainder
    profile = None
    if ":" in spec:
        spec, profile = spec.split(":", 1)
    browser = spec.split("+", 1)[0].strip().lower()
    return browser, (profile or None), remainder


# --------------------------------------------------------------------------
# Firefox: choose the profile that is actually logged in
# --------------------------------------------------------------------------

def _firefox_profiles_dir():
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Firefox")
    return os.path.expanduser("~/.mozilla/firefox")


def _count_firefox_auth_cookies(cookies_sqlite: str) -> int:
    """Number of Google/YouTube auth cookies in a Firefox cookies.sqlite."""
    tmp_dir = tempfile.mkdtemp(prefix="ytdl-ffck-")
    tmp = os.path.join(tmp_dir, "cookies.sqlite")
    try:
        shutil.copy(cookies_sqlite, tmp)
        con = sqlite3.connect(tmp)
        try:
            rows = con.execute(
                "SELECT name FROM moz_cookies "
                "WHERE host LIKE '%youtube.com' OR host LIKE '%google.com'"
            ).fetchall()
        finally:
            con.close()
    except (OSError, sqlite3.Error):
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return len({name for (name,) in rows} & _AUTH_COOKIE_NAMES)


def _best_firefox_profile_dir():
    """
    Directory of the Firefox profile holding the most Google/YouTube auth
    cookies, with its score. ``(None, 0)`` if nothing looks logged in.
    """
    profiles_root = os.path.join(_firefox_profiles_dir(), "Profiles")
    best_path, best_score = None, 0
    for cookies_sqlite in glob.glob(os.path.join(profiles_root, "*", "cookies.sqlite")):
        score = _count_firefox_auth_cookies(cookies_sqlite)
        if score > best_score:
            best_path, best_score = os.path.dirname(cookies_sqlite), score
    return best_path, best_score


def _resolve_firefox(profile, remainder):
    """
    Return a Resolution pointing yt-dlp at the signed-in Firefox profile.

    If the user pinned a profile explicitly we respect it untouched. Otherwise we
    scan every profile and pick the one holding the most auth cookies, so the
    extracted cookies actually belong to a logged-in session.
    """
    if profile:
        # Explicit profile: trust the user, change nothing.
        return Resolution(cookies_from_browser=f"firefox:{profile}{remainder}")

    best_path, best_score = _best_firefox_profile_dir()

    if best_path is None or best_score == 0:
        # Nothing looks logged in — let yt-dlp use its own default and warn.
        return Resolution(
            cookies_from_browser=f"firefox{remainder}",
            messages=["[WARNING] No signed-in Firefox profile found; using yt-dlp's "
                      "default profile. Sign in to YouTube in Firefox, or pass "
                      "--cookies-from-browser firefox:PROFILE_PATH."],
        )

    return Resolution(
        cookies_from_browser=f"firefox:{best_path}{remainder}",
        messages=[f"[INFO] Using signed-in Firefox profile: "
                  f"{os.path.basename(best_path)}"],
    )


# --------------------------------------------------------------------------
# Chromium: decrypt cookies ourselves and write a cookies.txt
# --------------------------------------------------------------------------

def _chromium_user_data_dir(browser):
    rel, env = _CHROMIUM_BROWSERS[browser]
    base = os.environ.get(env, "")
    return os.path.join(base, *rel) if base else ""


def _copy_locked(src, dst):
    """
    Copy a file even if the owning process keeps it open (WAL DBs).

    Falls back to a Windows shared-mode read for files that deny an ordinary
    open. Raises BrowserCookieError if the browser holds the file exclusively —
    the actionable fix for which is to close the browser.
    """
    try:
        shutil.copy(src, dst)
        return
    except PermissionError:
        pass

    if sys.platform != "win32":
        raise BrowserCookieError(f"could not read {src} (in use)")

    import ctypes
    from ctypes import wintypes

    GENERIC_READ = 0x80000000
    FILE_SHARE_ALL = 0x1 | 0x2 | 0x4
    OPEN_EXISTING = 3
    INVALID_HANDLE = ctypes.c_void_p(-1).value

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE]
    handle = k32.CreateFileW(src, GENERIC_READ, FILE_SHARE_ALL, None,
                             OPEN_EXISTING, 0x80, None)
    if handle == INVALID_HANDLE:
        raise BrowserCookieError(
            "the browser is holding its cookie database open. Close it fully "
            "(check the tray) and try again, or use Firefox / --cookies-file.")
    try:
        chunk = ctypes.create_string_buffer(1 << 20)
        read = wintypes.DWORD()
        with open(dst, "wb") as out:
            while True:
                if not k32.ReadFile(wintypes.HANDLE(handle), chunk, 1 << 20,
                                    ctypes.byref(read), None):
                    raise BrowserCookieError(f"read failed on {src}")
                if read.value == 0:
                    break
                out.write(chunk.raw[:read.value])
    finally:
        k32.CloseHandle(wintypes.HANDLE(handle))


def _dpapi_unprotect(data: bytes) -> bytes:
    """CryptUnprotectData — undo Windows DPAPI wrapping (v10 key, legacy values)."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    blob_in = DATA_BLOB(len(data), ctypes.cast(
        ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None,
                                      None, 0, ctypes.byref(blob_out)):
        raise BrowserCookieError("DPAPI decryption failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.WinDLL("kernel32").LocalFree(blob_out.pbData)


def _decrypt_app_bound_key(browser: str, blob: bytes) -> bytes:
    """
    Unwrap the App-Bound (v20) master key via the browser's IElevator service.

    ``blob`` is the ``app_bound_encrypted_key`` with its 4-byte "APPB" tag already
    stripped. The elevation service returns the raw key material; recent builds
    prepend a flag byte, so we take the trailing 32 bytes as the AES-256 key.
    """
    if sys.platform != "win32":
        raise BrowserCookieError("App-Bound Encryption is Windows-only")

    import ctypes
    from ctypes import wintypes, POINTER, byref, c_void_p

    com = _ELEVATOR_COM.get(browser)
    if not com:
        raise BrowserCookieError(f"no elevation service known for {browser}")

    ole32 = ctypes.WinDLL("ole32")
    oleaut32 = ctypes.WinDLL("oleaut32")

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    def guid(s):
        g = GUID()
        if ole32.CLSIDFromString(ctypes.c_wchar_p(s), byref(g)) != 0:
            raise BrowserCookieError(f"bad GUID {s}")
        return g

    oleaut32.SysAllocStringByteLen.restype = c_void_p
    oleaut32.SysAllocStringByteLen.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    oleaut32.SysStringByteLen.restype = ctypes.c_uint
    oleaut32.SysStringByteLen.argtypes = [c_void_p]
    oleaut32.SysFreeString.argtypes = [c_void_p]

    COINIT_APARTMENTTHREADED = 0x2
    RPC_C_AUTHN_LEVEL_PKT_PRIVACY = 6
    RPC_C_IMP_LEVEL_IMPERSONATE = 3
    EOAC_DYNAMIC_CLOAKING = 0x40
    CLSCTX_LOCAL_SERVER = 0x4
    RPC_C_AUTHN_DEFAULT = 0xFFFFFFFF
    RPC_C_AUTHZ_DEFAULT = 0xFFFFFFFF

    ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    # Best-effort; a second call in the same apartment returns RPC_E_TOO_LATE.
    ole32.CoInitializeSecurity(None, -1, None, None,
                               RPC_C_AUTHN_LEVEL_PKT_PRIVACY,
                               RPC_C_IMP_LEVEL_IMPERSONATE, None,
                               EOAC_DYNAMIC_CLOAKING, None)

    elevator = c_void_p()
    last_hr = None
    for iid in com["iids"]:
        hr = ole32.CoCreateInstance(byref(guid(com["clsid"])), None,
                                    CLSCTX_LOCAL_SERVER, byref(guid(iid)),
                                    byref(elevator))
        last_hr = hr
        if hr == 0 and elevator.value:
            break
        elevator = c_void_p()
    if not elevator.value:
        raise BrowserCookieError(
            f"this {browser} build uses an App-Bound cookie key this tool cannot "
            f"unwrap (elevation service returned 0x{(last_hr or 0) & 0xffffffff:08X}). "
            f"Use Firefox, or export a cookies.txt and pass --cookies-file.")

    ole32.CoSetProxyBlanket(elevator, RPC_C_AUTHN_DEFAULT, RPC_C_AUTHZ_DEFAULT,
                            None, RPC_C_AUTHN_LEVEL_PKT_PRIVACY,
                            RPC_C_IMP_LEVEL_IMPERSONATE, None,
                            EOAC_DYNAMIC_CLOAKING)

    # vtable: 0 QI, 1 AddRef, 2 Release, 3 RunRecoveryCRXElevated,
    #         4 EncryptData, 5 DecryptData(BSTR in, BSTR* out, DWORD* err)
    vtbl = ctypes.cast(elevator, POINTER(POINTER(c_void_p))).contents
    DecryptProto = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_void_p,
                                      POINTER(c_void_p), POINTER(wintypes.DWORD))
    decrypt = DecryptProto(vtbl[5])

    in_bstr = oleaut32.SysAllocStringByteLen(blob, len(blob))
    out_bstr = c_void_p()
    last_err = wintypes.DWORD(0)
    try:
        hr = decrypt(elevator, in_bstr, byref(out_bstr), byref(last_err))
        if hr != 0 or not out_bstr.value:
            if _is_elevator_refusal(hr):
                raise BrowserCookieError(
                    f"{browser}'s cookies use App-Bound Encryption with caller "
                    f"validation — the browser only lets itself decrypt them "
                    f"(0x{hr & 0xffffffff:08X}). This cannot be bypassed from a "
                    f"normal program. Use Firefox, or export a cookies.txt and "
                    f"pass --cookies-file.")
            raise BrowserCookieError(
                f"the elevation service refused to decrypt the key "
                f"(0x{hr & 0xffffffff:08X}, err {last_err.value})")
        n = oleaut32.SysStringByteLen(out_bstr)
        key = ctypes.string_at(out_bstr, n)
    finally:
        oleaut32.SysFreeString(in_bstr)
        if out_bstr.value:
            oleaut32.SysFreeString(out_bstr)

    if len(key) < 32:
        raise BrowserCookieError("elevation service returned a short key")
    return key[-32:]


def _load_master_keys(user_data_dir, browser):
    """
    Return the list of candidate AES keys for a Chromium profile.

    Modern stores are App-Bound (v20); older ones are DPAPI-wrapped (v10). We
    return whichever keys we can obtain so cookies of either vintage decrypt.
    """
    local_state = os.path.join(user_data_dir, "Local State")
    with open(local_state, "r", encoding="utf-8") as f:
        os_crypt = json.load(f).get("os_crypt", {})

    keys = {}  # version-prefix -> key bytes
    v10 = os_crypt.get("encrypted_key")
    if v10:
        raw = base64.b64decode(v10)
        if raw[:5] == b"DPAPI":
            keys[b"v10"] = _dpapi_unprotect(raw[5:])

    v20 = os_crypt.get("app_bound_encrypted_key")
    if v20:
        raw = base64.b64decode(v20)
        if raw[:4] == b"APPB":
            keys[b"v20"] = _decrypt_app_bound_key(browser, raw[4:])

    if not keys:
        raise BrowserCookieError("no usable cookie key found in Local State")
    return keys


def _decrypt_cookie_value(encrypted, keys):
    """Decrypt one Chromium ``encrypted_value`` blob to a string, or None."""
    if not encrypted:
        return None
    prefix = encrypted[:3]
    if prefix in (b"v10", b"v20"):
        key = keys.get(prefix)
        if key is None:
            return None
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = encrypted[3:15]
        ciphertext = encrypted[15:]
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
        except Exception:
            return None
        # v20 values carry a 32-byte header (domain hash + flags) before the
        # actual value; v10 values do not.
        if prefix == b"v20":
            plaintext = plaintext[32:]
        return plaintext.decode("utf-8", "replace")

    # Pre-v10: the value column is DPAPI-wrapped directly.
    try:
        return _dpapi_unprotect(encrypted).decode("utf-8", "replace")
    except BrowserCookieError:
        return None


def _netscape_line(host, name, value, path, expires_utc, is_secure):
    include_sub = "TRUE" if host.startswith(".") else "FALSE"
    secure = "TRUE" if is_secure else "FALSE"
    if expires_utc:
        expires = int(expires_utc // 1_000_000 - _WINDOWS_TO_UNIX_EPOCH)
        expires = max(expires, 0)
    else:
        expires = 0  # session cookie
    return "\t".join([host, include_sub, path or "/", secure,
                      str(expires), name, value])


def _profile_cookie_db(user_data_dir, profile):
    """Path to a profile's cookie DB, trying the modern and legacy locations."""
    for rel in ((profile, "Network", "Cookies"), (profile, "Cookies")):
        candidate = os.path.join(user_data_dir, *rel)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(user_data_dir, profile, "Network", "Cookies")


def _pick_chromium_profile(user_data_dir, work_dir):
    """
    Choose the signed-in Chromium profile.

    Reads each profile's cookie DB (only the unencrypted ``name`` column) and
    picks the one with the most Google/YouTube auth cookies, mirroring the
    Firefox logic. Falls back to "Default" if nothing can be read.
    """
    profiles = ["Default"] + sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(user_data_dir, "Profile *"))
    )
    best, best_score = "Default", -1
    for profile in profiles:
        db = _profile_cookie_db(user_data_dir, profile)
        if not os.path.exists(db):
            continue
        tmp = os.path.join(work_dir, f"probe-{profile}.db")
        try:
            _copy_locked(db, tmp)
            con = sqlite3.connect(tmp)
            try:
                rows = con.execute(
                    "SELECT name FROM cookies "
                    "WHERE host_key LIKE '%youtube.com' OR host_key LIKE '%google.com'"
                ).fetchall()
            finally:
                con.close()
        except (BrowserCookieError, sqlite3.Error, OSError):
            continue
        score = len({name for (name,) in rows} & _AUTH_COOKIE_NAMES)
        if score > best_score:
            best, best_score = profile, score
    return best


def _resolve_chromium(browser, profile, remainder):
    """Extract, decrypt, and write a cookies.txt for a Chromium browser."""
    if sys.platform != "win32":
        # Elsewhere yt-dlp's own keyring handling is fine; don't get in the way.
        return Resolution(cookies_from_browser=f"{browser}:{profile}{remainder}"
                          if profile else f"{browser}{remainder}")

    user_data_dir = _chromium_user_data_dir(browser)
    if not user_data_dir or not os.path.isdir(user_data_dir):
        raise BrowserCookieError(f"{browser} profile directory not found")

    work_dir = tempfile.mkdtemp(prefix="ytdl-ck-")

    def cleanup():
        shutil.rmtree(work_dir, ignore_errors=True)

    try:
        chosen = profile or _pick_chromium_profile(user_data_dir, work_dir)
        keys = _load_master_keys(user_data_dir, browser)

        db_src = _profile_cookie_db(user_data_dir, chosen)
        if not os.path.exists(db_src):
            raise BrowserCookieError(f"no cookie database for profile {chosen!r}")
        db_copy = os.path.join(work_dir, "Cookies.db")
        _copy_locked(db_src, db_copy)

        con = sqlite3.connect(db_copy)
        con.text_factory = bytes
        try:
            cols = [d[1] for d in con.execute("PRAGMA table_info(cookies)")]
            secure_col = b"is_secure" if b"is_secure" in cols else b"secure"
            secure_col = secure_col.decode()
            rows = con.execute(
                f"SELECT host_key, name, encrypted_value, path, expires_utc, "
                f"{secure_col} FROM cookies").fetchall()
        finally:
            con.close()

        cookies_txt = os.path.join(work_dir, "cookies.txt")
        written = 0
        with open(cookies_txt, "w", encoding="utf-8", newline="\n") as out:
            out.write("# Netscape HTTP Cookie File\n")
            out.write("# Generated by YTDownload for --cookies-from-browser\n")
            for host, name, enc, path, expires, secure in rows:
                value = _decrypt_cookie_value(enc, keys)
                if value is None:
                    continue
                out.write(_netscape_line(
                    host.decode(errors="replace"), name.decode(errors="replace"),
                    value, path.decode(errors="replace"), expires, bool(secure)) + "\n")
                written += 1

        if written == 0:
            raise BrowserCookieError(
                "extracted 0 cookies — the master key could not decrypt this "
                "store (App-Bound Encryption may be unsupported on this build).")

        return Resolution(
            cookies_file=cookies_txt,
            messages=[f"[INFO] Extracted {written} cookies from {browser} "
                      f"profile {chosen!r}."],
            cleanup=cleanup,
        )
    except BrowserCookieError:
        cleanup()
        raise
    except Exception as exc:
        cleanup()
        raise BrowserCookieError(str(exc))


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def resolve(browser_spec: str) -> Resolution:
    """
    Turn a ``--cookies-from-browser`` spec into something that authenticates.

    Firefox specs come back refined to the signed-in profile; Chromium specs come
    back as a decrypted ``cookies.txt`` path. On any failure or unsupported
    combination the original spec is returned unchanged with an explanatory
    message, so behaviour never regresses below yt-dlp's own handling.
    """
    browser, profile, remainder = _parse_spec(browser_spec)

    if browser == "firefox":
        try:
            return _resolve_firefox(profile, remainder)
        except Exception as exc:  # never let cookie tuning break a download
            return Resolution(cookies_from_browser=browser_spec,
                              messages=[f"[WARNING] Firefox profile detection "
                                        f"failed ({exc}); using yt-dlp default."])

    if browser in _CHROMIUM_BROWSERS:
        try:
            return _resolve_chromium(browser, profile, remainder)
        except BrowserCookieError as exc:
            return Resolution(
                cookies_from_browser=browser_spec,
                messages=[f"[WARNING] Could not read {browser} cookies: {exc}",
                          "          Letting yt-dlp try its own extraction as a "
                          "last resort."])

    # Unknown browser: leave it to yt-dlp.
    return Resolution(cookies_from_browser=browser_spec)


# --------------------------------------------------------------------------
# Standalone export: write a reusable Netscape cookies.txt
# --------------------------------------------------------------------------

def _export_firefox(profile_dir: str, out_path: str) -> int:
    """Write every cookie in a Firefox profile to out_path in Netscape format."""
    src = os.path.join(profile_dir, "cookies.sqlite")
    if not os.path.exists(src):
        raise BrowserCookieError(f"no cookies.sqlite in {profile_dir}")
    tmp_dir = tempfile.mkdtemp(prefix="ytdl-ffexp-")
    tmp = os.path.join(tmp_dir, "cookies.sqlite")
    try:
        shutil.copy(src, tmp)
        con = sqlite3.connect(tmp)
        try:
            rows = con.execute(
                "SELECT host, name, value, path, expiry, isSecure FROM moz_cookies"
            ).fetchall()
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        out.write("# Netscape HTTP Cookie File\n")
        out.write("# Generated by YTDownload — use with --cookies-file\n")
        for host, name, value, path, expiry, secure in rows:
            include_sub = "TRUE" if str(host).startswith(".") else "FALSE"
            sec = "TRUE" if secure else "FALSE"
            out.write("\t".join([str(host), include_sub, path or "/", sec,
                                 str(_firefox_expiry_seconds(expiry)),
                                 str(name), str(value)]) + "\n")
    return len(rows)


def _firefox_expiry_seconds(expiry) -> int:
    """
    Normalise a Firefox expiry to Unix seconds for the Netscape format.

    Firefox is documented to store ``expiry`` in seconds, but some builds record
    it in milliseconds (and the sibling timestamp columns are microseconds).
    A real seconds expiry is ~1.7e9; anything far larger is a finer unit and is
    scaled down, so a genuinely expired cookie is not written as never-expiring.
    """
    exp = int(expiry or 0)
    if exp >= 10 ** 14:        # microseconds
        exp //= 1_000_000
    elif exp >= 10 ** 11:      # milliseconds
        exp //= 1000
    return exp


def export_to_file(browser_spec: str, out_path: str) -> int:
    """
    Write a browser's cookies to a Netscape cookies.txt for later --cookies-file.

    Firefox exports the signed-in profile's cookies directly. Chromium reuses the
    decrypt path, so it succeeds only where the store is readable — current
    Chrome/Edge App-Bound stores raise BrowserCookieError explaining why. Returns
    the number of cookies written (0/None when the count is not known).
    """
    browser, profile, remainder = _parse_spec(browser_spec)

    if browser == "firefox":
        if profile:
            prof_dir = profile
        else:
            prof_dir, score = _best_firefox_profile_dir()
            if not prof_dir:
                raise BrowserCookieError(
                    "no signed-in Firefox profile found; sign in to YouTube in "
                    "Firefox, or pass firefox:PROFILE_PATH")
        return _export_firefox(prof_dir, out_path)

    if browser in _CHROMIUM_BROWSERS:
        resolution = _resolve_chromium(browser, profile, remainder)
        if not resolution.cookies_file:
            raise BrowserCookieError(f"no cookies extracted from {browser}")
        try:
            shutil.copy(resolution.cookies_file, out_path)
        finally:
            resolution.cleanup()
        return 0

    raise BrowserCookieError(f"unsupported browser {browser!r}")


def _main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        prog="python -m src.browsercookies",
        description="Export browser cookies to a Netscape cookies.txt for "
                    "--cookies-file. Firefox works fully; current Chrome/Edge "
                    "cookies are blocked by App-Bound Encryption.")
    parser.add_argument("browser",
                        help="firefox | chrome | edge | brave, optionally "
                             "browser:PROFILE (e.g. firefox:C:\\path\\to\\profile)")
    parser.add_argument("output", help="path to write cookies.txt")
    args = parser.parse_args(argv)
    try:
        count = export_to_file(args.browser, args.output)
    except BrowserCookieError as exc:
        print(f"[ERROR] {exc}")
        return 1
    suffix = f" ({count} cookies)" if count else ""
    print(f"[OK] Wrote {args.output}{suffix}")
    print(f"     Use it with:  --cookies-file \"{args.output}\"")
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_main())
