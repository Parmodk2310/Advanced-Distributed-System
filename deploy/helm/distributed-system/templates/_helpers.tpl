{{- define "distributed-system.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "distributed-system.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "distributed-system.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "distributed-system.labels" -}}
app.kubernetes.io/name: {{ include "distributed-system.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}
{{- define "distributed-system.selectorLabels" -}}
app.kubernetes.io/name: {{ include "distributed-system.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "distributed-system.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}{{- default (include "distributed-system.fullname" .) .Values.serviceAccount.name -}}{{- else -}}{{- required "serviceAccount.name is required when serviceAccount.create=false" .Values.serviceAccount.name -}}{{- end -}}
{{- end -}}
{{- define "distributed-system.image" -}}
{{- if .Values.releaseMode -}}
{{- $repository := required "image.repository is required in release mode" .Values.image.repository -}}
{{- $digest := required "image.digest is required in release mode" .Values.image.digest -}}
{{- printf "%s@%s" $repository $digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}
{{- end -}}
{{- define "distributed-system.validate" -}}
{{- if ne (int .Values.replicaCount) 3 -}}{{- fail "replicaCount must be exactly 3 for the Phase 7 release contract" -}}{{- end -}}
{{- if gt (int .Values.cluster.replicationFactor) (int .Values.replicaCount) -}}{{- fail "cluster.replicationFactor cannot exceed replicaCount" -}}{{- end -}}
{{- if and .Values.tls.mtlsRequired (not .Values.tls.enabled) -}}{{- fail "tls.enabled must be true when tls.mtlsRequired=true" -}}{{- end -}}
{{- if .Values.publicEndpoint.enabled -}}{{- fail "publicEndpoint is forbidden in committed values; enable it only through the gated Phase 7B workflow" -}}{{- end -}}
{{- end -}}
