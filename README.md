# netbird-gitops

Declarative access control for a self-hosted [NetBird](https://netbird.io), reconciled from Git,
plus a static portal that shows each user which internal tools they can reach.

One list of tools drives both:

```yaml
tools:
  - name: grafana
    title: Grafana
    address: grafana.vpn.example.com
    groups: [platform-admins, developers, viewers]
```

- **Reconciler**: a Kubernetes CronJob that makes NetBird match the declaration: groups,
  policies, the network, its resources and router, account settings, and optionally users.
  A change made by hand in the console is reverted at the next run.
- **Portal**: one HTML page served by nginx. It lists the tools as cards and checks from the
  browser which ones answer, so users can see what their groups give them.

The reconciler uses only the Python standard library; the portal is static HTML, CSS and a small
script. Developed against the NetBird management API v0.79.

## How access is modelled

For each user group and port set, the reconciler maintains:

| NetBird object | Name | Content |
|---|---|---|
| Group (destination) | `gitops-<group>-tcp-443` | the resources that group may reach on tcp/443 |
| Network resource | `<tool name>` | the tool address, member of the destination groups above |
| Policy | `gitops-<group>` | one one-way rule per port set: `<group>` -> `gitops-<group>-…` |
| Network router | — | the routing peers of `network.routerGroup` |

Rules are one way and always name their ports. Peers of different users never reach each
other unless you declare it.

**Ownership.** netbird-gitops owns objects prefixed `gitops-`, plus the declared network with its
resources and router. User groups and the router group are created if missing, never deleted.
It never touches peers, setup keys or tokens.

**strict mode** (default): every enabled policy not owned by netbird-gitops is *disabled* (never
deleted, so it can be re-enabled by hand). Owned objects that are no longer declared are deleted.
Without strict, unknown objects are kept and only reported. All -> All policies (NetBird's
`Default` one) are disabled in both modes unless `disableAllToAll: false`.

**Order.** Every run grants new access before it revokes anything:

1. settings
2. groups
3. network, resources and router
4. policies
5. disabling and deleting old objects
6. users

Deletions are best effort: a failure is reported and the job fails, but the rest of the run is
still applied.

**Users** (optional). With `users: null`, group membership stays in the console. In that mode the
reconciler only sets console roles: `admin` for members of `adminsGroup`, `user` for the other
user groups. Roles are left alone when `adminsGroup` is not set. With a `users` map, Git owns
membership of the user groups:
- Each listed e-mail gets exactly its groups.
- Listed users pending approval are approved.
- In strict mode, users who are not listed lose their user groups.
- Groups outside `userGroups` (device groups, for example) are kept.
- The owner's role and service users are never changed.

## Quick start

Requirements: NetBird with a **routing peer** whose setup key auto-assigns a group (the
`routerGroup`), and a **personal access token of an admin service user**.

```sh
kubectl -n netbird create secret generic netbird-admin-pat --from-literal=token=<PAT>

helm install netbird-gitops oci://ghcr.io/hatemmezlini/charts/netbird-gitops \
  -n netbird -f my-values.yaml    # start from examples/values.yaml
```

The chart starts in **dry run**. Run the job once and read the plan:

```sh
kubectl -n netbird create job --from=cronjob/netbird-gitops netbird-gitops-plan
kubectl -n netbird logs -f job/netbird-gitops-plan
```

When the plan is what you expect, set `reconciler.dryRun: false`. A failed Job means an API
error, a deletion that could not be applied, or no routing peer connected.

Run it outside Kubernetes:

```sh
pip install .
NB_API_URL=https://netbird.example.com NB_TOKEN_FILE=./pat \
  netbird-gitops --config config.json --dry-run
```

## Configuration

Helm values under `config` (rendered to JSON for the reconciler). Full example:
[examples/values.yaml](examples/values.yaml).

| Key | Default | Meaning |
|---|---|---|
| `strict` | `true` | Disable unmanaged policies, delete undeclared managed objects |
| `disableAllToAll` | `true` | Disable All -> All policies |
| `settings` | `{}` | Partial NetBird `AccountSettings`, merged into the current ones |
| `adminsGroup` | — | Group whose members get the console role `admin` |
| `userGroups` | required | Groups of people; every one of them can open the portal |
| `users` | `null` | `{e-mail: [groups]}` to manage membership in Git |
| `approveListedUsers` | `true` | Approve listed users who are pending approval |
| `network.name` | required | Network that holds the resources |
| `network.routerGroup` | required | Group of the routing peers |
| `network.masquerade`, `network.metric` | `true`, `9999` | Router settings |
| `checkRouterOnline` | `true` | Fail the job when no routing peer is connected |
| `tools[]` | `[]` | See below |

Each tool:

| Key | Default | Meaning |
|---|---|---|
| `name` | required | Resource name: lowercase, digits, dashes |
| `address` | required | Domain, `*.domain`, IP or CIDR |
| `groups` | required | User groups allowed to reach it |
| `protocol` | `tcp` | `tcp`, `udp`, `icmp` or `all` |
| `ports` | `[443]` | Ports (ignored for `icmp` and `all`) |
| `title`, `description` | name, empty | Shown on the card |
| `url` | `https://<address>` | Link on the card; default only for a plain domain on 443 |
| `icon` | `globe` | `globe`, `chart`, `activity`, `bell`, `search`, `git`, `database`, `terminal`, `server`, `lock`, `book`, `box` |
| `portal` | `true` | `false`: access only, no card |

Under `portal` (deployment) and `reconciler` (schedule, dry run, resources), see
[values.yaml](charts/netbird-gitops/values.yaml).

## Portal

`portal.address` is the host name users open through the VPN. netbird-gitops adds it as a
resource reachable by every user group on port 443. Expose the `<release>-portal` Service
behind whatever serves your internal tools (the routing peer's reverse proxy, or an internal
Ingress with `portal.ingress`).

**Reachability check.** The page sends a `no-cors` request to each tool URL:
- If any answer arrives, even an error page, the card shows **Reachable**.
- If the request times out or fails, the card shows **Not reachable**. Possible reasons: the
  policy does not allow it, the name does not resolve, or the device is not on the VPN.

The summary is announced to screen readers. Without JavaScript, the cards and links still work.

Design notes:
- system fonts and no external requests;
- light and dark themes;
- status shown by text and icon, never by color alone;
- the whole card is the link target;
- reduced-motion and forced-colors support;
- strict Content-Security-Policy.

The page lists every tool with its groups to anyone who can open it. Do not put anything secret
in titles or descriptions.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
helm lint charts/netbird-gitops -f examples/values.yaml
```

The tests run the real reconciler against an in-memory NetBird (`tests/fake_netbird.py`).

To release:
1. Bump the version in `src/netbird_gitops/__init__.py` and in `charts/netbird-gitops/Chart.yaml`
   (`version` and `appVersion`).
2. Push a `vX.Y.Z` tag.

The workflow publishes `ghcr.io/hatemmezlini/netbird-gitops` and
`oci://ghcr.io/hatemmezlini/charts/netbird-gitops`.

## License

[Apache-2.0](LICENSE). This is an independent project, not affiliated with or endorsed by NetBird.
