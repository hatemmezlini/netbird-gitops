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
- **Portal**: one HTML page served by nginx, with a search bar. It shows each user only the
  tools their groups let them reach.

The reconciler uses only the Python standard library; the portal is static HTML, CSS and a small
script. Developed against the NetBird management API v0.79.

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

- A self-hosted NetBird (developed and tested against management API v0.79) with a **routing peer**: the NetBird
  peer that forwards VPN traffic to your tools (often a pod in the cluster). Its setup key must
  auto-assign a group, for example `k8s-routers`: that group is `network.routerGroup`.
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

**2. Write your values.** Copy [examples/values.yaml](examples/values.yaml), or start from this
minimum. `helm show values oci://ghcr.io/hatemmezlini/charts/netbird-gitops` lists every option.

```yaml
netbird:
  apiUrl: http://netbird-server.netbird.svc.cluster.local   # management API, from the cluster
  tokenSecret: { name: netbird-admin-pat, key: token }
config:
  adminsGroup: platform-admins
  userGroups: [platform-admins, developers]
  network: { name: production, routerGroup: k8s-routers }
  settings:
    groups_propagation_enabled: true   # group changes reach devices already enrolled
  tools:
    - name: grafana
      title: Grafana
      address: grafana.vpn.example.com
      groups: [platform-admins, developers]
portal:
  address: portal.vpn.example.com
```

**3. Install.** The chart starts in **dry run**: nothing is written to NetBird.

```sh
helm install netbird-gitops oci://ghcr.io/hatemmezlini/charts/netbird-gitops \
  --version 0.2.1 -n netbird -f values.yaml
```

**4. Read the plan.** Run the job once instead of waiting for the schedule:

```sh
kubectl -n netbird create job --from=cronjob/netbird-gitops netbird-gitops-plan
kubectl -n netbird logs -f job/netbird-gitops-plan
```

Each `[plan]` line is a change it would make, for example `create policy gitops-developers` or
`disable policy Default: All -> All`. In strict mode (the default), every policy you created by
hand appears as `disable`: declare what you still need before going further.

**5. Apply.** Set `reconciler.dryRun: false` in your values, then:

```sh
helm upgrade netbird-gitops oci://ghcr.io/hatemmezlini/charts/netbird-gitops \
  --version 0.2.1 -n netbird -f values.yaml
```

From then on the CronJob runs every 5 minutes. To change access, edit the values and run the same
`helm upgrade`, or let your GitOps tool deploy it. `kubectl -n netbird get jobs` shows the runs.
A failed job means one of three things: an API error, a deletion that could not be applied, or
no routing peer connected. `kubectl logs` tells which.

**6. Publish the portal.** Point `portal.address` at the `netbird-gitops-portal` Service (port
80), through whatever serves your internal tools behind the routing peer. Every user group can
reach the portal; the reconciler grants that.

`helm uninstall` removes the CronJob and the portal, but not what was created in NetBird.

Run the reconciler outside Kubernetes (the configuration is the `config` block as JSON):

```sh
pip install .
NB_API_URL=https://netbird.example.com NB_TOKEN_FILE=./pat \
  netbird-gitops --config config.json --dry-run
```

## Who can reach what

A person reaches a tool only when all three hold:

1. **They are in one of the tool's `groups`.** Membership comes from `users` in Git when
   declared, otherwise from the NetBird console (Team → Users).
2. **They use a device enrolled with their own login.** NetBird gives their groups to that
   device. A device enrolled with a setup key only gets that key's groups.
3. **The traffic uses the tool's protocol and ports.** Other ports of the same address stay
   closed.

Nothing else is open:
- All -> All policies are disabled.
- Rules are one-way, so devices of different people never reach each other.
- Every user group can open the portal.

With [examples/values.yaml](examples/values.yaml):

| Tool | Port | platform-admins | developers | viewers |
|---|---|---|---|---|
| argocd | tcp/443 | yes | yes | — |
| grafana | tcp/443 | yes | yes | yes |
| logs | tcp/443 | yes | yes | — |
| prometheus | tcp/443 | yes | — | — |
| alertmanager | tcp/443 | yes | — | — |
| postgres | tcp/5432 | yes | — | — |
| portal | tcp/443 | yes | yes | yes |

So `bob@example.com`, listed in `developers`, reaches Argo CD, Grafana, Logs and the portal, and
nothing else. To check access at each stage:
- **Before applying:** read the dry-run plan.
- **In the NetBird console:**
  - Access Control → Policies shows one `gitops-<group>` policy per group.
  - Networks → `<network.name>` shows the resources and their groups.
- **From a person's device:** the portal lists exactly the tools that device can reach.

