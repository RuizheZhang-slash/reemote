<!--
Copyright (c) 2026 Kim Jarvis.
SPDX-License-Identifier: EPL-2.0
-->

# Ansible → reemote vocabulary

The destination vocabulary for the coverage table. **Verify every mapping's
signature** on the module's docs page (`https://reemote.org/modules/<mod>/`)
or in its source on GitHub
(`https://github.com/kimjarvis/reemote/blob/main/src/reemote/modules/<mod>/<mod>.py`)
before using it — parameter names, defaults and idempotence rules are
reemote's, not Ansible's. Issue numbers (`#13`, `#15`) reference the upstream
tracker, [https://github.com/kimjarvis/reemote/issues](https://github.com/kimjarvis/reemote/issues).
`GAP` = no faithful mapping; follow [gap-analysis.md](gap-analysis.md)
(prove, classify, resolve) — never silently drop the task.

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
| `apt_key` | `apt.key` | key **content** as control-side IO stream; URL `src` rejected; **stateless** (always changed) — for a converging shared keyring use `gpg.import_key(dest=…, keyid=…)`, recipe 10 |
| `rpm_key` | `dnf.key` | same stream contract; import direction non-idempotent (rpm dedupes) |
| `apt_repository` | `apt.repo` (one-line), `apt.sources_file` (deb822), `apt.ppa` | all take `update_cache=True`; `present=False` removes the line wherever it is configured by default (`filename=None`, #15 closed); a `filename` scopes the removal to one file |
| `deb822_repository` | `apt.sources_file` | deb822 `.sources` parity; `signed_by` takes an existing keyring path **or an http(s) key URL** — the URL form fetches the ASCII-armored key control-side and installs `/etc/apt/keyrings/<filename>.asc` (`0644`) itself; armored-only (a binary body raises `ValueError`); `present=False` removes the sources + `.asc`/`.gpg` keyrings (#17 closed — recipe 12c) |
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
| `copy content=…` | `files.install(content=…, dest=…)` | spool-and-install; `content: str \| bytes` (#23 closed); `sudo=True` for root-owned |
| `copy src=<file>` | read control-side → `files.install(content=text or bytes)` | no controller paths in requests; a binary body is sha1-idempotent and needs a login-readable mode |
| `copy remote_src=yes` | `files.copy` | full parity (#22 closed): existing-dir `dest` → copy inside, else **rename** (parent validated in both phases); `mode`/`user`/`group` in the same request; sha1-gated — equal content no-ops, drift needs `overwrite=True` (Ansible `force: yes`). `files.move` takes the same forms but is **stateless** |
| `template` | pre-render in `main()` + `files.install` | recipe 4; jinja2 **or PyYAML** (`to_nice_yaml`) is your dependency |
| `copy/template validate:` | `files.install(validate="cmd {spool}")` | recipe 5; atomic |
| `lineinfile` / `replace` / `blockinfile` | `files.transform` (+ `block_transform` factory) | recipe 6; pure fixpoint transform |
| edits to login-writable files | `files.edit` | unprivileged write-back |
| `file state=touch/absent` + mode/owner | `files.file` | metadata convergence. **`state=absent` needs `force=True`**: the `File` fact reads a symlink as "exists and is not a file" and the default `force=False` raises `ValueError` on it; `force=True` is Ansible's type-agnostic removal (`rm -rf` on a symlink removes only the link, never its target) |
| `file state=directory` | `files.directory` | |
| `file state=link/hard` | `files.link` | |
| `file attributes=…` (chattr) | `files.flags` | immutable etc. |
| `get_url` (text) | `files.download` | recipe 7; control-side fetch, checksum-pin |
| `get_url` (binary) | `files.download` | **#23 closed**: a non-UTF-8 body installs the raw bytes via `files.install(content=<bytes>)`, sha1-idempotent (drush launcher: `/usr/local/bin/drush`, `0755`); a `.rpm`/`.deb` **to install as a package** → `dnf.rpm`/`apt.deb`; a tarball **to extract** → `files.unarchive(src=<url>)` (#21 closed) |
| `fetch` | `files.get(src=…, dest=<per-host IO sink>)` | remote→control |
| `stat` | `files.File`, `FileExists`, `FileLink`, `Md5File`/`Sha256File`/`Sha384File` | via `gather_fact` |
| `slurp` | `files.FileContents` (gather) or `files.get` | |
| `find` (name/size/type) | `FindFiles`, `FindDirectories`, `FindLinks` | |
| `find contains=…` | `FindInFiles` (recursive grep), `FindInFile` (one file) | exists — do not report as gap |
| `assemble` | workaround: concatenate control-side → `files.install` | |
| `unarchive` | `files.unarchive(src, dest, creates=…, checksum=…, user=…, group=…)` | **#21 closed**: http(s) `src` fetched control-side as binary, spooled + extracted in-operation; `creates` gates before any fetch (converged → no change, zero commands); without `creates` stateless |
| `archive` (compression) | **GAP** | create the archive control-side, or a `Shell` tar action outside deploys |
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
| GPG keyring tasks | `gpg.key`, `.import_key`, `.export_key`, `.delete_key`, `.dearmor`, `.gen_key`, `.trust`, `.refresh_keys` | `import_key(dest=…, keyid=…)` imports **additively** into a named keyring, idempotent per fingerprint (recipe 10); without `dest` it imports into the login user's GNUPGHOME; `gpg.key` installs a keyring file wholesale |

## Meta constructs

Handlers, vars, loops, tags, serial, check mode, become, register/when,
include/import, block/rescue, environment, vault → see the general construct
map in [construct-recipes.md](construct-recipes.md).
