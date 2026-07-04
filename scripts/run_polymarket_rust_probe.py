import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MANIFEST_PATH = PROJECT_ROOT / "scripts" / "polymarket_rust_probe" / "Cargo.toml"


def _normalize_private_key(private_key: str) -> str:
    value = (private_key or "").strip()
    if value and not value.startswith("0x"):
        value = f"0x{value}"
    return value


def _find_cargo() -> str:
    candidates = [
        shutil.which("cargo"),
        str(Path.home() / ".cargo" / "bin" / "cargo"),
        "/usr/local/opt/rustup/bin/cargo",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("cargo not found; install Rust toolchain first")


def _build_env(account_snapshot: dict, args) -> dict:
    settings = dict(account_snapshot.get("settings") or {})
    private_key = _normalize_private_key(account_snapshot.get("api_secret") or "")
    funder = str(settings.get("polymarket_funder_address") or "").strip()
    clob_api_key = str(settings.get("polymarket_clob_api_key") or "").strip()
    clob_api_secret = str(settings.get("polymarket_clob_api_secret") or "").strip()
    clob_api_passphrase = str(settings.get("polymarket_clob_api_passphrase") or "").strip()
    if not private_key:
        raise RuntimeError("account.api_secret is empty")
    if not funder:
        raise RuntimeError("missing settings.polymarket_funder_address")

    env = os.environ.copy()
    env["PATH"] = ":".join(
        [
            str(Path.home() / ".cargo" / "bin"),
            "/usr/local/opt/rustup/bin",
            env.get("PATH", ""),
        ]
    )
    env["POLYMARKET_PRIVATE_KEY"] = private_key
    env["POLYMARKET_FUNDER"] = funder
    env["POLYMARKET_HOST"] = args.host
    env["POLYMARKET_DO_POST_ORDER"] = "true" if args.post_order else "false"
    if clob_api_key and clob_api_secret and clob_api_passphrase:
        env["POLYMARKET_CLOB_API_KEY"] = clob_api_key
        env["POLYMARKET_CLOB_API_SECRET"] = clob_api_secret
        env["POLYMARKET_CLOB_API_PASSPHRASE"] = clob_api_passphrase
    if args.token_id:
        env["POLYMARKET_TOKEN_ID"] = args.token_id
    if args.price is not None:
        env["POLYMARKET_PRICE"] = str(args.price)
    if args.size is not None:
        env["POLYMARKET_SIZE"] = str(args.size)
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the standalone Rust Polymarket probe with account credentials loaded from DB")
    parser.add_argument("--account-id", type=int, required=True, help="Polymarket account id in local DB")
    parser.add_argument("--host", default="https://clob-v2.polymarket.com", help="CLOB host, defaults to the V2 endpoint")
    parser.add_argument("--post-order", action="store_true", help="Also place a minimal BUY limit order after auth succeeds")
    parser.add_argument("--token-id", help="Token id to use when --post-order is set")
    parser.add_argument("--price", type=float, default=0.35, help="Limit price used for --post-order")
    parser.add_argument("--size", type=float, default=5.0, help="Order size used for --post-order")
    args = parser.parse_args()

    if args.post_order and not args.token_id:
        raise SystemExit("--token-id is required with --post-order")

    from app.core.database import SessionLocal
    from app.models.risk_control import Account

    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == args.account_id).first()
        if account is None:
            raise SystemExit(f"Account {args.account_id} not found")
        if (account.exchange or "").strip().lower() != "polymarket":
            raise SystemExit(f"Account {args.account_id} is not a Polymarket account")

        account_snapshot = {
            "id": account.id,
            "exchange": account.exchange,
            "api_key": account.api_key,
            "api_secret": account.api_secret,
            "settings": dict(account.settings or {}),
        }
    finally:
        db.close()

    cargo = _find_cargo()
    env = _build_env(account_snapshot, args)

    print(
        {
            "account_id": account_snapshot["id"],
            "host": args.host,
            "wallet_address": account_snapshot["api_key"],
            "funder": (account_snapshot.get("settings") or {}).get("polymarket_funder_address"),
            "has_saved_clob_creds": all(
                bool(str((account_snapshot.get("settings") or {}).get(key) or "").strip())
                for key in (
                    "polymarket_clob_api_key",
                    "polymarket_clob_api_secret",
                    "polymarket_clob_api_passphrase",
                )
            ),
            "post_order": args.post_order,
            "token_id": args.token_id,
            "price": args.price,
            "size": args.size,
        }
    )

    command = [cargo, "run", "--manifest-path", str(MANIFEST_PATH), "--quiet"]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())