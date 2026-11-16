<!--
Copyright (c) 2026 Kim Jarvis.
SPDX-License-Identifier: EPL-2.0
-->

# Construct recipes — the documented shape changes

Condensed from the migration guide
([https://reemote.org/migrating/](https://reemote.org/migrating/) — the
canonical source; read the full section, especially "What to watch", before
implementing any of these). Anchors are MkDocs default slugs (underscores
are kept: `#migrating-host_vars`). Each recipe lists the runnable example to
copy from the
[examples/ tree on GitHub](https://github.com/kimjarvis/reemote/tree/main/examples).

**Recipes 1–8** condense the guide. **Recipes 9–12** cover tracked-gap
shapes: 9, 10 and 12 document shipped behavior (upstream issues #12, #11,
#14, #15 and #17 are closed); 11 is the one workaround for a still-open gap
(dnf's unconditional `latest`, the dnf half of #13), proven end-to-end by
the DataDog role migration
([examples/roles/ansible-datadog/ansible-datadog.py](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-datadog/ansible-datadog.py)).
The files gaps **#21 (`files.unarchive`) and #22 (`files.copy` remote-src
parity) are closed** and reflected in recipes 7–8, proven end-to-end by the
php-xdebug role migration
([examples/roles/ansible-role-php-xdebug/ansible-role-php-xdebug.py](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-role-php-xdebug/ansible-role-php-xdebug.py)).
Issue numbers reference
[https://github.com/kimjarvis/reemote/issues](https://github.com/kimjarvis/reemote/issues);
re-prove the absence before relying on a workaround — see
[gap-analysis.md](gap-analysis.md).

The universal principle: **a deploy cannot observe facts or its own outcomes
while running** (it executes twice; divergent sequences raise
`DeterminismError`). Every recipe moves the read into `main()` — the gap
before/between runs — freezes it, and closes a factory-built deploy over the
snapshot: **gather → snapshot → factory**.

## 1. Handlers (`notify:` + `handlers/main.yml`)

Guide: [https://reemote.org/migrating/#migrating-a-handler](https://reemote.org/migrating/#migrating-a-handler) ·
Example:
[handler_restart.py](https://github.com/kimjarvis/reemote/blob/main/examples/demonstrations/composition/handler_restart.py)

Shape: **two-deploy outcome split**.
1. Pass 1 = the notifying tasks, branch-free; give every notifying request a
   stable `name=` and collect the names into module-level `frozenset`s (one
   per handler when verbs differ, e.g. NOTIFY_RESTART / NOTIFY_RELOAD).
2. Between runs: `changed = changed_hosts(report, NOTIFYING)`.
3. Pass 2 = `restart_handler(changed, "nginx")` / `reload_handler(...)` /
   `service_handler(changed, services, action="restarted"|"reloaded"|
   "running")`; `await run(inventory, handler_deploy)`.

Watch: `restarted=True` restarts only a *running* unit and `reloaded=True`
reloads only a *running* one — both keep the operation's default
`running=True`, which **starts a stopped unit** (matches `state: restarted` /
`state: reloaded` after install). Dry preview of pass 1 cannot predict
handler firing; dry preview of pass 2 is honest.
Chained handlers (handler notifies handler) collapse to one pass-2 call
listing all services upstream-first: `restart_handler(changed, ("nginx",
"php-fpm"))`. Non-systemd handlers: hand-build a deploy closing over the
frozen set. `changed_when: false` ≈ omit the task's name from NOTIFYING.

## 2. `host_vars` / `group_vars` / role defaults

Guide: [https://reemote.org/migrating/#migrating-host_vars](https://reemote.org/migrating/#migrating-host_vars)

Shape: **the inventory entry is the vars file**. Any key beyond `host`,
`connection`, `privilege`, `group`, `tags` lands in `host.extra`
(`extra="allow"`). Read `host.extra["java_home"]` or
`host.extra.get("key", DEFAULT)` in the deploy; defaults become module-level
constants; `group_vars` becomes a module-level dict keyed by `host.group`.

Watch: lists must become `tuple(...)` before `op()`; `host.extra` is static,
so `when` guards may read it; it is an unschema'd dict — validate yourself
(e.g. a pydantic model in `main()`) where the role needs guarantees.

## 3. `include_vars` OS dispatch (`vars/RedHat.yml`, `ansible_os_family`)

Guide: [https://reemote.org/migrating/#migrating-include_vars-os-dispatch](https://reemote.org/migrating/#migrating-include_vars-os-dispatch) ·
Example:
[two_deploy_split.py](https://github.com/kimjarvis/reemote/blob/main/examples/demonstrations/composition/two_deploy_split.py)
(same shape, different fact)

Shape: gather → snapshot → factory.
1. `hosts = [Host.from_inventory(e) for e in inventory]`;
   `distro = await gather_fact(hosts, server.LinuxDistribution)`; close the
   gather's hosts yourself (`gather_fact` does not).
2. Freeze a per-host map through a module-level table keyed on
   `info["family"]` — the direct `ansible_os_family` equivalent (`RedHat`,
   `Debian`, `Suse`, `Archlinux`, `Alpine`, …; RHEL rebuilds collapse to
   `RedHat`). Values carry the package module *and* the package tuple.
3. Factory `build_install(map)` returns a deploy reading
   `map.get(host.name)`; uncovered hosts `return` early.
4. `await run(inventory, build_install(map))` — run builds fresh hosts.

Watch: key on `family`, not `name` (use `name`/`major` only for finer
splits); unknown distros fall back to `name`, missing release files →
`family=None`, both queue nothing. **Fixed single-OS target? Skip the whole
recipe** — freeze the vars as module constants (the worked example's
precedent).

## 4. Jinja2 templates (`template:`)

Guide: [https://reemote.org/migrating/#migrating-jinja2-templates](https://reemote.org/migrating/#migrating-jinja2-templates) ·
Shape example:
[two_deploy_split.py](https://github.com/kimjarvis/reemote/blob/main/examples/demonstrations/composition/two_deploy_split.py)
with a `FileExists` snapshot

There is **no `files.template`** (a render context is unhashable; a live fact
can never reach an in-deploy render). Shape: **pre-render control-side in
`main()`, between deploys**.
1. Gather any fact the template consumes (`register: cert` +
   `cert.stat.exists` → `gather_fact(hosts, files.FileExists, CERT)`).
2. Render with **your own** renderer from static inventory data + the frozen
   snapshot; freeze `{host.name: rendered_str}`. reemote ships **no** template
   engine and **no** YAML library — both are your dependency:
   - `template:` with Jinja2 syntax → `jinja2`, your own `Environment`.
   - `template:` whose body is mostly `{{ var | to_nice_yaml }}` (the common
     agent/exporter config shape) → **PyYAML**, no Jinja2 at all. Ansible's
     filter defaults are `indent=4, sort_keys=True, width=80`:
     `yaml.safe_dump(data, default_flow_style=False, allow_unicode=True,
     indent=4, sort_keys=True, width=80)`. Per-template overrides ride as
     keyword args (`checks.yaml.j2` uses `indent=2, width=160,
     sort_keys=False`); Jinja's `indent(width, True)` filter becomes a pure
     helper that prefixes every non-blank line.
   - **Declare the renderer in your program's own dependencies.** Import it
     inside the render function, not at module scope, whenever the module may
     be imported by tooling that does not declare the dependency (offline
     tests, editors' import checkers); a plain `__main__` program may import
     at module scope.
3. Factory-built deploy yields `op(files.install, content=rendered[host.name],
   dest=…, mode=…, sudo=True)`.

Watch: rendered content is a plain hashable `str` — no stream-identity rules.
If an *earlier deploy* creates what the template reads (a cert), gather
**after** that deploy's apply join. `StrictUndefined` is your renderer's
choice now; match Ansible's environment for the rest (see below). A `0640`
service-owned destination converges as-is — the read-back re-reads
unreadable files elevated (recipe 9).
The role's own `assert:`/`fail:` variable gates become plain raises in
`main()` **before** any host is contacted — and a type gate (`is mapping`)
raises `TypeError`, not `ValueError`, so the entry point's `except` tuple
must include `TypeError`.

**Reproducing Ansible's environment.** A hand-renderer — Jinja2 you configure,
or pure-Python f-strings — must match Ansible's template environment or the
bytes diverge: `trim_blocks=True` (the newline after a `{% … %}` block tag is
dropped) and trailing newlines preserved (`keep_trailing_newline=True`). A
bare `Environment()` does neither. **Single-variable native-type passthrough**
is the subtle one: a template that is exactly `"{{ var }}"` resolves to the
variable's *native type*, so an int `0` stays `0` and
`{{ x | default(500, true) }}` yields `500` (0 is falsy), not `0` — a renderer
that stringifies the substitution first gets this wrong. And mind the
**dual-use gate/render trap**: a variable that both gates a task
(`when: x | bool`) *and* renders verbatim (`opcache.enable={{ x }}`) must keep
its raw value for the render — derive a separate bool for the gate; boolifying
in place renders `True` where Ansible renders `1`. Proven by an Ubuntu PHP
role migration whose pure-Python renders were checked byte-identical to
Jinja2 under exactly these defaults.

## 5. `validate:` hooks on copy/template

Guide: [https://reemote.org/migrating/#migrating-a-validate-hook](https://reemote.org/migrating/#migrating-a-validate-hook)

Shape: `files.install(validate="nginx -t -c {spool}")` (also
`files.transform(validate=…)`, `files.download(validate=…)`). One request
yields three commands: unprivileged scp to a dest-derived `/tmp` spool →
validator on the spool (inherits the request's sudo/su/doas) → elevated
install. Fail-fast makes it atomic: a non-zero validator exit raises
`CommandError` **before** the install runs; dest keeps its old content.

Watch: validate `{spool}` (the staged bytes), not `{dest}` (still the old
file) — `{spool}` is Ansible's `%s`. Placeholders are shell-quoted; empty
template raises `ValueError`. This is a scoped hook, not a generic in-deploy
shell.

## 6. `lineinfile` / `replace` / `blockinfile` (protected-file edits)

Guide: [https://reemote.org/migrating/#migrating-a-protected-file-line-edit-lineinfile](https://reemote.org/migrating/#migrating-a-protected-file-line-edit-lineinfile) ·
Examples:
[files_transform.py](https://github.com/kimjarvis/reemote/blob/main/examples/modules/files/files_transform.py),
[files_block.py](https://github.com/kimjarvis/reemote/blob/main/examples/modules/files/files_block.py)
(the `block_transform` factory),
[files_edit.py](https://github.com/kimjarvis/reemote/blob/main/examples/modules/files/files_edit.py)

Shape: `files.transform(path=…, transform=fn, sudo=True)` — a **pure
function** `fn(current: str | None) -> str` mapping the whole current text
(None = absent) to the whole desired text; the operation reads
`FileContents`, applies the transform, and writes back via spool-and-install
only when the result differs.

| Ansible | transform body |
| --- | --- |
| `lineinfile {line}` | append the line only when not already present |
| `lineinfile {regexp, line}` | rewrite matching lines; append when none matched |
| `lineinfile {regexp, state: absent}` | drop matching lines |
| `replace {regexp, replace}` | `re.sub(regexp, replace, current)` |
| `blockinfile {block, marker}` | `block_transform` factory (files_block.py) |
| `create: yes` | free — `transform(None)` produces the creation content |
| `backup: yes` | dropped (timestamped cp is non-deterministic) |

Three laws: **pure** (no IO/clock/random/globals), **fixpoint**
(`fn(fn(x)) == fn(x)` — check before adding), **stable object** (module-level
function or a factory called ONCE outside the generator; never a lambda or
per-yield closure). Body shape: `lines = (current or "").splitlines()` → edit
only owned lines → `"\n".join(lines) + "\n"` (restore trailing newline).

Watch: `files.edit` is the same contract but writes via *unprivileged* scp —
login-writable targets only; `/etc` needs `files.transform`. Idempotence is
content-only (mode/owner drift → `files.file`). A login-unreadable target
(0640) is re-read elevated, so it converges too (recipe 9).
`/etc/hosts` has its own operation: `server.etc_hosts`.

## 7. `get_url` (URL downloads)

Guide: [https://reemote.org/migrating/#migrating-a-url-download-get_url](https://reemote.org/migrating/#migrating-a-url-download-get_url) ·
Example:
[files_download.py](https://github.com/kimjarvis/reemote/blob/main/examples/modules/files/files_download.py)

Shape: `files.download(url=…, dest=…, mode=…, checksum="sha256:<hex>",
sudo=True)`. The fetch is **control-side** (opposite of Ansible's on-target
fetch): works when only the controller has egress; the body is fetched once
per phase (twice per host) — **pin `checksum` in production** so both phases
install identical bytes. Text only (UTF-8); delegates to `files.install`
(content-only idempotence, spool, owner/mode, validate).

Watch: binary bodies (`.rpm`, tarballs) raise `ValueError` — fetch
control-side into `io.BytesIO` and `files.put` to a login-writable path, or
use `dnf.rpm`/`apt.deb`. A tarball **to extract** is
`files.unarchive(src=<url>, dest=…, creates=…)` — the binary fetch, spool
and extraction are all in-operation (#21 closed). `http(s)` only. `rpm_key`
import is a **separate**
`dnf.key(src=io.BytesIO(key_bytes))` request — it takes key *content*, never
the downloaded path (and its import direction is non-idempotent; rpm
dedupes). `dnf.repo`/`apt.deb`/`dnf.rpm` reject URL `src` by design.
A role that imports *several* keys into one shared `signed-by` keyring
needs **recipe 10** — per-key `gpg.import_key(dest=…, keyid=…)`.

## 8. Build-from-source roles (`git:` + `command:`/`shell:` compile)

Guide: [https://reemote.org/migrating/#migrating-a-build-from-source-role](https://reemote.org/migrating/#migrating-a-build-from-source-role) ·
Example:
[deploy_action_deploy.py](https://github.com/kimjarvis/reemote/blob/main/examples/actions/deploy_action_deploy.py)

Shape: **split declarative from imperative** — deploy → gather → action →
deploy, sequenced in `main()`:
1. Deploy 1: `git.repo(src=…, dest=…, branch=…)` — or a tarball source via
   `files.unarchive(src=<url>, dest=…, creates=…)` (#21 closed: the
   `creates` gate is in-operation, so a converged tree fetches nothing) —
   plus config not depending on the binary and any `files.directory` the
   install step needs. Opt-in flag is static `host.extra` → `when` guard is
   legal.
2. Gather built state *after* deploy 1's apply join (a fact, or a `Shell`
   probe whose `Result` you freeze) — the `creates:`/`stat:` idempotence.
3. `await gather_action(hosts, Shell, command="cd … && ./configure … && make
   && make install", sudo=True)` — outside any deploy; filter hosts first
   (or `group=`/`tags=`). Long builds: stage a script in deploy 1, run
   `Script`. Check `result["exit_status"]` yourself and raise — an action
   interprets nothing (`failed_when` is your code).
4. Deploy 2: `files.link` + config referencing the built binary. When the
   role installs the artifact under a new name instead of `make install`
   (Ansible `copy: {remote_src: true, mode, owner}`), yield
   `files.copy(src=<built binary>, dest=<versioned target>, mode=…,
   user=…, group=…, overwrite=True, sudo=True)` — full remote-src parity
   (#22 closed).

Watch: `op(Shell, …)` is refused; `gather_action` inside a deploy raises
`ActionInDeployError`. `gather_action` closes its own hosts (do not aclose
after). Keep clone/symlink/config in deploys — only the compile is an action.
`files.copy` validates `src` in **both** phases, so the install must follow
the build barrier — never share deploy 1 with the build; its rename `dest`
parent must already exist (`files.directory` in deploy 1), and
`overwrite=True` is sha1-gated, so a converged install no-ops. Proven
end-to-end by the php-xdebug migration
([ansible-role-php-xdebug.py](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-role-php-xdebug/ansible-role-php-xdebug.py)).

## 9. Service-owned `0640` config — the read-back is elevated

Not in the guide. Shipped behavior (upstream issue **#12 — closed**) ·
Example:
[ansible-datadog.py](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-datadog/ansible-datadog.py)
(`build_configure`)

`files.install` / `transform` / `download` decide idempotence by reading the
destination back with `files.FileContents`. The read is **two-tier**: the
first `cat` rides unprivileged; when the login user cannot read the file
(a `0640` — or `0600` — config owned by a service account) the command
prints an `UNREADABLE` marker instead of content, and `process` re-reads it
**elevated** with `sudo` (run-as user and password from the inventory
`privilege` data). Content idempotence therefore holds for restrictive
modes: a converged `0640` file is a no-op, and its handler stays quiet.

Shape: **write the file directly — no workaround deploy.**
1. `op(files.install, content=…, dest=…, mode="0640", user="svc",
   group="svc", sudo=True)` (or `files.transform` / `files.download`).
2. Nothing else: no group membership, no earlier-run ordering constraint,
   no login-readable requirement.

Watch:
- Idempotence is still **content-only**: mode/owner drift converges through
  a paired `files.file`, not a re-install.
- The elevated re-read needs the inventory `privilege` section to actually
  elevate; a login user with no sudo path cannot read the file back.
- Offline, `SimulatedHost.login_can_read(path)` models readability from the
  `file_stats` mode plus `os_users` groups — seed both to exercise the
  fallback in a test (see the repo's offline harness).
- **Older releases**: before the elevated read-back shipped, the read came
  back empty and every run re-installed the file *and* fired its handler; the
  era's workaround (adding the login user to the owning group with
  `server.user(groups=…, append=True)` in an earlier run) is retired — do
  not reproduce it in new migrations. Re-prove the two-tier read against your
  installed version ([gap-analysis.md](gap-analysis.md)).

## 10. Several signing keys into one shared keyring

Not in the guide. Shipped behavior (upstream issue **#11 — closed**) ·
Example:
[ansible-datadog.py](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-datadog/ansible-datadog.py)
(`fetch_keys`, `build_repository`);
[gpg_import_key.py](https://github.com/kimjarvis/reemote/blob/main/examples/modules/gpg/gpg_import_key.py)

Ansible: `get_url` each key, then `apt_key` / `gpg --no-default-keyring
--keyring /usr/share/keyrings/vendor.gpg --import`, one task per key.
`gpg.import_key(src, keyid=…, dest=…)` reproduces this **directly**:
`dest` names the keyring file and the import is **additive** — the keys
already in the file stay.

Shape: **one import request per key, fingerprint-pinned.**
1. In `main()`: fetch each key's bytes control-side (`files.download` is
   text-only — for armored/binary key bodies use plain
   `urllib.request.urlopen(url, timeout=…).read()`), keeping the bodies
   **separate**, one per key.
2. Freeze the per-host `io.BytesIO` streams **in the factory body, outside
   the inner generator**: a stream is hashable but compared by *identity*,
   so a fresh stream per phase trips `DeterminismError`. `Host.upload_file`
   rewinds before each transfer, so one stream serves the dry run and the
   real run.
3. One request per key: `op(gpg.import_key, src=stream, dest=KEYRING,
   keyid=FINGERPRINT, sudo=True)`. `dest` scopes the import to that one
   keyring (`--no-default-keyring --keyring`), creates its parent directory
   and chmods the file `0644`; `keyid` makes it idempotent against the
   `GpgKeyrings` entry whose path is `dest` — a repeat import is a no-op.

Watch / deviations:
- `secret=True` cannot combine with `dest` (`ValueError`): gpg keeps secret
  material in `GNUPGHOME`, never in an explicit keyring file. An empty
  `dest` and a `str` `src` also raise `ValueError`.
- Without `keyid` the import **always runs and reports changed** — the
  stream's fingerprint is unknown controller-side. Pin every key the role
  pins; an unpinned key rotates invisibly until the keyring file is removed,
  so pinning it is a deliberate, documented deviation (the DataDog example
  pins it).
- Additive means an operator-added key **survives** — unlike `gpg.key`,
  which installs a keyring file wholesale and drops anything not in `src`.
- One failed URL fails only that key's fetch; Ansible's per-key tasks fail
  independently too.
- Offline, the repo's `SimulatedHost.import_gpg_key` seam appends the spool
  bytes to the keyring and accumulates a **content-hash stub** fingerprint —
  not the real key's. Seed the real fingerprints into `gpg_keyrings` (or
  import once and re-pin to the stubs) or pass 2 re-imports.

## 11. `state: latest` that converges

Not in the guide. apt half of upstream issue **#13 — closed**; the dnf half
is still open ·
Example:
[ansible-datadog.py](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-datadog/ansible-datadog.py)
(`deploy_agent`, no snapshot)

`apt.packages(latest=True)` is fact-gated: the operation reads
`AptUpgradable` itself and upgrades only installed, unpinned names with a
pending upgrade, naming each `pkg -> candidate` jump in the reason. A
converged host is a no-op, so pass `latest=True` directly — no gather, no
snapshot, no barrier. The DataDog example's `deploy_agent` does exactly
that.

`dnf.packages(latest=True)` still upgrades every installed, unpinned
package it is given **without checking whether an upgrade exists** — the
`to_upgrade` set is `installed ∧ unpinned`, so a fully converged host still
reports `changed=True` and re-runs the upgrade. Ansible's `state=latest`
is a no-op when the candidate equals the installed version. dnf ships no
upgradable fact (no `DnfUpgradable`, no `check-update` anywhere in the
module), so the gate must be built outside the deploy.

Shape for dnf: **gather → snapshot → factory**.
1. `gather_action(targets, Shell, command="dnf check-update")` outside the
   deploy — read `Result` yourself; a non-zero exit (100) means upgrades
   are pending. Freeze the pending names per host.
2. `op(dnf.packages, packages=(pkg,), latest=pkg in pending, …)` — the
   *flag* is the branch, so both phases yield the identical request
   sequence.

Watch:
- `latest=False` is a plain presence check, so an absent package is still
  installed on the first pass.
- Once the upgrade lands, the next pass reads an empty pending set and the
  request converges. This is what makes the second-pass no-op assertion hold.
- The dnf decision is frozen from **pre-state**: a package that becomes
  upgradable mid-run waits for the next run. Record it as a deviation.
  (apt has no such freeze — the fact is read in-operation.)
- `cache_valid_time` **is** supported on `apt.packages(update=True, …)` and
  on `apt.update` (the `AptUpdateStamp` fact). `apt.repo`/`key`/`ppa`/
  `sources_file` take `update_cache` too — recipe 12a.

## 12. `apt_repository` / `deb822_repository`: cache, removal, signing key

Not in the guide. All three shipped: `update_cache` (**#14 — closed**),
global removal (**#15 — closed**), deb822 `signed_by` URL (**#17 — closed**) ·
Example:
[ansible-datadog.py](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-datadog/ansible-datadog.py)
(`repo_entry`, `build_repository`); 12c:
[ansible-role-docker.py](https://github.com/kimjarvis/reemote/blob/main/examples/roles/ansible-role-docker/ansible-role-docker.py)
(`build_setup`)

**(a) `update_cache: yes` (#14 — closed).** `apt.repo`, `apt.sources_file`,
`apt.key` and `apt.ppa` take `update_cache=True` (and `cache_valid_time`
for Ansible spelling parity). On a real sources change the operation yields
`AptUpdateCommand` *after* the install, so the very next `apt.packages` sees
the new repo's packages; a no-op yields nothing. Pass `update_cache=True`
directly — no gather, no snapshot, no separate `apt.update`. The DataDog
example's `build_repository` does exactly that.

Watch: `cache_valid_time` is **inert** on these four operations. The refresh
only fires on a real change, and a change must force the refresh even when
the stamp is fresh (a fresh index predates the repo just added), so the
window can never suppress it — it is accepted for spelling parity, not
consulted. (`dnf.repo` has no refresh parameter: there the answer is a
separate scoped `dnf.makecache(repos=…)` request.)

**(b) `state: absent` wherever the line lives (#15 — closed).** `apt.repo(
present=False)` with the default `filename=None` removes the line *wherever
it is configured* — Ansible `apt_repository state=absent` parity, directly.
`AptSources` entries carry the sources file each entry was read from as
`filename` provenance; presence comparisons ignore it, and every provenance
file whose text the removal actually changes gets its own upload+install
pair. Pass it directly — no gather, no snapshot, no fan-out.

Watch:
- A `filename` scopes the removal to that one file — pass it only when the
  role really targets one file; the default is global.
- Idempotence is fact-resolved: a line configured nowhere is a no-op, so a
  converged host is a no-op.
- Only line-based files (`.list`/`sources.list`) are editable this way; a
  match that lives solely in a deb822 `.sources` stanza is left untouched
  and named in the no-op reason — record it as a deviation if the role's
  line lives in a `.sources` file.
- **Retired workaround**: before #15 the parser dropped the provenance and
  `apt.repo(present=False)` edited only the file `filename` named; the era's
  recipe recovered provenance with one `FindInFiles` content grep
  (`grep -rlE` over `/etc/apt`) and fanned out per file. Re-prove against
  your installed version ([gap-analysis.md](gap-analysis.md)).

**(c) `deb822_repository` `signed_by` from a URL (#17 — closed).**
`apt.sources_file(signed_by=…)` accepts an existing keyring path **or an
`http(s)` key URL** — Ansible's `deb822_repository` URL form, directly. A URL
is fetched control-side (the apt namespace's own `_fetch_url_bytes` seam,
which the offline test monkeypatches) and installed as the repo-named keyring
`/etc/apt/keyrings/<filename>.asc` (mode `0644`, content-idempotent) through
the same spool-and-install pair; `Signed-By:` is rewritten to that path. Pass
the URL directly — no `files.download`, no separate key request. The Docker
example's `build_setup` does exactly that.

Watch:
- Only ASCII-armored text is accepted: a binary `.gpg` body raises
  `ValueError` (fetch it control-side, install with `apt.key`, pass the
  keyring path instead).
- The key-content gate and the repository-identity gate are independent —
  either alone triggers a write; a converged host is a no-op.
- `present=False` removes the sources file **and** the managed
  `<filename>.asc`/`.gpg` keyrings, each existence-gated, without fetching.
- `update_cache=True` chains `AptUpdateCommand` only on a real change
  (recipe 12a).
- **Retired workaround**: before #17 the URL form was unsupported, so the
  recipe landed the key with
  `files.download(dest=/etc/apt/keyrings/<name>.asc)` first and owned its
  removal by hand. Re-prove against your installed version
  ([gap-analysis.md](gap-analysis.md)).

## General construct map (no dedicated guide section)

| Ansible construct | reemote shape |
| --- | --- |
| `template` | pre-render in `main()` + `files.install` (recipe 4); jinja2 **or PyYAML** is your dependency |
| `to_nice_yaml` filter | `yaml.safe_dump(..., default_flow_style=False, allow_unicode=True, indent=4, sort_keys=True, width=80)` (recipe 4) |
| `file mode=0640 owner=svc` | `files.install`/`transform` directly — the two-tier elevated read-back keeps content idempotence (recipe 9) |
| `unarchive` (extract) | `files.unarchive(src, dest, creates=…, checksum=…)` — URL fetched binary control-side, `creates` gated in-operation (#21 closed, recipes 7–8) |
| `copy remote_src=yes` (rename/mode) | `files.copy(src, dest, overwrite=True, mode=…, user=…, group=…)` — sha1-gated remote-to-remote parity (#22 closed, recipe 8) |
| `apt state=latest` / `yum state=latest` | apt: `latest=True` directly (fact-gated, #13); dnf: recipe 11 — gate `latest=` on a check-update snapshot; the bare keyword always reports changed |
| `apt_repository update_cache=yes` | `apt.repo(update_cache=True)` — the refresh rides the op on a real change (#14, recipe 12a) |
| `apt_repository state=absent` (global) | `apt.repo(present=False)` directly — the default `filename=None` removes the line wherever it is configured (#15 closed, recipe 12b) |
| `deb822_repository` | `apt.sources_file` (deb822); a URL `signed_by` is fetched + installed in-operation (#17 closed, recipe 12c) |
| `apt_key` loop into one `signed-by` keyring | per-key `gpg.import_key(dest=…, keyid=…)` — additive, fingerprint-idempotent (recipe 10) |
| `become: yes` | `sudo=True` on `op()` (run-as user/password from inventory `privilege`) |
| `become_user: other` | no per-request override — inventory `privilege.sudo_user` only; a different user needs a separate inventory entry/host or a gap note |
| `loop` / `with_items` (scalars) | Python `for` in the deploy over a frozen tuple, one `op()` per item |
| `with_items` (list of dicts) | flatten control-side to tuples of scalars (e.g. `(dest, content)` per vhost), one `op()` per item — dicts are unhashable |
| `register: r` + `when: r.changed` | two-deploy split: `changed_hosts(report, {name})` between runs |
| `register: r` + `when: r.stdout …` | `gather_fact`/`gather_action(Shell)` snapshot in `main()`, factory deploy |
| `set_fact` | a frozen snapshot dict in `main()` (never mutable state in a deploy) |
| `when:` on static vars | `when=` module-level predicate reading `host.group`/`tags`/`extra`, or a plain `if` in the deploy (static only) |
| block-level `when:`/`become:` | `sub_deploy(when=…, sudo=…)` |
| `include_tasks` / `import_tasks` / roles | separate deploy functions + `compose(...)` / `yield from` |
| role ordering / dependencies | `compose` argument order (repos before packages, users before owned files) |
| `tags:` / `--tags` | inventory `tags` + `when` guards / `gather_action(tags=…)`; or run a subset compose in `main()` |
| group targeting (`hosts: webservers`) | inventory `group` + `when` guard, or filter the inventory list in `main()` |
| `serial: 1` (rolling batches) | no first-class analogue — slice the inventory in `main()` and `await run(batch, …)` per batch |
| `forks` (parallelism) | free — the runtime is concurrent across hosts |
| `--check` / check mode | `run(..., dry=True)` + inspect `plans` |
| `--diff` | `format_plan` / `format_log` (commands and reasons, not file diffs) |
| `changed_when: false` | omit the name from NOTIFYING (report still records changed); no per-request suppression flag |
| `failed_when` / `ignore_errors` | deploys are fail-fast (`CommandError` aborts); for actions, interpret `Result` yourself; catch library errors in `main()` if the role tolerates them |
| `environment:` (task env) | actions: `Shell(env=…)`/`Script(env=…)`; operations have no env parameter — bake values into content/args or note a gap |
| `reboot` + wait | `gather_action(Shell, command="reboot")` then `gather_action(WaitForConnection, timeout=…)` then next deploy |
| `wait_for: port=…` | `server.wait(port=…, timeout=…)` (in-deploy, polls the Port fact) |
| `wait_for_connection` | `WaitForConnection` action |
| `pause` / `wait_for: timeout` | `await asyncio.sleep(...)` in `main()` between runs |
| `assert` | plain Python `assert`/raise in `main()` on snapshots or reports |
| `debug: var=…` | print gathered snapshots / `format_plan` / `format_log` |
| `fetch` (remote→control) | `files.get(src=…, dest=<per-host IO sink>)` |
| `stat` + registered fields | `files.File` / `FileExists` / hash facts via `gather_fact` |
| `uri` (HTTP calls) | no operation — control-side `urllib`/`httpx` in `main()`; on-target HTTP needs a Shell action or a gap note |
| `cron` | no module — `files.install` a `/etc/cron.d` drop-in (content-idempotent) or note a gap |
| `block`/`rescue`/`always` | no analogue — try/except around `await run(...)` in `main()`; rescue logic is your code |
| vault-encrypted vars | decrypt control-side before building inventory/constants; never commit secrets |
