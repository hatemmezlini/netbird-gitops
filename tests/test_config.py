import unittest

from netbird_gitops.config import ConfigError, normalize

MINIMAL = {
    "access": {"admins": ["grafana"]},
    "resources": {"grafana": {"address": "Grafana.vpn.example.com"}},
    "network": {"name": "production", "routerGroup": "routers"},
}


def with_(**kw):
    return {**MINIMAL, **kw}


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = normalize(MINIMAL)
        self.assertTrue(cfg["strict"])
        self.assertTrue(cfg["disableAllToAll"])
        self.assertIsNone(cfg["members"])
        self.assertIsNone(cfg["consoleAdmins"])
        self.assertIsNone(cfg["portal"])
        self.assertEqual(cfg["settings"], {})
        self.assertEqual(cfg["userGroups"], ["admins"])
        res = cfg["resources"][0]
        self.assertEqual(res["address"], "grafana.vpn.example.com")
        self.assertEqual(res["url"], "https://grafana.vpn.example.com")
        self.assertEqual((res["protocol"], res["ports"], res["groups"]), ("tcp", [443], ["admins"]))
        self.assertEqual(cfg["network"]["metric"], 9999)

    def test_access_is_the_inverse_of_the_matrix(self):
        cfg = normalize(with_(
            access={"admins": ["*"], "developers": ["grafana", "db"], "viewers": []},
            resources={
                "grafana": {"address": "grafana.vpn.example.com"},
                "prometheus": {"address": "prometheus.vpn.example.com"},
                "db": {"address": "10.0.0.5", "ports": 5432},
            },
        ))
        groups = {r["name"]: r["groups"] for r in cfg["resources"]}
        self.assertEqual(groups, {"db": ["admins", "developers"], "grafana": ["admins", "developers"],
                                  "prometheus": ["admins"]})
        self.assertEqual(cfg["userGroups"], ["admins", "developers", "viewers"])
        self.assertEqual([r["ports"] for r in cfg["resources"] if r["name"] == "db"], [[5432]])

    def test_no_default_url_for_non_web_resources(self):
        cfg = normalize(with_(
            access={"admins": ["*"]},
            resources={
                "db": {"address": "10.0.0.5", "ports": [5432]},
                "all": {"address": "*.vpn.example.com"},
                "lan": {"address": "10.1.0.0/24", "protocol": "all"},
            },
        ))
        self.assertEqual([r["url"] for r in cfg["resources"]], [None, None, None])
        self.assertEqual([r["kind"] for r in cfg["resources"]], ["domain", "host", "subnet"])

    def test_account_settings_are_translated(self):
        cfg = normalize(with_(account={
            "restrictRegularUsers": True,
            "groupsPropagation": True,
            "userApproval": True,
            "peerLoginExpiration": "2d",
            "peerInactivityExpiration": False,
            "raw": {"jwt_groups_enabled": False, "extra": {"network_traffic_logs_enabled": False}},
        }))
        self.assertEqual(cfg["settings"], {
            "regular_users_view_blocked": True,
            "groups_propagation_enabled": True,
            "peer_login_expiration_enabled": True,
            "peer_login_expiration": 172800,
            "peer_inactivity_expiration_enabled": False,
            "jwt_groups_enabled": False,
            "extra": {"user_approval_required": True, "network_traffic_logs_enabled": False},
        })
        self.assertEqual(normalize(with_(account={"peerLoginExpiration": "1h30m"}))["settings"]["peer_login_expiration"], 5400)

    def test_rejections(self):
        res = {"grafana": {"address": "grafana.vpn.example.com"}}
        cases = {
            "unknown top-level key": with_(tools=[]),
            "typo in a resource (port instead of ports)": with_(resources={"grafana": {"address": "a.example.com", "port": 5432}}),
            "typo in network": with_(network={"name": "n", "routerGroup": "r", "metrics": 1}),
            "typo in account": with_(account={"userApprovals": True}),
            "no group": with_(access={}),
            "reserved group": with_(access={"gitops-x": ["grafana"]}),
            "unknown resource in access": with_(access={"admins": ["grafana", "nope"]}),
            "star with other names": with_(access={"admins": ["*", "grafana"]}),
            "resource nobody can reach": with_(resources={**res, "db": {"address": "10.0.0.5", "ports": [5432]}}),
            "missing address": with_(resources={"grafana": {"title": "Grafana"}}),
            "bad address": with_(resources={"grafana": {"address": "not an address"}}),
            "bad port": with_(resources={"grafana": {"address": "a.example.com", "ports": [0]}}),
            "ports with icmp": with_(resources={"grafana": {"address": "10.0.0.1", "protocol": "icmp", "ports": [1]}}),
            "bad name": with_(access={"admins": ["A_b"]}, resources={"A_b": {"address": "a.example.com"}}),
            "reserved name": with_(access={"admins": ["portal"]}, resources={"portal": {"address": "a.example.com"}}),
            "bad url": with_(resources={"grafana": {"address": "a.example.com", "url": "ftp://a"}}),
            "consoleAdmins not in access": with_(consoleAdmins="root"),
            "member in unknown group": with_(members={"a@example.com": ["x"]}),
            "member without e-mail": with_(members={"alice": ["admins"]}),
            "bad duration": with_(account={"peerLoginExpiration": "2 days"}),
            "string boolean": with_(strict="false"),
            "missing router group": with_(network={"name": "production"}),
        }
        for label, raw in cases.items():
            with self.subTest(label), self.assertRaises(ConfigError):
                normalize(raw)


if __name__ == "__main__":
    unittest.main()
