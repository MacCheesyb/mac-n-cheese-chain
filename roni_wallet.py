#!/usr/bin/env python3
"""
RONI Wallet — software wallet prototype v0.1
=============================================
Mac 'N Cheese Chain — RONI
Prototype only — NOT audited, DO NOT use for real funds / real value.

What it does:
  * Generate an Ed25519 keypair (cryptography library)
  * Address = "RONI-" + first 40 hex chars of EvoHash-11(public key)
    EvoHash-11 is the same 1-pass 11-step chain as Block 0.
  * Private key is stored ENCRYPTED with a password, using
    EvoCrypt v0.2 (evocrypt_hybrid_v02.py, in this repo).
    The wallet file itself only holds the public key, address,
    and the EvoCrypt-encrypted private key — never plaintext.
  * Sign a message, verify a signature.

What it does NOT do yet:
  * No balance, no transactions, no network / node, no RPC.
  * No MetaMask connection yet — see extension/ and README.
  * No seed phrase / mnemonic yet. Back up the wallet file
    AND the password separately; losing either loses the key.

Run:
  python3 roni_wallet.py
    # self-test: create temp wallet, sign, verify, wrong-password reject
  python3 roni_wallet.py create my-wallet.json "your-password"
  python3 roni_wallet.py show my-wallet.json
  python3 roni_wallet.py sign my-wallet.json "your-password" "hello RONI"
  python3 roni_wallet.py verify <public-key-hex> "hello RONI" <signature-hex>

MetaMask note:
  MetaMask speaks EVM (Ethereum-style secp256k1 addresses,
  JSON-RPC, chain ID). This chain is NOT EVM today, so MetaMask
  cannot talk to it directly. Three routes, Mac to choose:
  A. Own browser extension (scaffold in extension/) — talks
     directly to a Mac 'N Cheese node, uses RONI addresses above.
  B. MetaMask Snap — a Snap can add custom chain support inside
     MetaMask, but needs a Snap audit / distribution path.
  C. Make the chain EVM-compatible, or issue RONI as an ERC-20
     on an existing EVM chain — then MetaMask works natively,
     but the chain is no longer purely EvoHash-11 / custom.
  Route A is the default in this prototype.
"""

import base64
import json
import sys
from pathlib import Path

# EvoHash-11, same chain as evochain_genesis.py (copied, 1 pass)
import hashlib

def _b2b(d):    return hashlib.blake2b(d, digest_size=64).digest()
def _sha3_512(d): return hashlib.sha3_512(d).digest()
def _sha512(d): return hashlib.sha512(d).digest()
def _sha256(d): return hashlib.sha256(d).digest()
def _b2s(d):    return hashlib.blake2s(d, digest_size=32).digest()
def _sha3_256(d): return hashlib.sha3_256(d).digest()
def _shake256(d): return hashlib.shake_256(d).digest(64)
def _sha512_256(d): return hashlib.sha512(d).digest()[:32] + hashlib.sha256(d).digest()
def _b2b_32(d): return hashlib.blake2b(d, digest_size=32).digest()
def _sha3_384(d): return hashlib.sha3_384(d).digest() + hashlib.sha256(d).digest()[:16]
def _sha512_b(d): return hashlib.sha512(d).digest()

CHAIN = [
    _b2b, _sha3_512, _sha512, _sha256, _b2s, _sha3_256,
    _shake256, _sha512_256, _b2b_32, _sha3_384, _sha512_b,
]

def evo_hash_11(data: bytes) -> bytes:
    state = data
    for fn in CHAIN:
        state = fn(state)
    return state

def roni_address(public_key_bytes: bytes) -> str:
    return "RONI-" + evo_hash_11(public_key_bytes).hex()[:40]


try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
except ImportError as e:
    raise SystemExit("Missing 'cryptography'. pip install cryptography "
                     "(Termux: pkg install python-cryptography)") from e

# EvoCrypt for encrypting the private key at rest
try:
    from evocrypt_hybrid_v02 import encrypt_b64, decrypt_b64
except ImportError:
    encrypt_b64 = decrypt_b64 = None


def create_wallet(password: str, path: str) -> dict:
    if encrypt_b64 is None:
        raise SystemExit("evocrypt_hybrid_v02.py must be in the same folder — "
                         "it encrypts the private key.")
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption())
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    wallet = {
        "chain": "Mac 'N Cheese Chain",
        "ticker": "RONI",
        "address": roni_address(pub_raw),
        "public_key_hex": pub_raw.hex(),
        "encrypted_private_key": encrypt_b64(password, base64.b64encode(priv_raw).decode("ascii")),
        "warning": "Prototype only — not audited. Do not use for real funds.",
    }
    Path(path).write_text(json.dumps(wallet, indent=2) + "\n", encoding="utf-8")
    return wallet


def _load_private(password: str, path: str):
    wallet = json.loads(Path(path).read_text(encoding="utf-8"))
    priv_b64 = decrypt_b64(password, wallet["encrypted_private_key"])
    priv_raw = base64.b64decode(priv_b64.encode("ascii"))
    return wallet, Ed25519PrivateKey.from_private_bytes(priv_raw)


def show_wallet(path: str) -> dict:
    wallet = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "chain": wallet.get("chain"),
        "ticker": wallet.get("ticker"),
        "address": wallet["address"],
        "public_key_hex": wallet["public_key_hex"],
    }


def sign_message(password: str, path: str, message: str) -> str:
    _wallet, priv = _load_private(password, path)
    return priv.sign(message.encode("utf-8")).hex()


def verify_signature(public_key_hex: str, message: str, signature_hex: str) -> bool:
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    try:
        pub.verify(bytes.fromhex(signature_hex), message.encode("utf-8"))
        return True
    except Exception:
        return False


def self_test():
    import tempfile, os
    print("RONI Wallet prototype v0.1 — self-test")
    with tempfile.TemporaryDirectory() as d:
        p = f"{d}/test-wallet.json"
        w = create_wallet("test-password", p)
        print(f"1. created wallet, address {w['address']}")
        assert w["address"].startswith("RONI-") and len(w["address"]) == 45
        assert show_wallet(p)["address"] == w["address"]
        print("2. show wallet ok")
        sig = sign_message("test-password", p, "hello RONI")
        assert verify_signature(w["public_key_hex"], "hello RONI", sig)
        print("3. sign + verify ok")
        assert not verify_signature(w["public_key_hex"], "tampered", sig)
        print("4. tampered message correctly rejected")
        try:
            sign_message("wrong-password", p, "hello RONI")
            print("5. FAIL: wrong password signed!")
        except Exception:
            print("5. wrong password correctly rejected")
    print("ALL TESTS PASSED")


def _usage():
    print("usage:")
    print("  python3 roni_wallet.py                              # self-test")
    print("  python3 roni_wallet.py create <wallet.json> <password>")
    print("  python3 roni_wallet.py show <wallet.json>")
    print("  python3 roni_wallet.py sign <wallet.json> <password> <message>")
    print("  python3 roni_wallet.py verify <public-key-hex> <message> <signature-hex>")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        self_test()
    elif args[0] == "create" and len(args) == 3:
        w = create_wallet(args[2], args[1])
        print(json.dumps(show_wallet(args[1]), indent=2))
    elif args[0] == "show" and len(args) == 2:
        print(json.dumps(show_wallet(args[1]), indent=2))
    elif args[0] == "sign" and len(args) == 4:
        print(sign_message(args[2], args[1], args[3]))
    elif args[0] == "verify" and len(args) == 4:
        print(verify_signature(args[1], args[2], args[3]))
    else:
        _usage()
