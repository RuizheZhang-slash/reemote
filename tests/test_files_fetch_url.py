# Copyright (c) 2026 Kim Jarvis.
# SPDX-License-Identifier: EPL-2.0

"""Tests for ``files.fetch_url``: fetch a URL control-side, return its text.

``files.fetch_url`` is the control-side GET helper -- Ansible's ``uri`` with
``return_content: true`` mapped to a plain coroutine called from ``main()``,
not an operation: it takes no ``OpContext``, yields no commands and never
touches a host. The *control* machine opens the connection (the same
``_fetch_url_bytes`` seam ``files.download`` rides), the optional Ansible-style
``"<algorithm>:<hexdigest>"`` checksum is verified against the raw bytes before
the caller sees the content, and the body is decoded as UTF-8 -- a binary
response raises ``ValueError``. ``files.download`` shares the scheme guard
and checksum contract through ``_fetch_url_verified``; unlike this helper it
also installs a binary body (issue #23).

The single network read (``_fetch_url_bytes``) is monkeypatched to a canned-bytes
stub so every test stays offline (the ``tests/test_files_download.py``
precedent). Covers the content-returning contract (verbatim text, once per
call), the http(s) scheme guard and malformed/unknown checksum rejection before
any fetch, checksum match/mismatch, the binary-body rejection, error
propagation, the keyword-only ``checksum`` signature, the package export and
the shared download fetch seam.
"""

import hashlib
import urllib.error

import pytest

from reemote.core import FactCache, OpContext
from reemote.modules import files
from reemote.modules.files import files as files_module
from reemote.modules.files.files import InstallCommand, InstallSpoolCommand
from tests.simulated_host import SimulatedHost

URL = "https://composer.github.io/installer.sig"
CONTENT = "9f2cab1234567890abcdef\n"
DATA = CONTENT.encode()
CHECKSUM = "sha256:" + hashlib.sha256(DATA).hexdigest()
DEST = "/tmp/composer-installer.php"


@pytest.fixture
def canned_fetch(monkeypatch):
    """Replace the control-side network read with a canned-bytes stub.

    ``files.fetch_url`` looks ``_fetch_url_bytes`` up as a module global at call
    time (through ``asyncio.to_thread``), so patching the module attribute
    redirects the fetch. Returns the list of URLs the stub was called with, so
    a test can assert the fetch happened -- and how many times, since the
    helper runs exactly when the caller awaits it.
    """
    fetched: list[str] = []

    def fake_fetch(url: str) -> bytes:
        fetched.append(url)
        return DATA

    monkeypatch.setattr(files_module, "_fetch_url_bytes", fake_fetch)
    return fetched


# --- The content-returning contract -------------------------------------------


async def test_fetch_url_returns_the_decoded_text(canned_fetch):
    """The uri ``return_content`` payoff: the body comes back to the program
    as a str, decoded UTF-8, with nothing installed anywhere."""
    content = await files.fetch_url(URL)
    assert content == CONTENT
    assert canned_fetch == [URL]


async def test_fetch_url_returns_the_body_verbatim(monkeypatch):
    """No normalization: leading/trailing whitespace and newlines survive, so
    the caller decides what to strip before freezing the text into a plan."""
    body = "  9f2cab\n\n"
    monkeypatch.setattr(files_module, "_fetch_url_bytes", lambda url: body.encode())
    assert await files.fetch_url(URL) == body


async def test_fetch_url_returns_empty_text_for_an_empty_body(monkeypatch):
    monkeypatch.setattr(files_module, "_fetch_url_bytes", lambda url: b"")
    assert await files.fetch_url(URL) == ""


async def test_fetch_url_runs_once_per_call(canned_fetch):
    """Unlike an operation body (once per phase per host), the helper fetches
    exactly when awaited -- the fetch-once-in-main() recipe."""
    await files.fetch_url(URL)
    await files.fetch_url(URL)
    assert canned_fetch == [URL, URL]


async def test_fetch_url_needs_no_host(canned_fetch):
    """The helper takes no ctx and opens no transport: the canned control-side
    read is the only IO, so no SimulatedHost is involved at all."""
    assert await files.fetch_url(URL) == CONTENT


# --- The http(s) scheme guard -------------------------------------------------


@pytest.mark.parametrize(
    "url", ["ftp://example.com/f", "file:///etc/passwd", "/local/path", ""]
)
async def test_fetch_url_rejects_a_non_http_url_before_fetching(url, canned_fetch):
    """A ``file:``/``ftp:`` scheme or a bare path raises before the fetch, so
    the control machine never opens an unexpected connection."""
    with pytest.raises(ValueError, match=r"http\(s\) URL"):
        await files.fetch_url(url)
    assert canned_fetch == []


