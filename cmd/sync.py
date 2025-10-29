#!/usr/bin/env python3
"""Proxmox certificate sync entrypoint."""

from __future__ import annotations

import datetime
import fnmatch
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

import requests
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, rsa
from cryptography.x509.oid import NameOID

DEFAULT_CERT_DIR = "/certs"
DEFAULT_THRESHOLD_DAYS = 20
DEFAULT_MAX_RETRIES = 1
DEFAULT_RETRY_DELAY = 5

LOG_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
LOG_LEVEL = LOG_LEVELS.get(os.getenv("LOG_LEVEL", "info").lower(), 20)
LOG_FORMAT = os.getenv("LOG_FORMAT", "text").lower()


class ConfigError(Exception):
    """Raised when configuration is invalid."""


@dataclass
class Config:
    api_url: str
    node_name: str
    token_id: str
    token_secret: str
    cert_dir: str = DEFAULT_CERT_DIR
    include_ca_bundle: bool = True
    verify_tls: bool = True
    ca_bundle_path: Optional[str] = None
    expected_hostnames: List[str] = field(default_factory=list)
    min_validity_days: int = DEFAULT_THRESHOLD_DAYS
    dry_run: bool = False
    services_to_restart: List[str] = field(default_factory=lambda: ["pveproxy"])
    poll_task: bool = True
    poll_interval_seconds: int = 2
    poll_timeout_seconds: int = 60
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay_seconds: int = DEFAULT_RETRY_DELAY

    @classmethod
    def from_env(cls) -> "Config":
        env = os.environ
        api_url = env.get("PROXMOX_API_URL", "").strip()
        node_name = env.get("PROXMOX_NODE_NAME", "").strip()
        token_id = env.get("PROXMOX_TOKEN_ID", "").strip()
        token_secret = env.get("PROXMOX_TOKEN_SECRET", "").strip()

        if not api_url:
            raise ConfigError("PROXMOX_API_URL is required")
        if not node_name:
            raise ConfigError("PROXMOX_NODE_NAME is required")
        if not token_id:
            raise ConfigError("PROXMOX_TOKEN_ID is required")
        if not token_secret:
            raise ConfigError("PROXMOX_TOKEN_SECRET is required")

        cert_dir = env.get("CERTIFICATE_DIRECTORY", DEFAULT_CERT_DIR)
        include_ca_bundle = _parse_bool(env.get("INCLUDE_CA_BUNDLE", "true"))
        verify_tls = _parse_bool(env.get("VERIFY_TLS", "true"))
        ca_bundle_path = env.get("CA_BUNDLE_PATH") or None
        min_validity_days = int(env.get("MIN_VALIDITY_DAYS", DEFAULT_THRESHOLD_DAYS))
        dry_run = _parse_bool(env.get("DRY_RUN", "false"))
        services_raw = env.get("SERVICES_TO_RESTART", "")
        services_to_restart = [s.strip() for s in services_raw.split(",") if s.strip()] or ["pveproxy"]
        poll_task = _parse_bool(env.get("POLL_TASK", "true"))
        poll_interval_seconds = int(env.get("POLL_INTERVAL_SECONDS", "2"))
        poll_timeout_seconds = int(env.get("POLL_TIMEOUT_SECONDS", "60"))
        max_retries = int(env.get("MAX_RETRIES", DEFAULT_MAX_RETRIES))
        retry_delay_seconds = int(env.get("RETRY_DELAY_SECONDS", DEFAULT_RETRY_DELAY))

        expected_hosts_env = env.get("EXPECTED_HOSTNAMES", "").strip()
        expected_hostnames = [h.strip() for h in expected_hosts_env.split(",") if h.strip()]
        if not expected_hostnames:
            parsed = urlparse(api_url)
            if parsed.hostname:
                expected_hostnames = [parsed.hostname]

        return cls(
            api_url=api_url.rstrip("/"),
            node_name=node_name,
            token_id=token_id,
            token_secret=token_secret,
            cert_dir=cert_dir,
            include_ca_bundle=include_ca_bundle,
            verify_tls=verify_tls,
            ca_bundle_path=ca_bundle_path,
            expected_hostnames=expected_hostnames,
            min_validity_days=min_validity_days,
            dry_run=dry_run,
            services_to_restart=services_to_restart,
            poll_task=poll_task,
            poll_interval_seconds=poll_interval_seconds,
            poll_timeout_seconds=poll_timeout_seconds,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
        )


