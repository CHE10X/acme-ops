#!/usr/bin/env python3
"""
Acme License Verifier — PROJ-2026-010
Offline Ed25519 license verification for Acme CLI products.

Usage (Python):
    from acme_license import check_license
    result = check_license(required_feature="sentinel")
    if not result.valid:
        print(f"[ERROR] {result.message}")
        sys.exit(2)

Usage (CLI):
    python3 acme_license.py --feature sentinel
    # exit 0 = valid, exit 2 = invalid/missing, exit 3 = expired
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

__version__ = "1.0.0"

# License search path — first found wins
LICENSE_SEARCH_PATHS = [
    Path(os.environ.get("ACME_LICENSE_PATH", "")) if os.environ.get("ACME_LICENSE_PATH") else None,
    Path.home() / ".acme" / "license.json",
    Path("/etc/acme/license.json"),
    Path("license.json"),
]

# Public key location — env var or ~/.acme/acme_public_key.pem
PUBLIC_KEY_ENV = "ACME_LICENSE_PUBLIC_KEY"
PUBLIC_KEY_PATH = Path.home() / ".acme" / "acme_public_key.pem"

# Products with no free tier — all functionality gated
FULLY_GATED_FEATURES = {
    "sentinel",
    "infrawatch",
    "watchdog",
    "lazarus",
    "agent911",
    "fleet_control",
    "radcheck:predictive",
}

# Free tier features (community mode)
COMMUNITY_FEATURES = {
    "watch",
    "radcheck:basic",
    "telemetry:basic",
}


@dataclass
class LicenseResult:
    valid: bool
    message: str
    plan: Optional[str] = None
    features: Optional[list] = None
    expires: Optional[str] = None
    license_id: Optional[str] = None


def _find_license_file() -> Optional[Path]:
    for path in LICENSE_SEARCH_PATHS:
        if path and path.exists():
            return path
    return None


def _load_public_key() -> Optional[bytes]:
    """Load Ed25519 public key from env or file."""
    raw = os.environ.get(PUBLIC_KEY_ENV)
    if raw:
        try:
            return base64.b64decode(raw)
        except Exception:
            pass

    if PUBLIC_KEY_PATH.exists():
        content = PUBLIC_KEY_PATH.read_text().strip()
        # Strip PEM headers if present
        lines = [l for l in content.splitlines() if not l.startswith("-----")]
        try:
            return base64.b64decode("".join(lines))
        except Exception:
            pass

    return None


def _verify_signature(license_data: dict, signature_b64: str, public_key_bytes: bytes) -> bool:
    """Verify Ed25519 signature over the canonical license payload."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        # cryptography library not available — skip signature verification
        # Log warning but don't block (graceful degradation for environments without cryptography)
        return True

    try:
        # Canonical payload: all fields except signature, sorted keys, no whitespace
        payload_fields = {k: v for k, v in license_data.items() if k != "signature"}
        canonical = json.dumps(payload_fields, sort_keys=True, separators=(",", ":")).encode()

        sig_bytes = base64.b64decode(signature_b64)
        public_key = load_der_public_key(public_key_bytes)
        public_key.verify(sig_bytes, canonical)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def _check_integrity_digest(license_data: dict) -> bool:
    """Verify SHA256 integrity digest matches license content."""
    digest = license_data.get("integrity_digest")
    if not digest:
        return True  # Not required in all license versions

    payload_fields = {k: v for k, v in license_data.items()
                      if k not in ("signature", "integrity_digest")}
    canonical = json.dumps(payload_fields, sort_keys=True, separators=(",", ":")).encode()
    computed = hashlib.sha256(canonical).hexdigest()
    return computed == digest


def check_license(required_feature: Optional[str] = None) -> LicenseResult:
    """
    Load and validate the local license file.

    Args:
        required_feature: Feature flag to check (e.g. "sentinel", "infrawatch").
                         If None, just validates the license is present and valid.

    Returns:
        LicenseResult with valid=True if licensed, valid=False otherwise.
        Never raises — always returns a result.
    """
    try:
        return _check_license_internal(required_feature)
    except Exception as e:
        return LicenseResult(
            valid=False,
            message=f"License check failed unexpectedly: {e}. Contact support@acmeagentsupply.com"
        )


def _check_license_internal(required_feature: Optional[str]) -> LicenseResult:
    # Community mode check — free features don't need a license
    if required_feature and required_feature in COMMUNITY_FEATURES:
        return LicenseResult(valid=True, message="Community feature — no license required.",
                             plan="community")

    # Find license file
    license_path = _find_license_file()
    if not license_path:
        return LicenseResult(
            valid=False,
            message=(
                f"No Acme license found. "
                f"Purchase at acmeagentsupply.com or set ACME_LICENSE_PATH. "
                f"Expected: ~/.acme/license.json"
            )
        )

    # Parse license
    try:
        license_data = json.loads(license_path.read_text())
    except Exception as e:
        return LicenseResult(
            valid=False,
            message=f"License file could not be parsed: {e}. Re-install from your delivery email."
        )

    # Integrity digest check
    if not _check_integrity_digest(license_data):
        return LicenseResult(
            valid=False,
            message="License file has been tampered with. Re-install from your delivery email."
        )

    # Signature verification
    signature = license_data.get("signature")
    if signature:
        public_key = _load_public_key()
        if public_key:
            if not _verify_signature(license_data, signature, public_key):
                return LicenseResult(
                    valid=False,
                    message="License signature is invalid. Re-install from your delivery email."
                )

    # Expiry check
    valid_until = license_data.get("valid_until")
    if valid_until:
        try:
            expiry = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expiry:
                return LicenseResult(
                    valid=False,
                    message=f"License expired on {valid_until}. Renew at acmeagentsupply.com.",
                    plan=license_data.get("plan"),
                    expires=valid_until,
                    license_id=license_data.get("license_id"),
                )
        except Exception:
            pass

    # Feature check
    plan = license_data.get("plan", "community")
    features = license_data.get("features", [])

    if required_feature and required_feature in FULLY_GATED_FEATURES:
        if required_feature not in features:
            return LicenseResult(
                valid=False,
                message=(
                    f"Your license (plan={plan}) does not include '{required_feature}'. "
                    f"Upgrade at acmeagentsupply.com."
                ),
                plan=plan,
                features=features,
                license_id=license_data.get("license_id"),
            )

    return LicenseResult(
        valid=True,
        message="License valid.",
        plan=plan,
        features=features,
        expires=valid_until,
        license_id=license_data.get("license_id"),
    )


def print_license_status() -> None:
    """Print human-readable license status. Used by `acme license status`."""
    result = check_license()
    if result.valid:
        print(f"✅ License valid")
        print(f"   ID:      {result.license_id or 'unknown'}")
        print(f"   Plan:    {result.plan or 'unknown'}")
        print(f"   Expires: {result.expires or 'never'}")
        print(f"   Features: {', '.join(result.features or [])}")
    else:
        print(f"❌ License invalid: {result.message}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Acme License Verifier")
    parser.add_argument("--version", action="version", version=f"acme_license {__version__}")
    parser.add_argument("--feature", type=str, default=None,
                        help="Feature flag to check (e.g. sentinel, infrawatch)")
    parser.add_argument("--status", action="store_true",
                        help="Print full license status")
    args = parser.parse_args()

    if args.status:
        print_license_status()
        sys.exit(0)

    result = check_license(required_feature=args.feature)

    if not result.valid:
        print(f"[ACME LICENSE] ❌ {result.message}", file=sys.stderr)
        if result.expires and "expired" in result.message:
            sys.exit(3)
        sys.exit(2)

    sys.exit(0)
