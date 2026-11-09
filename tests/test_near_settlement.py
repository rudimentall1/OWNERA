import json

import pytest

from ownera.near_settlement import NearNep141SettlementVerifier, NearSettlementVerificationError

TX = "11111111111111111111111111111111111111111111"
SIGNER = "marketplace.near"
TOKEN = "usdc.near"
SENDER = "treasury.near"
RECIPIENT = "ownera.near"
AMOUNT = "9500000"


class Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.payload).encode()


def payload(*, amount=AMOUNT, recipient=RECIPIENT, token=TOKEN, status=None, signer=SIGNER):
    log = "EVENT_JSON:" + json.dumps({
        "standard": "nep141", "version": "1.0.0", "event": "ft_transfer",
        "data": [{"old_owner_id": SENDER, "new_owner_id": recipient, "amount": amount}],
    })
    return {"jsonrpc": "2.0", "id": "1", "result": {
        "transaction": {"hash": TX, "signer_id": signer},
        "status": status or {"SuccessValue": ""},
        "receipts_outcome": [{"id": "receipt-1", "block_hash": "block-1", "outcome": {
            "executor_id": token, "status": {"SuccessValue": ""}, "logs": [log],
        }}],
    }}


def verifier(data):
    def opener(request, timeout):
        assert request.get_method() == "POST"
        body = json.loads(request.data)
        assert body["method"] == "EXPERIMENTAL_tx_status"
        assert body["params"] == [TX, SIGNER]
        return Response(data)
    return NearNep141SettlementVerifier(opener=opener)


def verify(v):
    return v.verify_payout(
        transaction_hash=TX, signer_account_id=SIGNER, token_contract=TOKEN,
        recipient_account_id=RECIPIENT, expected_amount_atomic=AMOUNT,
        expected_sender_account_id=SENDER,
    )


def test_verifies_final_nep141_payout_and_returns_evidence_digest():
    result = verify(verifier(payload()))
    assert result.amount_atomic == AMOUNT
    assert result.sender_account_id == SENDER
    assert result.recipient_account_id == RECIPIENT
    assert result.token_contract == TOKEN
    assert result.verification_level == "NEAR_RPC_VERIFIED"
    assert len(result.rpc_response_sha256) == 64


@pytest.mark.parametrize("data", [
    payload(status={"Failure": {"error_message": "failed"}}),
    payload(signer="attacker.near"),
    payload(recipient="attacker.near"),
    payload(token="fake-token.near"),
    payload(amount="1"),
])
def test_rejects_failed_or_mismatched_payout(data):
    with pytest.raises(NearSettlementVerificationError):
        verify(verifier(data))


def test_rejects_missing_transfer_event():
    data = payload()
    data["result"]["receipts_outcome"][0]["outcome"]["logs"] = []
    with pytest.raises(NearSettlementVerificationError, match="no matching"):
        verify(verifier(data))


def test_rejects_rpc_error():
    data = {"jsonrpc": "2.0", "id": "1", "error": {"code": -32000}}
    with pytest.raises(NearSettlementVerificationError, match="RPC returned an error"):
        verify(verifier(data))


def test_rejects_invalid_input_before_rpc():
    with pytest.raises(ValueError, match="transaction hash"):
        NearNep141SettlementVerifier(opener=lambda *_a, **_k: None).verify_payout(
            transaction_hash="not-a-hash", signer_account_id=SIGNER,
            token_contract=TOKEN, recipient_account_id=RECIPIENT,
            expected_amount_atomic=AMOUNT,
        )


def test_rejects_amount_mismatch():
    with pytest.raises(NearSettlementVerificationError, match="does not equal expected"):
        verify(verifier(payload(amount="9500001")))
