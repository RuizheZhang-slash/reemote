# Copyright (c) 2026 Kim Jarvis.
# SPDX-License-Identifier: EPL-2.0

"""Regression tests: every non-interactive transport channel closes stdin.

Some remote commands read stdin when it is an open pipe and block forever
waiting for input that never comes -- ``lxc profile create``, ``lxc launch``
and ``lxc snapshot`` all do, which is what hung the lxd profile example over
SSH. Both transports must therefore hand the command a *closed* stdin:
``asyncssh.DEVNULL`` on the SSH channel, ``subprocess.DEVNULL`` on the docker
CLI subprocess (which ``exec -i`` forwards into the container). ``input=""``
is not a substitute on the SSH side: asyncssh only writes EOF for a *truthy*
input, so the empty string leaves the pipe open too.

The fakes below record the kwargs each transport seam passes, pinning the
closure without a socket or a docker daemon -- the same fake-module pattern
``test_connection_errors.py`` uses for ``asyncssh``.
"""

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

from reemote import DockerHost, Host


class RecordingConn:
    """A stand-in asyncssh connection recording every ``run`` call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def run(self, shell: str, **kwargs) -> SimpleNamespace:
        self.calls.append((shell, kwargs))
        return SimpleNamespace(exit_status=0, stdout="", stderr="")

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


def _install_fake_asyncssh(
    monkeypatch: pytest.MonkeyPatch, conn: RecordingConn
) -> types.ModuleType:
    """Install a stub ``asyncssh`` whose ``connect`` returns *conn*.

    ``DEVNULL`` is the real constant: asyncssh re-exports
    ``asyncio.subprocess.DEVNULL``, so asserting against it here checks the
    very value the transport must pass.
    """
    module = types.ModuleType("asyncssh")
    module.DEVNULL = asyncio.subprocess.DEVNULL  # type: ignore[attr-defined]

    async def _connect(address, **kwargs):
        return conn

    module.connect = _connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "asyncssh", module)
    return module


# --- SSH: the channel seam and the askpass cleanup -----------------------------


async def test_run_shell_closes_channel_stdin(monkeypatch: pytest.MonkeyPatch):
    conn = RecordingConn()
    _install_fake_asyncssh(monkeypatch, conn)
    host = Host(name="web1", connection={"address": "10.0.0.1"})

    await host.run_shell("lxc profile create web")

    assert len(conn.calls) == 1
    shell, kwargs = conn.calls[0]
    assert shell == "lxc profile create web"
    assert kwargs["stdin"] is asyncio.subprocess.DEVNULL
    assert kwargs["check"] is False


async def test_run_shell_result_closes_channel_stdin(monkeypatch: pytest.MonkeyPatch):
    # The raw-result seam actions ride shares ``_run_shell``; pin it too so a
    # future second call site cannot reintroduce the open pipe unnoticed.
    conn = RecordingConn()
    _install_fake_asyncssh(monkeypatch, conn)
    host = Host(name="web1", connection={"address": "10.0.0.1"})

    result = await host.run_shell_result("lxc snapshot web1 snap0")

    assert result.exit_status == 0
    _, kwargs = conn.calls[0]
    assert kwargs["stdin"] is asyncio.subprocess.DEVNULL


async def test_aclose_cleanup_closes_channel_stdin(monkeypatch: pytest.MonkeyPatch):
    conn = RecordingConn()
    _install_fake_asyncssh(monkeypatch, conn)
    host = Host(name="web1", connection={"address": "10.0.0.1"})
    await host.connect()
    host._askpass_path = "/tmp/reemote-askpass-test"

    await host.aclose()

    assert len(conn.calls) == 1
    shell, kwargs = conn.calls[0]
    assert shell == "rm -f /tmp/reemote-askpass-test"
    assert kwargs["stdin"] is asyncio.subprocess.DEVNULL


# --- docker: the local CLI seam ------------------------------------------------


async def test_docker_run_local_closes_subprocess_stdin(monkeypatch: pytest.MonkeyPatch):
    recorded: dict = {}

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def _exec(*argv, **kwargs):
        recorded["argv"] = argv
        recorded["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)
    host = DockerHost(
        name="build1",
        connection={
            "connector": "docker",
            "identifier": "alpine:3.20",
            "docker_cmd": "docker",
        },
    )

    result = await host._run_local(["docker", "version"])

    assert result.exit_status == 0
    assert recorded["argv"] == ("docker", "version")
    assert recorded["kwargs"]["stdin"] is asyncio.subprocess.DEVNULL