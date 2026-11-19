# EvoChain White Paper — Draft v0.1

**For Mac's direction and oversight — not final, not published**
Author: Mac (MacCheezyb), with Destiny's Child
Date: 2026-11-19
Status: Draft v0.1 — prototype only, not audited, no real value

## Abstract

EvoChain is a prototype blockchain built by Mac and Destiny's Child, starting
in the ai.evo thread on 2026-11-13. It reuses EvoCrypt's EvoKDF-11, an
X11-style 11-step chained hash, as its block hash, EvoHash-11.

Genesis Block 0 was mined on 2026-11-19 at 15:47:05 PST, timestamp
1795132025, nonce 4452, with a hash starting `0000`. This paper records
exactly what was built, how it was verified, what it is not, and the
decisions Mac still needs to make before this becomes anything more
than a working demo.

No token, no economics, no network, and no claim of security are made
in this draft. Those are open decisions, listed in Section 7.

## 1. Introduction

Mac asked, in ai.evo, for a next-level encryption algorithm using SHA
functions, X11, and related hashing. He chose to build the hybrid
encryption prototype first — EvoCrypt. On 2026-11-19 he then asked
whether a language model could solve the next block of a blockchain,
and then asked to instantiate the first block and timestamp of a
blockchain network together, using the algorithm from that separate
ai.evo thread.

EvoChain is the answer to that second request: a small, runnable,
verifiable chain whose first block is real, mined, and reproducible —
and whose limits are stated plainly.

## 2. Background: EvoCrypt and EvoKDF-11

EvoCrypt Hybrid Prototype v0.1 (2026-11-13) and v0.2 (2026-11-13,
verified 2026-11-14) work as follows:

- Password + random salt go through EvoKDF-11, an 11-step hash chain,
  X11-style, 1,000 rounds, deriving three 32-byte keys.
- Layer 1: AES-256-GCM
- Layer 2: ChaCha20-Poly1305, locking the first layer's output again
- Seal: HMAC-SHA3-512, checked before any decryption

Self-tests passed: roundtrip, wrong-password reject, 1-bit tamper
reject, empty and 1 MB messages, and in v0.2 file mode and opt-in
Argon2id (EVOC2).

Honest limit, carried over from EvoCrypt: Python's standard library
does not contain the real BMW, Groestl, JH, Skein, Luffa, CubeHash,
SHAvite, SIMD, or Echo hashes from X11. Each step in EvoKDF-11 is
therefore mapped to a standard-library hash and labelled as a
substitution in the source. EvoChain inherits that mapping, and does
not claim to be real X11.

## 3. EvoHash-11: the block hash

EvoHash-11 is one pass through the same 11 functions, in the same
order, as EvoKDF-11:

1. BLAKE2b-512 — `blake2b, digest_size=64`
2. SHA3-512 — `sha3_512`
3. SHA-512 — `sha512`
4. SHA-256 — `sha256`
5. BLAKE2s-256 — `blake2s, digest_size=32`
6. SHA3-256 — `sha3_256`
7. SHAKE-256 — `shake_256, 64 bytes out`
8. SHA-512/256-mix — first 32 bytes of SHA-512 + SHA-256
9. BLAKE2b-256 — `blake2b, digest_size=32`
10. SHA3-384-mix — SHA3-384 + first 16 bytes of SHA-256
11. SHA-512-final — `sha512`

Output: 64 bytes, 128 hex characters.

Why one pass, not 1,000 rounds? EvoCrypt's KDF uses 1,000 rounds
to make password guessing slow. Mining tries thousands of nonces,
so 1,000 rounds per try would make even a low-difficulty demo
impractically slow. EvoHash-11 keeps the same chain and order,
with 1 pass per hash attempt. That is a deliberate, stated
trade-off, not a hidden change.

Block hash input, UTF-8:

```
index|timestamp|previous_hash|data|nonce
```

## 4. Genesis Block 0

Mined and verified 2026-11-19, in the "Cryptocurrency mining
capability question" thread.

