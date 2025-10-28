# proxmox-cert-sync Installation Guide

## Overview

`proxmox-cert-sync` keeps a Proxmox VE node in sync with the latest TLS certificate issued in your Kubernetes cluster. A CronJob validates the certificate bundle, uploads it to Proxmox through the REST API, and restarts the required services.

The project is published as a Helm chart (`oci://ghcr.io/liofal/proxmox-cert-sync/proxmox-cert-sync`) and container image (`ghcr.io/liofal/proxmox-cert-sync`). Use Helm directly or manage the release declaratively with Flux.

## Prerequisites

- Kubernetes 1.27+ cluster with `kubectl` access
- Proxmox VE 7.x/8.x node reachable over HTTPS
- cert-manager (or equivalent) issuing the TLS secret `proxmox-certmanager-tls`
- Proxmox API token with permission to upload certificates and restart services
- Local workstation with `kubectl`; install `helm` for CLI deployments or `flux` if you use FluxCD

## Proxmox API Token

1. Log in to the Proxmox UI as an account with `Sys.Modify` privileges on the target node.
2. Navigate to **Datacenter ➜ Permissions ➜ API Tokens** and create a token.
3. Grant `Sys.Audit` and `Sys.Modify` privileges on `/nodes/<node-name>`.
4. Record the token ID (`<user>@<realm>!<token_name>`) and the secret. The secret appears only once—store it securely.

## Kubernetes Secrets

### Certificate Secret

The CronJob mounts a TLS secret named `proxmox-certmanager-tls` that must contain `tls.crt`, `tls.key`, and optionally `ca.crt`.

If cert-manager manages the certificate, nothing more is needed. Otherwise:

```bash
kubectl -n proxmox create secret generic proxmox-certmanager-tls \
  --from-file=tls.crt \
  --from-file=tls.key \
  --from-file=ca.crt
```

### Proxmox Credentials Secret

Create a secret that stores the API endpoint, token ID, token secret, and target node name. Encrypt it with SOPS (or your preferred system) before committing.

```bash
kubectl -n proxmox create secret generic proxmox-credentials \
  --from-literal=apiUrl=https://proxmox.example.com:8006 \
  --from-literal=apiTokenId="root@pam!flux-sync" \
  --from-literal=apiTokenSecret="<token-secret>" \
  --from-literal=nodeName=pve
```

Adjust key names if you change them via Helm values.

## Option A – Helm CLI

1. Create the namespace if it does not exist:

   ```bash
   kubectl create namespace proxmox
   ```

2. Authenticate to GitHub Container Registry (replace with a PAT that has `read:packages`):

   ```bash
   echo "$GHCR_TOKEN" | helm registry login ghcr.io --username "$GHCR_USER" --password-stdin
   ```

3. Install the chart with your overrides:

   ```bash
   helm install proxmox-cert-sync oci://ghcr.io/liofal/proxmox-cert-sync/proxmox-cert-sync \
     --namespace proxmox \
     --version 1.2.0 \
     --values my-values.yaml
   ```

   `kube/charts/proxmox-cert-sync/values.yaml` documents all configurable options. Notably:

   - Leave `image.tag` empty to follow the chart `appVersion` (e.g., `1.2.0`).
   - Override `cronJob.schedule` or `servicesToRestart` as required.

4. Upgrade later releases with `helm upgrade` and the new chart version.

## Option B – Flux HelmRelease

Use FluxCD to reconcile the Helm chart from GHCR. Create a `HelmRepository` and `HelmRelease` similar to:

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: proxmox-cert-sync
  namespace: flux-system
spec:
  interval: 30m
  type: oci
  url: oci://ghcr.io/liofal/proxmox-cert-sync
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: proxmox-cert-sync
  namespace: proxmox
spec:
  interval: 15m
  timeout: 5m
  chart:
    spec:
      chart: proxmox-cert-sync
      version: "1.2.0"
      sourceRef:
        kind: HelmRepository
        name: proxmox-cert-sync
        namespace: flux-system
      interval: 15m
  install:
    remediation:
      retries: 3
  upgrade:
    cleanupOnFail: true
    remediation:
      retries: 3
  uninstall:
    keepHistory: false
  values:
    image:
      # tag defaults to {{ .Chart.AppVersion }}; override only if you need a specific build
      pullPolicy: IfNotPresent
    proxmox:
      credentialsSecretName: proxmox-credentials
      apiUrlKey: apiUrl
      tokenIdKey: apiTokenId
      tokenSecretKey: apiTokenSecret
      nodeNameKey: nodeName
      verifyTls: true
    certificate:
      secretName: proxmox-certmanager-tls
      tlsCrtKey: tls.crt
      tlsKeyKey: tls.key
      caCrtKey: ca.crt
      includeCaBundle: true
    cronJob:
      schedule: "0 3 1 * *"
      concurrencyPolicy: Forbid
      successfulJobsHistoryLimit: 1
      failedJobsHistoryLimit: 3
    job:
      dryRun: false
      maxRetries: 1
      backoffLimit: 1
      resources:
        requests:
          cpu: 50m
          memory: 64Mi
        limits:
          cpu: 200m
          memory: 256Mi
```

Commit the manifest to your Flux repository. Flux will fetch chart updates every 15 minutes; bump `spec.chart.spec.version` when you want to roll out a new release.

## Manual Sync

Force a run between scheduled executions:

```bash
kubectl -n proxmox create job \
  --from=cronjob/proxmox-cert-sync \
  proxmox-cert-sync-manual-$(date +%s)
```

Follow the job progress:

```bash
kubectl -n proxmox logs -f job/proxmox-cert-sync-manual-<timestamp>
```

## Troubleshooting

- **Certificate mismatch**: Ensure the secret contains matching `tls.crt`/`tls.key`. The job exits early if validation fails.
- **Hostname validation**: The uploaded certificate must cover the host extracted from `PROXMOX_API_URL`. Override `EXPECTED_HOSTNAMES` via values if needed.
- **API failures**: Inspect job logs. Non-2xx responses from the Proxmox API include the returned message.
- **TLS issues**: If the Proxmox API uses a self-signed certificate, mount a CA bundle secret. Set `proxmox.verifyTls=false` only as a last resort.

## Cleanup

### Helm CLI

```bash
helm uninstall proxmox-cert-sync --namespace proxmox
```

### Flux

Delete the `HelmRelease` (and optionally the `HelmRepository`):

```bash
kubectl delete helmrelease proxmox-cert-sync -n proxmox
kubectl delete helmrepository proxmox-cert-sync -n flux-system
```

Secrets remain in place so you can redeploy later.
