# Mac 'N Cheese Chain White Paper — Draft v0.2

**For Mac's direction and oversight — not final, not published**
Author: Mac (MacCheezyb), with Destiny's Child
Date: 2026-11-19
Status: Draft v0.2 — prototype only, not audited, no real value
Ticker: RONI

## Abstract

Mac 'N Cheese Chain is a prototype blockchain built by Mac and
Destiny's Child, starting in the ai.evo thread on 2026-11-13. It
reuses EvoCrypt's EvoKDF-11, an X11-style 11-step chained hash,
as its block hash, EvoHash-11.

Genesis Block 0 was restarted on 2026-11-19 at 15:58:43 PST,
timestamp 1795132723, nonce 23976, with a hash starting `0000`,
and a circulating supply of 100,000 RONI to start. This paper
records exactly what was built, how it was verified, what it is
not, and the decisions Mac still needs to make.

Mac's direction for RONI, 2026-11-19: lightweight enough for
mobile phone processors to support the network, a reasonably
acquirable max supply so more people can access it, real-world
physical and digital assets backing value where possible, and
a RONI/USD trade pair first.

No network, exchange listing, or backing exists yet. Those are
roadmap items, listed in Section 7, not claims in this draft.

## 1. Introduction

Mac asked, in ai.evo, for a next-level encryption algorithm using SHA
functions, X11, and related hashing. He chose to build the hybrid
encryption prototype first — EvoCrypt. On 2026-11-19 he then asked
whether a language model could solve the next block of a blockchain,
and then asked to instantiate the first block and timestamp of a
blockchain network together, using the algorithm from that separate
ai.evo thread. He then named it Mac 'N Cheese Chain, ticker RONI,
and directed the mobile, supply, backing, and USD-pair design below.

## 2. Background: EvoCrypt and EvoKDF-11

EvoCrypt Hybrid Prototype v0.1 (2026-11-13) and v0.2 (2026-11-13,
verified 2026-11-14) work as follows:

- Password + random salt go through EvoKDF-11, an 11-step hash chain,
  X11-style, 1,000 rounds, deriving three 32-byte keys.
- Layer 1: AES-256-GCM
- Layer 2: ChaCha20-Poly1305, locking the first layer's output again
- Seal: HMAC-SHA3-512, checked before any decryption

Honest limit, carried over from EvoCrypt: Python's standard library
does not contain the real BMW, Groestl, JH, Skein, Luffa, CubeHash,
SHAvite, SIMD, or Echo hashes from X11. Each step in EvoKDF-11 is
therefore mapped to a standard-library hash and labelled as a
substitution in the source. This chain inherits that mapping, and
does not claim to be real X11.

## 3. EvoHash-11: the block hash, and mobile-lightweight design

EvoHash-11 is one pass through the same 11 functions, in the same
order, as EvoKDF-11:

1. BLAKE2b-512, 2. SHA3-512, 3. SHA-512, 4. SHA-256, 5. BLAKE2s-256,
6. SHA3-256, 7. SHAKE-256, 8. SHA-512/256-mix, 9. BLAKE2b-256,
10. SHA3-384-mix, 11. SHA-512-final

Output: 64 bytes, 128 hex characters.

Why one pass, not 1,000 rounds? EvoCrypt's KDF uses 1,000 rounds
to make password guessing slow. Mining tries thousands of nonces,
so 1,000 rounds per try would make even a low-difficulty demo
impractically slow, especially on a phone. EvoHash-11 keeps the
same chain and order, with 1 pass per hash attempt.

Mobile-lightweight, per Mac's direction:
- CPU-only, standard-library hashes, no ASIC-specific step,
  no GPU requirement, no large memory requirement.
- Genesis difficulty is `0000` (4 hex zeros, ~1 in 65,536) —
  a phone can find a block in seconds at this difficulty in a demo.
- Difficulty must rise / adjust before any real network, or
  phones would be outrun by desktops. Block time target,
  difficulty adjustment, and a native / optimised mobile
  implementation are future work, not built yet.
