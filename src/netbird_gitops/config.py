"""Desired state: loading, defaults and validation.

The configuration is a JSON document; the Helm chart renders it from its values.

  access         {group: [resource, ...]}, ["*"] for every resource
  resources      {name: {address, protocol, ports, title, description, url, ...}}
  members        {e-mail: [group, ...]}, or null to manage membership in the console
  consoleAdmins  group whose members get the console role "admin"
  network        {name, description, routerGroup, masquerade, metric}
  account        readable NetBird account settings, plus "raw" API settings
  strict, disableAllToAll, approveMembers, checkRouterOnline
  portal         {address, ports}: the portal host, reachable by every group

Unknown keys are errors: a typo must never silently fall back to a default.
See README.md for the reference.
"""

import ipaddress
import json
import re

PROTOCOLS = ("tcp", "udp", "icmp", "all")
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
DOMAIN_RE = re.compile(r"^(\*\.)?([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
DURATION_RE = re.compile(r"^(?:\d+[smhd])+$")
DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

RESOURCE_KEYS = {"address", "protocol", "ports", "title", "description", "url", "probe", "icon", "showInPortal"}
NETWORK_KEYS = {"name", "description", "routerGroup", "masquerade", "metric"}
# Readable account settings -> NetBird AccountSettings fields.
ACCOUNT_FLAGS = {
    "restrictRegularUsers": ("regular_users_view_blocked",),
    "groupsPropagation": ("groups_propagation_enabled",),
    "userApproval": ("extra", "user_approval_required"),
    "peerApproval": ("extra", "peer_approval_enabled"),
}
ACCOUNT_DURATIONS = {
    "peerLoginExpiration": ("peer_login_expiration_enabled", "peer_login_expiration"),
    "peerInactivityExpiration": ("peer_inactivity_expiration_enabled", "peer_inactivity_expiration"),
}
TOP_KEYS = {"access", "resources", "members", "consoleAdmins", "network", "account", "strict",
            "disableAllToAll", "approveMembers", "checkRouterOnline", "portal"}


class ConfigError(Exception):
    pass


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from None
    return normalize(raw)


def _object(value, where):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a map")
    return value


def _no_unknown(obj, allowed, where):
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {', '.join(unknown)} (allowed: {', '.join(sorted(allowed))})")


def _bool(value, where):
    if not isinstance(value, bool):
        raise ConfigError(f"{where} must be true or false")
    return value


def _address_kind(address, where):
    """Return 'subnet', 'host' or 'domain' (the NetBird resource types)."""
    try:
        net = ipaddress.ip_network(address, strict=True)
    except ValueError:
        if DOMAIN_RE.match(address):
            return "domain"
        raise ConfigError(f"{where}: invalid address {address!r} (expected an IP, a CIDR or a domain)") from None
    return "host" if net.num_addresses == 1 else "subnet"


def _ports(value, where):
    ports = value if isinstance(value, list) else [value]
    out = []
    for p in ports:
        if isinstance(p, bool) or not isinstance(p, int) or not 1 <= p <= 65535:
            raise ConfigError(f"{where}: invalid port {p!r}")
        out.append(p)
    return sorted(set(out))


def _url(value, where):
    if value is not None and not (isinstance(value, str) and re.match(r"^https?://", value)):
        raise ConfigError(f"{where} must start with https:// or http://")
    return value or None


def duration(value, where):
    """'48h', '7d', '1h30m' -> seconds."""
    if not isinstance(value, str) or not DURATION_RE.match(value):
        raise ConfigError(f"{where}: {value!r} is not a duration such as 48h, 7d or 1h30m (or false)")
    seconds = sum(int(n) * DURATION_UNITS[u] for n, u in re.findall(r"(\d+)([smhd])", value))
    if seconds <= 0:
        raise ConfigError(f"{where} must be longer than 0")
    return seconds


def account_settings(account):
    """Readable account settings -> partial NetBird AccountSettings."""
    account = _object(account, "account")
    _no_unknown(account, set(ACCOUNT_FLAGS) | set(ACCOUNT_DURATIONS) | {"raw"}, "account")
    settings = json.loads(json.dumps(_object(account.get("raw"), "account.raw")))
    for key, path in ACCOUNT_FLAGS.items():
        if account.get(key) is not None:
            target = settings
            for part in path[:-1]:
                target = target.setdefault(part, {})
            target[path[-1]] = _bool(account[key], f"account.{key}")
    for key, (enabled, seconds) in ACCOUNT_DURATIONS.items():
        value = account.get(key)
        if value is None:
            continue
        if value is False:
            settings[enabled] = False
        else:
            settings[enabled] = True
            settings[seconds] = duration(value, f"account.{key}")
    return settings


def normalize(raw):
    """Validate the raw document and return it with every default filled in."""
    if not isinstance(raw, dict):
        raise ConfigError("the configuration must be a map")
    _no_unknown(raw, TOP_KEYS, "configuration")

    cfg = {
        "strict": _bool(raw.get("strict", True), "strict"),
        "disableAllToAll": _bool(raw.get("disableAllToAll", True), "disableAllToAll"),
        "approveMembers": _bool(raw.get("approveMembers", True), "approveMembers"),
        "checkRouterOnline": _bool(raw.get("checkRouterOnline", True), "checkRouterOnline"),
        "settings": account_settings(raw.get("account")),
    }

    # Resources: what can be reached.
    resources = _object(raw.get("resources"), "resources")
    out = {}
    for name, r in resources.items():
        where = f"resources.{name}"
        if not NAME_RE.match(name) or name == "portal":
            raise ConfigError(f"{where}: invalid or reserved name (lowercase letters, digits, dashes)")
        r = _object(r, where)
        _no_unknown(r, RESOURCE_KEYS, where)
        if not r.get("address"):
            raise ConfigError(f"{where}: address is required")
        protocol = r.get("protocol", "tcp")
        if protocol not in PROTOCOLS:
            raise ConfigError(f"{where}: protocol must be one of {', '.join(PROTOCOLS)}")
        if protocol in ("icmp", "all"):
            if "ports" in r:
                raise ConfigError(f"{where}: ports do not apply to protocol {protocol}")
            ports = []
        else:
            ports = _ports(r.get("ports", [443]), where)
        address = str(r["address"]).lower()
        kind = _address_kind(address, where)
        url = _url(r.get("url"), f"{where}.url")
        if url is None and kind == "domain" and not address.startswith("*.") and protocol == "tcp" and ports == [443]:
            url = f"https://{address}"
        out[name] = {
            "name": name,
            "title": r.get("title", name),
            "description": r.get("description", ""),
            "address": address,
            "kind": kind,
            "url": url,
            "probe": _url(r.get("probe"), f"{where}.probe"),
            "icon": r.get("icon", "globe"),
            "protocol": protocol,
            "ports": ports,
            "showInPortal": _bool(r.get("showInPortal", True), f"{where}.showInPortal"),
            "groups": [],
        }

    # Access: who can reach what. Its keys are the groups of people.
    access = _object(raw.get("access"), "access")
    if not access:
        raise ConfigError("access must list at least one group")
    for group, names in access.items():
        where = f"access.{group}"
        if not isinstance(group, str) or not group or group.startswith("gitops-") or group == "All":
            raise ConfigError(f"{where}: invalid group name (empty, reserved prefix gitops- or All)")
        if names is None:
            names = []
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ConfigError(f"{where} must be a list of resource names, or [\"*\"]")
        if "*" in names:
            if len(names) > 1:
                raise ConfigError(f"{where}: \"*\" already means every resource; list nothing else")
            names = list(out)
        for n in names:
            if n not in out:
                raise ConfigError(f"{where}: unknown resource {n!r}")
            out[n]["groups"].append(group)
    for r in out.values():
        if not r["groups"]:
            raise ConfigError(f"resources.{r['name']}: no group in access can reach it (grant it or remove it)")
        r["groups"].sort()
    cfg["userGroups"] = list(access)
    cfg["resources"] = sorted(out.values(), key=lambda r: r["name"])

    admins = raw.get("consoleAdmins")
    if admins is not None and admins not in access:
        raise ConfigError(f"consoleAdmins: {admins!r} is not a group in access")
    cfg["consoleAdmins"] = admins

    members = raw.get("members")
    if members is not None:
        members = _object(members, "members")
        cfg["members"] = {}
        for email, groups in members.items():
            where = f"members.{email}"
            if not isinstance(email, str) or not re.match(r"^[^@\s]+@[^@\s]+$", email):
                raise ConfigError(f"{where}: not an e-mail address")
            groups = groups or []
            if not isinstance(groups, list):
                raise ConfigError(f"{where} must be a list of groups")
            for g in groups:
                if g not in access:
                    raise ConfigError(f"{where}: {g!r} is not a group in access")
            cfg["members"][email.lower()] = sorted(set(groups))
    else:
        cfg["members"] = None

    net = _object(raw.get("network"), "network")
    _no_unknown(net, NETWORK_KEYS, "network")
    if not net.get("name") or not net.get("routerGroup"):
        raise ConfigError("network.name and network.routerGroup are required")
    metric = net.get("metric", 9999)
    if isinstance(metric, bool) or not isinstance(metric, int) or not 1 <= metric <= 9999:
        raise ConfigError("network.metric must be between 1 and 9999")
    cfg["network"] = {
        "name": net["name"],
        "description": net.get("description", ""),
        "routerGroup": net["routerGroup"],
        "masquerade": _bool(net.get("masquerade", True), "network.masquerade"),
        "metric": metric,
    }

    portal = _object(raw.get("portal"), "portal")
    _no_unknown(portal, {"address", "ports"}, "portal")
    if portal.get("address"):
        address = str(portal["address"]).lower()
        cfg["portal"] = {
            "address": address,
            "kind": _address_kind(address, "portal"),
            "ports": _ports(portal.get("ports", [443]), "portal"),
        }
    else:
        cfg["portal"] = None
    return cfg
