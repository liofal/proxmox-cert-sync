# Helper Scripts

This directory contains utility scripts that support local development and testing.

## extract-k8s-cert.sh

Extracts `tls.crt` and `tls.key` from a Kubernetes TLS secret. Useful for populating the local `./test/certs` directory so you can dry-run the sync logic without touching Proxmox.

```bash
./scripts/extract-k8s-cert.sh [options]
```

Options:

- `-s, --secret SECRET_NAME` — Name of the TLS secret (default: `ingress-certmanager-tls`)
- `-n, --namespace NAMESPACE` — Kubernetes namespace (default: `default`)
- `-o, --output OUTPUT_DIR` — Directory to save the certs (default: `./test/certs`)
- `-h, --help` — Show help message

Example:

```bash
# Extract from 'my-tls-secret' in namespace 'production' to './output'
./scripts/extract-k8s-cert.sh -s my-tls-secret -n production -o ./output
```