| Field | Value |
|---|---|
| Chain | EvoChain (provisional) |
| Index | 0 |
| Timestamp (Unix) | 1795132025 |
| Timestamp (UTC) | 2026-11-19T23:47:05Z |
| Timestamp (PST) | 2026-11-19 15:47:05 -08:00 |
| Data | EvoChain genesis — created by Mac & Destiny's Child in ai.evo |
| Previous hash | 128 zeros (`0` × 128) |
| Nonce | 4452 |
| Attempts | 4,453 |
| Mine time | 0.068 seconds |
| Difficulty | hash must start with `0000` (4 hex zeros, ~1 in 65,536) |
| Hash | `000002d7954aef129e29b68b19fa44156d104edde9a335071a8c20267e83162683aab5e9d2428200ac8061b996f529e6aa51b6f1aa1e70d4a71d89df1a9ea06b` |
| Hash length | 128 hex chars |
| Hash function | EvoHash-11 — 1-pass EvoKDF-11 chain from ai.evo / EvoCrypt v0.2 |

Verification, done twice: recomputing
`EvoHash-11("0|1795132025|<128 zeros>|<data>|4452")`
gives exactly the hash above, it starts with `0000`, and the
previous hash is all zeros. The script `evochain_genesis.py`
contains `verify()` for this check.

Reproducing it:

```bash
python3 evochain_genesis.py
```

Note: re-running mines a new genesis block with the current time,
so the nonce and hash will differ. The saved block in
`evochain_genesis_block.json` is the canonical Block 0 above.

## 5. Block structure and mining — current design

- **Block:** index, timestamp, data, previous_hash, nonce, hash,
  difficulty_prefix, hash_function, attempts, mine_time_seconds.
- **Mining:** proof-of-work by nonce search. Increment nonce from
  0 until the EvoHash-11 hex starts with the difficulty prefix.
  Genesis difficulty is `0000`.
- **Linking:** Block 1+ must set `previous_hash` to Block 0's hash
  above, and be mined the same way. No Block 1 exists yet in this draft.
- **Consensus:** none beyond this demo yet. There is a single node
  (this workspace), no peer network, no wallet, no transaction format,
  and no difficulty adjustment. Those are future decisions, not
  existing features.

## 6. Security, limits, and what this is not

- Prototype only, not audited. Do not use for real secrets or real value.
- EvoHash-11 is a custom, unreviewed hash chain. It is not SHA-256,
  not real X11, and has no security proof.
- A 4-hex-zero difficulty is a demo difficulty. A real network
  would need far higher difficulty, difficulty adjustment, and
  protection against reorganisation, double-spending, and Sybil attacks.
- No token exists. No supply, price, or promise of income is made.
- The EvoCrypt encryption layers (AES + ChaCha) are not used in
  block hashing. They remain a separate prototype for locking files
  and messages.
- GitHub status at draft time: the username MacCheezyb is still
  unclaimed on GitHub (API 404, checked 2026-11-19). No account
  exists yet, so no repo has been pushed. GitHub requires accounts
  to be created by a human, so Mac must create the account himself.

## 7. Open decisions — for Mac

These are Mac's calls, under his direction and oversight. Nothing
in this section is decided in the draft:

1. **Chain name:** keep EvoChain, or rename?
2. **Purpose:** learning/demo only, payments, data anchoring,
   or another use?
3. **Token / economics:** any token, name, supply, or none at all?
4. **Consensus and difficulty:** stay proof-of-work? Raise difficulty?
   Add difficulty adjustment? Add a block time target?
5. **Transactions and wallets:** what goes in a block's data, and
   how are keys / wallets handled?
6. **Network:** stay single-node, or add peers, nodes, and sync?
7. **License and visibility:** MIT, another licence, or closed?
   Public or private GitHub repo?
8. **Next block:** what should Block 1 contain, and when?

## Appendix A. Files

- `evochain_genesis.py` — genesis miner + verifier
- `evochain_genesis_block.json` — canonical Genesis Block 0
- `evocrypt_hybrid_v02.py` — EvoCrypt v0.2
- `evocrypt_hybrid_prototype.py` — EvoCrypt v0.1
- `README.md` — repo readme

## Appendix B. Timeline

- 2026-11-13, ai.evo: Mac asks for a next-level algorithm using SHA / X11.
  Chooses hybrid encryption prototype first. EvoCrypt v0.1 built, self-test passes.
- 2026-11-13 / 14: EvoCrypt v0.2 built, verified in a clean venv, all 6 checks pass.
- 2026-11-19: Mac asks about mining a real block. Answer: not competitively
  possible on model hardware. He asks to instantiate Block 0 together
  using the ai.evo algorithm. Genesis Block 0 mined 15:47:05 PST.
- 2026-11-19: Repo bundle prepared locally, ready to push once a GitHub
  account exists. White Paper Draft v0.1 written for Mac's review.

---
*Draft v0.1 — 2026-11-19. Changes only under Mac's direction.*