## How it maps to NetBird

For each user group and port set, the reconciler maintains:

| NetBird object | Name | Content |
|---|---|---|
| Group (destination) | `gitops-<group>-tcp-443` | the resources that group may reach on tcp/443 |
| Network resource | `<tool name>` | the tool address, member of the destination groups above |
| Policy | `gitops-<group>` | one one-way rule per port set: `<group>` -> `gitops-<group>-…` |
| Network router | — | the routing peers of `network.routerGroup` |

**Ownership.**
- netbird-gitops owns the objects prefixed `gitops-`, plus the declared network with its
  resources and router.
- It creates user groups and the router group if they are missing, and never deletes them.
- It never touches peers, setup keys or tokens.

**Strict mode** (default):
- Every enabled policy that netbird-gitops does not own is *disabled*. It is never deleted, so
  it can be re-enabled by hand.
- Owned objects that are no longer declared are deleted.

Without strict mode, unknown objects are kept and only reported. All -> All policies (such as
NetBird's `Default` policy) are disabled in both modes, unless `disableAllToAll: false`.

**Order.** Every run grants new access before it revokes anything:

1. settings
2. groups
3. network, resources and router
4. policies
5. disabling and deleting old objects
6. users

Deletions are best effort. If one fails, the job fails, but the rest of the run is still applied.

**Users** (optional). With `users: null`, group membership stays in the console. In that mode the
reconciler only sets console roles:
- `admin` for members of `adminsGroup`;
- `user` for members of the other user groups;
- no change at all when `adminsGroup` is not set.

With a `users` map, Git owns membership of the user groups:
- Each listed e-mail gets exactly its groups.
- Listed users pending approval are approved.
- In strict mode, users who are not listed lose their user groups.
- Groups outside `userGroups` (device groups, for example) are kept.
- The owner's role and service users are never changed.

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
| `probe` | see [Portal](#portal) | URL the browser requests to check access |
| `icon` | `globe` | `globe`, `chart`, `activity`, `bell`, `search`, `git`, `database`, `terminal`, `server`, `lock`, `book`, `box` |
| `portal` | `true` | `false`: access only, no card |

Under `portal` (deployment) and `reconciler` (schedule, dry run, resources), see
[values.yaml](charts/netbird-gitops/values.yaml).

## Portal

`portal.address` is the host name users open through the VPN. netbird-gitops adds it as a
resource reachable by every user group on port 443. Expose the `<release>-portal` Service
behind whatever serves your internal tools (the routing peer's reverse proxy, or an internal
Ingress with `portal.ingress`).

**Only permitted tools are shown.** The page is static and does not know who is looking at it
(the routing peer masquerades traffic). It does not need to: NetBird enforces access in the
network, and a policy that does not grant a tool drops its packets. So the browser probes every
tool from the device, and a card appears only when its tool answers:

| Tool | Probe | Shown when |
|---|---|---|
| Web (`url`, or a domain on 443) | `HEAD` request to the URL | any HTTP answer, even an error page |
| TCP, not web (e.g. `ports: [5432]`) | `https://<address>:<port>/` | any answer before the timeout, even a protocol error |
| With `probe` | `HEAD` request to that URL | any HTTP answer |

A blocked tool only ever times out (`portal.checkTimeoutMs`, 4 s by default), so cards appear
progressively and the last ones settle after the timeout.

**When it checks.** The page checks when it opens, and again in three cases: when you come back
to the tab (at most every 30 s), when the network comes back, and when you click *Check again*.
It does not poll. A re-check updates the cards in place: newly granted tools appear, revoked
ones disappear. The probes use `HEAD` requests, without cookies, and download no page content.
This shows access, not health: a tool that is down behind a gateway still answers with an error,
so its card stays. Health belongs in your monitoring. Browsers refuse some ports (22, 25,
…); such tools, and `udp`, `icmp`, `all`, wildcard or CIDR tools, need `probe` or
`portal: false`, and the chart says so when rendering.

The probe proves network access, not a login: the tool still authenticates the user. The tool
list is in the page source for anyone who can open the portal, so keep titles and descriptions
free of secrets. Without JavaScript nothing can be checked: every tool is listed.

**Search.** The search bar filters by name, description and address as you type. Press `/` to
focus it and Escape to clear it; `?q=` in the URL pre-fills it.

**Look.** Inter (bundled, SIL Open Font License) or system fonts (`portal.font`), dark theme by
default and light theme by system preference. `portal.logo.svg` takes your logo as inline SVG;
use `fill="currentColor"` for parts that should follow the text color. A third-party logo needs
its owner's permission. All texts are in `portal.text`, for translation.

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
