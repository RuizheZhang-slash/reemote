# Ansible → reemote vocabulary

The destination vocabulary for the coverage table. **Verify every mapping's
signature** in `docs/modules/<mod>.md` (or `src/reemote/modules/<mod>/<mod>.py`)
before using it — parameter names, defaults and idempotence rules are
reemote's, not Ansible's. `GAP` = no faithful mapping; follow
[gap-analysis.md](gap-analysis.md) (prove, classify, resolve) — never silently
drop the task.

Convention: operations are lower-case functions (`apt.packages`); facts are
classes (`apt.AptPackages`); actions (`Shell`, `Script`, `WaitForConnection`)
run via `gather_action` **outside** deploys.

## Packages

| Ansible | reemote | Notes |
| --- | --- | --- |
| `package` / `apt` / `yum` / `dnf` | `apt.packages` / `dnf.packages` / `apk.packages` | pick per target OS; `packages=("name",)` tuple; `pkg=version` pins supported |
| `apt state=latest` / `yum state=latest` | `apt.packages(latest=…)` / `dnf.packages(latest=…)` | apt is **fact-gated** (#13 closed): `latest=True` upgrades only installed unpinned names with a pending `AptUpgradable` entry — pass it directly. **dnf still upgrades unconditionally** — gate its flag on a check-update snapshot (recipe 11) |
| `apt update_cache=yes` | `apt.packages(update=True)` (a full `apt-get update` prefix) or `apt.update` (standalone, stateless — always yields) | `cache_valid_time=N` **is** supported on both (the `AptUpdateStamp` fact gates it); the kwarg is `update` on apt, `update_cache` on dnf |
| `yum enablerepo/disablerepo` | `dnf.packages(repos=…, disable_repos=…)` | first-class |
| `dnf allow_downgrade` | `dnf.packages(allow_downgrade=True)` | version-aware presence |
| `apt default_release` | `apt.packages(default_release=…)` | renders apt's `-t <release>` |
| `apt install_recommends=no` | `apt.packages(no_recommends=True)` | verified in module source |
| `apt_key` | `apt.key` | key **content** as control-side IO stream; URL `src` rejected; **stateless** (always changed) — for a converging shared keyring use `gpg.import_key(dest=…, keyid=…)`, recipe 10 (#11 closed) |
| `rpm_key` | `dnf.key` | same stream contract; import direction non-idempotent (rpm dedupes) |
| `apt_repository` | `apt.repo` (one-line), `apt.sources_file` (deb822), `apt.ppa` | all take `update_cache=True` (#14 closed); `apt.repo(present=False)` with no `filename` removes the line from **every** sources file that holds it (#15 closed — recipe 12b); a `filename` scopes to one file; a deb822-only match needs `apt.sources_file(present=False)` |
| `deb822_repository` | `apt.sources_file` | deb822 `.sources` parity; `signed_by` takes an existing keyring **path** or an **http(s) key URL** — the URL form fetches the ASCII-armored key control-side and installs `/etc/apt/keyrings/<filename>.asc` (`0644`) itself, rewriting `Signed-By:` to that path; armored-only (a binary body raises `ValueError`); `present=False` removes the sources + `.asc`/`.gpg` keyrings without fetching (**#17 closed** — recipe 12c) |
| `yum_repository` | `dnf.repo` | single `[section]`; multi-section `.repo` → `files.download`/`files.install` the whole file |
| `apk` repositories | `apk.repository` | path-aware presence |
| `apt deb=…` / local `.deb` | `apt.deb` | URL `src` rejected — fetch control-side |
| `yum name=….rpm` | `dnf.rpm` | URL `src` rejected — fetch control-side |
| `apt_mark` / `dpkg_selections` (hold) | `apt.mark` | hold/unhold |
| `apk hold` / world | `apk.hold`, `apk.virtual` | |
| `yum autoremove` / `apt autoremove` | `dnf` (verify) / `apt.auto_remove`, `apk.autoremove` | |
| `apt upgrade` / `dist-upgrade` | `apt.upgrade`, `apt.dist_upgrade` | |
| `yum update` / makecache / clean | `dnf.update`, `dnf.makecache`, `dnf.clean` | `repos=` scoping |
| `dnf module` | `dnf.module` | enable/disable streams |
| `package_facts` | `AptPackages` / `DnfPackages` / `ApkInstalledPackages` facts | via `gather_fact` |
| `snap` | `snap.package` | |
| `flatpak` | `flatpak.packages` | |
| `pip` | **GAP** | no pip module; stopgap: install `python3-pip` via package module + `Shell` action, or extend the library |
| `pacman` / `zypper` / `pkgng` / `openbsd_pkg` | **GAP** | no modules (Arch/SUSE/BSD) |
| `npm` / `yarn` / `gem` / `composer` | **GAP** | language package managers unshipped |

## Files

| Ansible | reemote | Notes |
| --- | --- | --- |
| `copy content=…` | `files.install(content=…, dest=…)` | spool-and-install; `sudo=True` for root-owned |
| `copy src=<file>` | read control-side → `files.install(content=text)`; binary → `files.put(src=io stream)` | no controller paths in requests |
| `copy remote_src=yes` | `files.copy` | remote-to-remote |
| `template` | pre-render in `main()` + `files.install` | recipe 4; jinja2 **or PyYAML** (`to_nice_yaml`) is your dependency — `dev` group for a repo example |
| `copy/template validate:` | `files.install(validate="cmd {spool}")` | recipe 5; atomic |
| `lineinfile` / `replace` / `blockinfile` | `files.transform` (+ `block_transform` factory) | recipe 6; pure fixpoint transform |
| edits to login-writable files | `files.edit` | unprivileged write-back |
| `file state=touch/absent` + mode/owner | `files.file` | metadata convergence. **`state=absent` needs `force=True`**: the `File` fact reads a symlink as "exists and is not a file" and the default `force=False` raises `ValueError` on it; `force=True` is Ansible's type-agnostic removal (`rm -rf` on a symlink removes only the link, never its target) |
| `file state=directory` | `files.directory` | |
| `file state=link/hard` | `files.link` | |
| `file attributes=…` (chattr) | `files.flags` | immutable etc. |
| `get_url` (text) | `files.download` | recipe 7; control-side fetch, checksum-pin |
| `get_url` (binary) | control-side fetch → `io.BytesIO` → `files.put` | or `dnf.rpm`/`apt.deb` |
| `fetch` | `files.get(src=…, dest=<per-host IO sink>)` | remote→control |
| `stat` | `files.File`, `FileExists`, `FileLink`, `Md5File`/`Sha256File`/`Sha384File` | via `gather_fact` |
| `slurp` | `files.FileContents` (gather) or `files.get` | |
| `find` (name/size/type) | `FindFiles`, `FindDirectories`, `FindLinks` | |
| `find contains=…` | `FindInFiles` (recursive grep), `FindInFile` (one file) | exists — do not report as gap |
| `assemble` | workaround: concatenate control-side → `files.install` | |
| `unarchive` / `archive` | **GAP** | stopgap: fetch/put + `Shell` tar action outside deploys |
| `synchronize` (rsync) | **GAP** | no rsync operation |
| `patch` | **GAP** | `Shell` action or a transform |
| `acl` (setfacl) | **GAP** | no ACL operation |
| `xattr` (setfattr) | **GAP** | `files.flags` is chattr, not xattr |
| `tempfile` | workaround: fixed `/tmp` path or `Shell` action | |

## Services and init

| Ansible | reemote | Notes |
| --- | --- | --- |
| `service` / `systemd` | `systemd.service` | `running`/`enabled` idempotent; `restarted`/`reloaded`/`daemon_reload` stateless |
| `systemd scope=user` | `systemd.service(user_mode=True)` | |
| `service state=reloaded` | `reloaded=True` (+ `soft_reload=True` for reload-or-try-restart) | reloads only a *running* unit; the default `running=True` starts a stopped one |
| unit file drop-ins | `systemd.dropin` | preferred over editing packaged units |
| `systemd mask/unmask` | `systemd.mask` | |
| tmpfiles / sysusers / preset | `systemd.tmpfiles`, `systemd.sysusers`, `systemd.preset` | |
| `service_facts` | `SystemdStatus`, `SystemdUnitFiles`, `SystemdServiceState` facts | |
| sysvinit / OpenRC (Alpine) | `openrc.service`, `openrc.runlevel`, `openrc.config` | |
| `cron` / `at` | **GAP** | cron stopgap: `files.install` a `/etc/cron.d` drop-in |
| `reboot` | `Shell(command="reboot")` + `WaitForConnection` actions | recipe: general map |

## System configuration

| Ansible | reemote | Notes |
| --- | --- | --- |
| `user` | `server.user` | `groups=… append=True` for docker-style membership |
| `group` | `server.group` | |
| `authorized_key` | `server.user_authorized_keys` | |
| `hostname` | `server.hostname` | |
| `mount` | `server.mount` | |
| `sysctl` | `sysctl.setting`, `sysctl.conf` | drop-in files |
| `modprobe` | `server.modprobe` | |
| `timezone` | `server.timezone` | systemd-only prerequisite |
| `locale_gen` | `server.locale` | |
| `pam_limits` | `server.security_limit` | |
| `hosts` (/etc/hosts) | `server.etc_hosts` | dedicated operation |
| `known_hosts` | **GAP** | stopgap: `files.install`/`transform` the file, or `Shell` ssh-keyscan |
| `alternatives` | **GAP** | |
| `debconf` | **GAP** | |
| `seboolean` | `selinux.boolean` | `persistent=True` → `-P` |
| `selinux` (mode/policy) | `selinux.mode`, `selinux.config` | config change needs reboot note |
| `seport` / `sefcontext` / `selogin` | `selinux.port`, `selinux.file_context(_mapping)`, `selinux.login` | |
| `selinux_permissive` | `selinux.permissive_domain` | |
| `restorecon` / autorelabel | `selinux.restorecon`, `selinux.autorelabel` | |
| `selinux module` | `selinux.module` | |
| ansible `setup` facts | `server.LinuxDistribution` (name/**family**/major/minor), `Arch`, `KernelVersion`, `Hostname`, `hardware.*` (Cpus, memory via DmiInfo, devices, IPs), `server.Env`/`Which`/`Port`/`Processes`/`Mounts`/`Uptime` | gather → snapshot for anything a template/branch consumes |

## Firewalls

| Ansible | reemote |
| --- | --- |
| `firewalld` port/service/rich_rule/zone/masquerade/forward_port/icmp_block/interface/source/protocol/ipset | `firewalld.port`, `.zone_service`, `.rich_rule`, `.zone`, `.masquerade`, `.forward_port`, `.icmp_block`, `.interface`, `.source`, `.protocol`, `.ipset` (+ `default_zone`, `lockdown`, `panic`, `reload`, `service`) |
| `iptables` | `iptables.rule`, `.chain`, `.policy`, `.save`, `.restore`, `.flush`, `.zero`, `.ipset` |
| `ufw` | `ufw.rule`, `.state`, `.logging`, `.default_policy`, `.reset` |

## Network / waits / commands

| Ansible | reemote | Notes |
| --- | --- | --- |
| `command` / `shell` / `raw` | `Shell` action via `gather_action` | outside deploys; interpret `Result` yourself |
| `script` | stage (`files.put`/`install`) then `Script` action | no transfer in the action |
| `wait_for port=` | `server.wait(port=…, protocol=…, timeout=…)` | in-deploy wait descriptor |
| `wait_for` service active | `server.wait_service(service=…)` | |
| `wait_for_connection` | `WaitForConnection` action | fatal `ConnectionTimeoutError` |
| `wait_for path=/timeout=` (other) | workaround: gather/poll in `main()` | no generic in-deploy fact wait beyond the two above |
| `uri` | **GAP** | control-side HTTP in `main()`; on-target → `Shell` |
| `expect` | **GAP** | |

## Version control, databases, containers, keys

| Ansible | reemote | Notes |
| --- | --- | --- |
| `git` | `git.repo` (clone/pull/branch), `git.config`, `git.worktree` | |
| `mysql_db` / `mysql_user` / `mysql_variables` / `mysql_query` / `mysql_replication` | `mysql.database`, `.user`, `.variable`, `.sql`, `.replica` (+ tables, indexes, privileges, roles, plugins, dump/load) | |
| `postgresql_db` / `_user` / `_privs` / `_ext` / `_schema` / `_query` / `_set` | `postgresql.database`, `.role`, `.privilege`, `.extension`, `.schema`, `.sql`, `.setting` (+ membership, publications/subscriptions, tablespaces, dump/load) | |
| `lxd_container` / `lxd_profile` | `lxd.instance`/`.container`, `.profile` (+ images, networks, storage, snapshots, projects) | |
| `docker_container` / `docker_image` / `docker_*` | **GAP** | no Docker management module (the docker *connector* drives a container as a host — different thing) |
| GPG keyring tasks | `gpg.key`, `.import_key`, `.export_key`, `.delete_key`, `.dearmor`, `.gen_key`, `.trust`, `.refresh_keys` | `import_key(dest=…, keyid=…)` imports **additively** into a named keyring, idempotent per fingerprint (#11 closed, recipe 10); without `dest` it imports into the login user's GNUPGHOME; `gpg.key` installs a keyring file wholesale |

## Meta constructs

Handlers, vars, loops, tags, serial, check mode, become, register/when,
include/import, block/rescue, environment, vault → see the general construct
map in [construct-recipes.md](construct-recipes.md).