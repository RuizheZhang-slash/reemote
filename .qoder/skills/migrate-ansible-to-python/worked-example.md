<!--
Copyright (c) 2026 Kim Jarvis.
SPDX-License-Identifier: EPL-2.0
-->

# Worked example — an nginx role, migrated end to end

A complete Phase 1→7 pass over a small but realistic role. It exercises
four shape changes at once: **handlers with two verbs**, **defaults +
host_vars**, a **validated Jinja2 template**, and a **lineinfile on a
protected file**. Phase 0 decisions: deliverable = runnable standalone
program; target = CentOS Stream 9 only (single-OS role, so no
`include_vars` dispatch); default path only; real-host runs need approval.

## The role (Phase 1 input)

```
roles/webserver/
├── defaults/main.yml
├── tasks/main.yml
├── handlers/main.yml
└── templates/nginx.conf.j2
```

`defaults/main.yml`:

```yaml
nginx_listen_port: 8080
nginx_server_name: example.com
nginx_worker_connections: 1024
```

`tasks/main.yml`:

```yaml
- name: Install nginx
  ansible.builtin.dnf:
    name: nginx
    state: present
  notify: Restart nginx

- name: Deploy nginx.conf
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
    mode: "0644"
    validate: nginx -t -c %s
  notify: Reload nginx

- name: Hide nginx version
  ansible.builtin.lineinfile:
    path: /etc/nginx/conf.d/tuning.conf
    line: "server_tokens off;"
    create: yes
    mode: "0644"
  notify: Reload nginx

- name: Start and enable nginx
  ansible.builtin.service:
    name: nginx
    state: started
    enabled: yes
```

`handlers/main.yml`:

```yaml
- name: Restart nginx
  ansible.builtin.service: {name: nginx, state: restarted}
- name: Reload nginx
  ansible.builtin.service: {name: nginx, state: reloaded}
```

`templates/nginx.conf.j2` (abridged; the program carries it verbatim):

```nginx
user nginx;
worker_processes auto;
events { worker_connections {{ nginx_worker_connections }}; }
http {
    include /etc/nginx/conf.d/*.conf;
    server {
        listen {{ nginx_listen_port }};
        server_name {{ nginx_server_name }};
        location / { root /usr/share/nginx/html; index index.html; }
    }
}
```

## Phase 1 — role at a glance

- 4 tasks, 2 handlers. Fan-in: Install → **Restart**; Deploy + Hide →
  **Reload**. Handlers fire end-of-play, deduplicated per host.
- Variables: 3 defaults, overridable per host (`host_vars`). The template
  consumes **only static variables** — no registered facts — so the
  migration needs **no `gather_fact`** at all.
- No loops, no `register`, no OS dispatch, no opt-in branches.
- Shape changes needed: handler split (recipe 1), host_vars (2), template
  pre-render (4), validate hook (5), lineinfile transform (6).

## Phase 2 — coverage table

| # | Ansible task | reemote target | Status | Evidence |
|---|---|---|---|---|
| 1 | Install nginx (`dnf present`, notify Restart) | `op(dnf.packages, packages=("nginx",), sudo=True)`, name ∈ NOTIFY_RESTART | recipe | migrating guide §handler; reemote.org/modules/dnf/ |
| 2 | Deploy nginx.conf (`template` + `validate`, notify Reload) | render in `main()` + `files.install(validate="nginx -t -c {spool}")`, name ∈ NOTIFY_RELOAD | recipe | §Jinja2 + §validate |
| 3 | Hide nginx version (`lineinfile create=yes`, notify Reload) | `files.transform(transform=set_server_tokens)`, name ∈ NOTIFY_RELOAD | recipe | §lineinfile |
| 4 | Start and enable (`service started/enabled`) | `systemd.service(running=True, enabled=True)` | covered | reemote.org/modules/systemd/ |
| H1 | Restart nginx (handler) | `restart_handler(changed_hosts(report, NOTIFY_RESTART), "nginx")` | recipe | §handler |
| H2 | Reload nginx (handler) | `reload_handler(changed_hosts(report, NOTIFY_RELOAD) - restart_set, "nginx")` | recipe | §handler |
| V1 | defaults + host_vars | `DEFAULTS` constants + `host.extra` overlay | recipe | §host_vars |

