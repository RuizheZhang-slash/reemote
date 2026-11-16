---
name: migrating-ansible-roles
description: Migrate an Ansible role or playbook into a Python program built on reemote, or audit a role for migration feasibility and implementation gaps. Use when the user asks to migrate, port, convert or translate an Ansible role/playbook to Python or reemote, to map Ansible tasks onto reemote facts, operations or actions, or to find where reemote lacks coverage for a role. Covers the two-phase determinism model, the documented construct recipes (handlers, host_vars, include_vars, Jinja2 templates, validate hooks, lineinfile, get_url, build-from-source), the full module vocabulary, gap proof and ranking, program-shape design, and verification.
---

# Migrating an Ansible role to reemote

reemote is a configuration-management **library** shaped like Ansible —
inventory, facts, operations, idempotence — so a role migration is a *mapping*
task, not an architecture task. But it is not a keyword swap either: several
Ansible constructs (handlers, `include_vars`, fact-fed templates, `register` +
`when`) have no direct equivalent because reemote's determinism model forbids
the shape they rely on. Those migrate as **shape changes**: the fact/outcome
read moves out of the deploy into the gap *between* runs.

This is a long-running, multi-phase task. Work the phases in order, keep the
checklist, and never skip the gap analysis — an unmapped task silently dropped
is the classic migration failure.

## Canonical human guidance — read it first

Two documents are the authoritative migration guidance. **Read both before
mapping anything** (they are long; read them fully, not in excerpts):

- `docs/migrating.md` — the technical construct-by-construct guide. Eight
  sections, each with a mapping table, a numbered process, before/after code
  and a "What to watch" list: handler, host_vars, include_vars OS dispatch,
  Jinja2 templates, validate hook, lineinfile/replace/blockinfile, get_url,
  build-from-source. [construct-recipes.md](construct-recipes.md) is a
  condensed index of these — use it for orientation, but the docs page wins
  on any conflict, and its "What to watch" caveats are part of the recipe.
- `docs/articles/migrating.md` — the thesis and the Ansible→reemote vocabulary
  table: why the library is the transpilation target, what reemote is
  (four-word model: inventory / fact / operation / action), and the honest
  boundaries ("What Reemote is not").

Supporting docs: `docs/guide.md` (execution model, determinism, actions),
`docs/modules/<mod>.md` (every operation/fact signature), `docs/handlers.md`,
`docs/core.md`, `docs/drivers.md`, `docs/hosts.md`.

## The model rules that shape every migration

Violating any of these produces `DeterminismError`, `UnhashableArgumentError`
or `ActionInDeployError` at run time — design around them, never against them.
Full detail in [project-surface.md](project-surface.md).

1. **A deploy runs twice** (prepare against pre-state, apply against live
   state) and both passes must yield the *identical* request sequence. Never
   branch a deploy body on a fact, a run outcome, `datetime.now()`, randomness,
   or anything mutable. Fact-driven selection moves to `main()`:
   **gather → snapshot → factory** (freeze a dict, close the deploy over it).
2. **Every `op()` argument must be hashable.** Tuples not lists; no dicts;
   streams and transforms must be stable module-level objects (or built once
   in `main()`), never lambdas/closures created inside the generator.
3. **No commands inside a deploy.** `command:`/`shell:`/`script:` tasks become
   `Shell`/`Script` actions run via `gather_action` *outside* deploys. The
   boundary is enforced (`ActionInDeployError`), not conventional.
4. **No controller filesystem paths.** `files.install` takes `content: str`;
   `files.put`/`get` take IO streams you opened; `files.copy`/`move` are
   remote-to-remote. Templates are pre-rendered control-side in `main()`.
5. **`when` guards read static inventory data only** (`host.group`,
   `host.tags`, `host.extra`) and must be stable module-level functions.
6. **Handlers are a two-deploy split**: name the notifying requests, read
   `changed_hosts(report, NAMES)` between runs, feed the frozen set to
   `restart_handler` / `reload_handler` / `service_handler`.
7. **Transfers never elevate**; root-owned writes use the spool-and-install
   family (`files.install`, `files.transform`, `files.download`, …) with
   `sudo=True` on the request. Run-as users/passwords come from the inventory
   `privilege` section, never from an operation.

