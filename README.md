# proxmox-cert-sync

`proxmox-cert-sync` publishes the latest TLS certificate managed inside Kubernetes to a Proxmox VE node. It validates the certificate chain, uploads it using the Proxmox REST API, and restarts the required services.

## Components

- **Container image**: Runs the sync script with minimal runtime dependencies.
- **Kubernetes manifests**: `manifests/proxmox-cert-sync.yaml` applies the CronJob, RBAC, and ServiceAccount.
- **Automation helpers**: Makefile target for building the container image.

Refer to `docs/INSTALL.md` for installation and operational guidance.
