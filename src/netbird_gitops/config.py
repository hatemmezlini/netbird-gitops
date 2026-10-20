"""Desired state: loading, defaults and validation.

The configuration is a JSON document (the Helm chart renders it from values.yaml).
See README.md for the full reference.
"""

import ipaddress
import json
import re

PROTOCOLS = ("tcp", "udp", "icmp", "all")
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
DOMAIN_RE = re.compile(r"^(\*\.)?([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class ConfigError(Exception):
    pass


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from None
    return normalize(raw)


def _address_kind(address):
    """Return 'subnet', 'host' or 'domain' (the NetBird resource types)."""
    try:
        net = ipaddress.ip_network(address, strict=True)
    except ValueError:
        if DOMAIN_RE.match(address):
            return "domain"
        raise ConfigError(f"invalid address {address!r}: expected an IP, a CIDR or a domain") from None
    return "host" if net.num_addresses == 1 else "subnet"


def _ports(value, where):
    ports = value if isinstance(value, list) else [value]
    out = []
    for p in ports:
        if isinstance(p, bool) or not isinstance(p, int) or not 1 <= p <= 65535:
            raise ConfigError(f"{where}: invalid port {p!r}")
        out.append(p)
    return sorted(set(out))


def normalize(raw):
    """Validate the raw document and return it with every default filled in."""
    if not isinstance(raw, dict):
        raise ConfigError("the configuration must be an object")
    known = {"strict", "disableAllToAll", "settings", "adminsGroup", "userGroups", "users",
             "approveListedUsers", "network", "tools", "portal", "checkRouterOnline"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"unknown keys: {', '.join(unknown)}")

    cfg = {
        "strict": bool(raw.get("strict", True)),
        "disableAllToAll": bool(raw.get("disableAllToAll", True)),
        "settings": raw.get("settings") or {},
        "adminsGroup": raw.get("adminsGroup"),
        "userGroups": list(raw.get("userGroups") or []),
        "users": raw.get("users"),
        "approveListedUsers": bool(raw.get("approveListedUsers", True)),
        "checkRouterOnline": bool(raw.get("checkRouterOnline", True)),
    }
    if not isinstance(cfg["settings"], dict):
        raise ConfigError("settings must be an object")

    groups = cfg["userGroups"]
    if not groups:
        raise ConfigError("userGroups must list at least one group")
    if len(set(groups)) != len(groups):
        raise ConfigError("userGroups contains duplicates")
    for g in groups:
        if not isinstance(g, str) or not g or g.startswith("gitops-") or g == "All":
            raise ConfigError(f"invalid user group {g!r} (reserved or empty)")
    if cfg["adminsGroup"] is not None and cfg["adminsGroup"] not in groups:
        raise ConfigError("adminsGroup must be one of userGroups")

    if cfg["users"] is not None:
        if not isinstance(cfg["users"], dict):
            raise ConfigError("users must map an e-mail to a list of groups")
        users = {}
        for email, member_of in cfg["users"].items():
            if "@" not in email:
                raise ConfigError(f"users: {email!r} is not an e-mail address")
            member_of = list(member_of or [])
            for g in member_of:
                if g not in groups:
                    raise ConfigError(f"users: {email}: group {g!r} is not in userGroups")
            users[email.lower()] = sorted(set(member_of))
        cfg["users"] = users

    net = raw.get("network")
    if not isinstance(net, dict) or not net.get("name") or not net.get("routerGroup"):
        raise ConfigError("network.name and network.routerGroup are required")
    metric = net.get("metric", 9999)
    if not isinstance(metric, int) or not 1 <= metric <= 9999:
        raise ConfigError("network.metric must be between 1 and 9999")
    cfg["network"] = {
        "name": net["name"],
        "description": net.get("description", ""),
        "routerGroup": net["routerGroup"],
        "masquerade": bool(net.get("masquerade", True)),
        "metric": metric,
    }

    tools = []
    seen = set()
    for i, t in enumerate(raw.get("tools") or []):
        where = f"tools[{i}]"
        if not isinstance(t, dict) or not t.get("name") or not t.get("address"):
            raise ConfigError(f"{where}: name and address are required")
        name = t["name"]
        if not NAME_RE.match(name) or name == "portal":
            raise ConfigError(f"{where}: invalid or reserved name {name!r} (lowercase, digits, dashes)")
        if name in seen:
            raise ConfigError(f"{where}: duplicate name {name!r}")
        seen.add(name)
        protocol = t.get("protocol", "tcp")
        if protocol not in PROTOCOLS:
            raise ConfigError(f"{where}: protocol must be one of {', '.join(PROTOCOLS)}")
        ports = [] if protocol in ("icmp", "all") else _ports(t.get("ports", [443]), where)
        if protocol in ("tcp", "udp") and not ports:
            raise ConfigError(f"{where}: ports are required for {protocol}")
        tool_groups = list(t.get("groups") or [])
        if not tool_groups:
            raise ConfigError(f"{where}: groups must list at least one user group")
        for g in tool_groups:
            if g not in groups:
                raise ConfigError(f"{where}: group {g!r} is not in userGroups")
        address = t["address"].lower()
        kind = _address_kind(address)
        url = t.get("url")
        if url and not re.match(r"^https?://", url):
            raise ConfigError(f"{where}: url must start with https:// or http://")
        if url is None and kind == "domain" and not address.startswith("*.") and ports == [443]:
            url = f"https://{address}"
        tools.append({
            "name": name,
            "title": t.get("title", name),
            "description": t.get("description", ""),
            "address": address,
            "kind": kind,
            "url": url or None,
            "icon": t.get("icon", "globe"),
            "groups": sorted(set(tool_groups)),
            "protocol": protocol,
            "ports": ports,
            "portal": bool(t.get("portal", True)),
        })
    cfg["tools"] = tools

    # The portal itself is a resource reachable by every user group. It is not a card.
    portal = raw.get("portal") or {}
    if portal.get("address"):
        address = portal["address"].lower()
        cfg["portal"] = {
            "address": address,
            "kind": _address_kind(address),
            "ports": _ports(portal.get("ports", [443]), "portal"),
        }
    else:
        cfg["portal"] = None
    return cfg
