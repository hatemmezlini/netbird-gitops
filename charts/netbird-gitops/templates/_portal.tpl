{{- define "netbird-gitops.portalHtml" -}}
{{- $p := .Values.portal -}}
{{- $t := $p.text -}}
{{- $toolIcons := include "netbird-gitops.toolIcons" . | fromYaml -}}
{{- $icons := merge (dict) $toolIcons (include "netbird-gitops.uiIcons" . | fromYaml) -}}
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
<meta name="color-scheme" content="dark light">
<meta name="robots" content="noindex">
<title>{{ $p.title | html }}</title>
{{- if eq $p.font "inter" }}
<link rel="preload" href="inter.woff2" as="font" type="font/woff2" crossorigin>
{{- end }}
<link rel="stylesheet" href="portal.css">
<noscript><link rel="stylesheet" href="noscript.css"></noscript>
<link rel="icon" href="data:,">
</head>
<body data-timeout="{{ $p.checkTimeoutMs | html }}"
  data-text-checking="{{ $t.checking | html }}"
  data-text-available="{{ $t.available | html }}"
  data-text-available-one="{{ $t.availableOne | html }}"
  data-text-matching="{{ $t.matching | html }}"
  data-text-copied="{{ $t.copied | html }}">
<svg class="sprite" aria-hidden="true" focusable="false">
{{- range $name, $path := $icons }}
<symbol id="i-{{ $name }}" viewBox="0 0 24 24">{{ $path }}</symbol>
{{- end }}
</svg>
{{- with $p.logo.svg }}
<header class="top">
  <div class="wrap">
    <span class="logo" role="img" aria-label="{{ $p.logo.alt | html }}">{{ . }}</span>
  </div>
</header>
{{- end }}
<main class="wrap">
  <section class="hero" aria-labelledby="title">
    <h1 id="title">{{ $p.title | html }}</h1>
    <p class="subtitle">{{ $p.subtitle | html }}</p>
    <form class="search" role="search" action="" autocomplete="off">
      <label for="q">{{ $t.searchLabel | html }}</label>
      <div class="field">
        <svg class="field-icon" aria-hidden="true" focusable="false"><use href="#i-search"/></svg>
        <input id="q" name="q" type="search" placeholder="{{ $t.searchPlaceholder | html }}" spellcheck="false" enterkeyhint="search">
        <kbd class="field-key" aria-hidden="true">/</kbd>
      </div>
    </form>
  </section>

  <div class="bar">
    <p id="summary" class="summary" role="status" aria-atomic="true">{{ $t.noScript | html }}</p>
    <button type="button" id="recheck" class="btn btn-ghost" hidden>
      <svg class="btn-icon" aria-hidden="true" focusable="false"><use href="#i-refresh"/></svg>{{ $t.recheck | html }}
    </button>
  </div>

  <ul id="tools" class="grid">
  {{- range $tools }}
  {{- $url := include "netbird-gitops.toolUrl" . }}
  {{- $probe := include "netbird-gitops.toolProbe" . | splitList " " }}
  {{- $ports := include "netbird-gitops.ports" . | fromJsonArray }}
  {{- $title := .title | default .name }}
  {{- $address := lower .address }}
  {{- $shown := ternary $address (printf "%s:%s" $address (join "," $ports)) (eq (toJson $ports) "[443]") }}
  {{- $icon := .icon | default "globe" }}
  {{- if not (hasKey $toolIcons $icon) }}{{ $icon = "globe" }}{{ end }}
    <li class="card" data-mode="{{ index $probe 0 }}" data-probe="{{ index $probe 1 | html }}"
      data-search="{{ lower (printf "%s %s %s %s" .name $title (.description | default "") $address) | html }}">
      <span class="tile"><svg class="icon" aria-hidden="true" focusable="false"><use href="#i-{{ $icon }}"/></svg></span>
      <div class="body">
        <h2 class="name">
        {{- if $url }}<a href="{{ $url | html }}" rel="noopener noreferrer">{{ $title | html }}</a>{{ else }}{{ $title | html }}{{ end -}}
        </h2>
        {{- with .description }}
        <p class="desc">{{ . | html }}</p>
        {{- end }}
        <p class="addr"><code>{{ $shown | html }}</code></p>
      </div>
      {{- if $url }}
      <svg class="go" aria-hidden="true" focusable="false"><use href="#i-external"/></svg>
      {{- else }}
      <button type="button" class="btn btn-icon-only copy" data-copy="{{ $shown | html }}" aria-label="{{ printf "%s %s" $t.copy $title | html }}" title="{{ $t.copy | html }}">
        <svg class="btn-icon" aria-hidden="true" focusable="false"><use href="#i-copy"/></svg>
      </button>
      {{- end }}
    </li>
  {{- end }}
  {{- range until (min 3 (len $tools) | int) }}
    <li class="skeleton" aria-hidden="true"><span class="tile"></span><span class="lines"><span></span><span></span></span></li>
  {{- end }}
  </ul>

  <div id="no-match" class="state" hidden>
    <svg class="state-icon" aria-hidden="true" focusable="false"><use href="#i-search"/></svg>
    <h2 class="state-title">{{ $t.noMatchTitle | html }} <q id="no-match-query"></q></h2>
    <p>{{ $t.noMatchBody | html }}</p>
    <button type="button" id="clear" class="btn">{{ $t.clear | html }}</button>
  </div>

  <div id="none" class="state" hidden>
    <svg class="state-icon" aria-hidden="true" focusable="false"><use href="#i-offline"/></svg>
    <h2 class="state-title">{{ $t.noneTitle | html }}</h2>
    <p>{{ $t.noneBody | html }}</p>
    <button type="button" id="retry" class="btn">{{ $t.recheck | html }}</button>
  </div>

  <p id="announce" class="visually-hidden" role="status" aria-atomic="true"></p>
</main>
<footer class="wrap foot"><p>{{ $t.footer | html }}</p></footer>
<script src="portal.js" defer></script>
</body>
</html>
{{- end -}}

{{/* Font tokens, prepended to portal.css. */}}
{{- define "netbird-gitops.fontCss" -}}
{{- if eq .Values.portal.font "inter" -}}
/* Inter, (c) The Inter Project Authors, SIL Open Font License 1.1 (inter-OFL.txt). */
@font-face {
  font-family: "Inter";
  src: url("inter.woff2") format("woff2");
  font-weight: 100 900;
  font-style: normal;
  font-display: swap;
}
:root { --font: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
{{- else -}}
:root { --font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
{{- end }}
{{ end -}}

{{- define "netbird-gitops.nginxConf" -}}
server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    server_tokens off;
    charset utf-8;
    charset_types text/css application/javascript;

    add_header Content-Security-Policy "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src http: https:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" always;
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
