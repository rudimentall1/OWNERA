"""Read-only verification of NEAR NEP-141 payout transactions.

The verifier checks finalized transaction outcomes and NEP-141 ft_transfer
logs returned by a NEAR JSON-RPC node. It does not sign or submit transactions.
Its trust boundary includes the configured RPC endpoint; this is RPC-verified,
not a client-verified Merkle proof or a bank/Stripe settlement verification.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class NearSettlementVerificationError(RuntimeError):
    """A NEAR payout transaction could not be verified."""


_BASE58_TX_HASH = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{43,44}$")
_ACCOUNT_ID = re.compile(r"^[a-z0-9]+(?:[-_.][a-z0-9]+)*$")
_ATOMIC_AMOUNT = re.compile(r"^[0-9]+$")


@dataclass(frozen=True)
class VerifiedNearPayout:
    transaction_hash: str
    signer_account_id: str
    token_contract: str
    sender_account_id: str
    recipient_account_id: str
    amount_atomic: str
    receipt_ids: tuple[str, ...]
    block_hashes: tuple[str, ...]
    rpc_response_sha256: str
    verification_level: str = "NEAR_RPC_VERIFIED"


class NearNep141SettlementVerifier:
    """Verify a NEP-141 transfer using NEAR's final transaction-status RPC."""

    def __init__(
        self,
        rpc_url: str = "https://rpc.mainnet.near.org",
        *,
        opener: Callable = urlopen,
        timeout: int = 20,
    ) -> None:
        if not isinstance(rpc_url, str) or not rpc_url.startswith("https://"):
            raise ValueError("rpc_url must be an HTTPS endpoint")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.rpc_url = rpc_url
        self.opener = opener
        self.timeout = timeout

    def verify_payout(
        self,
        *,
        transaction_hash: str,
        signer_account_id: str,
        token_contract: str,
        recipient_account_id: str,
        expected_amount_atomic: str,
        expected_sender_account_id: str | None = None,
    ) -> VerifiedNearPayout:
        self._require(_BASE58_TX_HASH.fullmatch(transaction_hash) is not None, "invalid NEAR transaction hash")
        for value, label in (
            (signer_account_id, "signer_account_id"),
            (token_contract, "token_contract"),
            (recipient_account_id, "recipient_account_id"),
        ):
            self._require(_ACCOUNT_ID.fullmatch(value) is not None, f"invalid {label}")
        if expected_sender_account_id is not None:
            self._require(_ACCOUNT_ID.fullmatch(expected_sender_account_id) is not None, "invalid expected_sender_account_id")
        self._require(
            isinstance(expected_amount_atomic, str)
            and _ATOMIC_AMOUNT.fullmatch(expected_amount_atomic) is not None
            and int(expected_amount_atomic) > 0,
            "expected_amount_atomic must be a positive integer string",
        )

        response = self._rpc_transaction_status(transaction_hash, signer_account_id)
        transaction = response.get("transaction")
        if not isinstance(transaction, dict):
            raise NearSettlementVerificationError("RPC response is missing transaction")
        if transaction.get("hash") != transaction_hash:
            raise NearSettlementVerificationError("RPC transaction hash does not match request")
        if transaction.get("signer_id") != signer_account_id:
            raise NearSettlementVerificationError("RPC signer does not match requested signer")
        if not self._successful_status(response.get("status")):
            raise NearSettlementVerificationError("NEAR transaction has not reached successful final execution")

        receipts = response.get("receipts_outcome")
        if not isinstance(receipts, list):
            raise NearSettlementVerificationError("RPC response is missing receipts_outcome")

        matches: list[tuple[str, str, str, str]] = []
        for item in receipts:
            if not isinstance(item, dict):
                continue
            outcome = item.get("outcome")
            if not isinstance(outcome, dict) or outcome.get("executor_id") != token_contract:
                continue
            if not self._successful_status(outcome.get("status")):
                continue
            logs = outcome.get("logs")
            if not isinstance(logs, list):
                continue
            for log in logs:
                if not isinstance(log, str) or not log.startswith("EVENT_JSON:"):
                    continue
                try:
                    event = json.loads(log[len("EVENT_JSON:"):])
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("standard") != "nep141" or event.get("event") != "ft_transfer":
                    continue
                data = event.get("data")
                if not isinstance(data, list):
                    continue
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("new_owner_id") != recipient_account_id:
                        continue
                    if expected_sender_account_id is not None and entry.get("old_owner_id") != expected_sender_account_id:
                        continue
                    amount = entry.get("amount")
                    if not isinstance(amount, str) or _ATOMIC_AMOUNT.fullmatch(amount) is None:
                        continue
                    receipt_id = item.get("id")
                    block_hash = item.get("block_hash")
                    if not isinstance(receipt_id, str) or not isinstance(block_hash, str):
                        continue
                    matches.append((amount, receipt_id, block_hash, str(entry.get("old_owner_id", ""))))

        if not matches:
            raise NearSettlementVerificationError("no matching successful NEP-141 transfer was found")
        total = sum((int(row[0]) for row in matches), 0)
        if total != int(expected_amount_atomic):
            raise NearSettlementVerificationError(
                f"verified transfer amount {total} does not equal expected amount {expected_amount_atomic}"
            )
        senders = {row[3] for row in matches}
        if len(senders) != 1 or not next(iter(senders)):
            raise NearSettlementVerificationError("payout transfer sender is missing or inconsistent")

        response_digest = hashlib.sha256(
            json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return VerifiedNearPayout(
            transaction_hash=transaction_hash,
            signer_account_id=signer_account_id,
            token_contract=token_contract,
            sender_account_id=next(iter(senders)),
            recipient_account_id=recipient_account_id,
            amount_atomic=str(total),
            receipt_ids=tuple(sorted({row[1] for row in matches})),
            block_hashes=tuple(sorted({row[2] for row in matches})),
            rpc_response_sha256=response_digest,
        )

    def _rpc_transaction_status(self, transaction_hash: str, signer_account_id: str) -> dict:
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": "ownera-settlement-verifier",
            "method": "EXPERIMENTAL_tx_status",
            "params": [transaction_hash, signer_account_id],
        }, separators=(",", ":")).encode("utf-8")
        request = Request(
            self.rpc_url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "OWNERA-SettlementVerifier/0.1"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as result:
                payload = json.loads(result.read().decode("utf-8"))
        except HTTPError as exc:
            raise NearSettlementVerificationError(f"NEAR RPC returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NearSettlementVerificationError(f"NEAR RPC request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise NearSettlementVerificationError("NEAR RPC returned a non-object response")
        if payload.get("error") is not None:
            raise NearSettlementVerificationError("NEAR RPC returned an error")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise NearSettlementVerificationError("NEAR RPC response is missing result")
        return result

    @staticmethod
    def _successful_status(status: object) -> bool:
        return isinstance(status, dict) and "SuccessValue" in status

    @staticmethod
    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)
