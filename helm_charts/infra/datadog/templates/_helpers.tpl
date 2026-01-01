{{/*
Return the namespace Datadog should be installed into
*/}}
{{- define "datadog.namespace" -}}
{{ .Values.namespace | default .Release.Namespace }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "datadog.labels" -}}
app.kubernetes.io/name: datadog
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
