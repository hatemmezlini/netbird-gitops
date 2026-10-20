import unittest

from netbird_gitops.config import ConfigError, normalize

MINIMAL = {
    "userGroups": ["admins"],
    "network": {"name": "production", "routerGroup": "routers"},
}


def with_(**kw):
    return {**MINIMAL, **kw}


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = normalize(with_(tools=[{"name": "grafana", "address": "Grafana.vpn.example.com", "groups": ["admins"]}]))
        self.assertTrue(cfg["strict"])
        self.assertTrue(cfg["disableAllToAll"])
        tool = cfg["tools"][0]
        self.assertEqual(tool["address"], "grafana.vpn.example.com")
        self.assertEqual(tool["url"], "https://grafana.vpn.example.com")
        self.assertEqual((tool["protocol"], tool["ports"]), ("tcp", [443]))
        self.assertEqual(cfg["network"]["metric"], 9999)
        self.assertIsNone(cfg["portal"])

    def test_no_default_url_for_non_web_tools(self):
        cfg = normalize(with_(tools=[
            {"name": "db", "address": "10.0.0.5", "ports": 5432, "groups": ["admins"]},
            {"name": "all", "address": "*.vpn.example.com", "groups": ["admins"]},
            {"name": "lan", "address": "10.1.0.0/24", "protocol": "all", "groups": ["admins"]},
        ]))
        self.assertEqual([t["url"] for t in cfg["tools"]], [None, None, None])
        self.assertEqual([t["kind"] for t in cfg["tools"]], ["host", "domain", "subnet"])
        self.assertEqual(cfg["tools"][2]["ports"], [])

    def test_rejections(self):
        cases = {
            "unknown key": with_(tool=[]),
            "no user group": {**MINIMAL, "userGroups": []},
            "reserved group": {**MINIMAL, "userGroups": ["gitops-x"]},
            "admins outside userGroups": with_(adminsGroup="root"),
            "no router group": {**MINIMAL, "network": {"name": "production"}},
            "unknown tool group": with_(tools=[{"name": "a", "address": "a.example.com", "groups": ["x"]}]),
            "tool without groups": with_(tools=[{"name": "a", "address": "a.example.com"}]),
            "bad address": with_(tools=[{"name": "a", "address": "not an address", "groups": ["admins"]}]),
            "bad port": with_(tools=[{"name": "a", "address": "a.example.com", "ports": [0], "groups": ["admins"]}]),
            "bad name": with_(tools=[{"name": "A_b", "address": "a.example.com", "groups": ["admins"]}]),
            "reserved name": with_(tools=[{"name": "portal", "address": "a.example.com", "groups": ["admins"]}]),
            "duplicate": with_(tools=[{"name": "a", "address": "a.example.com", "groups": ["admins"]}] * 2),
            "unknown user group": with_(users={"a@example.com": ["x"]}),
            "bad e-mail": with_(users={"alice": ["admins"]}),
        }
        for label, raw in cases.items():
            with self.subTest(label), self.assertRaises(ConfigError):
                normalize(raw)


if __name__ == "__main__":
    unittest.main()
