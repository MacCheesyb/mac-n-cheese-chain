#!/usr/bin/env python3
"""
Accept a transaction signed OUTSIDE the testnet — e.g. by Mac
in his own wallet app (standalone wallet-app.html).

This is the ONLY way a transaction FROM Mac's genesis address
can enter the testnet:
  1. Mac signs the transfer in his own wallet app (his private
     key never leaves his device, is never sent to us, and is
     never imported here).
  2. He gives us the signed transaction JSON (sender, recipient,
     amount, nonce, signature, sender_pubkey_hex, txid).
  3. This script verifies the signature against the sender's
     public key and the address derivation, then submits it to
     a testnet node, which re-verifies it before accepting it
     into the mempool.

Usage:
  /tmp/r0ni-testnet-venv/bin/python testnet/accept_signed_tx.py \
      signed-tx.json [--port 8001]

The signed-tx JSON must contain: sender, recipient, amount,
nonce, signature, sender_pubkey_hex (txid is recomputed/checked).
If the signature is wrong, the address does not match the public
key, the nonce is wrong, or the balance is insufficient, the node
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
from roni_wallet import evo_hash_11, r0ni_address  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    tx = json.loads(Path(sys.argv[1]).read_text())
    port = 8001
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    # Local pre-check (the node re-checks everything on receipt).
    msg = f"{tx['sender']}|{tx['recipient']}|{tx['amount']}|{tx['nonce']}"
    assert r0ni_address(bytes.fromhex(tx["sender_pubkey_hex"])) == tx["sender"], \
        "address does not match sender public key"
    assert evo_hash_11(msg.encode()).hex() == tx.get("txid", evo_hash_11(msg.encode()).hex()), \
        "txid mismatch"
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx["sender_pubkey_hex"]))
    pub.verify(bytes.fromhex(tx["signature"]), msg.encode())
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