- No wallet, transaction format, or peer network yet.

Block hash input, UTF-8:

```
index|timestamp|previous_hash|data|nonce
```

## 4. Genesis Block 0 — restarted

Mined and verified 2026-11-19, in the "Cryptocurrency mining
capability question" thread. This is the third Block 0, and the
live one. The first two are superseded, listed below for audit.

| Field | Value |
|---|---|
| Chain | Mac 'N Cheese Chain |
| Ticker | RONI |
| Index | 0 |
| Timestamp (Unix) | 1795132723 |
| Timestamp (UTC) | 2026-11-19T23:58:43Z |
| Timestamp (PST) | 2026-11-19 15:58:43 -08:00 |
| Data | Mac 'N Cheese Chain genesis — RONI — circulating supply 100000 to start — created by Mac & Destiny's Child in ai.evo |
| Previous hash | 128 zeros (`0` × 128) |
| Nonce | 23976 |
| Attempts | 23,977 |
| Mine time | 0.369 seconds |
| Difficulty | hash must start with `0000` |
| Hash | `0000adbc0f16c14cc2540a4a259339fd0b02a1503bad43f0bbb484eb5007c36d68f9d825875297db1b26be6eb2a0532496c6a31317f6ce9a9fc7cf6a8591c1b0` |
| Hash length | 128 hex chars |
| Circulating supply to start | 100,000 RONI |
| Hash function | EvoHash-11 — 1-pass EvoKDF-11 chain from ai.evo / EvoCrypt v0.2 |

Verification, done twice: recomputing
`EvoHash-11("0|1795132723|<128 zeros>|<data>|23976")`
gives exactly the hash above, it starts with `0000`, and the
previous hash is all zeros.

Superseded Block 0s (audit only, not live):
- Mac 'N Cheese Chain, no supply in data: 2026-11-19 15:57:37 PST,
  nonce 112867, hash `000015339905af898cc80dfb8c247c0df1c9461155341de47314cf2c782d74a28249c4b93dffe494241a59c02f4460542329fe7dc162c26c86880588b201a5f3`
- EvoChain: 2026-11-19 15:47:05 PST, nonce 4452,
  hash `000002d7954aef129e29b68b19fa44156d104edde9a335071a8c20267e83162683aab5e9d2428200ac8061b996f529e6aa51b6f1aa1e70d4a71d89df1a9ea06b`

Reproducing it:

```bash
python3 evochain_genesis.py
```

Note: re-running mines a new genesis block with the current time,
so the nonce and hash will differ. The saved block in
`evochain_genesis_block.json` is the canonical Block 0 above.

## 5. Supply, utility, and value — Mac's direction

- **Circulating supply to start: 100,000 RONI.** Set by Mac
  2026-11-19, recorded in the hashed genesis data.
- **Max supply — proposal only, not final: 10,000,000,000 RONI (10B).**
  Proposed so more people can acquire RONI and use it, driving
  utility and demand. 100,000 to start is 0.001% of that proposal.
  Mac has not yet confirmed 10B. Alternatives: 1B / 10B / 100B.
  Max supply is not hashed into Block 0, so it can change
  without re-mining. Emission / block reward for the rest: TBD.
- **Utility:** RONI is intended to be usable by phone users
  supporting the network, not only by specialised miners.
  Transaction format, fees, staking / validation, and
  governance: TBD.
- **Backing — roadmap only:** Mac wants real-world physical
  and digital assets to back value where possible. That needs
  custodians, audits, proof of reserves, and legal structure —
  none of which exist yet. **Do not claim RONI is backed today.**
  No asset, price, or value is promised in this paper.
- **First trade pair — proposal: RONI/USD first,** before any
  other pair. That needs an exchange listing, liquidity, and
  compliance — not built yet. No exchange, price, or listing
  is promised.

## 6. Block structure and mining — current design

- **Block:** index, timestamp, data, previous_hash, nonce, hash,
  difficulty_prefix, hash_function, attempts, mine_time_seconds,
  circulating_supply_start_RONI.
