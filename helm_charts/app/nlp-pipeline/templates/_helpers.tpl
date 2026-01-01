{{/*
Common labels
*/}}
{{- define "nlp-pipeline.labels" -}}
app.kubernetes.io/name: nlp-pipeline
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
