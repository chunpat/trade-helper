from __future__ import annotations

import argparse
import json
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Dict

import httpx
from eth_abi import encode
from eth_account import Account
from eth_utils import keccak, to_checksum_address

from app.core.database import SessionLocal
from app.models.risk_control import Account as RiskControlAccount
from app.services.exchange.binance_adapter import create_adapter_for_account
from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams


CHAIN_ID = 137
PUSD_ADDRESS = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
DEPOSIT_WALLET_FACTORY = "0x00000000000Fb5C9ADea0298D729A0CB3823Cc07"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
WALLET_BATCH_TYPES = {
    "Call": [
        {"name": "target", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "data", "type": "bytes"},
    ],
    "Batch": [
        {"name": "wallet", "type": "address"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
        {"name": "calls", "type": "Call[]"},
    ],
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 Polymarket deposit wallet 转出 pUSD")
    parser.add_argument("--account-id", type=int, required=True, help="数据库中的账户 ID")
    parser.add_argument("--to", required=True, help="接收地址")
    parser.add_argument("--amount-usdc", required=True, help="转出金额，单位 USDC / pUSD")
    parser.add_argument("--deadline-seconds", type=int, default=600, help="WALLET batch 过期秒数，默认 600")
    parser.add_argument("--dry-run", action="store_true", help="只生成 payload，不提交 relayer")
    return parser.parse_args()


def _mask(value: str | None) -> str | None:
    if not value:
        return value
    value = str(value)
    if len(value) <= 12:
        return value
    return f"{value[:8]}...{value[-4:]}"


def _to_base_units(amount_text: str) -> int:
    try:
        amount = Decimal(str(amount_text))
    except InvalidOperation as exc:
        raise ValueError("amount-usdc 不是有效数字") from exc
    if amount <= 0:
        raise ValueError("amount-usdc 必须大于 0")
    scaled = (amount * Decimal("1000000")).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return int(scaled)


def _build_transfer_calldata(to_address: str, amount_base_units: int) -> str:
    selector = keccak(text="transfer(address,uint256)")[:4]
    encoded_args = encode(["address", "uint256"], [to_checksum_address(to_address), amount_base_units])
    return "0x" + (selector + encoded_args).hex()


def _build_wallet_batch_signature(
    *,
    private_key: str,
    deposit_wallet: str,
    nonce: int,
    deadline: int,
    calls: list[Dict[str, Any]],
) -> str:
    signed = Account.sign_typed_data(
        private_key=private_key,
        domain_data={
            "name": "DepositWallet",
            "version": "1",
            "chainId": CHAIN_ID,
            "verifyingContract": to_checksum_address(deposit_wallet),
        },
        message_types=WALLET_BATCH_TYPES,
        message_data={
            "wallet": to_checksum_address(deposit_wallet),
            "nonce": int(nonce),
            "deadline": int(deadline),
            "calls": calls,
        },
    )
    return "0x" + signed.signature.hex()


def _fetch_wallet_nonce(adapter: Any, owner_address: str) -> int:
    response = httpx.get(
        f"{adapter.relayer_host}/nonce",
        params={"address": owner_address, "type": "WALLET"},
        headers=adapter._build_relayer_headers(),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return int(payload.get("nonce") or 0)


def _submit_wallet_batch(adapter: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = httpx.post(
        f"{adapter.relayer_host}/submit",
        headers={
            **adapter._build_relayer_headers(),
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    args = _parse_args()
    target_address = to_checksum_address(args.to)
    amount_base_units = _to_base_units(args.amount_usdc)

    db = SessionLocal()
    try:
        account = db.query(RiskControlAccount).filter(RiskControlAccount.id == args.account_id).first()
        if account is None:
            raise SystemExit(f"account {args.account_id} not found")

        adapter = create_adapter_for_account(account)
        if adapter is None:
            raise SystemExit("failed to build polymarket adapter")
        if getattr(account, "exchange", "") != "polymarket":
            raise SystemExit("account is not a polymarket account")
        if int(getattr(adapter, "signature_type", 0) or 0) != 3:
            raise SystemExit("account is not configured as deposit wallet / POLY_1271")
        if not getattr(adapter, "funder", ""):
            raise SystemExit("missing deposit wallet address")
        if not getattr(adapter, "private_key", ""):
            raise SystemExit("missing signer private key")

        client = adapter._build_authed_client()
        collateral = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        available_balance = int(collateral.get("balance") or 0)
        if amount_base_units > available_balance:
            raise SystemExit(
                f"insufficient pUSD balance: requested={amount_base_units}, available={available_balance}"
            )

        owner_address = to_checksum_address(account.api_key)
        deposit_wallet = to_checksum_address(adapter.funder)
        nonce = _fetch_wallet_nonce(adapter, owner_address)
        deadline = int(time.time()) + int(args.deadline_seconds)
        calls = [
            {
                "target": PUSD_ADDRESS,
                "value": "0",
                "data": _build_transfer_calldata(target_address, amount_base_units),
            }
        ]
        signature = _build_wallet_batch_signature(
            private_key=adapter.private_key,
            deposit_wallet=deposit_wallet,
            nonce=nonce,
            deadline=deadline,
            calls=calls,
        )

        submit_payload = {
            "type": "WALLET",
            "from": owner_address,
            "to": DEPOSIT_WALLET_FACTORY,
            "nonce": str(nonce),
            "signature": signature,
            "depositWalletParams": {
                "depositWallet": deposit_wallet,
                "deadline": str(deadline),
                "calls": calls,
            },
        }

        summary = {
            "account_id": account.id,
            "owner_address": owner_address,
            "deposit_wallet": deposit_wallet,
            "relayer_api_key": _mask((account.settings or {}).get("polymarket_relayer_api_key")),
            "target_address": target_address,
            "amount_usdc": str(Decimal(amount_base_units) / Decimal("1000000")),
            "amount_base_units": str(amount_base_units),
            "available_balance_base_units": str(available_balance),
            "wallet_nonce": str(nonce),
            "deadline": str(deadline),
            "calls": calls,
            "submit_payload": submit_payload,
        }

        if args.dry_run:
            print(json.dumps({"ok": True, "dry_run": True, **summary}, ensure_ascii=False, indent=2))
            return

        submit_result = _submit_wallet_batch(adapter, submit_payload)
        print(json.dumps({"ok": True, "dry_run": False, **summary, "submit_result": submit_result}, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()