def _parse_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def _should_log(level: str) -> bool:
    return LOG_LEVELS.get(level, 20) >= LOG_LEVEL


def _log(level: str, message: str, **fields) -> None:
    if not _should_log(level):
        return
    payload = {"ts": datetime.datetime.utcnow().isoformat() + "Z", "level": level, "msg": message}
    payload.update(fields)
    if LOG_FORMAT == "json":
        print(json.dumps(payload))
    else:
        print(" ".join(f"{key}={json.dumps(value)}" for key, value in payload.items()))


def _read_file(path: str) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError as exc:
        raise ConfigError(f"Required file missing: {path}") from exc


def _validate_certificate_pair(cert_pem: bytes, key_pem: bytes, expected_hosts: List[str], min_valid_days: int) -> None:
    certificate = x509.load_pem_x509_certificate(cert_pem)
    private_key = serialization.load_pem_private_key(key_pem, password=None)

    cert_public_key = certificate.public_key()
    private_public_key = private_key.public_key()

    if not _public_keys_match(cert_public_key, private_public_key):
        raise ConfigError("Certificate and private key do not match")

    not_after = certificate.not_valid_after
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    remaining = not_after - now
    if remaining < datetime.timedelta(days=min_valid_days):
        raise ConfigError(
            f"Certificate expires too soon (in {remaining.days} days); requires >= {min_valid_days} days"
        )

    if expected_hosts and not _certificate_covers_hosts(certificate, expected_hosts):
        raise ConfigError("Certificate does not cover required hostnames")


def _public_keys_match(cert_key, private_key) -> bool:
    if isinstance(cert_key, rsa.RSAPublicKey) and isinstance(private_key, rsa.RSAPublicKey):
        return cert_key.public_numbers() == private_key.public_numbers()
    if isinstance(cert_key, ec.EllipticCurvePublicKey) and isinstance(private_key, ec.EllipticCurvePublicKey):
        return cert_key.public_numbers() == private_key.public_numbers()
    if isinstance(cert_key, dsa.DSAPublicKey) and isinstance(private_key, dsa.DSAPublicKey):
        return cert_key.public_numbers() == private_key.public_numbers()
    return False


def _certificate_covers_hosts(certificate: x509.Certificate, expected_hosts: List[str]) -> bool:
    names: List[str] = []
    try:
        san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        names.extend(san.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        pass

    common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    for attribute in common_names:
        names.append(attribute.value)

    normalized = [name.lower() for name in names]
    for host in expected_hosts:
        host_lower = host.lower()
        if not any(fnmatch.fnmatch(host_lower, pattern) for pattern in normalized):
            return False
    return True


def _build_session(config: Config) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"PVEAPIToken={config.token_id}={config.token_secret}",
            "User-Agent": "proxmox-cert-sync/1.0",
        }
    )
    if config.ca_bundle_path:
        session.verify = config.ca_bundle_path
    else:
        session.verify = config.verify_tls
    return session