## Phase 3 — gaps

None. Every task maps. For contrast: had the role also used
`synchronize` for static assets, that row would be **GAP** (genuine —
no rsync operation; stopgap: per-file `files.put`); a `cron` cert-renewal
task would be **workaroundable** (a `/etc/cron.d` drop-in via
`files.install`). See [gap-analysis.md](gap-analysis.md).

## Phase 4 — program shape

```
module constants: INVENTORY (hosts + host_vars), DEFAULTS, template text,
                  RENDERER, NOTIFY_RESTART / NOTIFY_RELOAD frozensets,
                  set_server_tokens (module-level pure transform)
main():
  validate inventory → build Host objects → render per host (static only)
  run 1: build_deploy(rendered)        # the play body, branch-free
  notification read: changed_hosts ×2 → restart_set, reload_set
  run 2: restart_handler(restart_set, "nginx")
  run 3: reload_handler(reload_set, "nginx")
```

Three runs because handlers fire end-of-play and the two verbs need two
frozen sets. Each `await run(...)` is a barrier: run 1's apply join
guarantees every config write landed before any handler plans. The
factory closes over the rendered dict — the deploy body never renders,
never reads facts, never branches on outcomes.

## Phase 5 — the program

```python
"""Migrated Ansible role: webserver (nginx) — CentOS Stream 9 target.

Run it with::

    python webserver.py --dry   # check-mode preview of the play body
    python webserver.py         # real run (needs host approval)
"""

import asyncio
import sys
from collections.abc import Callable, Generator
from typing import Any

from jinja2 import Environment, StrictUndefined  # the program's own dep

from reemote import (
    CommandError,
    Host,
    HostConnectionError,
    InventoryError,
    OperationRequest,
    PrivilegeError,
    changed_hosts,
    dnf,
    files,
    format_log,
    format_plan,
    op,
    reload_handler,
    restart_handler,
    run,
    systemd,
    validate_inventory,
)

# The inventory IS the hosts file + host_vars: every key beyond host /
# connection / privilege / group / tags lands in host.extra.
INVENTORY: list[dict[str, Any]] = [
    {
        "host": "web-1",
        "connection": {"address": "192.0.2.10", "username": "deploy",
                       "key_path": "~/.ssh/id_ed25519"},
        "privilege": {"sudo_user": "root"},
        "group": "centos",
        "nginx_listen_port": 8081,  # host_vars override
    },
    {
        "host": "web-2",
        "connection": {"address": "192.0.2.11", "username": "deploy",
                       "key_path": "~/.ssh/id_ed25519"},
        "privilege": {"sudo_user": "root"},
        "group": "centos",
    },
]

# defaults/main.yml — frozen module constants (fixed single-OS target).
DEFAULTS = {
    "nginx_listen_port": 8080,
    "nginx_server_name": "example.com",
    "nginx_worker_connections": 1024,
}

# templates/nginx.conf.j2 — verbatim; rendered control-side, never in-deploy.
NGINX_CONF_TEMPLATE = """\
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;

events {
    worker_connections {{ nginx_worker_connections }};
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    keepalive_timeout 65;
    include /etc/nginx/conf.d/*.conf;

    server {
        listen {{ nginx_listen_port }};
        server_name {{ nginx_server_name }};
        location / {
            root /usr/share/nginx/html;
            index index.html;
        }
    }
}
"""
RENDERER = Environment(
    undefined=StrictUndefined, trim_blocks=True, keep_trailing_newline=True
)

# notify: lists — the names of the notifying requests, frozen.
NOTIFY_RESTART = frozenset({"Install nginx"})
NOTIFY_RELOAD = frozenset({"Deploy nginx.conf", "Hide nginx version"})


def render_nginx_conf(host: Host) -> str:
    """Defaults overlaid with host.extra (host_vars precedence)."""
    variables = dict(DEFAULTS)
    variables.update({k: v for k, v in host.extra.items() if k in DEFAULTS})
    return RENDERER.from_string(NGINX_CONF_TEMPLATE).render(**variables)


def set_server_tokens(current: str | None) -> str:
    """lineinfile parity: ensure `server_tokens off;` — pure fixpoint.

    None (absent file) → creation content: `create: yes` comes free.
    """
    lines = (current or "").splitlines()
    if "server_tokens off;" not in lines:
        lines.append("server_tokens off;")
    return "\n".join(lines) + "\n"


def build_deploy(
    rendered: dict[str, str],
) -> Callable[[Host], Generator[OperationRequest]]:
    """Factory: close the deploy over the frozen per-host renders."""

    def deploy(host: Host) -> Generator[OperationRequest]:
        yield op(dnf.packages, name="Install nginx",
                 packages=("nginx",), sudo=True)
        yield op(files.install, name="Deploy nginx.conf",
                 content=rendered[host.name], dest="/etc/nginx/nginx.conf",
                 mode="0644", validate="nginx -t -c {spool}", sudo=True)
        yield op(files.transform, name="Hide nginx version",
                 path="/etc/nginx/conf.d/tuning.conf",
                 transform=set_server_tokens, mode="0644", sudo=True)
        yield op(systemd.service, name="Start and enable nginx",
                 service="nginx", running=True, enabled=True, sudo=True)

    return deploy


async def main(dry: bool) -> None:
    validate_inventory(INVENTORY)
    hosts = [Host.from_inventory(entry) for entry in INVENTORY]
    rendered = {host.name: render_nginx_conf(host) for host in hosts}

    # Run 1 — the play body. Its apply join is the handler barrier.
    plans, report, _ = await run(INVENTORY, build_deploy(rendered), dry=dry)
    print("== Play body ==")
    print(format_plan(plans))
    if dry:
        # Check mode cannot know whether handlers will fire — Ansible
        # skips handlers in check mode for the same reason.
        return
    assert report is not None
    print(format_log(report))

    # The notification read, between runs — one frozen set per verb.
    restart_set = changed_hosts(report, NOTIFY_RESTART)
    # Deviation: Ansible fires both handlers when both notify; a restart
    # already applies the config, so the redundant reload is suppressed.
    reload_set = changed_hosts(report, NOTIFY_RELOAD) - restart_set

    # Runs 2+3 — the handlers, notified hosts only. An empty set yields an
    # empty deploy: a converged re-run does nothing at all.
    for label, handler in (
        ("Restart nginx", restart_handler(restart_set, "nginx")),
        ("Reload nginx", reload_handler(reload_set, "nginx")),
    ):
        plans, report, _ = await run(INVENTORY, handler)
        print(f"== Handler: {label} ==")
        print(format_plan(plans))
        assert report is not None
        print(format_log(report))


if __name__ == "__main__":
    try:
        asyncio.run(main(dry="--dry" in sys.argv))
    except InventoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except (CommandError, HostConnectionError, PrivilegeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
```

