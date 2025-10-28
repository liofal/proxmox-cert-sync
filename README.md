# proxmox-cert-sync

`proxmox-cert-sync` publishes the latest TLS certificate managed inside Kubernetes to a Proxmox VE node. It validates the certificate chain, uploads it with the Proxmox REST API, and restarts the required services.

## What’s in the box?

- **Container image** — `ghcr.io/liofal/proxmox-cert-sync:<tag>`; built and pushed by the Release workflow.
- **Helm chart** — source under `kube/charts/proxmox-cert-sync`, published to `oci://ghcr.io/liofal/proxmox-cert-sync/proxmox-cert-sync`.
- **Automation** — semantic-release drives version bumps, publishes a GitHub release, pushes containers/Helm charts, and triggers the multi-arch Docker build.
- **Utilities** — Makefile helpers for local builds and `docs/INSTALL.md` for detailed setup guidance.

## Getting started

1. Configure your Proxmox API token and Kubernetes secrets (see `docs/INSTALL.md`).
2. Deploy via Helm CLI or Flux:
   - `helm install proxmox-cert-sync oci://ghcr.io/liofal/proxmox-cert-sync/proxmox-cert-sync --version <chart-version>`
   - or apply the sample `HelmRepository`/`HelmRelease` from the documentation.
3. Verify the CronJob in the `proxmox` namespace and monitor job logs for the first sync.

## Releasing & contributing

- Push commits with semantic commit types (`feat:`, `fix:`, etc.) to let the Release workflow cut versions automatically.
- The Helm chart’s image tag defaults to the chart `appVersion` (plain semver like `1.2.0`); updating the chart version via semantic-release keeps container and chart in sync.
- Renovate is configured for pip, Dockerfile, GitHub Actions, and Helm values to keep dependencies fresh.

Refer to `docs/INSTALL.md` for full installation and operational guidance.
