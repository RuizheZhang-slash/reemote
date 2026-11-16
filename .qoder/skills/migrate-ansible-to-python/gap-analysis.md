<!--
Copyright (c) 2026 Kim Jarvis.
SPDX-License-Identifier: EPL-2.0
-->

# Gap analysis — proving, classifying and resolving unmapped tasks

Phase 2 marks rows **GAP**; Phase 3 (this file) turns each mark into a
*proven, classified, ranked* finding with a chosen resolution. The two
failure modes to avoid: silently dropping a task, and reporting a gap the
library actually covers. Both have happened in real audits — the
historically-closed list below is the record of the second one.

## Coverage-table discipline

The Phase 2 table is the contract with the user: nothing in the role is
invisible.

- One row per Ansible task; split compound tasks (`get_url` + `rpm_key` =
  two rows: `files.download` + `dnf.key`).
- Non-task rows too: defaults/vars precedence, handler fan-in, loops,
  `become`, tags, `serial`, check-mode expectations, opt-in branches.
- Status vocabulary is fixed: **covered** / **recipe** / **workaround** /
  **GAP**. A `workaround` row must name the deviation in its Notes; a `GAP`
  row must carry the absence proof below before Phase 3 ends.
- Evidence column: the docs page (`https://reemote.org/modules/<mod>/`) or
  the source file on GitHub proving the mapping's *signature* (parameter
  names and defaults are reemote's, not Ansible's) **and its `changed`
  predicate** — see "Proving coverage" below.

## Proving absence — before writing GAP

A zero-match search alone is **not** evidence: reemote names hide behind
unexpected words (`server.etc_hosts`, `files.flags`, `FindInFiles`,
`service_handler(action="reloaded")` were all misreported as missing by
name-only searches). Protocol — everything here works without a local
checkout:

