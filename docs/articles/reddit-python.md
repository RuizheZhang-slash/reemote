Using synchronous generators + asyncssh to make LLM-generated infra code testable with pytest

Getting an LLM to translate declarative config (like Ansible YAML) into Python usually produces untestable spaghetti: imperative scripts stuffed with `subprocess.run()` calls that can only be verified by spinning up VMs.

We wanted to see if designing a pure-Python configuration-management target with the right constraints could turn LLM translation into a deterministic, `pytest`-able workflow.

**The Architecture: Synchronous Generators + Async Runner**

Instead of making users (or LLMs) write `async/await` orchestration code, a deploy is written as a plain synchronous generator that yields declarative operation requests:

```python
plans, report, hosts = await run(inventory, deploy)
```

Separating the *description* of state from the *execution* engine gives us a few clean Python properties:

* **Deterministic Plan/Apply:** The runner executes the generator twice—first in plan mode, then in apply mode—and raises an exception if the yielded operations diverge between passes. This catches non-deterministic logic or hallucinated side effects before anything touches a socket.
* **Zero-VM unit testing:** Because the generator only yields typed operation objects (and file contents must be explicit strings/streams rather than implicit local file paths), you can run an entire deployment against an in-memory simulated host driver in `pytest` in milliseconds.
* **Structured dry-runs:** Passing `dry=True` returns the diffable plan and exact shell commands as standard Python data structures you can write assertions against.
* **Concurrency stays in the runtime:** The `asyncssh` driver handles fleet-wide concurrency and per-host ordering, while the deploy logic stays linear, typed (`mypy`/`ruff` clean), and easy to read.
* **1:1 vocabulary:** Modules map directly to typed functions (`apt.repo`, `files.edit`, `files.download`, `systemd.service`) so an LLM maps tasks 1:1 rather than inventing wrappers.

**Benchmarking against 10 real-world roles**

We tested this by translating 10 widely used Ansible Galaxy roles (including Geerling's nginx, Docker, PHP, Java, and Apache roles, plus the Datadog agent role) and running them through an offline `pytest` suite. Each test asserts strict idempotency—running the generator a second time against the simulated converged state must yield zero changes and trigger zero handlers.

Has anyone else experimented with using generators/coroutines as an intermediate representation for LLM code generation? Constraining the output to a pure generator made static analysis and code review dramatically easier than letting the model emit arbitrary imperative Python.