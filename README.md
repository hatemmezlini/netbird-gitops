# netbird-gitops

Declarative access control for a self-hosted [NetBird](https://netbird.io), reconciled from Git,
plus a portal that shows each person the internal tools they can reach.

Access is written the way you would say it:

```yaml
access:
  platform-admins: ["*"]
  developers: [argocd, grafana]
  viewers: [grafana]

resources:
  argocd:
    address: argocd.vpn.example.com
  grafana:
    address: grafana.vpn.example.com
    title: Grafana
```

- **Reconciler**: a Kubernetes CronJob that makes NetBird match this file: groups, policies, the
  network with its resources and router, account settings, and optionally group membership.
  A change made by hand in the console is reverted at the next run.
- **Portal**: one page served by nginx, with a search bar. It shows each person only the tools
  their groups let them reach.

The reconciler uses only the Python standard library; the portal is static HTML, CSS and a small
script. Developed and tested against the NetBird management API v0.79.

## Requirements

- A Kubernetes cluster and `kubectl` configured for it.
- **Helm 3.8 or later** (Helm 4 works), for charts stored in OCI registries. Install it with
  your package manager, or see [helm.sh/docs/intro/install](https://helm.sh/docs/intro/install/):

  ```sh
  brew install helm                 # macOS
  winget install Helm.Helm          # Windows
  sudo snap install helm --classic  # Ubuntu
  helm version                      # check
  ```

- A self-hosted NetBird with a **routing peer**: the NetBird peer that forwards VPN traffic to
  your tools (often a pod in the cluster). Its setup key must auto-assign a group, for example
  `k8s-routers`: that group is `network.routerGroup`.
- An **admin service user** with a personal access token (PAT), for the reconciler.

## Install

**1. Create the token.** In the NetBird console:
   1. Open Team → Service Users, and create a service user with the Admin role.
   2. Create a token for it.

Then store the token in the namespace where you install the chart:

```sh
kubectl create namespace netbird   # if needed
kubectl -n netbird create secret generic netbird-admin-pat --from-literal=token=<PAT>
```

**2. Write two files**, starting from the [examples](examples/):
- `values.yaml` says how to reach NetBird: the API URL, the token Secret, the network and its
  router group, the account settings and the portal address. You write it once.
- `access.yaml` says who can reach what (see [The access file](#the-access-file)). This is the
  file you change from then on.

**3. Install.** The chart starts in **dry run**: nothing is written to NetBird.

```sh
helm install netbird-gitops oci://ghcr.io/hatemmezlini/charts/netbird-gitops \
  --version 0.1.0 -n netbird -f values.yaml -f access.yaml
```

Helm checks both files first, and stops with a message such as
`resources.postgres: Additional property port is not allowed` on any mistake.

**4. Read the plan.** Run the job once instead of waiting for the schedule:

```sh
kubectl -n netbird create job --from=cronjob/netbird-gitops netbird-gitops-plan
kubectl -n netbird logs -f job/netbird-gitops-plan
```

Each `[plan]` line is a change it would make, for example `create policy gitops-developers` or
`disable policy Default: All -> All`. In strict mode (the default), every policy you created by
hand appears as `disable`: declare what you still need before going further.

**5. Apply.** Set `reconciler.dryRun: false` in `values.yaml`, then:

```sh
helm upgrade netbird-gitops oci://ghcr.io/hatemmezlini/charts/netbird-gitops \
  --version 0.1.0 -n netbird -f values.yaml -f access.yaml
```

From then on the CronJob runs every 5 minutes. To change access, edit `access.yaml` and run the
same `helm upgrade`, or let your GitOps tool deploy it. `kubectl -n netbird get jobs` shows the
runs. A failed job means one of three things: an API error, a deletion that could not be
applied, or no routing peer connected. `kubectl logs` tells which.

**6. Publish the portal.** Point `portal.address` at the `netbird-gitops-portal` Service (port
80), through whatever serves your internal tools behind the routing peer. Every group in
`access` can reach the portal; the reconciler grants that.

`helm uninstall` removes the CronJob and the portal, but not what was created in NetBird.

## The access file

It has four sections ([example](examples/access.yaml)):

```yaml
# Who can reach what. "*" = every resource.
access:
  platform-admins: ["*"]
  developers: [argocd, grafana, logs]
  viewers: [grafana]

# What can be reached: tcp/443 unless ports or protocol say otherwise.
resources:
  grafana:
    address: grafana.vpn.example.com
    title: Grafana
    description: Dashboards and alerting
    icon: chart
  postgres:
    address: db.vpn.example.com
    ports: [5432]

# Optional. Who is in which group; without it, the NetBird console decides.
members:
  alice@example.com: [platform-admins]
  bob@example.com: [developers]

# Optional. Members of this group are admins of the NetBird console.
consoleAdmins: platform-admins
```

**Reading it.** A person reaches a resource only when all three hold:

1. **They are in a group that lists the resource in `access`.** Membership comes from `members`
   when it is set, otherwise from the NetBird console (Team → Users).
2. **They use a device enrolled with their own login.** NetBird gives their groups to that
   device. A device enrolled with a setup key only gets that key's groups.
3. **The traffic uses the resource's protocol and ports.** Other ports of the same address stay
   closed.

Nothing else is open:
- All -> All policies are disabled.
- Rules are one-way, so devices of different people never reach each other.
- Every group can open the portal.

The example gives:

| Resource | Port | platform-admins | developers | viewers |
|---|---|---|---|---|
| alertmanager | tcp/443 | yes | — | — |
| argocd | tcp/443 | yes | yes | — |
| grafana | tcp/443 | yes | yes | yes |
| logs | tcp/443 | yes | yes | — |
| postgres | tcp/5432 | yes | — | — |
| prometheus | tcp/443 | yes | — | — |
| portal | tcp/443 | yes | yes | yes |

**Mistakes are rejected.** These all stop `helm install` and `helm upgrade` with a message
naming the key:
- an unknown key (`port` for `ports`, `acess`);
- an unknown resource or group name;
- a resource that no group can reach;
- `"*"` mixed with names;
- a bad duration, address, port or icon.

The reconciler checks again on every run. To get the same checks in your editor, keep the
schema line at the top of the file (VS Code with the YAML extension, or any editor using
yaml-language-server):

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/hatemmezlini/netbird-gitops/v0.1.0/charts/netbird-gitops/values.schema.json
```

**Checking real access.**
- **Before applying:** read the dry-run plan.
- **In the NetBird console:**
  - Access Control → Policies shows one `gitops-<group>` policy per group.
  - Networks → `<network.name>` shows the resources and their groups.
- **From a person's device:** the portal lists exactly what that device can reach.

## Reference

`access` — `{group: [resource, …]}`. Groups are created in NetBird if missing, never deleted. Use
`["*"]` for every resource and `[]` for a group with no access, other than the portal.

`resources` — `{name: resource}`. Names use lowercase letters, digits and dashes; `portal` is
reserved.

| Key | Default | Meaning |
|---|---|---|
| `address` | required | Domain, `*.domain`, IP or CIDR |
| `protocol` | `tcp` | `tcp`, `udp`, `icmp` or `all` |
| `ports` | `[443]` | One port or a list; none for `icmp` and `all` |
| `title`, `description` | name, empty | Shown on the portal card |
| `url` | `https://<address>` | Card link; the default applies only to a domain on tcp/443 |
| `probe` | see [Portal](#portal) | URL the portal requests to check access |
| `icon` | `globe` | `globe`, `chart`, `activity`, `bell`, `search`, `git`, `database`, `terminal`, `server`, `lock`, `book`, `box` |
| `showInPortal` | `true` | `false`: access only, no card |

`members` — `{e-mail: [group, …]}`, or `null` (default) to manage membership in the console.
When set, Git owns membership of the groups in `access`:
- Listed people get exactly their groups, and are approved if pending.
- In strict mode, people who are not listed lose those groups.
- Other groups, such as device groups, are kept.
- Service users and the owner's role are never changed.

`consoleAdmins` — the group whose members get the console role `admin`; members of the other
groups get `user`. When it is empty, console roles are not managed.

`account` — NetBird account settings. Unset ones are left as they are.

| Key | NetBird setting |
|---|---|
| `groupsPropagation` | `groups_propagation_enabled`. Default `true`: group changes reach enrolled devices |
| `restrictRegularUsers` | `regular_users_view_blocked`: regular users only see their own devices |
| `userApproval` | `extra.user_approval_required` |
| `peerApproval` | `extra.peer_approval_enabled` |
| `peerLoginExpiration` | `peer_login_expiration(_enabled)`: a duration (`48h`, `7d`) or `false` |
| `peerInactivityExpiration` | `peer_inactivity_expiration(_enabled)`: a duration or `false` |
| `raw` | any other `AccountSettings` field, by its API name |

`network` — `name` and `routerGroup` are required; `description`, `masquerade` (`true`) and
`metric` (`9999`) are optional.

`reconciler` — the CronJob (`schedule`, `dryRun`, `resources`…) and its behaviour:

| Key | Default | Meaning |
|---|---|---|
| `strict` | `true` | Disable policies not managed here, delete managed objects no longer declared |
| `disableAllToAll` | `true` | Disable All -> All policies, in both modes |
| `approveMembers` | `true` | Approve people listed in `members` who are pending approval |
| `checkRouterOnline` | `true` | Fail the job when no routing peer is connected |

Everything else (`netbird`, `image`, `portal`) is described in
[values.yaml](charts/netbird-gitops/values.yaml).

## How it maps to NetBird

For each group and port set, the reconciler maintains:

| NetBird object | Name | Content |
|---|---|---|
| Group (destination) | `gitops-<group>-tcp-443` | the resources that group may reach on tcp/443 |
| Network resource | `<resource name>` | the address, member of the destination groups above |
| Policy | `gitops-<group>` | one one-way rule per port set: `<group>` -> `gitops-<group>-…` |
| Network router | — | the routing peers of `network.routerGroup` |

**Ownership.**
- netbird-gitops owns the objects prefixed `gitops-`, plus the declared network with its
  resources and router.
- It creates the groups of `access` and the router group if they are missing, and never deletes
  them.
- It never touches peers, setup keys or tokens.

**Strict mode** (default):
- Every enabled policy that netbird-gitops does not own is *disabled*. It is never deleted, so
  it can be re-enabled by hand.
- Owned objects that are no longer declared are deleted.

Without strict mode, unknown objects are kept and only reported.

**Order.** Every run grants new access before it revokes anything:

1. settings
2. groups
3. network, resources and router
4. policies
5. disabling and deleting old objects
6. members

Deletions are best effort. If one fails, the job fails, but the rest of the run is still applied.

Run the reconciler outside Kubernetes. Its configuration is the JSON the chart renders, in the
`netbird-gitops-config` ConfigMap:

```sh
pip install .
NB_API_URL=https://netbird.example.com NB_TOKEN_FILE=./pat \
  netbird-gitops --config config.json --dry-run
```

## Portal

`portal.address` is the host name people open through the VPN. netbird-gitops adds it as a
resource reachable by every group on port 443. Expose the `netbird-gitops-portal` Service
behind whatever serves your internal tools: the routing peer's reverse proxy, or an internal
Ingress with `portal.ingress`.

**Only permitted tools are shown.** The page is static and does not know who is looking at it
(the routing peer masquerades traffic). It does not need to: NetBird enforces access in the
network, and a policy that does not grant a resource drops its packets. So the browser checks
every resource from the device, and a card appears only when its resource answers:

| Resource | Check | Shown when |
|---|---|---|
| Web (`url`, or a domain on 443) | `HEAD` request to the URL | any HTTP answer, even an error page |
| TCP, not web (e.g. `ports: [5432]`) | `https://<address>:<port>/` | any answer before the timeout, even a protocol error |
| With `probe` | `HEAD` request to that URL | any HTTP answer |

A blocked resource only ever times out (`portal.checkTimeoutMs`, 4 s by default), so cards
appear progressively and the last ones settle after the timeout. Browsers refuse some ports
(22, 25, …). Those resources, and `udp`, `icmp`, `all`, wildcard or CIDR resources, need
`probe` or `showInPortal: false`; the chart says so when rendering. Cards are sorted by name.

**When it checks.** The page checks when it opens, and again in three cases: when you come back
to the tab (at most every 30 s), when the network comes back, and when you click *Check again*.
It does not poll. A re-check updates the cards in place: newly granted tools appear, revoked
ones disappear. The checks use `HEAD` requests, without cookies, and download no page content.

This shows access, not health: a tool that is down behind a gateway still answers with an error,
so its card stays. Health belongs in your monitoring. The check proves network access, not a
login: the tool still authenticates the person. The list of resources is in the page source for
anyone who can open the portal, so keep titles and descriptions free of secrets. Without
JavaScript nothing can be checked: every card is listed.

**Search.** The search bar filters by name, description and address as you type. Press `/` to
focus it and Escape to clear it; `?q=` in the URL pre-fills it.

**Look.** The font is Inter (bundled, SIL Open Font License) or the system fonts
(`portal.font`). The theme is dark by default, light when the system prefers it.
`portal.logo.svg` takes your logo as inline SVG: use `fill="currentColor"` for the parts that
should follow the text color. A third-party logo needs its owner's permission. Every text is in
`portal.text`, for translation.

Accessibility:
- labelled search field;
- one status message for screen readers, updated after typing pauses;
- visible focus;
- the whole card is the link target;
- 3:1 contrast for controls and 4.5:1 for text in both themes;
- reduced-motion and forced-colors support.

There are no external requests, and the Content-Security-Policy is strict.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
helm lint charts/netbird-gitops -f examples/values.yaml -f examples/access.yaml
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