1. **Name the owning namespace** from the task's domain (cron → `server`;
   uri/waits → `server`; archives → `files`; no obvious owner → check all 20
   modules via [https://reemote.org/modules/](https://reemote.org/modules/)).
2. **Enumerate the full surface**: the member list on the module's docs page,
   `__all__` in the module source
   (`https://github.com/kimjarvis/reemote/blob/main/src/reemote/modules/<mod>/<mod>.py`),
   and the package-root exports in
   [`src/reemote/__init__.py`](https://github.com/kimjarvis/reemote/blob/main/src/reemote/__init__.py).
   Read operations **and facts and descriptors** — a fact plus a transform
   often composes the "missing" operation. Fastest route, no clone: ask the
   *installed* package
   (`python -c "import reemote.modules.apt as m; print(sorted(m.__all__))"`).
3. **Check sibling names** for the capability under a different word
   (hosts-file edits → `server.etc_hosts`; `find contains=` → `FindInFiles`;
   chattr attributes → `files.flags`; reload handlers → `reload_handler`).
4. **Corroborate with greps** across
   [`src/reemote/modules/`](https://github.com/kimjarvis/reemote/tree/main/src/reemote/modules):
   GitHub code search
   (`https://github.com/search?q=repo%3Akimjarvis%2Freemote+<pattern>&type=code`)
   or a shallow clone
   (`git clone --depth 1 https://github.com/kimjarvis/reemote.git` into a
   scratch directory, then grep locally). Search the operation name,
   plausible class names, and the shell strings an implementation would
   contain (`crontab`, `rsync`, `tar -x`, `pip install`, `setfacl`,
   `setfattr`, `update-alternatives`, `ssh-keyscan`). Zero matches
   everywhere = absence corroborated.
5. **Record the evidence** in the gap entry: which surfaces were
   enumerated, which patterns were grepped, and against which reemote
   version. Re-prove at report time — this library evolves and gaps close.

Tooling note: treat an empty search result as suspect, never as proof —
corroborate absence with a second independent method (docs page vs source
vs installed-package introspection) before writing GAP.

## Proving coverage — the signature is not the semantics

The mirror image of the absence proof, and the failure mode that produced
upstream issue #13: **a keyword existing does not mean the Ansible behavior
exists.** Before marking a row `covered`, read the operation's `changed`
predicate and its command-selection branch, not just its signature.

- `apt.packages(latest=True)` took the keyword but upgraded *every*
  installed, unpinned package **without checking whether an upgrade
  exists** — issue #13, now closed: the operation reads `AptUpgradable`
  itself. `dnf.packages(latest=True)` still has that shape (no upgradable
  fact ships) — recipe 11 in
  [construct-recipes.md](construct-recipes.md). Ansible's `state=latest`
  is idempotent, so an unconditional upgrade is a gap even when the
  signature matches.
- Stateless operations (`restarted`, `reloaded`, `daemon_reload`,
  `apt.update` with `cache_valid_time=0`) always report `changed=True`. In a
  converged deploy they break the no-op second pass and fire every handler
  on every run.
- Content writes are idempotent on **content only** (mode/owner drift →
  `files.file`). The read-back is two-tier: `FileContents` cats
  unprivileged first and re-reads elevated with `sudo` when the login user
  cannot read, so a `0640` service-owned file converges too (recipe 9).
- A `**kwargs`-absorbing operation swallows an unknown Ansible keyword
  silently: `apt.repo` absorbed `update_cache=` and did nothing until #14
  added it as a real parameter — the spelling looked plausible and was
  inert. Search the parameter name in the owning module — zero matches means
  the spelling is absent, however plausible it looks.

Rule: for every `covered` row, be able to name the fact the operation
compares against and what makes it report *no* change. If you cannot, the
row is `workaround` or `GAP`, not `covered`.

## Classification

Every proven gap gets exactly one class:

| Class | Meaning | Examples | Action |
| --- | --- | --- | --- |
| **Deliberate boundary** | the library refuses by design; docs/article say so | URL/filename `src` on key/deb/rpm ops; no `files.template`; no shell inside deploys; no per-request `become_user`; transfers never elevate; `backup:` dropped as non-deterministic | reshape per the recipe; **never propose eroding it** |
| **Workaroundable** | composable from existing primitives, with a deviation | cron → `/etc/cron.d` drop-in; assemble → concat + install; serial → batch slicing; reboot → Shell + WaitForConnection; uri → control-side HTTP | implement the workaround, record the deviation |
| **Genuine library gap** | no faithful composition exists | pip, unarchive, acl, docker_* management | rank it; propose an extension (user-approved workstream) |
| **Out of scope** | the target platform/OS is unshipped | pacman/zypper/pkgng (Arch/SUSE/BSD), Windows | a Phase 0 scope decision, not a library bug |

Classification can move after proof: "no cron module" looks genuine until
the cron.d drop-in composition is recognized → workaroundable. Boundary
vs gap is the critical distinction: boundaries are documented design
("What Reemote is not" in the [thesis article](https://reemote.org/articles/migrating/)),
gaps are absences.

## Verified open gaps (snapshot — re-prove before reporting)

Proven against the source at the time of writing, per the protocol above.
Update this table when a gap closes; never copy it into a report unverified;
re-prove against the version you installed.

| Domain | Missing | Class | Stopgap / resolution |
| --- | --- | --- | --- |
| Packages | `pip` | genuine | install `python3-pip` via the package module + `Shell` action; or extend the library |
| Packages | `npm` / `yarn` / `gem` / `composer` | genuine | `Shell` actions; or extend |
| Packages | `pacman` / `zypper` / `pkgng` / `openbsd_pkg` | out of scope | no Arch/SUSE/BSD modules — fix the target OS in Phase 0 |
| Packages | dnf `state=latest` **idempotence** | genuine (workaroundable) | the keyword exists but upgrades without checking for a pending upgrade, and no upgradable fact ships — gate `latest` on a `Shell(command="dnf check-update")` snapshot (recipe 11). apt's equivalent was closed by #13 |
| Files | `unarchive` / `archive` | genuine | extract control-side + `files.put` per file, or a `Shell` tar action outside deploys |
| Files | `synchronize` (rsync) | genuine | per-file `files.put`, or a `Shell` rsync action |
| Files | `patch` | workaroundable | a pure `files.transform`, or a `Shell` action |
| Files | `acl` (setfacl) | genuine | no ACL primitive; `Shell` action stopgap |
| Files | `xattr` (setfattr) | genuine | `files.flags` is chattr, **not** xattr; `Shell` stopgap |
| Services | `cron` / `at` | workaroundable (cron) | `files.install` a `/etc/cron.d` drop-in (content-idempotent); `at` → `Shell` |
| System | `known_hosts` | workaroundable | `files.transform` the file, or `Shell` ssh-keyscan |
| System | `alternatives` | genuine | `Shell` update-alternatives action |
| System | `debconf` | genuine | `Shell` debconf-set-selections action |
| Network | `uri` | workaroundable | control-side HTTP in `main()`; on-target HTTP → `Shell` action |
| Network | `expect` | genuine | no interactive-command primitive |
| Network | generic `wait_for path=` / arbitrary conditions | workaroundable | poll a fact in `main()` between runs; only port/service waits are in-deploy (`server.wait`, `server.wait_service`) |
| Containers | `docker_container` / `docker_image` / `docker_*` | genuine | the docker **connector** drives a container as a host — it is not a management module |
| Meta | `serial` rolling batches | workaroundable | slice the inventory in `main()`, `await run(batch, …)` per batch |
| Meta | `environment:` on operations | workaroundable | actions have `env=`; operations have no env parameter — bake values into content/args |

## Historically closed — do not re-report

Each of these was reported missing by an earlier audit and **now exists**
(verified in source). If your mapping instinct says "gap", check here first:

| Once reported missing | Now exists |
| --- | --- |
| task `environment:` on command/shell | `Shell(env=…)` / `Script(env=…)` |
| copy/template `validate:` | `files.install` / `transform` / `download` `validate="cmd {spool}"` |
| service *reload* handlers | `reload_handler`, `service_handler(action="reloaded")` |
| `ansible_os_family` dispatch | `server.LinuxDistribution` — `family` key |
| text `get_url` | `files.download` (control-side fetch, checksum-pin) |
| yum version pins / enablerepo / disablerepo / update_cache | `dnf.packages` `pkg=version`, `allow_downgrade`, `repos`, `disable_repos`, `update_cache` |
| apt `default_release` / `install_recommends=no` | `apt.packages(default_release=…, no_recommends=…)` |
| apt `cache_valid_time` / "no cache-age fact" | the `AptUpdateStamp` fact (mtime of `/var/lib/apt/periodic/update-success-stamp`); **both** `apt.update(cache_valid_time=N)` and `apt.packages(update=True, cache_valid_time=N)` gate on it and report no change inside the window. Only the baseline's `cache_time` alias is still absorbed by `**kwargs` |
| apt `state=latest` idempotence (#13) | `apt.packages(latest=True)` reads `AptUpgradable` in-operation and upgrades only installed, unpinned names with a pending upgrade — a converged host is a no-op. dnf's `latest` is still unconditional |
| apt `update_cache` on `repo`/`key`/`sources_file`/`ppa` (#14) | all four take `update_cache=True` and yield `AptUpdateCommand` **after** a real sources change (nothing on a no-op); `cache_valid_time` is accepted for Ansible spelling parity but inert — a change always forces the refresh |
| apt repo removal beyond one file (#15) | `apt.repo(src, present=False)` with the default `filename=None` removes the line *wherever it is configured*: `AptSources` entries carry their sources file as `filename` provenance and every matching file gets its own upload+install pair; a `filename` scopes the removal to one file. Only line-based files (`.list`/`sources.list`) are editable — a match living solely in a deb822 `.sources` stanza stays untouched and is named in the no-op reason. Recipe 12b's `FindInFiles` provenance fan-out is retired |
| deb822 `signed_by` key URL (#17) | `apt.sources_file(signed_by=<http(s) URL>)` fetches the ASCII-armored key control-side (the apt namespace's own `_fetch_url_bytes`) and installs `/etc/apt/keyrings/<filename>.asc` (mode `0644`, content-idempotent) itself, rewriting `Signed-By:` to that path; armored-only (a binary body raises `ValueError`); `present=False` removes the sources + `.asc`/`.gpg` keyrings without fetching; `update_cache=True` chains on a real change. The `files.download` pre-fetch workaround is retired (recipe 12c) |
| elevated read-back for `0640` targets (#12) | `FileContents` is two-tier: the unprivileged `cat` prints an `UNREADABLE` marker when the login user cannot read, and `process` re-reads elevated (run-as/password from inventory `privilege`). `files.install`/`transform`/`download` content idempotence holds for restrictive modes |
| `gpg.import_key` into a named keyring (#11) | `gpg.import_key(src, keyid=…, dest=…)` imports **additively** into one keyring file (`--no-default-keyring --keyring`, parent created, chmod `0644`); `keyid` idempotence reads the `GpgKeyrings` entry scoped to `dest`. `secret=True` + `dest` raises `ValueError` |
| offline `Shell`/`Script` gathers (#16) | `SimulatedHost` overrides `_run_shell`: `gather_action`'s `Shell`/`Script` fan-out answers from the seeded `shell_results` map (exact shell string → a `Result` record; unseeded → hard `UnseededShellResult`) and records every shell in `ran_shells` |
| simulated removals leaving stale content (#18) | `SimulatedHost.remove_file`/`remove_link` pop `remote_files` first (mirroring `remove_tree`), so `FileContents`/`RemoteFileSha1` stop answering for a removed path and an equal-content `files.install` after a removal still installs; removal assertions can read `remote_files` directly. Proven in `tests/test_simulated_host.py`; the nginx migration's second pass retired its `file_stats`-only workaround |
| `find contains=` | `FindInFiles` / `FindInFile` facts |
| /etc/hosts line edits | `server.etc_hosts` operation |

`state=latest` sat on this list until the DataDog migration proved the
keyword non-idempotent (#13); apt's is now fixed in-operation and back on
this list, while dnf's remains an **open** gap above. A closed *signature*
is not a closed *behavior* — re-read the `changed` predicate even for rows
on this table.

## Ranking

- **Core-blocking**: the role's central purpose cannot be expressed
  (a container role whose every task is `docker_container`; a Python-app
  role built on `pip`). The migration cannot proceed faithfully without a
  decision — surface it to the user **before** implementing anything.
- **Feature-only**: auxiliary or opt-in tasks (a cron log-rotation, an
  optional build-from-source branch). Never blocks the default-path
  migration; workaround + deviation note, or descope with approval.

Rank by the role's purpose, not by the gap count. Present core-blocking
gaps first, each with options and a recommendation.

## Resolution paths

1. **Workaround first** (default): compose existing primitives, record the
   deviation in the coverage table and the final report. Most
   "gaps" in real roles resolve here.
2. **Library extension** — a separate, user-approved workstream (Phase 0
   deliverable decision), contributed upstream: fork
   [github.com/kimjarvis/reemote](https://github.com/kimjarvis/reemote)
   (branch `main`) and open a pull request. Discuss the design in an
   upstream issue first. A contribution touches, end to end: the typed
   command descriptor(s) in `commands.py`, the operation/fact in its module,
   `__all__` and the package-root exports, a `SimulatedHost` seam and pytest
   coverage in `tests/`, the docs module page, and a runnable example under
   `examples/` — the repo's own examples and their tests are the model to
   copy.
3. **AskUserQuestion** when the choice is a scope/design conflict
   (workaround vs extension vs descope; which target OS). Never silently
   pick, never silently drop.
4. **Check the upstream tracker** before claiming novelty:
   [https://github.com/kimjarvis/reemote/issues](https://github.com/kimjarvis/reemote/issues)
   may already track the gap (or a stale issue may claim it wrongly — see
   below).

## Reporting gaps upstream

One issue per gap, not one per role. Offer this when the user asks for it,
or when a genuine gap will outlive the migration. Create the issues through
the GitHub web UI or `gh issue create` if the environment has it; otherwise
hand the prepared title and body to the user.

1. **Check existing issues first.** A stale one may claim the gap wrongly —
   e.g. an issue claiming apt `cache_valid_time` was dropped, which the
   source disproves (the `AptUpdateStamp` fact implements it). Comment with
   the disproving evidence and recommend closing; do not close someone
   else's issue unasked.
2. **Title**: `<module>: <one-line absence>` (e.g. `files: no ACL/setfacl
   operation`).
3. **Body structure**: the Ansible construct and the role task that needs it
   → the absence proof (enumerated surface, search patterns, reemote version)
   → classification and rank → the workaround used and its deviation → the
   proposed fix with an in-repo precedent → acceptance criteria → what
   disappears from the program on the second pass.
4. **Cite repo-relative paths with line ranges** (`src/reemote/modules/apt/apt.py`,
   lines 400–450), never local `file:///` links — those do not render on
   GitHub.
5. **Back-fill the issue number into the deliverable**: every `GAP-n`
   comment and the module docstring's gap list carry `(#N)`. A workaround
   with no ticket number is invisible to the next reader.

## Report templates

Gap entry (Phase 3 artifact, reused in the Phase 7 report):

```
### GAP-<n>: <Ansible module/construct> — <one-line summary>
- Task(s): <file:line or task name>
- Evidence: enumerated <module(s)> (docs members + __all__ + root exports);
  searches: <patterns> → 0 matches; reemote version <x.y.z>
- Class: deliberate boundary | workaroundable | genuine gap | out of scope
- Impact: core-blocking | feature-only — <what the role loses>
- Options: 1) <workaround + deviation>  2) <extension sketch>
- Resolution: <chosen option + who approved it>
- Upstream issue: <#N with URL> — filed, or "not tracked: <boundary /
  scoped out / user declined>"
```

Audit summary (the Phase 7 deliverable when the scope is audit-only):

```
# Migration audit: <role name>
## Verdict
<one paragraph: feasible as-is / feasible with workarounds / blocked — why>
## Coverage
<counts: N covered, N recipe, N workaround, N GAP> + the full table
## Gaps (ranked, core-blocking first)
<gap entries>
## Deviations
<every workaround: Ansible behavior vs reemote behavior, one line each>
## Next actions
<implement the program / propose a library improvement / descope — offer, don't start>
```