def _upload_certificate(session: requests.Session, config: Config, cert_pem: bytes, key_pem: bytes, ca_pem: Optional[bytes]) -> Optional[str]:
    bundle = cert_pem
    if ca_pem and config.include_ca_bundle:
        bundle += b"\n" + ca_pem.strip() + b"\n"

    url = f"{config.api_url}/api2/json/nodes/{config.node_name}/certificates/custom"
    data = {
        "certificates": bundle.decode("utf-8"),
        "key": key_pem.decode("utf-8"),
        "force": 1,
    }
    response = session.post(url, data=data, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Certificate upload failed: HTTP {response.status_code} {response.text}")

    payload = response.json()
    task_id = None
    if isinstance(payload.get("data"), str):
        task_id = payload["data"]

    _log("info", "Certificate upload request sent", task_id=task_id)
    return task_id


def _poll_task(session: requests.Session, config: Config, task_id: str) -> None:
    deadline = time.time() + config.poll_timeout_seconds
    url = f"{config.api_url}/api2/json/nodes/{config.node_name}/tasks/{task_id}/status"
    while time.time() < deadline:
        response = session.get(url, timeout=15)
        if response.status_code >= 400:
            raise RuntimeError(f"Task status fetch failed: HTTP {response.status_code} {response.text}")
        data = response.json().get("data") or {}
        status = data.get("status")
        exitstatus = data.get("exitstatus")
        if status == "stopped":
            if exitstatus == "OK":
                _log("info", "Certificate upload task completed", task_id=task_id)
                return
            raise RuntimeError(f"Certificate upload task failed: {exitstatus}")
        time.sleep(config.poll_interval_seconds)
    raise RuntimeError("Timed out waiting for certificate upload task to complete")


def _restart_services(session: requests.Session, config: Config) -> None:
    for service in config.services_to_restart:
        url = f"{config.api_url}/api2/json/nodes/{config.node_name}/services/{service}/restart"
        # Proxmox expects a POST for service restarts; PUT returns 501 on recent releases.
        response = session.post(url, timeout=15)
        if response.status_code >= 400:
            raise RuntimeError(f"Failed to restart service {service}: HTTP {response.status_code} {response.text}")
        _log("info", "Service restart requested", service=service)


def _verify_remote_certificate(session: requests.Session, config: Config) -> None:
    url = f"{config.api_url}/api2/json/nodes/{config.node_name}/certificates/info"
    response = session.get(url, timeout=15)
    if response.status_code >= 400:
        _log("warn", "Unable to verify remote certificate", http_status=response.status_code)
        return
    data = response.json().get("data") or {}
    fingerprint = data.get("fingerprint")
    not_after = data.get("notafter")
    _log("info", "Remote certificate state", fingerprint=fingerprint, not_after=not_after)


def main() -> int:
    try:
        config = Config.from_env()
    except ConfigError as exc:
        _log("error", "Configuration error", error=str(exc))
        return 2

    cert_path = os.path.join(config.cert_dir, os.environ.get("TLS_CERT_KEY", "tls.crt"))
    key_path = os.path.join(config.cert_dir, os.environ.get("TLS_KEY_KEY", "tls.key"))
    ca_path = os.path.join(config.cert_dir, os.environ.get("TLS_CA_KEY", "ca.crt"))

    try:
        cert_pem = _read_file(cert_path)
        key_pem = _read_file(key_path)
        ca_pem = _read_file(ca_path) if os.path.exists(ca_path) else None

        _validate_certificate_pair(cert_pem, key_pem, config.expected_hostnames, config.min_validity_days)
        _log("info", "Certificate validation succeeded")
    except ConfigError as exc:
        _log("error", "Validation failure", error=str(exc))
        return 3
    except Exception as exc:  # noqa: BLE001
        _log("error", "Unexpected validation error", error=str(exc))
        return 4

    if config.dry_run:
        _log("info", "Dry run complete; skipping upload")
        return 0

    session = _build_session(config)

    attempt = 0
    while attempt <= config.max_retries:
        try:
            task_id = _upload_certificate(session, config, cert_pem, key_pem, ca_pem)
            if task_id and config.poll_task:
                _poll_task(session, config, task_id)
            _restart_services(session, config)
            _verify_remote_certificate(session, config)
            _log("info", "Certificate sync completed")
            return 0
        except Exception as exc:  # noqa: BLE001
            attempt += 1
            _log("error", "Sync attempt failed", attempt=attempt, error=str(exc))
            if attempt > config.max_retries:
                break
            time.sleep(config.retry_delay_seconds * attempt)

    return 1


if __name__ == "__main__":
    sys.exit(main())
