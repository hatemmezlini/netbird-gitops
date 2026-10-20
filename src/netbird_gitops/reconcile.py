"""Reconcile a NetBird account with the desired state.

Ownership rules (see README.md):
- objects named with the `gitops-` prefix (groups, policies) belong to netbird-gitops;
- the declared network, its resources and its router belong to netbird-gitops;
- user groups and the router group are created if missing, never deleted;
- peers, setup keys and tokens are never touched.

Changes are ordered so that access is granted before anything is revoked.
"""

from .api import ApiError

PREFIX = "gitops-"
MANAGED = "[netbird-gitops]"
READ_ONLY_SETTINGS = ("embedded_idp_enabled", "local_auth_disabled")
MANAGED_ROLES = ("admin", "user")


def _ids(objs):
    return sorted(o["id"] for o in objs or [])


def _differs(desired, current):
    """True when a key of `desired` (recursively) has another value in `current`."""
    if isinstance(desired, dict):
        if not isinstance(current, dict):
            return True
        return any(_differs(v, current.get(k)) for k, v in desired.items())
    return desired != current


def _merge(current, desired):
    out = dict(current or {})
    for k, v in desired.items():
        out[k] = _merge(out.get(k), v) if isinstance(v, dict) else v
    return out


def _rule_body(rule):
    """Policy rule as returned by GET -> as accepted by PUT."""
    body = {k: v for k, v in rule.items() if k not in ("sources", "destinations")}
    body["sources"] = _ids(rule.get("sources"))
    body["destinations"] = _ids(rule.get("destinations"))
    for k in ("sourceResource", "destinationResource"):
        if not body.get(k):
            body.pop(k, None)
    return body


def _rule_key(rule):
    return (
        rule.get("name"), rule.get("enabled"), rule.get("action"), rule.get("bidirectional"),
        rule.get("protocol"), tuple(sorted(rule.get("ports") or [])),
        tuple(sorted(rule["sources"])), tuple(sorted(rule["destinations"])),
        bool(rule.get("sourceResource")), bool(rule.get("destinationResource")),
    )


def access_group_name(group, protocol, ports):
    name = f"{PREFIX}{group}-{protocol}"
    return f"{name}-{'_'.join(str(p) for p in ports)}" if ports else name