Notes on the code:

- Prefer a separate inventory file over embedding it? The inventory is a
  plain list of dictionaries — load the JSON in `main()` and pass it to
  `run`; the schema (and the `host.extra` mechanism) is documented at
  [https://reemote.org/hosts/](https://reemote.org/hosts/). A `when=` guard
  on every request can scope the program to a subset of the entries (the
  guard reads static `host.group`, so it is legal in both phases).
- `validate` runs on the **spool** with the request's elevation; a failing
  `nginx -t` raises `CommandError` before the install — dest keeps its old
  content (Ansible `validate:` parity, atomic).
- The content read-back is two-tier: `FileContents` cats unprivileged and
  re-reads elevated when the login user cannot read, so even a `0640`
  service-owned target converges (recipe 9). Both file targets here are
  `0644`.
- `jinja2` is imported at module scope because this is a `__main__`
  program that declares its own dependency. Import the renderer inside the
  render function instead whenever the module may be imported by tooling
  that does not declare the dependency — recipe 4.

## Phase 6 — verification

Offline (no hosts, no approval):

```python
def test_transform_fixpoint():
    for text in (None, "", "server_tokens off;\n", "other;\n"):
        once = set_server_tokens(text)
        assert set_server_tokens(once) == once


def test_render_uses_host_vars():
    host = Host.from_inventory(INVENTORY[0])
    assert "listen 8081;" in render_nginx_conf(host)
```

The deploy generator itself is testable without a server:
`list(build_deploy({"web-1": "…"})(host))` yields four requests whose
names/kwargs can be asserted. For a full offline two-pass test — plan →
apply → second apply is a no-op — the repo's model tests show what the
`SimulatedHost` harness takes in practice:
[`tests/test_roles_ansible_datadog.py`](https://github.com/kimjarvis/reemote/blob/main/tests/test_roles_ansible_datadog.py)
(persistent simulated hosts, seam seeding, between-pass bridging) and
[`tests/test_roles_ansible_role_apache.py`](https://github.com/kimjarvis/reemote/blob/main/tests/test_roles_ansible_role_apache.py)
(seeding the `Shell` probe in the action-transport seam). SKILL.md Phase 6
has the recipe.

Real hosts (user approval first): `--dry` and read the plan; real run;
then **run the whole program again** — no changes, handlers idle.

## Phase 7 — report extract

Deviations from Ansible semantics (all deliberate, all recorded):

1. Fixed CentOS Stream 9 target — `dnf`/`systemd` hardcoded; a multi-OS
   migration would add the gather→snapshot→factory dispatch (recipe 3).
2. Redundant reload suppressed when a restart fires (set subtraction);
   Ansible would run both handlers.
3. Jinja2 is the program's dependency; the renderer matches Ansible's
   environment (`trim_blocks=True`, `keep_trailing_newline=True`) with
   `StrictUndefined`.
4. `--dry` previews the play body only; handler firing is unpredictable
   in check mode (Ansible parity). A handler deploy's own dry preview,
   computed from a real run 1 report, is honest.
5. `lineinfile create: yes` → `transform(None)` produces the creation
   content; `mode` is applied by the spool-and-install write.

Run instructions: add `jinja2` to the program's dependencies, point
`INVENTORY` at the real hosts (passwordless sudo for `deploy`), then
`python webserver.py --dry` followed by the real run.

## What this example does not exercise

Fact-fed templates (gather **after** the deploy that creates the input —
recipe 4), `include_vars` OS dispatch (recipe 3), `register` + `when`
(the same two-deploy split as handlers), loops over lists-of-dicts
(flatten to tuples), `get_url` (recipe 7), build-from-source (recipe 8),
and the tracked-gap recipes (9–12: `0640` read-back, multi-key keyrings,
`apt_repository` cache + global removal and the deb822 `signed_by` URL — all
shipped; converging dnf `latest` — the one open workaround).
See [construct-recipes.md](construct-recipes.md) and
[two_deploy_split.py](https://github.com/kimjarvis/reemote/blob/main/examples/demonstrations/composition/two_deploy_split.py).
For a second worked example that *does* exercise those — a whole multi-file
role, seven deploys, PyYAML rendering and a play-wide handler union — read
[examples/roles/ansible-datadog/ansible-datadog.py](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-datadog/ansible-datadog.py)
with its [companion doc](https://reemote.org/examples/roles/ansible-datadog/)
(coverage table, gap register, deviations).
