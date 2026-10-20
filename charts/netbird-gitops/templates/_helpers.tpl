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

{{/* Desired state as JSON. The portal address is injected from .Values.portal. */}}
{{- define "netbird-gitops.config" -}}
{{- $cfg := deepCopy .Values.config -}}
{{- if and .Values.portal.enabled .Values.portal.address -}}
{{- $_ := set $cfg "portal" (dict "address" .Values.portal.address "ports" (list 443)) -}}
{{- end -}}
{{- if not $cfg.adminsGroup -}}
{{- $_ := unset $cfg "adminsGroup" -}}
{{- end -}}
{{- toPrettyJson $cfg -}}
{{- end -}}

{{/* Portal URL of a tool: explicit url, else https://<address> for a plain domain on 443. */}}
{{- define "netbird-gitops.toolUrl" -}}
{{- $ports := .ports | default (list 443) -}}
{{- $proto := .protocol | default "tcp" -}}
{{- if .url -}}
{{- if not (regexMatch "^https?://" .url) -}}
{{- fail (printf "tools: %s: url must start with https:// or http://" .name) -}}
{{- end -}}
{{ .url }}
{{- else if and (eq $proto "tcp") (eq (toJson $ports) "[443]") (not (hasPrefix "*." .address)) (not (regexMatch "^[0-9a-fA-F.:/]+$" .address)) -}}
https://{{ lower .address }}
{{- end -}}
{{- end -}}

{{- define "netbird-gitops.securityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: [ALL]
{{- end -}}
