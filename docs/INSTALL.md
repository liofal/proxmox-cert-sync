# proxmox-cert-sync Installation Guide

## Overview

`proxmox-cert-sync` keeps a Proxmox VE node in sync with the latest TLS certificate issued in your Kubernetes cluster. A CronJob validates the certificate bundle, uploads it to Proxmox through the REST API, and restarts the required services.

The repository ships a ready-to-apply manifest at `manifests/proxmox-cert-sync.yaml`. Customize it for your environment and apply it with `kubectl`.

## Prerequisites

- Kubernetes 1.27+ cluster with `kubectl` access
- Proxmox VE 7.x/8.x node reachable over HTTPS
- cert-manager (or equivalent) issuing the TLS secret `proxmox-certmanager-tls`
- Proxmox API token with permission to upload certificates and restart services
- Local workstation with `kubectl` (and optionally `kustomize`) for applying manifests

## Create a Proxmox API Token

1. Log in to the Proxmox UI as an account with `Sys.Modify` privileges on the target node.
2. Navigate to **Datacenter ➜ Permissions ➜ API Tokens** and create a token.
3. Grant these privileges to the token:
   - `Sys.Audit`
   - `Sys.Modify`
4. Record the token ID (`<user>@<realm>!<token_name>`) and the secret. The secret is only shown once—store it securely.

## Prepare Kubernetes Secrets

### Certificate Secret

The CronJob mounts a TLS secret named `proxmox-certmanager-tls` that must contain the keys `tls.crt`, `tls.key`, and optionally `ca.crt`.

If cert-manager manages the certificate, the secret already exists. Otherwise, create it manually:

```bash
kubectl -n proxmox create secret tls proxmox-certmanager-tls \
  --cert=tls.crt \
  --key=tls.key
```

Add the CA certificate if required:

```bash
kubectl -n proxmox create secret generic proxmox-certmanager-tls \
  --from-file=tls.crt \
  --from-file=tls.key \
  --from-file=ca.crt
```

### Proxmox Credentials Secret

Create a secret that stores the API endpoint, token ID, token secret, and target node name. Encrypt it with SOPS before committing to Git.

```bash
kubectl -n proxmox create secret generic proxmox-credentials \
  --from-literal=apiUrl=https://proxmox.liofal.net:8006 \
  --from-literal=apiTokenId="root@pam!flux-sync" \
  --from-literal=apiTokenSecret="<token-secret>" \
  --from-literal=nodeName=pve
```

Adjust the key names if you change them inside the manifest.

## Deploy the CronJob

1. Create the namespace if it does not exist:

   ```bash
   kubectl create namespace proxmox
   ```

2. Review `manifests/proxmox-cert-sync.yaml` and tailor it to your environment:

   - Update `image:` to the release tag you want to run (e.g., `ghcr.io/liofal/proxmox-cert-sync:v0.1.0`).
   - Change `schedule`, `services`, or additional environment variables as needed.
   - Adjust secret names if they differ from the defaults above.

3. Apply the manifest:

   ```bash
   kubectl apply -f manifests/proxmox-cert-sync.yaml
   ```

4. Verify the CronJob:

   ```bash
   kubectl -n proxmox get cronjob proxmox-cert-sync
   ```

### GitOps / Kustomize

For GitOps workflows, copy the manifest into your configuration repository and manage overrides via `kustomization.yaml` patches. Ensure the secrets are provided via your preferred secret management workflow (SOPS, SealedSecrets, External Secrets, etc.).

## Manual Sync

To force a run between scheduled executions:

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
- **Hostname validation**: The uploaded certificate must cover the host extracted from `PROXMOX_API_URL`. Override `EXPECTED_HOSTNAMES` via the manifest if needed.
- **API failures**: Inspect the job logs. Non-2xx responses from the Proxmox API return detailed error messages.
- **TLS issues**: If the Proxmox API uses a self-signed certificate, mount a CA bundle secret and set `VERIFY_TLS=false` only as a last resort.

## Cleanup

Remove the deployment with:

```bash
kubectl delete -f manifests/proxmox-cert-sync.yaml
```

This deletes the CronJob and associated RBAC while leaving secrets untouched.
