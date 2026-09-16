{{- define "etcd.name" -}}etcd{{- end -}}
{{- define "etcd.fullname" -}}{{- .Release.Name | trunc 63 | trimSuffix "-" -}}{{- end -}}
{{- define "etcd.labels" -}}
app.kubernetes.io/name: {{ include "etcd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}
{{- define "etcd.selectorLabels" -}}
app.kubernetes.io/name: {{ include "etcd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "etcd.image" -}}{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}{{- end -}}
{{- define "etcd.initialCluster" -}}
{{- $name := include "etcd.fullname" . -}}
{{- printf "%s-0=http://%s-0.%s-headless:%d,%s-1=http://%s-1.%s-headless:%d,%s-2=http://%s-2.%s-headless:%d" $name $name $name (int .Values.service.peerPort) $name $name $name (int .Values.service.peerPort) $name $name $name (int .Values.service.peerPort) -}}
{{- end -}}
