#!/bin/bash
set -e
# Extract certificates from Kubernetes secret for testing

# Defaults
DEFAULT_SECRET_NAME="ingress-certmanager-tls"
DEFAULT_NAMESPACE="default" # Changed default from 'downloads'
OUTPUT_DIR="./test/certs"

# Initialize variables with defaults
SECRET_NAME="$DEFAULT_SECRET_NAME"
NAMESPACE="$DEFAULT_NAMESPACE"

# Function to show help message
usage() {
  echo "Usage: $0 [-s SECRET_NAME] [-n NAMESPACE] [-o OUTPUT_DIR]"
  echo "Extracts tls.crt and tls.key from a Kubernetes secret."
  echo ""
  echo "Options:"
  echo "  -s, --secret SECRET_NAME  Name of the TLS secret (default: $DEFAULT_SECRET_NAME)"
  echo "  -n, --namespace NAMESPACE Kubernetes namespace (default: $DEFAULT_NAMESPACE)"
  echo "  -o, --output OUTPUT_DIR   Directory to save the certs (default: $OUTPUT_DIR)"
  echo "  -h, --help                Show this help message"
  exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -s|--secret)
      SECRET_NAME="$2"
      shift 2
      ;;
    -n|--namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    -o|--output)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

echo "Extracting certificate from secret '$SECRET_NAME' in namespace '$NAMESPACE'..."

# Extract certificate
CERT_DATA=$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.tls\.crt}' 2>/dev/null)
if [ -z "$CERT_DATA" ]; then
  echo "Error: Could not retrieve tls.crt from secret '$SECRET_NAME' in namespace '$NAMESPACE'."
  exit 1
fi
echo "$CERT_DATA" | base64 -d > "$OUTPUT_DIR/tls.crt"

# Extract key
KEY_DATA=$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.tls\.key}' 2>/dev/null)
if [ -z "$KEY_DATA" ]; then
  echo "Error: Could not retrieve tls.key from secret '$SECRET_NAME' in namespace '$NAMESPACE'."
  # Clean up cert file if key extraction failed
  rm -f "$OUTPUT_DIR/tls.crt"
  exit 1
fi
echo "$KEY_DATA" | base64 -d > "$OUTPUT_DIR/tls.key"

echo "Certificate and key successfully saved to $OUTPUT_DIR"
