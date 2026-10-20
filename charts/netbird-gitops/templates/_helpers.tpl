{{- define "netbird-gitops.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "netbird-gitops.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* Image reference. Arguments: image (repository, tag, digest), defaultTag. */}}
{{- define "netbird-gitops.image" -}}
{{- if .image.digest -}}
{{ .image.repository }}@{{ .image.digest }}
{{- else -}}
{{ .image.repository }}:{{ .image.tag | default .defaultTag }}
{{- end -}}
{{- end -}}

{{/* Desired state as JSON, read by the reconciler (format: src/netbird_gitops/config.py). */}}
{{- define "netbird-gitops.config" -}}
{{- $v := .Values -}}
{{- $r := $v.reconciler -}}
{{- $cfg := dict
  "access" ($v.access | default dict)
  "resources" ($v.resources | default dict)
  "members" $v.members
  "network" $v.network
  "account" ($v.account | default dict)
  "strict" $r.strict
  "disableAllToAll" $r.disableAllToAll
  "approveMembers" $r.approveMembers
  "checkRouterOnline" $r.checkRouterOnline -}}
{{- with $v.consoleAdmins }}{{ $_ := set $cfg "consoleAdmins" . }}{{ end -}}
{{- if and $v.portal.enabled $v.portal.address -}}
{{- $_ := set $cfg "portal" (dict "address" $v.portal.address "ports" (list 443)) -}}
{{- end -}}
{{- toPrettyJson $cfg -}}
{{- end -}}

{{/*
Cross-references the schema cannot express, checked at install time (the reconciler
checks them again at run time).
*/}}
{{- define "netbird-gitops.validate" -}}
{{- $access := .Values.access | default dict -}}
{{- $resources := .Values.resources | default dict -}}
{{- if not $access -}}
{{- fail "access must list at least one group" -}}
{{- end -}}
{{- $granted := dict -}}
{{- range $group, $names := $access -}}
{{- if or (hasPrefix "gitops-" $group) (eq $group "All") -}}
{{- fail (printf "access.%s: reserved group name (prefix gitops- or All)" $group) -}}
{{- end -}}
{{- if and (has "*" ($names | default list)) (gt (len $names) 1) -}}
{{- fail (printf "access.%s: \"*\" already means every resource; list nothing else" $group) -}}
{{- end -}}
{{- range ($names | default list) -}}
{{- if eq . "*" -}}
{{- range $name, $unused := $resources }}{{ $_ := set $granted $name true }}{{ end -}}
{{- else if not (hasKey $resources .) -}}
{{- fail (printf "access.%s: unknown resource %q" $group .) -}}
{{- else -}}
{{- $_ := set $granted . true -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- range $name, $unused := $resources -}}
{{- if not (hasKey $granted $name) -}}
{{- fail (printf "resources.%s: no group in access can reach it (grant it or remove it)" $name) -}}
{{- end -}}
{{- end -}}
{{- with .Values.consoleAdmins -}}
{{- if not (hasKey $access .) -}}
{{- fail (printf "consoleAdmins: %q is not a group in access" .) -}}
{{- end -}}
{{- end -}}
{{- range $email, $groups := (.Values.members | default dict) -}}
{{- range ($groups | default list) -}}
{{- if not (hasKey $access .) -}}
{{- fail (printf "members.%s: %q is not a group in access" $email .) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Resources as a JSON list sorted by name, each with its `name`. */}}
{{- define "netbird-gitops.resourceList" -}}
{{- $out := list -}}
{{- range $name, $res := (.Values.resources | default dict) -}}
{{- $out = append $out (merge (dict "name" $name) (deepCopy $res)) -}}
{{- end -}}
{{- toJson $out -}}
{{- end -}}

{{/* Ports of a resource as a JSON list (a single port may be given as a scalar). */}}
{{- define "netbird-gitops.ports" -}}
{{- $ports := .ports | default (list 443) -}}
{{- if not (kindIs "slice" $ports) }}{{ $ports = list $ports }}{{ end -}}
{{- toJson $ports -}}
{{- end -}}

{{/* Card link of a resource: explicit url, else https://<address> for a plain domain on 443. */}}
{{- define "netbird-gitops.toolUrl" -}}
{{- $ports := include "netbird-gitops.ports" . -}}
{{- $proto := .protocol | default "tcp" -}}
{{- if .url -}}
{{- if not (regexMatch "^https?://" .url) -}}
{{- fail (printf "resources.%s.url must start with https:// or http://" .name) -}}
{{- end -}}
{{ .url }}
{{- else if and (eq $proto "tcp") (eq $ports "[443]") (not (hasPrefix "*." .address)) (not (regexMatch "^[0-9a-fA-F.:/]+$" .address)) -}}
https://{{ lower .address }}
{{- end -}}
{{- end -}}

{{/*
How the browser checks access to a resource: "<mode> <url>".
- http: the request must get an HTTP answer (web tools, or an explicit probe URL);
- tcp: any answer before the timeout, even a protocol error, proves the port is open
  (non-web tools such as databases). A policy that blocks the port drops the packets.
*/}}
{{- define "netbird-gitops.toolProbe" -}}
{{- $url := include "netbird-gitops.toolUrl" . -}}
{{- $ports := include "netbird-gitops.ports" . | fromJsonArray -}}
{{- $proto := .protocol | default "tcp" -}}
{{- /* Ports browsers refuse to connect to (Fetch standard, "bad port"). */ -}}
{{- $bad := list 1 7 9 11 13 15 17 19 20 21 22 23 25 37 42 43 53 69 77 79 87 95 101 102 103 104 109 110 111 113 115 117 119 123 135 137 139 143 161 179 389 427 465 512 513 514 515 526 530 531 532 540 548 554 556 563 587 601 636 989 990 993 995 1719 1720 1723 2049 3659 4045 4190 5060 5061 6000 6566 6665 6666 6667 6668 6669 6679 6697 10080 -}}
{{- if .probe -}}
{{- if not (regexMatch "^https?://" .probe) -}}
{{- fail (printf "resources.%s.probe must start with https:// or http://" .name) -}}
{{- end -}}
http {{ .probe }}
{{- else if $url -}}
http {{ $url }}
{{- else if and (eq $proto "tcp") (not (hasPrefix "*." .address)) (not (contains "/" .address)) -}}
{{- $port := int (first $ports) -}}
{{- if has $port $bad -}}
{{- fail (printf "resources.%s: browsers refuse port %d, so the portal cannot check it; set showInPortal: false or a probe URL" .name $port) -}}
{{- end -}}
{{- $host := ternary (printf "[%s]" .address) .address (contains ":" .address) -}}
tcp https://{{ lower $host }}:{{ $port }}/
{{- else -}}
{{- fail (printf "resources.%s: the portal cannot check access to it (%s %s); set showInPortal: false or a probe URL" .name $proto .address) -}}
{{- end -}}
{{- end -}}

{{- define "netbird-gitops.securityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: [ALL]
{{- end -}}
