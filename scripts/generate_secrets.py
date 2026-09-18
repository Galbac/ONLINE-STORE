#!/usr/bin/env python3
"""Production Secrets Generator and Hardening Validator.

Generates cryptographically secure 256-bit keys and audits .env files.
"""

import os
import secrets
import sys
from pathlib import Path


DEFAULT_WEAK_VALUES = {
    "change-me-in-env",
    "postgres",
    "secret",
    "123456",
    "StrongPassword123",
    "admin",
}


def generate_secure_token(bytes_len: int = 32) -> str:
    return secrets.token_hex(bytes_len)


def audit_env_file(env_path: Path) -> list[str]:
    warnings = []
    if not env_path.exists():
        warnings.append(f"File not found: {env_path}")
        return warnings

    with open(env_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("\"'")

            if val in DEFAULT_WEAK_VALUES:
                warnings.append(f"Line {line_no}: Weak default value '{val}' detected for key '{key}'!")

    return warnings


def main():
    print("=" * 60)
    print("🔒 GroceryStore Production Hardening & Secrets Generator")
    print("=" * 60)

    # 1. Audit .env if present
    env_file = Path(".env")
    if env_file.exists():
        print(f"\n[1] Auditing existing {env_file}...")
        issues = audit_env_file(env_file)
        if issues:
            print("⚠️  Security warnings found in .env:")
            for issue in issues:
                print(f"   ❌ {issue}")
        else:
            print("✅ No weak default values detected in .env!")
    else:
        print("\n[1] No .env file found in current directory. Creating fresh secrets...")

    # 2. Generate cryptographically strong keys
    print("\n[2] Generated 256-bit cryptographically secure production keys:")
    print("-" * 60)
    print(f"JWT_SECRET_KEY={generate_secure_token(32)}")
    print(f"POSTGRES_PASSWORD={generate_secure_token(24)}")
    print(f"ONE_C_API_TOKEN={generate_secure_token(32)}")
    print(f"HEALTH_INTERNAL_TOKEN={generate_secure_token(24)}")
    print(f"PAYMENT_PROVIDER_WEBHOOK_SECRET={generate_secure_token(32)}")
    print("-" * 60)
    print("\n💡 Copy and paste these keys into your production .env on the server.")
    print("=" * 60)


if __name__ == "__main__":
    main()
