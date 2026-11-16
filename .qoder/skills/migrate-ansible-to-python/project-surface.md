<!--
Copyright (c) 2026 Kim Jarvis.
SPDX-License-Identifier: EPL-2.0
-->

# The reemote project surface — everything a migration touches

Authoritative detail lives in the online documentation
([https://reemote.org/](https://reemote.org/)) and the source on GitHub
([https://github.com/kimjarvis/reemote](https://github.com/kimjarvis/reemote),
branch `main`); this file is the map.

## Installation

- The **controller** (the machine running the migrated program) needs
  **Python 3.13 or newer**. Nothing is installed on the target servers.
- From PyPI: `pip install reemote` (or `uv pip install reemote`; inside a
  project of your own, `uv add reemote`).
- Installing from source is the recommended route — the checkout also gives
  you the runnable `examples/` tree:
  `git clone https://github.com/kimjarvis/reemote.git && cd reemote && uv sync`
  (or use `venv`/`pip`).
- Runtime dependencies: `asyncssh`, `distro`, `pydantic`. **Neither Jinja2 nor
  PyYAML is a runtime dependency** — a migrated program that renders templates
  owns its renderer dependency (`jinja2` for Jinja syntax, `pyyaml` for
  Ansible's `to_nice_yaml`).
- Supported targets: the Red Hat family (RHEL, CentOS, Rocky Linux, AlmaLinux,
  Fedora, openEuler), the Ubuntu/Debian family, and Alpine. **BSD, macOS and
  Windows targets are not supported.**

## Repository layout (on GitHub)

- [`src/reemote/`](https://github.com/kimjarvis/reemote/tree/main/src/reemote) —
  the library: `core.py` (requests/op/composition), `drivers.py`
  (run/plan/apply/gather), `hosts.py` (inventory/Host/transport), `actions.py`
  (Shell/Script/WaitForConnection), `handlers.py` (notification helpers),
  `commands.py` (descriptor bases), `connectors/docker.py`,
  `modules/<name>/<name>.py` (facts + operations + descriptors per namespace).
- [`docs/`](https://github.com/kimjarvis/reemote/tree/main/docs) — the MkDocs
  source published at reemote.org: `migrating.md` (the migration guide),
  `articles/migrating.md` (the Ansible→Python thesis), `guide.md`, `core.md`,
  `drivers.md`, `hosts.md`, `handlers.md`, `commands.md`, `exceptions.md`,
  `actions/actions.md`, `modules/<mod>.md` (rendered API per module),
  `examples/…` (rendered example docstrings), `docs/examples/roles/<role>.md`
  (per-role migration docs, wired into the Examples → Roles nav in
  `mkdocs.yml`, published at `https://reemote.org/examples/roles/<role>/`).
- [`examples/`](https://github.com/kimjarvis/reemote/tree/main/examples) —
  runnable scripts (they connect for real): `modules/<mod>/`, `actions/`,
  `demonstrations/composition|connectors|privilege/`, `tutorials/website/`,
  `roles/ansible-datadog/`, `roles/ansible-role-apache/`,
  `roles/ansible-role-docker/`, `roles/ansible-role-nginx/`,
  `roles/ansible-role-php-xdebug/`.
- [`tests/`](https://github.com/kimjarvis/reemote/tree/main/tests) — the
  offline pytest suite; `tests/simulated_host.py` is the `SimulatedHost` test
  framework (structural pattern matching over command descriptors).
- `inventory.json` — the examples' shared inventory (groups incl. `centos`,
  `alpine`, `ubuntu`).

## Execution model

- A **deploy** is a plain *sync* generator `def deploy(host: Host) ->
  Generator[OperationRequest]` yielding `op(...)` requests in order.
- `run(inventory, deploy)` executes it **twice**: *prepare* materializes every
  request against pre-deployment facts (nothing is sent) producing the plan;
  *apply* re-materializes per lockstep step with a fresh `FactCache` and sends
  the yielded commands only when `changed`. Hosts progress concurrently
  (asyncio + asyncssh); each host's commands stay ordered.
- The apply-phase request sequence must equal the plan's, value-for-value —
  otherwise `DeterminismError`. This is why deploys are pure functions of
  static input and why fact-driven branching moves between runs.
- Operations are **async generators** `async def name(ctx: OpContext, …) ->
  AsyncGenerator[Command]`: they `await ctx.facts.get(FactClass, …)`, set
  `ctx.changed` / `ctx.reason`, and yield typed command descriptors. They
  never touch the host directly; the driver's `send_command` executes
  descriptors in apply only. Fail-fast: a non-zero exit raises `CommandError`.
- Descriptor kinds (`commands.py`): `Command` (shell text via `shell()`),
  `TransferCommand` (scp, **never elevated**), `WaitCommand` (polls a fact
  until a predicate holds or `WaitTimeoutError`).
- Facts are classes with `async def process(host, …)` classmethods returning
  typed, sorted, JSON-printable data. They are phase-unaware and
  user-extensible (a new fact is just a class with `process`).

## Core API (`reemote.core`, exported at package root)

- `op(func, *, name="", sudo=UNSET, su=UNSET, doas=UNSET, when=None, **kwargs)
  -> OperationRequest`. `name`/`sudo`/`su`/`doas`/`when` are meta-parameters,
  never forwarded to the operation. Privilege flags accept `bool` or the
  `Privilege` tri-state (`ON`/`OFF`/`UNSET` = no opinion, so a `sub_deploy`
  policy can fill it). `when` is a stable module-level predicate over static
  host data, or a tuple of them (all must pass); a guarded request stays in
  the sequence and is *skipped* per host. Every kwarg is `hash()`-checked →
  `UnhashableArgumentError` on lists/dicts (even nested in tuples). Building
  a request without yielding it → `DeployRequestError`.
- `sub_deploy(sub, *, name_prefix="", sudo=…, su=…, doas=…, when=None)` —
  wraps a deploy: escalation *policy* fills only `UNSET` flags (inner wins;
  `sudo=True` forces elevation except deliberate `sudo=False` opt-outs);
  `when` composes by conjunction (outer guards can only restrict);
  `name_prefix` labels plans. The Ansible block-level `when:` / `become:`
  analogue. Nest with `yield from`.
- `compose(*subs, dedupe=False)` — concatenate deploys in argument order
  (cross-role ordering: repos before packages). `dedupe=True` collapses
  requests by effective identity (func+args+kwargs+resolved privilege+when,
  **not** name) to the first occurrence.
- `OperationRequest` — frozen dataclass; equality is maximal (name included),
  streams compare by identity.

## Drivers (`reemote.drivers`)

- `await run(inventory, deploy_func, *, host_factory=Host.from_inventory,
  dry=False) -> (plans, report, hosts)`:
  - `plans`: `{host_label: [PlannedOperation, …]}`; each carries `request`,
    `changed`, `reason`, `commands`, `skipped`.
  - `report`: `ApplyReport` with `.log: list[LogEntry]` (`host`, `name`,
    `changed`, `reason`, `commands`, privilege fields, `skipped`) and
    `.changed` (any entry). `None` when `dry=True`.
  - `hosts`: materialized hosts; `run` validates the inventory up front
    (`InventoryError`) and **closes the hosts it built** in its own `finally`.
  - `dry=True` stops after prepare — Ansible `--check` as a return value.
- `await gather_fact(hosts, FactClass, *args, **kwargs) -> {host.name: value}`
  — concurrent fan-out of one fact. Opens connections, does **NOT close
  them** — close them yourself (`await host.aclose()`). No `when` parameter:
  filter the host list first. Aggregates `CommandNotFoundError` across hosts.
- `run_prepare` / `run_apply` — the phases separately (tests use them).
- `format_plan(plans)` / `format_log(report)` — human-readable renderings;
  the log shows `$ <shell>` lines with resolved elevation, never passwords.
- `materialize(host, cache, request)` — rejects non-async-generator funcs
  (`OperationError`: actions cannot run inside a deploy).

## Inventory and hosts (`reemote.hosts`)

Entry schema (`InventoryEntry`, pydantic, `extra="allow"`): five recognized
keys — `host` (name, required), `connection` (dict, required), `privilege`
(dict), `group` (single label), `tags` (list of labels). **Every other key is
preserved** and reaches the deploy as `host.extra` — this is the `host_vars`
mechanism. `validate_inventory(inventory)` checks a whole list. Full schema:
[https://reemote.org/hosts/](https://reemote.org/hosts/).

- `connection`: `address` (aliases `host`/`hostname`), `username` (alias
  `user`), `key_path` (single-key shorthand for `client_keys`), `port`,
  `password`, `passphrase`, `known_hosts` (`None` disables checking),
  `proxy_command`, `tunnel`, keepalive/timeout knobs, plus
  `asyncssh_connect_kwargs` passthrough. `connector: "ssh"` (default) or
  `"docker"` (builds a `DockerHost` driving a local container through the
  same seams). `kbdint_auth` is forbidden.
- `privilege`: `sudo_user`/`sudo_password`, `su_user`/`su_password`,
  `doas_user` (passwordless only). The run-as user is chosen **here**, never
  per request — there is no per-task `become_user` override.
- `Host.from_inventory(entry)` materializes one entry; `Host` fields: `name`,
  `connection`, `privilege`, `group`, `tags`, `extra`.
- Errors: `InventoryError`, `HostConnectionError`, `CommandError`,
  `CommandNotFoundError` (exit 127), `PrivilegeError`.

## Actions (`reemote.actions`) — outside deploys only

`gather_action(hosts, ActionClass, *, group=None, tags=None, **kwargs)` is
deliberately sync-returning-a-coroutine: calling it inside a running deploy
raises `ActionInDeployError` immediately. The awaited gather is a barrier;
it filters hosts by static `group`/`tags` (AND), runs concurrently, and
**closes every host's connection** when done (each call re-connects).
Library failures raise (`HostConnectionError`, `PrivilegeError`,
`ConnectionTimeoutError`, aggregated); the command's own exit status is
**data**, never an exception — you interpret it (`failed_when` is your code).
Action detail: [https://reemote.org/actions/actions/](https://reemote.org/actions/actions/).

- `Shell`: `command=` (verbatim), `env=` (mapping → shell-quoted `env K=V`
  prefix), `sudo`/`su`/`doas` bools → `Result` TypedDict
  (`exit_status: int | None`, `stdout: str`, `stderr: str`).
- `Script` (alias `server.script`): runs a file **already staged on the host**
  (stage it with `files.put`/`files.install` in a deploy first — no
  transfer). `path=`, `args=` (iterable, not one string), `interpreter=`,
  `env=`, privilege bools. Missing file → exit 127 in the `Result`.
- `WaitForConnection`: `timeout=300.0`, `retry=5.0`; polls full SSH connects
  (the reboot companion); exhaustion raises fatal `ConnectionTimeoutError`.

## Handlers (`reemote.handlers`)

- `changed_hosts(report, names) -> frozenset[str]` — hosts whose **named**
  entries reported `changed` (skipped entries never queue).
- `service_handler(hosts, services, *, action="restarted"|"reloaded"|
  "running", name=None, sudo=True, when=None)` — factory closing over the
  frozen set; returns a deploy yielding one `systemd.service` request per
  service for notified hosts only. Empty set → empty deploy (converged no-op).
  `restarted`/`reloaded` act only on a *running* unit; the default
  `running=True` starts a stopped one (recipe 1's Watch).
- `restart_handler` / `reload_handler` — thin wrappers pinning the action.
- Non-systemd handlers (a script, a custom command): hand-build the same
  shape — a function closing over the frozen set that `return`s for other
  hosts and `yield`s requests for members.
- Handler chains collapse to listing every downstream service in one pass-2
  call, ordered upstream-first.
- Detail: [https://reemote.org/handlers/](https://reemote.org/handlers/).

## Module catalog (20 namespaces)

Operations are reached as `<mod>.<name>`; facts/descriptors are also exported
at package root. Full signatures: `https://reemote.org/modules/<mod>/`. One
page per module: [https://reemote.org/modules/](https://reemote.org/modules/).
Class-style names are facts, lower-case functions are operations.

| Module | Operations |
| --- | --- |
| `apk` | packages, virtual, hold, autoremove, repository |
| `apt` | packages, repo, sources_file, ppa, key, deb, mark, update, upgrade, dist_upgrade, auto_remove |
| `dnf` | packages, repo, key, rpm, module, update, makecache, clean |
| `snap` | package |
| `flatpak` | packages |
| `files` | file, directory, link, copy, move, put, get, install, transform, download, edit, flags, unarchive |
| `git` | repo, config, worktree |
| `systemd` | service, daemon_reload, mask, reset_failed, dropin, tmpfiles, sysusers, preset |
| `openrc` | service, runlevel, custom_runlevel, config |
| `firewalld` | zone, zone_service, port, interface, source, rich_rule, protocol, icmp_block, forward_port, masquerade, service, ipset, default_zone, lockdown, panic, reload |
| `iptables` | chain, policy, rule, flush, zero, save, restore, ipset |
| `ufw` | state, default_policy, logging, reset, rule |
| `server` | user, group, user_authorized_keys, hostname, etc_hosts, kill, locale, security_limit, modprobe, mount, timezone, wait, wait_service (+ `script` action alias; `service` is a deprecated alias of `systemd.service`) |
| `sysctl` | setting, conf |
| `selinux` | mode, boolean, file_context, file_context_mapping, port, login, module, permissive_domain, restorecon, autorelabel, config |
| `hardware` | (facts only: Cpus, CpuInfo, DmiInfo, SmbiosInfo, BlockDevices, LsBlk, DiskStats, NetworkDevices, Ipv4Addrs, Ipv6Addrs) |
| `gpg` | key, import_key, export_key, delete_key, dearmor, gen_key, trust, refresh_keys |
| `mysql` | database, user, table, index, privileges, role, replica, plugin, variable, sql, dump, load, kill, optimize |
| `postgresql` | database, role, membership, schema, extension, table, index, privilege, publication, subscription, setting, tablespace, sql, dump, load |
| `lxd` | instance, instance_config, instance_state, instance_copy, instance_snapshot, container, image, image_alias, profile, project, network, storage_pool, storage_volume, operation |

Key facts for migrations (non-exhaustive — enumerate the module for the rest):
`server.LinuxDistribution` (`name`, **`family`** = Ansible `os_family`,
`major`, `minor`, `release_meta`), `server.User`/`Users`/`Groups`/`Hostname`/
`Mounts`/`Timezone`/`Which`/`Port`/`Processes`/`Env`, `files.File` (stat-like
metadata), `FileExists`, `FileContents` (whole text; unprivileged cat with
an elevated re-read when the login user cannot read), `FileLink`,
`DirectoryEntries`, `FindFiles`/`FindDirectories`/`FindLinks`/`FindInFile`/
`FindInFiles` (recursive content grep), `Md5File`/`Sha256File`/`Sha384File`/
`RemoteFileSha1`, `dnf.DnfPackages` (per-name versions), `DnfRepositories`,
`RpmGpgKeys`, `apt.AptPackages`/`AptSources`/`AptKeys`/`AptHeldPackages`/
`AptUpgradable` (pending upgrades: name/installed/candidate)/
`AptUpdateStamp` (cache age — the `cache_valid_time` gate),
`systemd.SystemdServiceState`/`SystemdServiceEnabled`/`SystemdUnitFiles`,
`hardware.Cpus`, `git.GitStatus`/`GitLocalCommit`/`GitRemoteBranchCommit`.

Notable semantics: `dnf.packages` presence is version-aware for `pkg=version`
pins, with `allow_downgrade`, `repos`/`disable_repos`/`update_cache`;
`apt.packages` supports `default_release` (apt `-t`), `latest`,
`no_recommends`, and `update=True` + `cache_valid_time=N` (gated on
`AptUpdateStamp`, so it converges inside the window). apt's **`latest=True`
is fact-gated**: it upgrades only installed, unpinned names with a pending
`AptUpgradable` entry, read in-operation, and names each candidate in the
reason. **dnf's `latest=True` is still non-idempotent**: the upgrade set is
`installed ∧ unpinned`, with no pending-upgrade check, so a converged host
still reports changed — gate the flag on a check-update snapshot (recipe 11
in [construct-recipes.md](construct-recipes.md)).
**Cache-refresh asymmetry**: `dnf.packages(update_cache=True)` carries a
first-class refresh flag (a scoped `dnf.makecache` ahead of the work); apt
spells it `update=True` on `packages`. `apt.repo`/`key`/`sources_file`/`ppa`
also take `update_cache=True` — the refresh rides the op after a real sources
change. `dnf.repo` has no refresh parameter: follow a dnf repo change with a
scoped `dnf.makecache`. `apt.sources_file(signed_by=…)` accepts an existing
keyring path **or an http(s) key URL** — the URL form fetches the
ASCII-armored key control-side and installs `/etc/apt/keyrings/<filename>.asc`
itself (#17 closed — recipe 12c). `files.download` is **control-side fetch, text only**,
checksum-pinnable, delegating to `files.install`;
`files.unarchive(src, dest, creates=…, checksum=…)` extracts in-deploy — an
http(s) `src` is fetched control-side as **binary**, and `creates` gates
in-operation before any fetch (#21 closed); `files.copy` is full Ansible
`remote_src` parity — dest auto-detect (existing directory → copy inside,
else rename with the parent validated in both phases), sha1-gated
`overwrite`, `mode`/`user`/`group` in the same request (#22 closed);
`files.move` shares the forms but stays **stateless**. `dnf.repo`/`dnf.key`/
`apt.key`/`gpg.key` **reject URL/filename `src`** — key content arrives as a
control-side IO stream. `apt.key(src, dest)` writes any keyring path but is
**stateless** (always changed); `gpg.import_key(src, dest=…, keyid=…)`
imports **additively** into a named keyring, idempotent per fingerprint — the
one to use for a shared `signed-by` keyring (recipe 10).
`gpg.key(src, dest, keyid=(…), dearmor=True)` is idempotent per fingerprint
too, but installs the keyring file wholesale.

## Errors you will meet

`InventoryError` (bad inventory) · `UnhashableArgumentError` (list/dict arg) ·
`DeployRequestError` (built-but-unyielded request) · `DeterminismError`
(phases diverged) · `OperationError` (non-operation in `op()`, missing host
prerequisite) · `ActionInDeployError` · `CommandError` (non-zero exit,
fail-fast) · `CommandNotFoundError` (127) · `HostConnectionError` ·
`PrivilegeError` · `ConnectionTimeoutError` · `WaitTimeoutError`.
Full list: [https://reemote.org/exceptions/](https://reemote.org/exceptions/).

## Runnable pattern library (examples/, on GitHub)

- [`demonstrations/composition/handler_restart.py`](https://github.com/kimjarvis/reemote/blob/main/examples/demonstrations/composition/handler_restart.py) —
  two-deploy handler split with `changed_hosts` + `restart_handler`, `when`
  guard, dry preview.
- [`demonstrations/composition/two_deploy_split.py`](https://github.com/kimjarvis/reemote/blob/main/examples/demonstrations/composition/two_deploy_split.py) —
  gather → snapshot → factory (post-install `DnfPackages` snapshot gates
  deploy 2).
- [`demonstrations/composition/conf_d_cleanup.py`](https://github.com/kimjarvis/reemote/blob/main/examples/demonstrations/composition/conf_d_cleanup.py) —
  `FindFiles` enumeration + removal (the DataDog conf.d cleanup idiom).
- [`actions/deploy_action_deploy.py`](https://github.com/kimjarvis/reemote/blob/main/examples/actions/deploy_action_deploy.py) —
  deploy → `Shell` probe → factory deploy (the build-from-source skeleton).
- [`modules/files/files_block.py`](https://github.com/kimjarvis/reemote/blob/main/examples/modules/files/files_block.py) —
  the `block_transform` factory (blockinfile parity);
  [`files_install.py`](https://github.com/kimjarvis/reemote/blob/main/examples/modules/files/files_install.py),
  [`files_transform.py`](https://github.com/kimjarvis/reemote/blob/main/examples/modules/files/files_transform.py),
  [`files_download.py`](https://github.com/kimjarvis/reemote/blob/main/examples/modules/files/files_download.py).
- [`demonstrations/privilege/`](https://github.com/kimjarvis/reemote/tree/main/examples/demonstrations/privilege) —
  sudo-with-password, su, doas inventories.
- [`roles/ansible-datadog/ansible-datadog.py`](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-datadog/ansible-datadog.py) —
  a whole Ansible role migrated: seven deploys, control-side PyYAML
  rendering, play-wide handler union, per-key `gpg.import_key(dest=…)`.
- [`roles/ansible-role-apache/ansible-role-apache.py`](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-role-apache/ansible-role-apache.py) —
  the Ubuntu Apache role: three deploys, a `Shell` version probe and
  `FileExists` gathers between runs, control-side Jinja2 rendering, one
  handler.
- [`roles/ansible-role-docker/ansible-role-docker.py`](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-role-docker/ansible-role-docker.py) —
  the Ubuntu Docker role: five deploys, a `LinuxDistribution` codename
  snapshot feeding `build_setup`, the deb822 repo via
  `apt.sources_file(signed_by=<key URL>)` (the #17 URL form fetches and
  installs the keyring itself — the `files.download` workaround is retired),
  `daemon.json` rendered with `json.dumps` (no Jinja2/PyYAML), an ExecStart
  `systemd.dropin` override, a `service_handler` compose partitioned by
  `docker_restart_handler_state`, and a `Groups` getent gate before the users
  deploy. Its offline test
  ([`test_roles_ansible_role_docker.py`](https://github.com/kimjarvis/reemote/blob/main/tests/test_roles_ansible_role_docker.py))
  monkeypatches `apt._fetch_url_bytes` to answer the key fetch without
  network.
- [`roles/ansible-role-nginx/ansible-role-nginx.py`](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-role-nginx/ansible-role-nginx.py) —
  the Ubuntu nginx role: four deploys, a `Cpus` gather feeding the quoted
  `worker_processes` default, control-side Jinja2 rendering with template
  inheritance, and a restart/reload handler compose. Its offline test
  ([`test_roles_ansible_role_nginx.py`](https://github.com/kimjarvis/reemote/blob/main/tests/test_roles_ansible_role_nginx.py))
  asserts removals against `remote_files` directly — the #18 workaround
  is retired.
- [`roles/ansible-role-php-xdebug/ansible-role-php-xdebug.py`](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-role-php-xdebug/ansible-role-php-xdebug.py)
  (doc: [ansible-role-php-xdebug](https://reemote.org/examples/roles/ansible-role-php-xdebug/)) —
  the Ubuntu php-xdebug role with build-from-source as the **default** path:
  three deploys around a sudo `Shell` build action, `files.unarchive` with a
  `creates` gate for the tarball source (#21 closed), a versioned
  `files.copy` install of the built `.so` (#22 closed), and chained
  webserver/FPM restart handlers inherited from geerlingguy.php. Its offline
  test
  ([`test_roles_ansible_role_php_xdebug.py`](https://github.com/kimjarvis/reemote/blob/main/tests/test_roles_ansible_role_php_xdebug.py))
  monkeypatches `files._fetch_url_bytes`, seeds `archive_members` +
  `shell_results`, and bridges the built `.so` between passes.

Each role example's migration doc (coverage table, gap register, deviations)
lives at `docs/examples/roles/<role>.md` in the repo — not beside the
program — and publishes at `https://reemote.org/examples/roles/<role>/`
(e.g. [ansible-datadog](https://reemote.org/examples/roles/ansible-datadog/)).

## Offline test harness (advanced)

[`tests/simulated_host.py`](https://github.com/kimjarvis/reemote/blob/main/tests/simulated_host.py)
is the library's offline test double: structural pattern matching over
command descriptors, seeded fact seams, and a `shell_results` action-transport
seam. The repo's example tests
([`test_roles_ansible_datadog.py`](https://github.com/kimjarvis/reemote/blob/main/tests/test_roles_ansible_datadog.py),
[`test_roles_ansible_role_apache.py`](https://github.com/kimjarvis/reemote/blob/main/tests/test_roles_ansible_role_apache.py))
prove plan → apply → second apply is a no-op without any real host. Reusing
it means cloning the repo; the seeding/bridging recipe is in SKILL.md
Phase 6. Extending it for a new descriptor is part of any library
contribution (unknown descriptors must stay a hard `TypeError`).