- **Mining:** proof-of-work by nonce search. Increment nonce from
  0 until the EvoHash-11 hex starts with the difficulty prefix.
  Genesis difficulty is `0000`.
- **Linking:** Block 1+ must set `previous_hash` to Block 0's hash
  above, and be mined the same way. No Block 1 exists yet.
- **Consensus:** none beyond this demo yet. Single node,
  no peer network, no wallet, no transaction format, and no
  difficulty adjustment.

## 7. Security, limits, and what this is not

- Prototype only, not audited. Do not use for real secrets or real value.
- EvoHash-11 is a custom, unreviewed hash chain. It is not SHA-256,
  not real X11, and has no security proof.
- A 4-hex-zero difficulty is a demo difficulty. A real network
  would need far higher difficulty, difficulty adjustment, and
  protection against reorganisation, double-spending, and Sybil attacks.
- **Ticker collision:** RONI already exists as a tiny token on
  another chain (contract 0x79d374423a7ee71ad332cf8d8bb596d739f4c30c,
  pool ~4 years old, 51 holders, ~$6,248 market cap, checked
  2026-11-19). Mac chose to proceed with RONI for this chain
  anyway. Exchanges and wallets will need to distinguish the two.
  A similar Mac&Cheese $XVMC token and a CHEESE Blockchain $NCH
  also exist, with different tickers.
- No token is listed, no price exists, no backing exists.
- GitHub status: username MacCheezyb is still unclaimed
  (API 404, checked 2026-11-19). No account exists yet, so no
  repo has been pushed. GitHub requires accounts to be created
  by a human, so Mac must create the account himself. Source is
  prepared locally, ready to push.

## 8. Open decisions — for Mac

1. **Max supply:** confirm 10B, or pick 1B / 100B?
2. **Emission:** how is RONI after the first 100,000 issued?
   Block reward, halving, or another schedule?
3. **Purpose:** learning/demo only, payments, data anchoring,
   or another use?
4. **Consensus and difficulty:** stay proof-of-work? Add difficulty
   adjustment and a block time target? Mobile mining rules?
5. **Transactions and wallets:** what goes in a block's data, and
   how are keys / wallets handled, especially on phones?
6. **Network:** stay single-node, or add peers, nodes, and sync?
7. **Backing:** which physical / digital assets, who custodies,
   who audits, and how is proof published?
8. **RONI/USD:** which exchange / venue first, and what
   compliance and liquidity are needed?
9. **License and visibility:** MIT, another licence, or closed?
   Public or private GitHub repo?

## Appendix A. Files

- `evochain_genesis.py` — genesis miner + verifier
- `evochain_genesis_block.json` — canonical Genesis Block 0
- `evocrypt_hybrid_v02.py` — EvoCrypt v0.2
- `evocrypt_hybrid_prototype.py` — EvoCrypt v0.1
- `README.md` — repo readme

## Appendix B. Timeline

- 2026-11-13, ai.evo: Mac asks for a next-level algorithm using SHA / X11.
  Chooses hybrid encryption prototype first. EvoCrypt v0.1 built.
- 2026-11-13 / 14: EvoCrypt v0.2 built, verified in a clean venv.
- 2026-11-19: Mac asks about mining a real block, then to instantiate
  Block 0 together using the ai.evo algorithm. EvoChain Block 0 mined 15:47:05 PST.
- 2026-11-19: Repo bundle prepared locally, white paper Draft v0.1 built.
- 2026-11-19: Mac names it Mac 'N Cheese Chain, ticker RONI.
  RONI collision found, Mac proceeds. Block 0 re-mined 15:57:37 PST.
- 2026-11-19: Mac directs mobile-lightweight, acquirable max supply,
  RWA backing, RONI/USD first. Block 0 restarted with 100,000 RONI
  circulating to start, 15:58:43 PST. Draft v0.2.

---
*Draft v0.2 — 2026-11-19. Changes only under Mac's direction.*
