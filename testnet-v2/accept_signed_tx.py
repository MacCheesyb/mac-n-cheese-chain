#!/usr/bin/env python3
"""
Accept a transaction signed OUTSIDE the testnet — e.g. by Mac
in his own wallet app (standalone wallet-app.html) or the browser
extension (extension/popup.js, v0.5+).

This is the ONLY way a transaction FROM Mac's genesis address
can enter the testnet:
  1. Mac signs the transfer in his own wallet app / extension
     (his private key never leaves his device, is never sent to
     us, and is never imported here).
  2. He gives us the signed transaction JSON (sender, recipient,
     amount, nonce, signature, sender_pubkey_hex, txid).
  3. This script verifies the signature against the sender's
     public key and the address derivation, then submits it to
     a testnet node, which re-verifies it before accepting it
     into the mempool.

Units — milli-R0NI (2026-11-23, commit e308fee): a transaction's
"amount" is integer milli-R0NI (1 R0NI = 1000 milli; smallest unit
0.001 R0NI), and a milli-aware signer marks its tx with
"amount_unit": "milli-R0NI" (roni_wallet.py make_testnet_tx, the
extension v0.5, wallet-app.html).

DECISION — pre-milli transactions are REJECTED, never converted:
a transaction signed before the milli change carries a whole-R0NI
amount and no "amount_unit" marker. The node now reads "amount"
as milli, so a legacy 100 (meaning 100 R0NI) would land as 100
milli = 0.100 R0NI — a silent 1000x error. This script therefore
refuses any tx without "amount_unit": "milli-R0NI" and tells the
signer to re-sign it with a milli-aware wallet. The same rule
applies to a tx whose amount is not an integer (e.g. a float
1.5): it is rejected here, before the node ever sees it. A
rejection is loud and safe; a silent conversion would move the
wrong amount of money.

Usage:
  /tmp/r0ni-venv/bin/python testnet-v2/accept_signed_tx.py \
      signed-tx.json [--port 8021]

The signed-tx JSON must contain: sender, recipient, amount
(integer milli-R0NI), amount_unit ("milli-R0NI"), nonce,
signature, sender_pubkey_hex (txid is recomputed/checked).
If the tx is pre-milli, the amount is not an integer, the
signature is wrong, the address does not match the public key,
the nonce is wrong, or the balance is insufficient, the node
rejects it — same as any other transaction.

Recommended path (instead of spending from the genesis key
repeatedly): Mac makes ONE signed transfer in-app from genesis
to a fresh disposable test wallet, with a small amount. The
testnet then uses THAT disposable test wallet's keypair (generated
by the testnet, test-only) for further spending tests — never
the genesis key.
"""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from roni_wallet import (  # noqa: E402
    evo_hash_11, r0ni_address, testnet_tx_message, validate_payload,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: E402


def verify_signed_tx(tx: dict) -> tuple:
    """Local pre-check of an externally signed transaction.

    Returns (True, "ok") or (False, reason). The node re-checks
    everything on receipt. Checks, in order:
      1. amount_unit marker — a tx without "milli-R0NI" is a
         pre-milli tx and is REJECTED (see module docstring: a
         silent conversion would be a 1000x error).
      2. amount is an integer (not bool/float) — the node reads
         amounts as integer milli-R0NI.
      3. payload (if any) validates.
      4. address derives from the sender public key.
      5. txid matches the recomputed EvoHash-11 of the message.
      6. Ed25519 signature verifies over the message.
    """
    if tx.get("amount_unit") != "milli-R0NI":
        return False, (
            "pre-milli transaction rejected: no \"amount_unit\": "
            "\"milli-R0NI\" marker — this transaction was signed "
            "before the milli-R0NI change (or by a wallet that does "
            "not mark milli amounts). Its amount would be read as "
            "milli-R0NI and be 1000x smaller than intended. Re-sign "
            "it with a milli-aware wallet (extension v0.5+, "
            "wallet-app.html, or roni_wallet.py make-tx) and resubmit.")
    amount = tx.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool):
        return False, (
            "amount must be an integer number of milli-R0NI "
            f"(got {amount!r}) — the smallest unit is 1 milli = "
            "0.001 R0NI; use a milli-aware wallet to sign it")
    # Uses the shared v1/v2 message: a payload transaction is signed
    # over sender|recipient|amount|nonce|<payload sha256>, so a
    # payload is verified here too, not just the amount.
    if tx.get("data") is not None:
        ok, reason = validate_payload(tx["data"])
        if not ok:
            return False, f"invalid payload: {reason}"
    try:
        msg = testnet_tx_message(tx["sender"], tx["recipient"], tx["amount"],
                                 tx["nonce"], tx.get("data"))
    except Exception as e:
        return False, f"cannot build the signed message: {e}"
    try:
        if r0ni_address(bytes.fromhex(tx["sender_pubkey_hex"])) != tx["sender"]:
            return False, "address does not match sender public key"
    except Exception as e:
        return False, f"bad sender public key: {e}"
    if evo_hash_11(msg.encode()).hex() != tx.get("txid"):
        return False, "txid mismatch"
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx["sender_pubkey_hex"]))
        pub.verify(bytes.fromhex(tx["signature"]), msg.encode())
    except Exception as e:
        return False, f"signature verification failed: {e}"
    return True, "ok"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    tx = json.loads(Path(sys.argv[1]).read_text())
    port = 8021
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    ok, reason = verify_signed_tx(tx)
    if not ok:
        print(f"REJECTED: {reason}")
        sys.exit(1)
    print("signature verified locally against sender public key")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/tx", data=json.dumps(tx).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"node {port}: {r.status} {r.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"node {port} REJECTED: {e.code} {e.read().decode()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
