{{- define "netbird-gitops.portalHtml" -}}
{{- $p := .Values.portal -}}
{{- $t := $p.text -}}
{{- $icons := include "netbird-gitops.icons" . | fromYaml -}}
{{- $tools := list -}}
{{- range .Values.config.tools -}}
{{- if or (not (hasKey . "portal")) .portal -}}
{{- $tools = append $tools . -}}
{{- end -}}
{{- end -}}
<!doctype html>
<html lang="{{ $p.lang | html }}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex">
<title>{{ $p.title | html }}</title>
<link rel="stylesheet" href="portal.css">
<link rel="icon" href="data:,">
</head>
<body data-timeout="{{ $p.checkTimeoutMs | html }}"
  data-text-unknown="{{ $t.unknown | html }}" data-text-checking="{{ $t.checking | html }}"
  data-text-reachable="{{ $t.reachable | html }}" data-text-blocked="{{ $t.blocked | html }}"
  data-text-summary-checking="{{ $t.summaryChecking | html }}" data-text-summary="{{ $t.summary | html }}">
<svg class="sprite" aria-hidden="true" focusable="false">
{{- range $name, $path := $icons }}
<symbol id="i-{{ $name }}" viewBox="0 0 24 24">{{ $path }}</symbol>
{{- end }}
</svg>
<header class="top">
  <div class="wrap">
    <h1>{{ $p.title | html }}</h1>
    <p class="subtitle">{{ $p.subtitle | html }}</p>
    <div class="bar">
      <p id="summary" class="summary" role="status" aria-live="polite" aria-atomic="true">{{ $t.summaryNoScript | html }}</p>
      <button type="button" id="recheck" class="recheck" hidden>{{ $t.recheck | html }}</button>
    </div>
  </div>
</header>
<main class="wrap">
{{- if not $tools }}
  <p class="empty">{{ $t.empty | html }}</p>
{{- else }}
  <ul class="grid">
  {{- range $tools }}
  {{- $url := include "netbird-gitops.toolUrl" . }}
  {{- $icon := .icon | default "globe" }}
  {{- if not (hasKey $icons $icon) }}{{ $icon = "globe" }}{{ end }}
    <li class="card"{{ if $url }} data-check="{{ $url | html }}"{{ end }}>
      <div class="head">
        <svg class="icon" aria-hidden="true" focusable="false"><use href="#i-{{ $icon }}"/></svg>
        <h2>{{- if $url }}<a href="{{ $url | html }}" rel="noopener noreferrer">{{ .title | default .name | html }}</a>{{ else }}{{ .title | default .name | html }}{{ end -}}</h2>
      </div>
      {{- with .description }}
      <p class="desc">{{ . | html }}</p>
      {{- end }}
      <dl class="meta">
        <div><dt>{{ $t.address | html }}</dt><dd><code>{{ lower .address | html }}{{ with .ports }}{{ if ne (toJson .) "[443]" }}:{{ join "," . }}{{ end }}{{ end }}</code></dd></div>
        <div><dt>{{ $t.groups | html }}</dt><dd>{{ join ", " .groups | html }}</dd></div>
      </dl>
      {{- if $url }}
      <p class="status" data-state="unknown"><svg class="status-icon" aria-hidden="true" focusable="false"><use href="#i-unknown"/></svg><span>{{ $t.unknown | html }}</span></p>
      {{- else }}
      <p class="status" data-state="none"><svg class="status-icon" aria-hidden="true" focusable="false"><use href="#i-terminal"/></svg><span>{{ $t.noUrl | html }}</span></p>
      {{- end }}
    </li>
  {{- end }}
  </ul>
{{- end }}
</main>
<footer class="wrap foot"><p>{{ $t.footer | html }}</p></footer>
<script src="portal.js" defer></script>
</body>
</html>
{{- end -}}

{{- define "netbird-gitops.nginxConf" -}}
server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    server_tokens off;
    charset utf-8;

    add_header Content-Security-Policy "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src http: https:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy no-referrer always;
    add_header Cache-Control "no-cache" always;

    location = /healthz {
        access_log off;
        default_type text/plain;
        return 200 "ok\n";
    }
    location / {
        try_files $uri $uri/ =404;
    }
}
{{- end -}}
