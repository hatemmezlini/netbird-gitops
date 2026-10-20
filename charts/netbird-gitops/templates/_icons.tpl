{{/*
Built-in icons: 24x24, stroke only, drawn for this project (no brand logos).
Tool icons are referenced by name in tools[].icon; the others are used by the page.
*/}}
{{- define "netbird-gitops.toolIcons" -}}
globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9M12 3C9.5 5.6 8.2 8.6 8.2 12s1.3 6.4 3.8 9"/>'
chart: '<path d="M4 20h16M7 16v-5M12 16V6M17 16v-8"/>'
activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>'
bell: '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>'
search: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>'
git: '<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="8" r="2"/><path d="M6 8v8M18 10c0 4-7 3-10.5 6.5"/>'
database: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>'
terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>'
server: '<rect x="3" y="4" width="18" height="7" rx="1.5"/><rect x="3" y="13" width="18" height="7" rx="1.5"/><path d="M7 7.5h.01M7 16.5h.01"/>'
lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'
book: '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5zM5 19.5A1.5 1.5 0 0 0 6.5 21H19"/>'
box: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/>'
{{- end -}}

{{- define "netbird-gitops.uiIcons" -}}
external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>'
copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/>'
check: '<path d="m5 12.5 4.5 4.5L19 7"/>'
refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>'
offline: '<path d="M2 8.8a15 15 0 0 1 4.6-3M10 4.4a15 15 0 0 1 12 4.4M5.5 12.3a10 10 0 0 1 4-2.2M15.5 10.6a10 10 0 0 1 3 1.7M9 15.8a5 5 0 0 1 6 0M12 19.3h.01M3 3l18 18"/>'
{{- end -}}
