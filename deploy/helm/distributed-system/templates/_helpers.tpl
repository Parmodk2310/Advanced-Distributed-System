{{- define "distributed-system.name" -}}
distributed-system
{{- end }}

{{- define "distributed-system.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "distributed-system.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "distributed-system.labels" -}}
app.kubernetes.io/name: {{ include "distributed-system.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "distributed-system.serviceAccountName" -}}
{{- default (include "distributed-system.fullname" .) .Values.serviceAccount.name -}}
{{- end }}

{{- define "distributed-system.validate" -}}
{{- if and .Values.image.releaseMode (empty .Values.image.digest) -}}
{{- fail "image.digest is required when image.releaseMode=true" -}}
{{- end -}}
{{- if lt (int .Values.replicaCount) (int .Values.crdt.replicationFactor) -}}
{{- fail "replicaCount must be greater than or equal to crdt.replicationFactor" -}}
{{- end -}}
{{- if ne .Values.service.type "ClusterIP" -}}
{{- fail "only internal ClusterIP exposure is supported" -}}
{{- end -}}
{{- if and .Values.tls.enabled (empty .Values.tls.secretName) -}}
{{- fail "tls.secretName is required when TLS is enabled" -}}
{{- end -}}
{{- end }}