# --- Checksum verification ----------------------------------------------------


async def test_fetch_url_accepts_a_matching_checksum(canned_fetch):
    assert await files.fetch_url(URL, checksum=CHECKSUM) == CONTENT
    assert canned_fetch == [URL]


async def test_fetch_url_verifies_a_sha384_signature(canned_fetch):
    """The motivating composer shape: a sha384 pin over the fetched bytes."""
    pin = "sha384:" + hashlib.sha384(DATA).hexdigest()
    assert await files.fetch_url(URL, checksum=pin) == CONTENT


async def test_fetch_url_checksum_is_case_insensitive(canned_fetch):
    upper = "SHA256:" + hashlib.sha256(DATA).hexdigest().upper()
    assert await files.fetch_url(URL, checksum=upper) == CONTENT


async def test_fetch_url_rejects_a_checksum_mismatch(canned_fetch):
    """A digest mismatch raises after the fetch but before the caller sees the
    content, so a tampered or truncated artifact never reaches the plan."""
    with pytest.raises(ValueError, match="checksum mismatch"):
        await files.fetch_url(URL, checksum="sha256:" + "0" * 64)
    assert canned_fetch == [URL]


async def test_fetch_url_surfaces_a_malformed_checksum_spec(canned_fetch):
    """The spec is parsed before the fetch, so a malformed checksum fails fast."""
    with pytest.raises(ValueError, match="algorithm>:<hexdigest"):
        await files.fetch_url(URL, checksum="9f2cab")
    assert canned_fetch == []


async def test_fetch_url_rejects_an_unknown_algorithm_before_fetching(canned_fetch):
    with pytest.raises(ValueError, match="unknown checksum algorithm"):
        await files.fetch_url(URL, checksum="rot13:abcd")
    assert canned_fetch == []


async def test_checksum_is_keyword_only(canned_fetch):
    """The agreed signature is ``fetch_url(url, *, checksum=None)``."""
    with pytest.raises(TypeError):
        await files.fetch_url(URL, CHECKSUM)
    assert canned_fetch == []


# --- The binary-body rejection and error propagation ---------------------------


async def test_fetch_url_rejects_a_binary_body(monkeypatch):
    """The helper returns text only -- a non-UTF-8 response raises rather than
    handing back mojibake; installing a binary body at a path is
    ``files.download``'s or ``files.install(content=<bytes>)``'s job."""
    monkeypatch.setattr(
        files_module, "_fetch_url_bytes", lambda url: b"\xff\xfe\x00\x01binary"
    )
    with pytest.raises(ValueError, match="not valid UTF-8 text"):
        await files.fetch_url(URL)


async def test_fetch_url_propagates_a_urlerror(monkeypatch):
    """An unreachable URL or a non-2xx response surfaces as the OSError
    subclass urllib raises, exactly as a host connection error would."""

    def unreachable(url: str) -> bytes:
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(files_module, "_fetch_url_bytes", unreachable)
    with pytest.raises(OSError, match="name resolution failed"):
        await files.fetch_url(URL)


# --- The package export and the shared download fetch --------------------------


def test_fetch_url_is_exported_from_the_package():
    assert files.fetch_url is files_module.fetch_url
    assert "fetch_url" in files.__all__
    assert "fetch_url" in files_module.__all__


async def test_download_shares_the_verified_fetch_seam(monkeypatch):
    """``files.download`` rides the same ``_fetch_url_verified`` helper for its
    fetch half, so the scheme guard and checksum contract are shared, not
    duplicated -- but it keeps the raw bytes, so a binary body can install."""
    calls: list[tuple[str, str | None]] = []
    real_verified = files_module._fetch_url_verified

    async def spy(url: str, checksum: str | None) -> bytes:
        calls.append((url, checksum))
        return await real_verified(url, checksum)

    monkeypatch.setattr(files_module, "_fetch_url_verified", spy)
    monkeypatch.setattr(files_module, "_fetch_url_bytes", lambda url: DATA)
    host = SimulatedHost(name="h")
    ctx = OpContext(host=host, facts=FactCache(host, phase="prepare"))
    commands = [
        cmd async for cmd in files.download(ctx, URL, DEST, checksum=CHECKSUM)
    ]

    assert calls == [(URL, CHECKSUM)]
    spool_cmd, install_cmd = commands
    assert isinstance(spool_cmd, InstallSpoolCommand)
    assert spool_cmd.content == CONTENT
    assert isinstance(install_cmd, InstallCommand)
    assert install_cmd.dest == DEST