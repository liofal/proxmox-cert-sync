{{- define "proxmox-cert-sync.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "proxmox-cert-sync.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "proxmox-cert-sync.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "proxmox-cert-sync.selectorLabels" -}}
app.kubernetes.io/name: {{ include "proxmox-cert-sync.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "proxmox-cert-sync.labels" -}}
helm.sh/chart: {{ include "proxmox-cert-sync.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{ include "proxmox-cert-sync.selectorLabels" . }}
{{- end -}}

{{- define "proxmox-cert-sync.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "proxmox-cert-sync.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