## Workflow

Copy this checklist and track progress across the whole task:

```
Migration Progress:
- [ ] Phase 0: Scope agreed (deliverable, target OS, role paths)
- [ ] Phase 1: Role fully read; role-at-a-glance map written
- [ ] Phase 2: Coverage table — every task mapped or marked GAP
- [ ] Phase 3: Gaps proven, classified, ranked; resolutions decided
- [ ] Phase 4: Program shape designed (deploys / snapshots / actions / main)
- [ ] Phase 5: Program implemented
- [ ] Phase 6: Verified (offline tests, dry run, idempotent re-run)
- [ ] Phase 7: Report delivered (coverage, gaps, deviations, run instructions)
```

### Phase 0 — Scope

Agree with the user (AskUserQuestion when available) before deep work:

- **Deliverable**: feasibility audit only / runnable Python program /
  program + library extensions (new facts/operations) / a repo example under
  `examples/`. Audits are analysis-only — write no code until asked.
- **Target platform**: a multi-OS role does *not* force a multi-OS migration.
  Fixing one target (the audits' precedent is CentOS 9) collapses
  `include_vars` dispatch to frozen module constants. Keep the
  gather→snapshot→factory recipe only when multi-OS is actually required.
- **Role paths**: scope to the role's *default* path. Opt-in branches
  (default-false `when:` flags, e.g. build-from-source) are scoped out early
  unless requested — their gaps are boundary matters, not blockers.
- **Real hosts**: examples connect for real and mutate targets. Never run
  against real hosts without explicit user approval; offline verification
  (Phase 6) needs none.

### Phase 1 — Read the role completely

Read *every* file that shapes behavior: `tasks/*.yml` (all included files),
`handlers/main.yml`, `defaults/main.yml`, `vars/*.yml`, `templates/*.j2`,
`files/`, `meta/main.yml`, README. Produce a **role-at-a-glance** map: task
graph, OS dispatch mechanism, variable sources and precedence, loops,
registered facts, handler fan-in (which tasks notify which handler), opt-in
branches. Note every construct that needs a shape change (handler,
`include_vars`, `register`+`when`, fact-fed template, `command:`/`shell:`).

### Phase 2 — Coverage table

Map **every task** (and every handler) to a reemote target. Use
[vocabulary.md](vocabulary.md) for the Ansible-module→operation map and
[construct-recipes.md](construct-recipes.md) for the shape-change constructs.
Verify signatures in `docs/modules/<mod>.md` or the module source — never map
from memory of Ansible semantics alone; parameter names and idempotence rules
differ (e.g. `systemd.service(restarted=True)` is stateless, content writes
are idempotent on content only). **Read the `changed` predicate, not just the
signature**: a keyword can exist without the Ansible behavior
(`dnf.packages(latest=True)` upgrades unconditionally; apt's did too
until #13). See "Proving coverage" in
[gap-analysis.md](gap-analysis.md).

| # | Ansible task (module + key args) | reemote target | Status | Evidence |
|---|---|---|---|---|
| 1 | `package: name=nginx` | `dnf.packages(packages=("nginx",), sudo=True)` | covered | docs/modules/dnf.md |
| 2 | `template: … notify: reload` | pre-render + `files.install` + `reload_handler` | recipe | migrating.md §Jinja2 |
| 3 | `pip: …` | — | GAP | gap-analysis.md |

Status vocabulary: **covered** (direct operation), **recipe** (documented
shape change), **workaround** (possible with a deviation — record it),
**GAP** (no faithful mapping — Phase 3). A task may need several rows
(e.g. `get_url` + `rpm_key` = `files.download` + `dnf.key`).

### Phase 3 — Gap analysis

Follow [gap-analysis.md](gap-analysis.md). The essentials:

- **Prove absence before claiming it**: enumerate the owning module's full
  surface (`__all__`, docs members, sibling facts with different names), then
  corroborate with identifier greps. A zero-match grep alone is not evidence.
- **Classify** each gap: deliberate boundary (never propose eroding it),
  workaroundable deviation, or genuine library gap.
- **Rank** core-blocking vs feature-only; optional features never block the
  default-path migration.
- **Resolve**: workaround first; a library extension is a separate, user-
  approved workstream using the sibling skills (`migrating-pyinfra-facts`,
  `migrating-pyinfra-operations`, `converting-inplace-to-spool-install`).
  Surface design conflicts with AskUserQuestion — never silently drop a
  feature or silently pick an approach.

### Phase 4 — Design the program shape

Decide the structure before writing code. The universal skeleton:

```
module constants     # role defaults, frozen vars tables, template text,
                     # NOTIFYING frozensets, module-level transforms/guards
def deploy_N(host)   # sync generators, branch-free w.r.t. facts, yield op(...)
def build_X(snapshot)# factories closing over frozen per-host maps
async def main()     # load+validate inventory → [gather_fact → snapshot] →
                     # run(deploy) → changed_hosts / renders → run(handler) …
```

Sequence rules: each `await run(...)` / `gather_action(...)` is a barrier;
gather *after* the deploy whose effects it must observe; `gather_fact` does
**not** close its hosts (close them yourself), `gather_action` and `run` do.
Order deploys so dependencies hold (repos before packages, users before
file ownership, installs before config). Use `compose`/`sub_deploy` for
multi-role programs. Worked end-to-end example:
[worked-example.md](worked-example.md).

### Phase 5 — Implement

Write the program per the Phase 4 design. Conventions:

- Import from the public API only: `from reemote import Host, op, run, …`.
- Every request that a handler selects carries a stable `name=`; names are
  the notification channel.
- Lists from inventory/vars become `tuple(...)` before reaching `op()`.
- Ansible loops over lists-of-dicts flatten to frozen tuples of scalars, one
  `op()` per item (hashability forbids the dict itself).
- Record every deliberate deviation in a comment naming the Ansible behavior
  and why it changed ("Ansible's `backup: yes` is dropped — …"). Tag every
  workaround with its gap number and issue (`GAP-3 (#13)`) so the second pass
  can find it.
- **Renderer dependencies are yours**: reemote ships no Jinja2 and no YAML
  library. A `to_nice_yaml`-heavy template needs **PyYAML** — import it
  *inside* the render function (importing the example must not require it),
  declare it in `pyproject.toml`'s `dev` group for a repo example (the offline
  tests render the templates), and document `uv run --with pyyaml python …`
  for the standalone run. Recipe 4 in
  [construct-recipes.md](construct-recipes.md).
- **Resolve the linter's effective rule set before writing code**:
  `uv run ruff check --show-settings` prints the enabled rules. This repo has
  no `[tool.ruff]` section and no `ruff.toml`, yet ruff enforces a broad set
  (S110/S112, B025, SIM107, TRY002/TRY004/TRY201/TRY203/TRY401, RUF068, …) —
  "no config" does **not** mean "E4/E7/E9/F only". Lint a skeleton early so
  the surprises land before 1500 lines do. Known bite: `TRY004` wants a type
  check to raise `TypeError`, so a role's `assert: … is mapping` gate raises
  `TypeError` and `main()`'s `except` tuple must include it.
- If the deliverable is a **repo example**: follow `examples/` conventions
  (long module docstring with a `Run it with:: uv run python …` line,
  inventory loaded from the project root `inventory.json`, dry run then real
  run, `format_plan`/`format_log` output) and the static rules
  `tests/test_examples.py` enforces (no mutable-container literals in `op()`,
  import-time-constructible module constants).
- **Role documentation lives in `docs/examples/roles/<role>.md`**, never
  beside the program in `examples/roles/<role>/`. Register the page under
  Examples → Roles in `mkdocs.yml` and link the program with a GitHub blob
  URL (`https://github.com/kimjarvis/reemote/blob/main/examples/roles/<role>/<role>.py`)
  — a relative link escaping `docs/` fails the strict mkdocs gate.
  `docs/examples/roles/ansible-datadog.md` is the model. A docs change
  triggers the mkdocs gate (Phase 6).

### Phase 6 — Verify

Offline first (no real hosts, no approval needed):

- **Determinism/idempotence by construction**: re-read every generator —
  no fact branches, no fresh lambdas/streams, all arguments hashable.
- **In-repo changes**: `uv run pytest tests/ -q` (the SimulatedHost suite),
  `uv run ruff check .`; docs touched → `NO_MKDOCS_2_WARNING=1 uv run
  --group docs mkdocs build --strict`. `uv` is not always on the tool shell's
  PATH — fall back to its absolute path (`~/.local/bin/uv`).
- **A new repo example needs a SimulatedHost-backed test** proving
  plan → apply → **second apply is a no-op** (`changed=False` everywhere,
  handler set empty). `tests/test_roles_ansible_datadog.py` is the model; what
  it takes in practice:
  - Import the example **by path**
    (`importlib.util.spec_from_file_location`) — a name like
    `ansible-datadog.py` is not a valid module identifier. Never call its
    `main()` (it connects for real): replay its orchestration
    barrier-for-barrier in the test, feeding its factories snapshots gathered
    from the simulated hosts.
  - **Persist the hosts across runs**: pass
    `host_factory=lambda entry: hosts[entry["host"]]` so every `run` gets the
    *same* object. `Host.aclose()` returns early when `_conn is None`, so a
    simulated host survives the close each `run` performs — that is what lets
    pass 2 observe pass 1.
  - **Seed every fact seam the deploys read**, not just the obvious ones:
    `apt_packages`, `apt_sources`, `remote_files`, `existing_files`,
    `os_users`/`os_groups`, `systemd_unit_files`, `services`,
    `enabled_services`, `directory_stats` — and **`file_stats`**:
    `files.file(present=False)` reads the stat-shaped `File` fact, so an
    unseeded `file_stats` makes a removal misbehave (a symlinked path also
    needs `force=True` — the fact reads it as "exists and is not a file").
    Removals clear **every** file store: `remove_file`/`remove_link` pop
    `remote_files` first (#18 closed, mirroring `remove_tree`), so
    `FileContents`/`RemoteFileSha1` stop answering for a removed path —
    assert removals against `remote_files` directly. The `find`/`grep` seams
    are keyed by the *question*: build keys with `FindFiles.command(...)` and
    `(path, pattern)` for `grep_files` instead of spelling them out.
  - **Bridge the subsystems the simulation does not model, between passes**:
    a simulated `gpg --dearmor` or `import_key` stores no real key material,
    so `gpg_keyrings` entries need their real fingerprints seeded
    (`import_key`'s seam appends a content-hash stub that will not match a
    pinned `keyid`); `systemd_unit_files` is never
    reconciled with the simulated filesystem, so a unit whose file was
    removed must be forgotten by hand (what `daemon-reload` does for real).
    `make_directory` writes a `directory_stats` row but never adds the path
    to `existing_files` (the `FileExists` seam), so a directory created in
    pass 1 and gated on `FileExists` in pass 2 needs the two stores synced
    by hand (`existing_files |= directory_stats.keys()`) or its create
    request re-fires. A package *install* needs no bridge: the seam applies
    a pending upgrade's candidate and retires its `apt_upgradable` entry (a
    pin retires it only when it matches the candidate). Re-derive the
    `find`/`grep` answers from the simulated filesystem after every pass,
    or pass 2 reads a stale fixture. Each bridge is a *simulation* limit,
    not a library bug — say so in the test docstring. Python `re`
    reproduces `grep -E` only when the pattern is plain enough; otherwise
    seed the hits directly.
  - **Use the action transport seam (#16, closed)**: `SimulatedHost`
    answers `gather_action(hosts, Shell/Script, …)` from the seeded
    `shell_results` map — the key is the *exact* shell the action rendered
    (the `command` verbatim, a `Script` gather's full `sh -c` wrapper, an
    escalated gather's `sudo`/`doas`/`su` rendering), and every shell the
    seam ran is recorded in `ran_shells` for exactly-once assertions. An
    unseeded command is a hard `UnseededShellResult` error naming the key
    to plant, so a new action read cannot silently pass — a first failing
    gather plus `host.ran_shells[-1]` is the intended seed workflow.
    Proven in `tests/test_simulated_host.py`.
  - Assert the workarounds converge: pass 2 must have no changed log entry
    **and** an empty handler set.
  - **Register snapshot factories in `tests/test_examples.py`**: the
    examples suite auto-discovers every `examples/` file and drains each
    deploy entrypoint. A snapshot factory — one required parameter not
    named `host`, e.g. `build_setup(codenames)` — hard-fails without a
    `SNAPSHOT_ARGS` entry keyed `(relpath, factory_name)`, whose value is a
    callable taking the host name and returning the frozen argument
    (`lambda name: {name: "noble"}`). Host-taking deploys and zero-argument
    factories need no entry — and a factory with **more than one required
    parameter is skipped entirely** (never drained), so a multi-snapshot
    factory like `build_handlers(plans, restart_notified, reload_notified)`
    needs no entry either.
- **Standalone program**: unit-test the pure pieces directly (transforms are
  fixpoints: `t(t(x)) == t(x)`; render functions; the deploy generator's
  yielded requests can be asserted without a server).

Against real hosts (only with user approval): `run(inventory, deploy,
dry=True)` and inspect `format_plan(plans)`; then the real run; then **run
the whole program again** — the second pass must report no changes and queue
no handler. A `dry=True` preview of a *handler* deploy is honest (it consults
the frozen outcome); a dry preview of the notifying deploy cannot know
whether handlers will fire.

### Phase 7 — Report

Deliver: the coverage table (Phase 2), ranked gaps with evidence and chosen
resolutions (Phase 3), the program-shape diagram (which deploys/actions run
in which order and why), every deliberate deviation from Ansible semantics,
and run instructions. For an audit, end by offering the next actions
(implement the program / implement a library improvement) — do not start
them unasked.

When the user asks for tickets (or a genuine gap will outlive the migration),
**file one GitHub issue per gap** and back-fill the numbers into the code's
`GAP-n` comments, the module docstring and the role doc
(`docs/examples/roles/<role>.md`). The workflow
— in-workspace scratch body files, `gh issue create --body-file`, `gh api`
instead of `gh issue view`, repo-relative citations, and checking for a stale
issue that claims the gap wrongly — is in
[gap-analysis.md](gap-analysis.md) §"Filing gap tickets". Also report where
*this skill's* guidance was missing or wrong, with file:line evidence, so it
can be corrected.

## Reference files

| File | Read it when |
| --- | --- |
| [project-surface.md](project-surface.md) | You need any API detail: execution model, `op`/`run`/gather signatures, inventory schema, actions, handlers, the 20-module catalog, errors, docs/examples/tests map, environment |
| [construct-recipes.md](construct-recipes.md) | A task uses handlers, host_vars, include_vars, templates, validate, lineinfile, get_url, build-from-source, loops, register/when, or any meta construct. Recipes 9–12 track the gap fixes: `0640` read-back (#12, closed), multi-key keyrings (#11, closed), converging dnf `latest` (#13's dnf half, open), `apt_repository` cache + global removal (#14/#15, closed), deb822 `signed_by` URL (#17, closed); recipes 7–8 also carry the files fixes: `unarchive` (#21, closed) and `copy` remote-src parity (#22, closed) |
| [vocabulary.md](vocabulary.md) | Mapping an Ansible module to its reemote operation/fact/action (all domains) |
| [gap-analysis.md](gap-analysis.md) | A task has no obvious mapping: absence proof, classification, known open/closed gaps, resolution paths, report templates |
| [worked-example.md](worked-example.md) | Designing or writing the program: a complete role→Python migration |

## Notes

- Operations report `changed` only on a real fact-resolved delta; a non-zero
  command exit raises `CommandError` (fail-fast) — a `changed` log entry is
  trustworthy, which is what makes `changed_hosts` a sound notification read.
  Known exception: `dnf.packages(latest=True)` reports a change without
  checking for a pending upgrade — recipe 11. (apt's `latest` was fixed by
  #13: it gates on `AptUpgradable` in-operation.)
- Stateless operations (`restarted`, `reloaded`, `daemon_reload`, waits,
  `apt.update`, …) always yield when reached — keep them in handler deploys
  or guard them, never in a converged unconditional deploy.
- `files.install`/`transform`/`download` idempotence is **content-only**,
  and the read-back is two-tier: `FileContents` cats unprivileged first and
  re-reads elevated with `sudo` when the login user cannot read, so a `0640`
  service-owned file converges too (#12 closed — recipe 9's old
  group-membership workaround is retired). Mode/owner drift still needs
  `files.file` to converge.
- reemote is Linux-only, a library not a CLI, has no role ecosystem and no
  OS-name translation — pick the right package module per target yourself.