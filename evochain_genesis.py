#!/usr/bin/env python3
"""
EvoChain — Genesis Block 0
===========================
Built 2026-11-19 for Mac, in the "Cryptocurrency mining capability" thread,
using the algorithm from the separate ai.evo thread (2026-11-13).

Algorithm reused, exactly as in EvoCrypt v0.2 (evocrypt_hybrid_v02.py):
  EvoKDF-11 — an 11-step X11-style chained hash:
    BLAKE2b-512, SHA3-512, SHA-512, SHA-256, BLAKE2s-256, SHA3-256,
    SHAKE-256, SHA-512/256-mix, BLAKE2b-256, SHA3-384-mix, SHA-512-final
  (stdlib substitutions for X11's BMW / Groestl / JH / Skein etc.,
  labelled the same way as in v0.2.)

Difference for mining, stated plainly:
  * EvoCrypt's KDF runs that chain 1,000 rounds to derive keys — far too
    slow to try thousands of nonces.
  * EvoChain's block hash, EvoHash-11, runs the same 11 functions in the
    same order exactly ONCE per hash attempt. Same chain, 1 pass.
  * That makes the genesis mine feasible on a normal CPU, while keeping
    the hash tied to the ai.evo design.

Block hash = EvoHash-11( "index|timestamp|previous_hash|data|nonce" )
  as UTF-8, output 64 bytes = 128 hex chars (final step is SHA-512).

Genesis parameters (chosen here, changeable for block 1+):
  chain_name:      "EvoChain" (provisional — Mac can rename it)
  index:           0
  previous_hash:   "0" * 128  (no parent block)
  difficulty:      hash must start with "0000" (4 hex zeros, ~1 in 65,536)
  data / message:  "EvoChain genesis — created by Mac & Destiny's Child in ai.evo"
  timestamp:       Unix epoch seconds at creation, also ISO-8601 UTC + PST

PROTOTYPE ONLY — NOT AUDITED, DO NOT USE FOR REAL SECRETS / REAL VALUE.
Run:  python3 evochain_genesis.py
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

# --- EvoKDF-11 chain, copied exactly from EvoCrypt v0.2 -------------------
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
    ("BLAKE->blake2b-512", _b2b),
    ("Keccak->sha3-512", _sha3_512),
    ("SHA-512", _sha512),
    ("SHA-256", _sha256),
    ("BLAKE2s-256", _b2s),
    ("SHA3-256", _sha3_256),
    ("SHAKE-256", _shake256),
    ("SHA-512/256-mix", _sha512_256),
    ("BLAKE2b-256", _b2b_32),
    ("SHA3-384-mix", _sha3_384),
    ("SHA-512-final", _sha512_b),
]
assert len(CHAIN) == 11, "EvoHash-11 must have exactly 11 steps"


def evo_hash_11(data: bytes) -> bytes:
    """One pass through the 11-step chain. Returns 64 bytes."""
    state = data
    for _name, fn in CHAIN:
        state = fn(state)
    return state


def evo_hash_hex(data: bytes) -> str:
    return evo_hash_11(data).hex()


# --- Block -----------------------------------------------------------------
CHAIN_NAME = "EvoChain"
DIFFICULTY_PREFIX = "0000"
GENESIS_DATA = "EvoChain genesis — created by Mac & Destiny's Child in ai.evo"


def header_bytes(index: int, timestamp: int, previous_hash: str, data: str, nonce: int) -> bytes:
    return f"{index}|{timestamp}|{previous_hash}|{data}|{nonce}".encode("utf-8")


def block_hash(index: int, timestamp: int, previous_hash: str, data: str, nonce: int) -> str:
    return evo_hash_hex(header_bytes(index, timestamp, previous_hash, data, nonce))


def mine_genesis():
    timestamp = int(time.time())
    previous_hash = "0" * 128
    nonce = 0
    start = time.time()
    while True:
        h = block_hash(0, timestamp, previous_hash, GENESIS_DATA, nonce)
        if h.startswith(DIFFICULTY_PREFIX):
            break
        nonce += 1
    elapsed = time.time() - start
    block = {
        "chain": CHAIN_NAME,
        "index": 0,
        "timestamp": timestamp,
        "timestamp_utc": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "timestamp_pst": datetime.fromtimestamp(timestamp).astimezone().isoformat(),
        "data": GENESIS_DATA,
        "previous_hash": previous_hash,
        "nonce": nonce,
        "difficulty": f"hash starts with '{DIFFICULTY_PREFIX}'",
        "difficulty_prefix": DIFFICULTY_PREFIX,
        "hash": h,
        "hash_function": "EvoHash-11 — 1-pass EvoKDF-11 chain from ai.evo / EvoCrypt v0.2",
        "hash_hex_length": len(h),
        "attempts": nonce + 1,
        "mine_time_seconds": round(elapsed, 3),
    }
    return block


def verify(block: dict) -> bool:
    recomputed = block_hash(block["index"], block["timestamp"],
                            block["previous_hash"], block["data"], block["nonce"])
    return (
        recomputed == block["hash"]
        and block["hash"].startswith(block["difficulty_prefix"])
        and block["previous_hash"] == "0" * 128
        and block["index"] == 0
        and len(block["hash"]) == 128
    )


def main():
    block = mine_genesis()
    out_path = Path(__file__).with_name("evochain_genesis_block.json")
    out_path.write_text(json.dumps(block, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(block, indent=2))
    print(f"\nSaved to: {out_path}")
    print(f"Verify: recomputed hash matches, prefix ok, previous_hash is zeros: {verify(block)}")
    assert verify(block), "Genesis block failed verification"


if __name__ == "__main__":
    main()
