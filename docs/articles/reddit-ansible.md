Experiment: Transpiling Galaxy roles to Python without losing check-mode, handlers, or idempotency

Most "rewrite Ansible in Python" attempts fail for an obvious reason: people underestimate how much heavy lifting Ansible's execution engine actually does.

When you convert a role into a raw `paramiko` or `subprocess` script, you lose `--check` mode, per-host change reporting, handler notification queues, and predictable idempotency. You end up rebuilding a worse version of Ansible from scratch.

Out of curiosity, we wanted to see what happens if you try to preserve Ansible's exact operational guarantees in Python—specifically to handle complex data transformations where Jinja2 starts feeling painful, while still keeping `pytest` and static type checking.

**Keeping Ansible's execution model intact**

Instead of free-form Python, we mapped Ansible's core primitives 1:1 onto a constrained Python library:

* **1:1 module parity:** Standard modules map directly to equivalent functions (`apt_repository` → `apt.repo`, `lineinfile` → `files.edit`, `get_url` → `files.download`, `service` → `systemd.service`).
* **Check mode & Diffs:** Deploys run in two passes (plan, then apply). Running with `dry=True` evaluates live host state and outputs a structured plan of what would change—preserving `--check` behavior as inspectable data.
* **Handlers & Inventory:** Handlers run as a second deploy pass triggered only when tasks report changes, and inventory variables pass in as typed Python structures.
* **No controller path magic:** Templates and files are passed as explicit strings/streams so roles remain portable.

**Testing against Geerling's Galaxy roles**

To see if this holds up against real-world roles (and not just toy examples), we converted 10 popular Galaxy roles—Jeff Geerling's Apache, Docker, Java, Memcached, NFS, nginx, NTP, PHP, and Xdebug roles, plus DataDog's agent role—along their default OS paths.

We ran all 10 against a simulated host driver in an offline test suite to verify idempotency: running the converted role a second time against an already-converged host produces zero changes and queues zero handlers.

YAML + Ansible is still hard to beat for straightforward orchestration, but for teams dealing with heavy business logic inside roles, having a 1:1 target vocabulary makes LLM-assisted translation surprisingly clean and reviewable. Curious how other folks here handle roles once Jinja2 templating starts getting out of hand?