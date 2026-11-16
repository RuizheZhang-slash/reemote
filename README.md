
# Reemote

Reemote is a Python library for configuring and deploying servers, specifically built to support the automated migration of Ansible-based workflows into pure Python.

## Scope

Reemote is a library, not a deployment tool. It ships no CLI and no
inventory format: hosts are a plain *inventory* (a list of dictionaries) handed
to `run`. The transport is real — the default `Host.from_inventory` factory
opens an [asyncssh] connection per entry, gathers facts and runs commands over
it, and `run` closes the connections when it finishes.

## Documentation

A getting-started guide, the API reference for every module,
actions and connectors, and runnable examples — is available at
**[https://reemote.org/](https://reemote.org/)**.

## Installation

The *controller* is the machine running your Python script. It needs **Python
3.13 or newer**. You do not install reemote on the target servers.

**Installing from source is the recommended route**, because the checkout also
gives you the runnable `examples/` tree and lets you pin the exact revision you
deploy from. Run this in a directory where you want to keep the project:

```bash
git clone https://github.com/kimjarvis/reemote.git
cd reemote
uv sync
source .venv/bin/activate
```

`uv sync` creates `.venv`, installs reemote in editable mode and resolves its
declared dependencies — `asyncssh`, `distro` and `pydantic` — so the SSH
transport needs no separate install step. Here we use 
[uv](https://docs.astral.sh/uv/); `venv` and `pip` work just as well if you
prefer them.

The package is **also published on [PyPI](https://pypi.org/project/reemote/)**,
which is enough if you only need the library and not the examples:

```bash
uv pip install reemote
```

Inside a project of your own, use `uv add reemote` instead so it lands in your
`pyproject.toml`.

## Supported Linux Targets

reemote manages **Linux servers**. The supported targets are the Red Hat family
(RHEL, CentOS, Rocky Linux, AlmaLinux, Fedora, openEuler), the Ubuntu / Debian
family, and Alpine.

**BSD, macOS and Windows targets are not supported.**

The `examples/` tree is verified on CentOS 9, openEuler 24.03 LTS SP4, Ubuntu 26.04 LTS and Alpine 3.24.

## License & Intellectual Property

### License
This project is licensed under the Eclipse Public License 2.0 (EPL-2.0).
SPDX-License-Identifier: EPL-2.0

### Origin & Open Source Release
This software is part of a commercially available application. It is being released to the open source community under the EPL-2.0 to foster collaborative development, improve software reliability, and encourage community contributions and issue identification.

### Originality & Attribution
This codebase was independently developed and was inspired by the design concepts of Pyinfra by Nick Mills-Barrett. This project is an original work and does not contain, incorporate, or derive from any source code or copyrighted material of Pyinfra.

[asyncssh]: https://asyncssh.readthedocs.io/
