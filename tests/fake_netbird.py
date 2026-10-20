"""In-memory NetBird management API, enough for the reconciler.

It subclasses the real client and only replaces the HTTP layer, so dry-run handling and
change counting are the production code.
"""

import copy
import itertools
import re

from netbird_gitops.api import ApiError, NetBirdApi


class FakeNetBird(NetBirdApi):
    def __init__(self, dry_run=False):
        super().__init__("http://fake", "token", dry_run=dry_run, log=lambda _m: None)
        self.ids = itertools.count(1)
        self.calls = []
        self.account = {"id": "acc", "settings": {
            "peer_login_expiration_enabled": True,
            "peer_login_expiration": 86400,
            "regular_users_view_blocked": False,
            "groups_propagation_enabled": True,
            "embedded_idp_enabled": True,
            "extra": {"user_approval_required": False, "peer_approval_enabled": False},
        }}
        self.groups = {}
        self.policies = {}
        self.networks = {}
        self.resources = {}
        self.routers = {}
        self.users = {}
        self.peers = []
        self.add_group("All")

    # -- seeding ---------------------------------------------------------------

    def new_id(self, kind):
        return f"{kind}{next(self.ids)}"

    def add_group(self, name):
        gid = self.new_id("g")
        self.groups[gid] = {"id": gid, "name": name, "peers": [], "resources": []}
        return gid

    def gid(self, name):
        return next(g["id"] for g in self.groups.values() if g["name"] == name)

    def add_policy(self, name, sources, destinations, enabled=True, protocol="all", ports=None):
        pid = self.new_id("p")
        self.policies[pid] = {"id": pid, "name": name, "description": "", "enabled": enabled,
                              "source_posture_checks": [], "rules": [{
                                  "id": self.new_id("r"), "name": name, "description": "",
                                  "enabled": True, "action": "accept", "bidirectional": True,
                                  "protocol": protocol, "ports": ports or [],
                                  "sources": [self.gmin(g) for g in sources],
                                  "destinations": [self.gmin(g) for g in destinations]}]}
        return pid

    def add_user(self, email, role="user", groups=(), service=False, pending=False):
        uid = self.new_id("u")
        self.users[uid] = {"id": uid, "email": email, "name": email, "role": role,
                           "auto_groups": [self.gid(g) for g in groups], "status": "active",
                           "is_service_user": service, "is_blocked": False,
                           "pending_approval": pending}
        return uid

    def add_peer(self, name, groups, connected=True):
        self.peers.append({"id": self.new_id("peer"), "name": name, "connected": connected,
                           "groups": [self.gmin(self.gid(g)) for g in groups]})

    def gmin(self, gid):
        g = self.groups[gid]
        return {"id": gid, "name": g["name"]}

    def by_name(self, store, name):
        return next((o for o in store.values() if o["name"] == name), None)

    def group_names(self, ids):
        return sorted(self.groups[i]["name"] for i in ids)

    # -- HTTP layer ------------------------------------------------------------

    def _request(self, method, path, body=None):
        self.calls.append((method, path))
        body = copy.deepcopy(body)
        for pattern, handler in self.routes():
            m = re.fullmatch(pattern, f"{method} {path}")
            if m:
                return copy.deepcopy(handler(body, *m.groups()))
        raise ApiError(f"{method} {path}: HTTP 404 no route")

    def routes(self):
        return [
            (r"GET /accounts", lambda b: [self.account]),
            (r"PUT /accounts/(\w+)", self.put_account),
            (r"GET /groups", lambda b: list(self.groups.values())),
            (r"POST /groups", self.post_group),
            (r"DELETE /groups/(\w+)", self.delete_group),
            (r"GET /policies", lambda b: list(self.policies.values())),
            (r"POST /policies", lambda b: self.put_policy(b, self.new_id("p"))),
            (r"PUT /policies/(\w+)", self.put_policy),
            (r"DELETE /policies/(\w+)", lambda b, pid: self.policies.pop(pid) and None),
            (r"GET /networks", lambda b: list(self.networks.values())),
            (r"POST /networks", self.post_network),
            (r"PUT /networks/(\w+)", lambda b, nid: self.networks[nid].update(b)),
            (r"GET /networks/(\w+)/resources", lambda b, nid: list(self.resources[nid].values())),
            (r"POST /networks/(\w+)/resources", lambda b, nid: self.put_resource(b, nid, self.new_id("res"))),
            (r"PUT /networks/(\w+)/resources/(\w+)", self.put_resource),
            (r"DELETE /networks/(\w+)/resources/(\w+)", lambda b, nid, rid: self.resources[nid].pop(rid) and None),
            (r"GET /networks/(\w+)/routers", lambda b, nid: list(self.routers[nid].values())),
            (r"POST /networks/(\w+)/routers", lambda b, nid: self.put_router(b, nid, self.new_id("rt"))),
            (r"PUT /networks/(\w+)/routers/(\w+)", self.put_router),
            (r"DELETE /networks/(\w+)/routers/(\w+)", lambda b, nid, rid: self.routers[nid].pop(rid) and None),
            (r"GET /users", lambda b: list(self.users.values())),
            (r"PUT /users/(\w+)", lambda b, uid: self.users[uid].update(b)),
            (r"POST /users/(\w+)/approve", lambda b, uid: self.users[uid].update(pending_approval=False)),
            (r"GET /peers", lambda b: self.peers),
        ]

    def put_account(self, body, _aid):
        for k in ("embedded_idp_enabled", "local_auth_disabled"):
            if k in body["settings"]:
                raise ApiError(f"read-only setting {k} sent")
        self.account["settings"] = {**body["settings"], "embedded_idp_enabled": True}

    def post_group(self, body):
        if self.by_name(self.groups, body["name"]):
            raise ApiError("HTTP 422 group exists")
        gid = self.add_group(body["name"])
        return self.groups[gid]

    def delete_group(self, _body, gid):
        used = any(gid in [g["id"] for r in p["rules"] for g in r["sources"] + r["destinations"]]
                   for p in self.policies.values())
        used = used or any(gid in [g["id"] for g in r["groups"]]
                           for rs in self.resources.values() for r in rs.values())
        if used:
            raise ApiError(f"DELETE /groups/{gid}: HTTP 400 group is in use")
        del self.groups[gid]

    def put_policy(self, body, pid):
        for rule in body["rules"]:
            rule.setdefault("id", self.new_id("r"))
            rule["sources"] = [self.gmin(g) for g in rule.get("sources") or []]
            rule["destinations"] = [self.gmin(g) for g in rule.get("destinations") or []]
        self.policies[pid] = {**body, "id": pid}
        return self.policies[pid]

    def post_network(self, body):
        nid = self.new_id("n")
        self.networks[nid] = {**body, "id": nid}
        self.resources[nid] = {}
        self.routers[nid] = {}
        return self.networks[nid]

    def put_resource(self, body, nid, rid):
        body["groups"] = [self.gmin(g) for g in body["groups"]]
        self.resources[nid][rid] = {**body, "id": rid, "type": "domain"}
        return self.resources[nid][rid]

    def put_router(self, body, nid, rid):
        self.routers[nid][rid] = {"peer": "", **body, "id": rid}
        return self.routers[nid][rid]
