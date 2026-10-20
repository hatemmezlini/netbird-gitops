import copy
import unittest

from fake_netbird import FakeNetBird
from netbird_gitops import config
from netbird_gitops.reconcile import Reconciler

BASE = {
    "settings": {"regular_users_view_blocked": True, "extra": {"user_approval_required": True}},
    "adminsGroup": "admins",
    "userGroups": ["admins", "developers"],
    "network": {"name": "production", "routerGroup": "routers"},
    "portal": {"address": "portal.vpn.example.com"},
    "tools": [
        {"name": "grafana", "address": "grafana.vpn.example.com", "groups": ["admins", "developers"]},
        {"name": "prometheus", "address": "prometheus.vpn.example.com", "groups": ["admins"]},
        {"name": "db", "address": "10.0.0.5", "ports": [5432], "groups": ["developers"]},
    ],
}


def cfg(**overrides):
    raw = copy.deepcopy(BASE)
    raw.update(overrides)
    return config.normalize(raw)


def run(nb, conf):
    nb.changes = 0
    code = Reconciler(nb, conf, log=lambda _m: None).run()
    return code, nb.changes


def seeded():
    nb = FakeNetBird()
    nb.add_group("routers")
    nb.add_peer("k8s-router", ["routers"])
    return nb


class ReconcileTest(unittest.TestCase):
    def test_converges_then_idempotent(self):
        nb = seeded()
        code, changes = run(nb, cfg())
        self.assertEqual(code, 0)
        self.assertGreater(changes, 0)
        self.assertEqual(run(nb, cfg()), (0, 0))

        net = nb.by_name(nb.networks, "production")
        res = {r["name"]: r for r in nb.resources[net["id"]].values()}
        self.assertEqual(sorted(res), ["db", "grafana", "portal", "prometheus"])
        self.assertEqual(nb.group_names(g["id"] for g in res["grafana"]["groups"]),
                         ["gitops-admins-tcp-443", "gitops-developers-tcp-443"])
        self.assertEqual(nb.group_names(g["id"] for g in res["db"]["groups"]), ["gitops-developers-tcp-5432"])
        self.assertEqual(nb.group_names(g["id"] for g in res["portal"]["groups"]),
                         ["gitops-admins-tcp-443", "gitops-developers-tcp-443"])

        router = next(iter(nb.routers[net["id"]].values()))
        self.assertEqual(router["peer_groups"], [nb.gid("routers")])

        dev = nb.by_name(nb.policies, "gitops-developers")
        self.assertEqual(sorted((r["protocol"], tuple(r["ports"])) for r in dev["rules"]),
                         [("tcp", ("443",)), ("tcp", ("5432",))])
        self.assertTrue(all(not r["bidirectional"] for r in dev["rules"]))
        self.assertTrue(nb.account["settings"]["regular_users_view_blocked"])
        self.assertTrue(nb.account["settings"]["extra"]["user_approval_required"])
        self.assertFalse(nb.account["settings"]["extra"]["peer_approval_enabled"])

    def test_strict_disables_unmanaged_and_all_to_all(self):
        nb = seeded()
        all_id = nb.gid("All")
        default = nb.add_policy("Default", [all_id], [all_id])
        manual = nb.add_policy("manual", [nb.gid("routers")], [nb.gid("routers")])
        run(nb, cfg())
        self.assertFalse(nb.policies[default]["enabled"])
        self.assertFalse(nb.policies[manual]["enabled"])
        self.assertIn(manual, nb.policies, "unmanaged policies are disabled, never deleted")
        self.assertEqual(run(nb, cfg()), (0, 0))

    def test_non_strict_keeps_manual_policies_but_not_all_to_all(self):
        nb = seeded()
        all_id = nb.gid("All")
        default = nb.add_policy("Default", [all_id], [all_id])
        manual = nb.add_policy("manual", [nb.gid("routers")], [nb.gid("routers")])
        run(nb, cfg(strict=False))
        self.assertFalse(nb.policies[default]["enabled"])
        self.assertTrue(nb.policies[manual]["enabled"])

    def test_removed_tool_is_cleaned_up(self):
        nb = seeded()
        run(nb, cfg())
        tools = [t for t in BASE["tools"] if t["name"] != "db"]
        code, _ = run(nb, cfg(tools=tools))
        self.assertEqual(code, 0)
        net = nb.by_name(nb.networks, "production")
        self.assertNotIn("db", [r["name"] for r in nb.resources[net["id"]].values()])
        self.assertIsNone(nb.by_name(nb.groups, "gitops-developers-tcp-5432"))
        dev = nb.by_name(nb.policies, "gitops-developers")
        self.assertEqual([r["ports"] for r in dev["rules"]], [["443"]])
        self.assertEqual(run(nb, cfg(tools=tools)), (0, 0))

    def test_group_losing_all_access_loses_its_policy(self):
        nb = seeded()
        run(nb, cfg())
        conf = cfg(portal={}, tools=[t for t in BASE["tools"] if t["name"] == "prometheus"])
        run(nb, conf)
        self.assertIsNone(nb.by_name(nb.policies, "gitops-developers"))
        self.assertIsNone(nb.by_name(nb.groups, "gitops-developers-tcp-443"))
        self.assertIsNotNone(nb.by_name(nb.groups, "developers"), "user groups are never deleted")

    def test_users_from_git(self):
        nb = seeded()
        nb.add_group("admins")
        nb.add_group("developers")
        nb.add_group("laptops")
        alice = nb.add_user("Alice@example.com", groups=["laptops"], pending=True)
        bob = nb.add_user("bob@example.com", role="admin", groups=["admins"])
        owner = nb.add_user("owner@example.com", role="owner", groups=["admins"])
        bot = nb.add_user("", role="admin", service=True)
        conf = cfg(users={"alice@example.com": ["admins"], "owner@example.com": ["admins"],
                          "carol@example.com": ["developers"]})
        run(nb, conf)
        self.assertFalse(nb.users[alice]["pending_approval"])
        self.assertEqual(nb.users[alice]["role"], "admin")
        self.assertEqual(nb.group_names(nb.users[alice]["auto_groups"]), ["admins", "laptops"])
        # Not listed + strict: loses its user groups and its admin role.
        self.assertEqual(nb.users[bob]["auto_groups"], [])
        self.assertEqual(nb.users[bob]["role"], "user")
        self.assertEqual(nb.users[owner]["role"], "owner")
        self.assertEqual(nb.users[bot]["role"], "admin")
        self.assertEqual(run(nb, conf), (0, 0))

    def test_users_from_console_only_sync_roles(self):
        nb = seeded()
        nb.add_group("admins")
        nb.add_group("developers")
        dev = nb.add_user("dev@example.com", role="admin", groups=["developers"])
        adm = nb.add_user("adm@example.com", groups=["admins"])
        loner = nb.add_user("loner@example.com", role="admin")
        run(nb, cfg())
        self.assertEqual(nb.users[dev]["role"], "user")
        self.assertEqual(nb.users[adm]["role"], "admin")
        self.assertEqual(nb.users[loner]["role"], "admin", "no user group: left as is")
        self.assertEqual(nb.group_names(nb.users[dev]["auto_groups"]), ["developers"])

    def test_roles_untouched_without_admins_group(self):
        nb = seeded()
        nb.add_group("admins")
        nb.add_group("developers")
        adm = nb.add_user("adm@example.com", role="admin", groups=["developers"])
        raw = copy.deepcopy(BASE)
        del raw["adminsGroup"]
        conf = config.normalize({**raw, "users": {"adm@example.com": ["developers"]}})
        run(nb, conf)
        self.assertEqual(nb.users[adm]["role"], "admin")
        self.assertEqual(run(nb, conf), (0, 0))

    def test_dry_run_writes_nothing(self):
        nb = FakeNetBird(dry_run=True)
        nb.add_group("routers")
        nb.add_peer("k8s-router", ["routers"])
        nb.add_policy("Default", [nb.gid("All")], [nb.gid("All")])
        before = copy.deepcopy((nb.groups, nb.policies, nb.networks, nb.account))
        code, changes = run(nb, cfg())
        self.assertEqual(code, 0)
        self.assertGreater(changes, 0)
        self.assertEqual(before, (nb.groups, nb.policies, nb.networks, nb.account))
        self.assertTrue(all(method == "GET" for method, _ in nb.calls))

    def test_router_offline_fails_the_run(self):
        nb = FakeNetBird()
        nb.add_group("routers")
        nb.add_peer("k8s-router", ["routers"], connected=False)
        self.assertEqual(run(nb, cfg())[0], 1)
        self.assertEqual(run(nb, cfg(checkRouterOnline=False))[0], 0)

    def test_drifted_objects_are_restored(self):
        nb = seeded()
        run(nb, cfg())
        pol = nb.by_name(nb.policies, "gitops-admins")
        pol["rules"][0]["ports"] = ["1-65535"]
        net = nb.by_name(nb.networks, "production")
        res = nb.by_name(nb.resources[net["id"]], "prometheus")
        res["address"] = "evil.example.com"
        router = next(iter(nb.routers[net["id"]].values()))
        router["masquerade"] = False
        self.assertEqual(run(nb, cfg())[1], 3)
        self.assertEqual(run(nb, cfg()), (0, 0))
        self.assertEqual(nb.by_name(nb.resources[net["id"]], "prometheus")["address"],
                         "prometheus.vpn.example.com")


if __name__ == "__main__":
    unittest.main()
