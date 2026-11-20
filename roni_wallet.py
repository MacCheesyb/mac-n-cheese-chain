#!/usr/bin/env python3
"""
R0NI Wallet — software wallet prototype v0.2
=============================================
Mac 'N Cheese Chain — R0NI
Ticker renamed 2026-11-19: RONI -> R0NI (the number 0 in place of the
letter O), to avoid confusion with an existing RONI token. The Genesis
Block 0 hashed data still reads "RONI" — it is a historical record and
changing it would change the block hash, so it is NOT re-mined.

Prototype only — NOT audited, DO NOT use for real funds / real value.

What it does:
  * Generate an Ed25519 keypair (cryptography library)
  * Address = "R0NI-" + first 40 hex chars of EvoHash-11(public key)
    EvoHash-11 is the same 1-pass 11-step chain as Block 0.
  * Private key is stored ENCRYPTED with a password, using
    EvoCrypt v0.2 (evocrypt_hybrid_v02.py, in this repo).
    The wallet file itself only holds the public key, address,
    and the EvoCrypt-encrypted private key — never plaintext.
  * Sign a message, verify a signature.
  * Local ledger (genesis_allocation.json): show a balance and
    record a signed local transfer. There is no network / node yet,
    so the ledger is a local file — a demo of the accounting, not
    a live chain. The genesis allocation starts EMPTY: the first
    wallet Mac creates in the wallet app (wallet-app.html) is
    allocated the 100,000 R0NI genesis supply. No address is
    invented or pre-filled here.

What it does NOT do yet:
  * No network / node, no RPC, no block building.
  * No MetaMask connection yet — see extension/ and README.
  * No seed phrase / mnemonic yet. Back up the wallet file
    AND the password separately; losing either loses the key.

Ledger file format (genesis_allocation.json):
  {
    "chain": "Mac 'N Cheese Chain",
    "ticker": "R0NI",
    "genesis_block_hash": "0000adbc...c1b0",   # Block 0, unchanged
    "genesis_supply": 100000,
    "allocations": [],                          # {address, amount, source}
    "transfers": []                             # signed local transfers
  }

Run:
  python3 roni_wallet.py
    # self-test: wallet, sign/verify, ledger balance + transfer
  python3 roni_wallet.py create my-wallet.json "your-password"
  python3 roni_wallet.py show my-wallet.json
  python3 roni_wallet.py sign my-wallet.json "your-password" "hello R0NI"
  python3 roni_wallet.py verify <public-key-hex> "hello R0NI" <signature-hex>
  python3 roni_wallet.py init-ledger [genesis_allocation.json]
  python3 roni_wallet.py allocate-genesis <ledger.json> <wallet.json>
  python3 roni_wallet.py balance <ledger.json> <address>
  python3 roni_wallet.py transfer <ledger.json> <wallet.json> <password> <to-address> <amount>

MetaMask note:
  MetaMask speaks EVM (Ethereum-style secp256k1 addresses,
  JSON-RPC, chain ID). This chain is NOT EVM today, so MetaMask
  cannot talk to it directly. Three routes, Mac to choose:
  A. Own browser extension (scaffold in extension/) — talks
     directly to a Mac 'N Cheese node, uses R0NI addresses above.
  B. MetaMask Snap — a Snap can add custom chain support inside
     MetaMask, but needs a Snap audit / distribution path.
  C. Make the chain EVM-compatible, or issue R0NI as an ERC-20
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

GENESIS_BLOCK_HASH = (
    "0000adbc0f16c14cc2540a4a259339fd0b02a1503bad43f0bbb484eb5007c36d68f9d"
    "825875297db1b26be6eb2a0532496c6a31317f6ce9a9fc7cf6a8591c1b0"
)
GENESIS_SUPPLY = 100000
TICKER = "R0NI"


def r0ni_address(public_key_bytes: bytes) -> str:
    return "R0NI-" + evo_hash_11(public_key_bytes).hex()[:40]


# Backwards-compatible alias (v0.1 name).
roni_address = r0ni_address


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
        "ticker": TICKER,
        "address": r0ni_address(pub_raw),
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


# ---------------------------------------------------------------------------
# Local ledger (genesis_allocation.json) — demo accounting, no live chain yet.
# ---------------------------------------------------------------------------

def new_ledger() -> dict:
    return {
        "chain": "Mac 'N Cheese Chain",
        "ticker": TICKER,
        "genesis_block_hash": GENESIS_BLOCK_HASH,
        "genesis_supply": GENESIS_SUPPLY,
        "allocations": [],
        "transfers": [],
        "warning": "Prototype local ledger only — not a live chain. "
                   "Do not use for real funds.",
    }


def load_ledger(path: str) -> dict:
    ledger = json.loads(Path(path).read_text(encoding="utf-8"))
    if ledger.get("ticker") not in (TICKER, "RONI"):
        raise ValueError(f"ledger ticker {ledger.get('ticker')!r} is not R0NI")
    ledger.setdefault("allocations", [])
    ledger.setdefault("transfers", [])
    return ledger


def save_ledger(path: str, ledger: dict) -> None:
    Path(path).write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def ledger_balance(ledger: dict, address: str) -> int:
    balance = 0
    for alloc in ledger.get("allocations", []):
        if alloc.get("address") == address:
            balance += int(alloc.get("amount", 0))
    for tx in ledger.get("transfers", []):
        if tx.get("to") == address:
            balance += int(tx.get("amount", 0))
        if tx.get("from") == address:
            balance -= int(tx.get("amount", 0))
    return balance


def allocate_genesis(ledger_path: str, wallet_path: str) -> dict:
    """Give the whole 100,000 R0NI genesis supply to one wallet address.

    Only allowed while allocations is empty — the first wallet Mac
    creates is the genesis holder. No address is pre-filled anywhere.
    """
    ledger = load_ledger(ledger_path)
    if ledger["allocations"]:
        raise SystemExit("genesis supply is already allocated — "
                         f"see {ledger['allocations']}")
    wallet = show_wallet(wallet_path)
    total = sum(int(a.get("amount", 0)) for a in ledger["allocations"])
    if total + GENESIS_SUPPLY > GENESIS_SUPPLY:
        raise SystemExit("genesis supply would be exceeded")
    ledger["allocations"].append({
        "address": wallet["address"],
        "amount": GENESIS_SUPPLY,
        "source": "genesis",
        "genesis_block_hash": GENESIS_BLOCK_HASH,
    })
    save_ledger(ledger_path, ledger)
    return {"address": wallet["address"], "amount": GENESIS_SUPPLY}


def record_transfer(ledger_path: str, wallet_path: str, password: str,
                    to_address: str, amount: int) -> dict:
    """Sign a local transfer with the sender's key, verify it, and record it.

    The transfer message is signed, the signature is verified against the
    sender's public key, and the sender's ledger balance is checked first.
    """
    if amount <= 0:
        raise SystemExit("amount must be a positive whole number of R0NI")
    ledger = load_ledger(ledger_path)
    wallet, priv = _load_private(password, wallet_path)
    from_address = wallet["address"]
    if to_address == from_address:
        raise SystemExit("cannot transfer to your own address")
    if ledger_balance(ledger, from_address) < amount:
        raise SystemExit(
            f"insufficient balance: {ledger_balance(ledger, from_address)} "
            f"R0NI available, {amount} R0NI requested")
    message = f"R0NI transfer {from_address} -> {to_address} : {amount}"
    signature_hex = priv.sign(message.encode("utf-8")).hex()
    if not verify_signature(wallet["public_key_hex"], message, signature_hex):
        raise SystemExit("internal error: fresh signature did not verify")
    tx = {
        "from": from_address,
        "to": to_address,
        "amount": amount,
        "message": message,
        "signature_hex": signature_hex,
        "public_key_hex": wallet["public_key_hex"],
    }
    ledger["transfers"].append(tx)
    save_ledger(ledger_path, ledger)
    return tx


def self_test():
    import tempfile
    print("R0NI Wallet prototype v0.2 — self-test")
    with tempfile.TemporaryDirectory() as d:
        p = f"{d}/test-wallet.json"
        w = create_wallet("test-password", p)
        print(f"1. created wallet, address {w['address']}")
        assert w["address"].startswith("R0NI-") and len(w["address"]) == 45
        assert w["ticker"] == "R0NI"
        assert show_wallet(p)["address"] == w["address"]
        print("2. show wallet ok")
        sig = sign_message("test-password", p, "hello R0NI")
        assert verify_signature(w["public_key_hex"], "hello R0NI", sig)
        print("3. sign + verify ok")
        assert not verify_signature(w["public_key_hex"], "tampered", sig)
        print("4. tampered message correctly rejected")
        try:
            sign_message("wrong-password", p, "hello R0NI")
            print("5. FAIL: wrong password signed!")
            raise SystemExit(1)
        except SystemExit:
            raise
        except Exception:
            print("5. wrong password correctly rejected")
        # Ledger: empty genesis allocation, then allocate + transfer.
        ledger_path = f"{d}/genesis_allocation.json"
        ledger = new_ledger()
        assert ledger["allocations"] == [] and ledger["genesis_supply"] == 100000
        assert ledger["genesis_block_hash"] == GENESIS_BLOCK_HASH
        save_ledger(ledger_path, ledger)
        assert ledger_balance(load_ledger(ledger_path), w["address"]) == 0
        print("6. empty genesis ledger ok, balance 0")
        allocate_genesis(ledger_path, p)
        assert ledger_balance(load_ledger(ledger_path), w["address"]) == 100000
        print("7. genesis allocation ok, balance 100,000 R0NI")
        try:
            allocate_genesis(ledger_path, p)
            print("8. FAIL: second genesis allocation allowed!")
            raise SystemExit(1)
        except SystemExit as e:
            if "already allocated" not in str(e):
                raise
            print("8. second genesis allocation correctly rejected")
        q = f"{d}/test-wallet-2.json"
        w2 = create_wallet("test-password", q)
        tx = record_transfer(ledger_path, p, "test-password", w2["address"], 25000)
        assert verify_signature(tx["public_key_hex"], tx["message"], tx["signature_hex"])
        ledger = load_ledger(ledger_path)
        assert ledger_balance(ledger, w["address"]) == 75000
        assert ledger_balance(ledger, w2["address"]) == 25000
        print("9. signed transfer ok, balances 75,000 / 25,000 R0NI")
        try:
            record_transfer(ledger_path, p, "test-password", w2["address"], 999999)
            print("10. FAIL: overspend allowed!")
            raise SystemExit(1)
        except SystemExit as e:
            if "insufficient balance" not in str(e):
                raise
            print("10. overspend correctly rejected")
    print("ALL TESTS PASSED")


def _usage():
    print("usage:")
    print("  python3 roni_wallet.py                              # self-test")
    print("  python3 roni_wallet.py create <wallet.json> <password>")
    print("  python3 roni_wallet.py show <wallet.json>")
    print("  python3 roni_wallet.py sign <wallet.json> <password> <message>")
    print("  python3 roni_wallet.py verify <public-key-hex> <message> <signature-hex>")
    print("  python3 roni_wallet.py init-ledger [genesis_allocation.json]")
    print("  python3 roni_wallet.py allocate-genesis <ledger.json> <wallet.json>")
    print("  python3 roni_wallet.py balance <ledger.json> <address>")
    print("  python3 roni_wallet.py transfer <ledger.json> <wallet.json> <password> <to-address> <amount>")


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
    elif args[0] == "init-ledger" and len(args) in (1, 2):
        path = args[1] if len(args) == 2 else "genesis_allocation.json"
        if Path(path).exists():
            raise SystemExit(f"{path} already exists — refusing to overwrite")
        save_ledger(path, new_ledger())
        print(f"created {path} (allocations empty — allocate the genesis "
              "supply to Mac's wallet with allocate-genesis)")
    elif args[0] == "allocate-genesis" and len(args) == 3:
        print(json.dumps(allocate_genesis(args[1], args[2]), indent=2))
    elif args[0] == "balance" and len(args) == 3:
        ledger = load_ledger(args[1])
        print(json.dumps({
            "address": args[2],
            "balance_R0NI": ledger_balance(ledger, args[2]),
            "genesis_supply": ledger.get("genesis_supply"),
        }, indent=2))
    elif args[0] == "transfer" and len(args) == 6:
        try:
            amount = int(args[5])
        except ValueError:
            raise SystemExit("amount must be a whole number of R0NI") from None
        print(json.dumps(record_transfer(args[1], args[2], args[3], args[4], amount), indent=2))
    else:
        _usage()