class Reconciler:
    def __init__(self, api, cfg, log=print):
        self.api = api
        self.cfg = cfg
        self.log = log
        self.errors = []
        self.groups = {}  # name -> id

    # -- helpers ---------------------------------------------------------------

    def warn(self, msg):
        self.log(f"WARNING: {msg}")

    def error(self, msg):
        self.log(f"ERROR: {msg}")
        self.errors.append(msg)

    def create(self, path, body, summary):
        created = self.api.write("POST", path, body, summary)
        return created if created else {**body, "id": f"(new {body.get('name', path)})"}

    def delete(self, path, summary):
        """Deletions come last and are best effort: a failure is reported, not fatal."""
        try:
            self.api.write("DELETE", path, None, summary)
        except ApiError as exc:
            self.error(str(exc))

    # -- desired state ---------------------------------------------------------

    def access(self):
        """{(group, protocol, ports): [resource names]} for every granted access."""
        acc = {}
        for res in self.cfg["resources"]:
            for g in res["groups"]:
                acc.setdefault((g, res["protocol"], tuple(res["ports"])), []).append(res["name"])
        portal = self.cfg["portal"]
        if portal:
            for g in self.cfg["userGroups"]:
                acc.setdefault((g, "tcp", tuple(portal["ports"])), []).append("portal")
        return acc

    def resources(self, access):
        """Desired network resources: {name: {address, description, groups}}."""
        wanted = {}
        for res in self.cfg["resources"]:
            wanted[res["name"]] = {"address": res["address"], "description": res["title"]}
        if self.cfg["portal"]:
            wanted["portal"] = {"address": self.cfg["portal"]["address"], "description": "Access portal"}
        for res in wanted.values():
            res["groups"] = []
        for (g, proto, ports), names in access.items():
            gid = self.groups[access_group_name(g, proto, ports)]
            for n in names:
                wanted[n]["groups"].append(gid)
        for res in wanted.values():
            res["groups"].sort()
        return wanted

    # -- steps -----------------------------------------------------------------

    def settings(self):
        desired = self.cfg["settings"]
        if not desired:
            return
        account = self.api.get("/accounts")[0]
        current = account.get("settings") or {}
        if not _differs(desired, current):
            return
        merged = _merge(current, desired)
        for k in READ_ONLY_SETTINGS:
            merged.pop(k, None)
        changed = sorted(k for k, v in desired.items() if _differs(v, current.get(k)))
        self.api.write("PUT", f"/accounts/{account['id']}", {"settings": merged},
                       f"update account settings: {', '.join(changed)}")

    def ensure_groups(self, names):
        current = {g["name"]: g["id"] for g in self.api.get("/groups")}
        self.groups = dict(current)
        for name in names:
            if name not in self.groups:
                self.groups[name] = self.create("/groups", {"name": name}, f"create group {name}")["id"]
        return current

    def network(self):
        net = self.cfg["network"]
        body = {"name": net["name"], "description": net["description"]}
        for n in self.api.get("/networks"):
            if n["name"] == net["name"]:
                if (n.get("description") or "") != net["description"]:
                    self.api.write("PUT", f"/networks/{n['id']}", body, f"update network {net['name']}")
                return n["id"], False
        return self.create("/networks", body, f"create network {net['name']}")["id"], True

    def sync_resources(self, nid, is_new, wanted):
        current = {} if is_new else {r["name"]: r for r in self.api.get(f"/networks/{nid}/resources")}
        for name, res in sorted(wanted.items()):
            body = {"name": name, "description": res["description"], "address": res["address"],
                    "enabled": True, "groups": res["groups"]}
            cur = current.get(name)
            if cur is None:
                self.create(f"/networks/{nid}/resources", body, f"create resource {name} ({res['address']})")
            elif ((cur.get("address"), cur.get("description") or "", cur.get("enabled"), _ids(cur.get("groups")))
                  != (res["address"], res["description"], True, res["groups"])):
                self.api.write("PUT", f"/networks/{nid}/resources/{cur['id']}", body, f"update resource {name}")
        return [r for name, r in current.items() if name not in wanted]

    def sync_router(self, nid, is_new):
        net = self.cfg["network"]
        body = {"peer_groups": [self.groups[net["routerGroup"]]], "metric": net["metric"],
                "masquerade": net["masquerade"], "enabled": True}
        routers = [] if is_new else self.api.get(f"/networks/{nid}/routers")
        if not routers:
            self.create(f"/networks/{nid}/routers", body, f"create router (group {net['routerGroup']})")
            return
        first, extra = routers[0], routers[1:]
        current = (bool(first.get("peer")), sorted(first.get("peer_groups") or []),
                   first.get("metric"), first.get("masquerade"), first.get("enabled"))
        if current != (False, body["peer_groups"], body["metric"], body["masquerade"], True):
            self.api.write("PUT", f"/networks/{nid}/routers/{first['id']}", body, "update router")
        for r in extra:
            if self.cfg["strict"]:
                self.delete(f"/networks/{nid}/routers/{r['id']}", "delete extra router")
            else:
                self.warn(f"network {net['name']} has an extra router {r['id']} (kept: strict is off)")

    def desired_policies(self, access):
        policies = {}
        for (g, proto, ports), _ in sorted(access.items()):
            p = policies.setdefault(f"{PREFIX}{g}", {
                "name": f"{PREFIX}{g}",
                "description": f"{MANAGED} access of group {g}",
                "enabled": True,
                "source_posture_checks": [],
                "rules": [],
            })
            p["rules"].append({
                "name": f"{g} {proto}" + (f"/{','.join(str(x) for x in ports)}" if ports else ""),
                "enabled": True,
                "action": "accept",
                "bidirectional": False,
                "protocol": proto,
                "ports": [str(x) for x in ports],
                "sources": [self.groups[g]],
                "destinations": [self.groups[access_group_name(g, proto, ports)]],
            })
        return policies

    def sync_policies(self, desired):
        current = self.api.get("/policies")
        by_name = {p["name"]: p for p in current}
        for name, want in desired.items():
            cur = by_name.get(name)
            if cur is None:
                self.create("/policies", want, f"create policy {name}")
                continue
            cur_rules = [_rule_body(r) for r in cur.get("rules") or []]
            if (cur.get("enabled"), cur.get("description") or "", sorted(map(_rule_key, cur_rules))) != (
                    True, want["description"], sorted(map(_rule_key, want["rules"]))):
                self.api.write("PUT", f"/policies/{cur['id']}", want, f"update policy {name}")
        return current

    def revoke_policies(self, current, desired):
        all_id = self.groups.get("All")
        for p in current:
            name = p["name"]
            if name.startswith(PREFIX):
                if name not in desired:
                    self.delete(f"/policies/{p['id']}", f"delete policy {name}")
                continue
            if not p.get("enabled"):
                continue
            rules = [_rule_body(r) for r in p.get("rules") or []]
            all_to_all = any(all_id in r["sources"] and all_id in r["destinations"] for r in rules)
            if self.cfg["strict"] or (self.cfg["disableAllToAll"] and all_to_all):
                reason = "All -> All" if all_to_all else "not managed by netbird-gitops (strict)"
                body = {"name": name, "description": p.get("description") or "", "enabled": False,
                        "source_posture_checks": p.get("source_posture_checks") or [], "rules": rules}
                self.api.write("PUT", f"/policies/{p['id']}", body, f"disable policy {name}: {reason}")

    def cleanup(self, nid, orphan_resources, wanted_groups, groups_before):
        for r in orphan_resources:
            if self.cfg["strict"]:
                self.delete(f"/networks/{nid}/resources/{r['id']}", f"delete resource {r['name']}")
            else:
                self.warn(f"resource {r['name']} is not declared (kept: strict is off)")
        for name, gid in sorted(groups_before.items()):
            if name.startswith(PREFIX) and name not in wanted_groups:
                self.delete(f"/groups/{gid}", f"delete group {name}")

    def users(self):
        cfg = self.cfg
        user_gids = {self.groups[g]: g for g in cfg["userGroups"]}
        admins = cfg["consoleAdmins"]
        members = cfg["members"]
        found = set()
        for u in self.api.get("/users"):
            if u.get("is_service_user"):
                continue
            email = (u.get("email") or "").lower()
            current = set(u.get("auto_groups") or [])
            if members is not None:
                found.add(email)
                if email in members:
                    names = members[email]
                elif cfg["strict"]:
                    names = []
                else:
                    continue
                target = (current - set(user_gids)) | {self.groups[g] for g in names}
            else:
                names = [user_gids[g] for g in current if g in user_gids]
                target = current
            if members is not None and email in members and u.get("pending_approval"):
                if cfg["approveMembers"]:
                    self.api.write("POST", f"/users/{u['id']}/approve", None, f"approve user {email}")
                else:
                    self.warn(f"user {email} is in members but pending approval (approveMembers is off)")
            role = u.get("role")
            # Console roles are managed only when an admins group is declared.
            if admins and role in MANAGED_ROLES and (names or members is not None):
                role = "admin" if admins in names else "user"
            if role != u.get("role") or target != current:
                parts = []
                if role != u.get("role"):
                    parts.append(f"role {u.get('role')} -> {role}")
                if target != current:
                    gained = sorted(user_gids.get(g, g) for g in target - current)
                    lost = sorted(user_gids.get(g, g) for g in current - target)
                    parts += [f"+{g}" for g in gained] + [f"-{g}" for g in lost]
                self.api.write("PUT", f"/users/{u['id']}",
                               {"role": role, "auto_groups": sorted(target), "is_blocked": bool(u.get("is_blocked"))},
                               f"update user {email}: {' '.join(parts)}")
            elif members is None and not names and role in MANAGED_ROLES:
                self.warn(f"user {email} is in no user group (left as is)")
        for email in sorted(set(members or {}) - found):
            self.log(f"user {email} has not signed up yet")

    def router_online(self):
        rid = self.groups[self.cfg["network"]["routerGroup"]]
        peers = [p for p in self.api.get("/peers") if rid in _ids(p.get("groups"))]
        if not peers:
            self.error(f"no peer in router group {self.cfg['network']['routerGroup']}: resources are unreachable")
        elif not any(p.get("connected") for p in peers):
            self.error(f"router peer(s) offline: {', '.join(sorted(p['name'] for p in peers))}")

    # -- entry point -----------------------------------------------------------

    def run(self):
        cfg = self.cfg
        self.settings()
        access = self.access()
        wanted_groups = {access_group_name(g, proto, ports) for g, proto, ports in access}
        groups_before = self.ensure_groups(
            list(cfg["userGroups"]) + [cfg["network"]["routerGroup"]] + sorted(wanted_groups))
        nid, is_new = self.network()
        orphans = self.sync_resources(nid, is_new, self.resources(access))
        self.sync_router(nid, is_new)
        desired = self.desired_policies(access)
        current = self.sync_policies(desired)
        self.revoke_policies(current, desired)
        self.cleanup(nid, orphans, wanted_groups, groups_before)
        self.users()
        if cfg["checkRouterOnline"]:
            self.router_online()
        verb = "planned" if self.api.dry_run else "applied"
        self.log(f"{self.api.changes} change(s) {verb}")
        return 1 if self.errors else 0
