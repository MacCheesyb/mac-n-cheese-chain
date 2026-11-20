#!/usr/bin/env python3
"""
Mac 'N Cheese Chain — Genesis Block 0 — R0NI
=============================================
Built 2026-11-19 for Mac, in the "Cryptocurrency mining capability" thread,
using the algorithm from the separate ai.evo thread (2026-11-13).

Renamed 2026-11-19 by Mac, from the provisional "EvoChain":
  chain:  Mac 'N Cheese Chain
  ticker: R0NI (native asset)
  NOTE: RONI (with the letter O) already exists as a tiny token on
  another chain (see MEMORY / white paper). This chain's ticker was
  therefore changed to R0NI (0 in place of O) on 2026-11-19.
  Do not confuse the two. The GENESIS_DATA string below still reads
  RONI — it is the hashed historical record of Block 0 and must NOT
  be changed, or the block hash changes.

Algorithm reused, exactly as in EvoCrypt v0.2 (evocrypt_hybrid_v02.py):
  EvoKDF-11 — an 11-step X11-style chained hash:
    BLAKE2b-512, SHA3-512, SHA-512, SHA-256, BLAKE2s-256, SHA3-256,
    SHAKE-256, SHA-512/256-mix, BLAKE2b-256, SHA3-384-mix, SHA-512-final
  (stdlib substitutions for X11's BMW / Groestl / JH / Skein etc.,
  labelled the same way as in v0.2.)

Difference for mining, stated plainly:
  * EvoCrypt's KDF runs that chain 1,000 rounds to derive keys — far too
    slow to try thousands of nonces.
  * The block hash, EvoHash-11, runs the same 11 functions in the
    same order exactly ONCE per hash attempt. Same chain, 1 pass.
  * That makes mining feasible on a normal CPU, while keeping
    the hash tied to the ai.evo design.

Mobile-lightweight design (Mac's direction, 2026-11-19):
  * EvoHash-11 is CPU-only, stdlib hashes, no ASIC-specific step,
    no GPU requirement, no large memory requirement.
  * Genesis difficulty is "0000" (4 hex zeros, ~1 in 65,536) —
    a phone can find a block in seconds at this difficulty.
    Difficulty must rise / adjust before any real network, or
    phones would be outrun by desktops. This is a demo setting.
  * No wallet, transaction format, or peer network yet.

Circulating supply to start (Mac, 2026-11-19):
  * 100,000 R0NI in circulation to start.
    This IS recorded in the hashed genesis data below, so
    restarting Block 0 with this supply changes the hash.
  * This is initial circulating supply, not max supply.
    Block reward / emission schedule for the rest: TBD.

Max supply (PROPOSAL only, not hashed into Block 0, not final):
  * 10,000,000,000 R0NI (10 billion) — proposed 2026-11-19.
    Rationale: low enough to be scarce, high enough that a
    person can acquire thousands of R0NI for a small amount,
    supporting broad access / utility / demand.
    Mac has not yet confirmed this number. Alternatives he
    can pick: 1 billion, 10 billion (proposal), 100 billion.
    100,000 to start is 0.001% of the 10B proposal.
  * No premine beyond the 100,000 starting circulating supply.

Real-world backing + USD pair (roadmap, not built):
  * Mac wants value backed, where possible, by real-world
    physical and digital assets, and a R0NI/USD trade pair first.
  * Backing is NOT in this code. It would need custodians,
    audits, legal structure, and proof of reserves — none of
    which exist yet. Do not claim R0NI is backed today.
  * R0NI/USD first means: first exchange / liquidity pair
    should be R0NI/USD, not R0NI/BTC or R0NI/ETH. That also
    needs an exchange listing, liquidity, and compliance —
    also not built yet.

Block hash = EvoHash-11( "index|timestamp|previous_hash|data|nonce" )
  as UTF-8, output 64 bytes = 128 hex chars (final step is SHA-512).

Genesis parameters:
  chain_name:      "Mac 'N Cheese Chain"
  ticker:          "R0NI"
  index:           0
  previous_hash:   "0" * 128  (no parent block)
  difficulty:      hash must start with "0000" (4 hex zeros, ~1 in 65,536)
  data / message:  "Mac 'N Cheese Chain genesis — RONI — circulating supply 100000 to start — created by Mac & Destiny's Child in ai.evo"
  timestamp:       Unix epoch seconds at creation, also ISO-8601 UTC + PST

This Block 0 REPLACES the earlier Mac 'N Cheese Chain Block 0
(2026-11-19 15:57:37 PST, nonce 112867,
hash 00001533...) and the earlier EvoChain Block 0
(2026-11-19 15:47:05 PST, hash 000002d7...).
Both are superseded — the first by the name change, this one
by adding the 100,000 starting circulating supply to the
hashed data. Keep their records in the white paper appendix
for audit, do not present them as live.

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
CHAIN_NAME = "Mac 'N Cheese Chain"
TICKER = "R0NI"
DIFFICULTY_PREFIX = "0000"
GENESIS_DATA = "Mac 'N Cheese Chain genesis — RONI — circulating supply 100000 to start — created by Mac & Destiny's Child in ai.evo"
CIRCULATING_SUPPLY_START = 100_000
# Proposal only, not hashed, not final — see header.
MAX_SUPPLY_PROPOSAL = 10_000_000_000


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
        "ticker": TICKER,
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
        "circulating_supply_start_R0NI": CIRCULATING_SUPPLY_START,
        "design": {
            "mobile_lightweight": "CPU-only EvoHash-11, 1 pass, no ASIC/GPU/memory requirement; genesis difficulty 0000 is phone-feasible in demo",
            "circulating_supply_start_R0NI": CIRCULATING_SUPPLY_START,
            "max_supply_proposal_R0NI": MAX_SUPPLY_PROPOSAL,
            "max_supply_status": "proposal only, not hashed, not final — Mac to confirm (alternatives: 1B / 10B / 100B)",
            "first_trade_pair_proposal": "R0NI/USD",
            "backing": "roadmap only — real-world physical + digital asset backing would need custodians, audits, legal structure; NOT backed today",
            "supersedes": "Mac 'N Cheese Chain Block 0 (no supply in data), 2026-11-19 15:57:37 PST, nonce 112867, hash 000015339905af898cc80dfb8c247c0df1c9461155341de47314cf2c782d74a28249c4b93dffe494241a59c02f4460542329fe7dc162c26c86880588b201a5f3; and EvoChain Block 0, 2026-11-19 15:47:05 PST, hash 000002d7954aef129e29b68b19fa44156d104edde9a335071a8c20267e83162683aab5e9d2428200ac8061b996f529e6aa51b6f1aa1e70d4a71d89df1a9ea06b",
        },
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
