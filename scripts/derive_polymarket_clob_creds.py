import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read_private_key() -> str:
    private_key = (
        os.getenv("POLYMARKET_SIGNER_PRIVATE_KEY")
        or os.getenv("POLY_SIGNER_PRIVATE_KEY")
        or ""
    ).strip()
    if private_key and not private_key.startswith("0x"):
        private_key = f"0x{private_key}"
    return private_key


def _build_adapter_for_account(account, private_key: str):
    from app.services.exchange.polymarket_adapter import PolymarketAdapter

    return PolymarketAdapter(
        wallet_address=account.api_key,
        private_key=private_key,
        api_passphrase=getattr(account, "api_passphrase", None),
        settings=dict(account.settings or {}),
        proxy=(account.settings or {}).get("proxy") if account.settings else None,
    )


def _derive_signer_address(private_key: str) -> str:
    account_module = importlib.import_module("eth_account")
    return account_module.Account.from_key(private_key).address


def _issue_api_creds(adapter) -> dict:
    client = adapter._build_clob_client()
    create_errors = []

    for attempt in range(1, 4):
        try:
            creds_obj = client.create_api_key()
            return {
                "api_key": creds_obj.api_key,
                "api_secret": creds_obj.api_secret,
                "api_passphrase": creds_obj.api_passphrase,
                "source": f"create_api_key attempt {attempt}",
            }
        except Exception as exc:
            create_errors.append(f"attempt {attempt}: {exc}")
            if attempt < 3:
                time.sleep(1)

    try:
        creds_obj = client.derive_api_key()
        return {
            "api_key": creds_obj.api_key,
            "api_secret": creds_obj.api_secret,
            "api_passphrase": creds_obj.api_passphrase,
            "source": "derive_api_key",
            "create_errors": create_errors,
        }
    except Exception as exc:
        create_error_text = " | ".join(create_errors) if create_errors else "none"
        raise RuntimeError(
            "Failed to create or derive Polymarket CLOB credentials. "
            f"create_api_key errors: {create_error_text}. "
            f"derive_api_key error: {exc}"
        ) from exc


def _verify_creds(adapter, creds: dict) -> dict:
    from app.services.exchange.polymarket_adapter import GET_API_KEYS

    adapter.settings = {
        **dict(adapter.settings or {}),
        "polymarket_clob_api_key": creds["api_key"],
        "polymarket_clob_api_secret": creds["api_secret"],
        "polymarket_clob_api_passphrase": creds["api_passphrase"],
    }
    started_at = time.time()
    payload = adapter._l2_request_sync(method="GET", endpoint=GET_API_KEYS)
    return {
        "ok": True,
        "elapsed_ms": int((time.time() - started_at) * 1000),
        "response": payload,
    }


def _save_account(account, private_key: str, creds: dict) -> None:
    settings = dict(account.settings or {})
    settings["polymarket_clob_api_key"] = creds["api_key"]
    settings["polymarket_clob_api_secret"] = creds["api_secret"]
    settings["polymarket_clob_api_passphrase"] = creds["api_passphrase"]
    settings.setdefault("polymarket_signer_address", account.api_key)
    if settings.get("polymarket_funder_address") and settings.get("polymarket_signature_type") in (None, ""):
        settings["polymarket_signature_type"] = 3
    account.api_secret = private_key
    account.settings = settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive Polymarket CLOB credentials from a local signer private key.")
    parser.add_argument("--account-id", type=int, help="Polymarket account id in local DB")
    parser.add_argument("--write-account", action="store_true", help="Write signer private key and derived CLOB creds back to the account")
    parser.add_argument("--skip-verify", action="store_true", help="Skip GET /auth/api-keys verification")
    args = parser.parse_args()

    private_key = _read_private_key()
    if not private_key:
        print("Missing POLYMARKET_SIGNER_PRIVATE_KEY or POLY_SIGNER_PRIVATE_KEY", file=sys.stderr)
        return 1

    if len(private_key) != 66 or not private_key.startswith("0x"):
        print("Signer private key must be a 0x-prefixed 32-byte hex string", file=sys.stderr)
        return 1

    if args.account_id is None:
        print("--account-id is required so the script can reuse the account's funder/signature_type settings", file=sys.stderr)
        return 1

    try:
        from app.core.database import SessionLocal
        from app.models.risk_control import Account
    except ModuleNotFoundError as exc:
        print(
            "Missing runtime dependency: "
            f"{exc.name}. Install project requirements first with `python3 -m pip install -r requirements.txt`, "
            "or run this script inside an updated backend container.",
            file=sys.stderr,
        )
        return 1

    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == args.account_id).first()
        if account is None:
            print(f"Account {args.account_id} not found", file=sys.stderr)
            return 1
        if (account.exchange or "").lower() != "polymarket":
            print(f"Account {args.account_id} is not a Polymarket account", file=sys.stderr)
            return 1

        signer_address = _derive_signer_address(private_key)
        expected_signer = (account.api_key or "").strip().lower()
        if signer_address.lower() != expected_signer:
            print(
                "Signer private key does not match account.api_key. "
                f"derived signer={signer_address}, account signer={account.api_key}",
                file=sys.stderr,
            )
            return 1

        adapter = _build_adapter_for_account(account, private_key)
        creds = _issue_api_creds(adapter)

        result = {
            "account_id": account.id,
            "wallet_address": account.api_key,
            "signature_type": adapter.signature_type,
            "funder": adapter.funder,
            "creds": creds,
        }

        if not args.skip_verify:
            result["verification"] = _verify_creds(adapter, creds)

        if args.write_account:
            _save_account(account, private_key, creds)
            db.add(account)
            db.commit()
            result["account_updated"] = True

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())