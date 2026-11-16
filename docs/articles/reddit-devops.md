Why LLM-assisted Ansible-to-Python migrations break production safety (and how to fix the target)

If you’ve ever tried using an LLM to migrate legacy Ansible roles into standalone Python, you’ve probably seen the same failure mode: the model spits out a brittle script full of `subprocess` or `paramiko` calls.

It reproduces the happy path, but it silently drops the operational guarantees that keep production from catching fire—idempotency, `--check` mode previews, lock-step fleet execution, and structured per-host change reporting.

**Why prompt engineering doesn't fix it**

This isn't a model intelligence problem; it's a missing target idiom. LLMs work by pattern matching. Because Python hasn't had a standard configuration-management library shaped like Ansible, every prompt forces the model to invent its own orchestration engine from scratch. Spending more tokens gets you better comments and `try/except` blocks, not architectural convergence.

**Constraining the target vocabulary**

To make LLM translation safe enough to actually review in a PR, the target needs to map 1:1 to Ansible's execution model:

* **Generator-based deploys:** The deploy logic is a plain Python generator yielding operation requests (`plans, report, hosts = await run(inventory, deploy)`). An `asyncssh` runtime handles fleet concurrency and per-host ordering so generated code never touches concurrency primitives.
* **Two-pass execution (Plan/Apply):** The runner executes the generator twice—once to plan, once to apply—and aborts if the passes diverge. This catches non-deterministic model hallucinations at plan time.
* **Structured dry-runs:** `dry=True` returns a diffable plan and exact commands that would execute, restoring `--check` mode as standard data structures you can assert on in CI.
* **1:1 module mapping:** Common modules map directly to typed functions (`apt_repository` → `apt.repo`, `lineinfile` → `files.edit`, `service` → `systemd.service`).
* **No implicit controller paths:** File contents must be explicit strings or caller-opened streams, keeping converted scripts self-contained.

**Testing on real Galaxy roles**

To see if this survives real-world edge cases, we ran automated conversions on 10 high-usage Galaxy roles (Jeff Geerling’s Apache, Docker, Java, Memcached, NFS, nginx, NTP, PHP, and Xdebug roles, plus Datadog's official agent role).

All 10 cover the role's default OS path—including handlers as a second deploy pass and pre-rendered templates—and pass an offline `pytest` suite against a simulated host driver. The primary assertion is strict idempotency: a second run against the converged state reports zero changes and queues zero handlers.

The takeaway for migrations: don't ask an LLM for "idiomatic Python." Give it a strictly typed 1:1 operation library and a few verified role conversions as few-shot context. It turns an unreviewable rewrite into a bounded PR.