# Mac 'N Cheese Chain — RONI

Prototype blockchain by Mac (MacCheezyb) and Destiny's Child.
Built from the EvoCrypt / ai.evo work: an X11-style 11-step hash chain.

**Status: prototype only — not audited, no real value, do not use for real secrets or real money. RONI is NOT backed today.**

## What is here

- `evochain_genesis.py` — mines and verifies Genesis Block 0 using EvoHash-11
- `evochain_genesis_block.json` — the mined genesis block
- `evocrypt_hybrid_v02.py` — EvoCrypt Hybrid Prototype v0.2 (EvoKDF-11, AES-256-GCM + ChaCha20-Poly1305, HMAC-SHA3-512)
- `evocrypt_hybrid_prototype.py` — EvoCrypt v0.1
- `EVOCHAIN-WHITE-PAPER-DRAFT.md` — white paper draft (v0.2 in progress, see PDF)

## Genesis Block 0 — verified (restarted 2026-11-19, supersedes earlier Block 0s)

- Chain: Mac 'N Cheese Chain
- Ticker: RONI
- Timestamp: 1795132723 — 2026-11-19T23:58:43Z / 2026-11-19 15:58:43 PST
- Data: `Mac 'N Cheese Chain genesis — RONI — circulating supply 100000 to start — created by Mac & Destiny's Child in ai.evo`
- Previous hash: 128 zeros
- Nonce: 23976 — 23,977 attempts, 0.369s
- Difficulty: hash starts with `0000`
- Hash: `0000adbc0f16c14cc2540a4a259339fd0b02a1503bad43f0bbb484eb5007c36d68f9d825875297db1b26be6eb2a0532496c6a31317f6ce9a9fc7cf6a8591c1b0`
- Hash function: EvoHash-11 — 1-pass EvoKDF-11 chain from ai.evo / EvoCrypt v0.2
- Circulating supply to start: 100,000 RONI

Superseded blocks, kept for audit only — not live:
- Mac 'N Cheese Chain Block 0 (no supply in data): 2026-11-19 15:57:37 PST, nonce 112867,
  hash `000015339905af898cc80dfb8c247c0df1c9461155341de47314cf2c782d74a28249c4b93dffe494241a59c02f4460542329fe7dc162c26c86880588b201a5f3`
- EvoChain Block 0: 2026-11-19 15:47:05 PST, nonce 4452,
  hash `000002d7954aef129e29b68b19fa44156d104edde9a335071a8c20267e83162683aab5e9d2428200ac8061b996f529e6aa51b6f1aa1e70d4a71d89df1a9ea06b`

## Design direction — Mac, 2026-11-19

- **Mobile-lightweight:** EvoHash-11 is CPU-only, stdlib hashes, 1 pass,
  no ASIC/GPU/large-memory requirement. Genesis difficulty `0000` is
  phone-feasible in a demo. Difficulty must adjust before any real
  network, or phones would be outrun.
- **Circulating supply to start:** 100,000 RONI, set by Mac 2026-11-19.
  Recorded in the hashed genesis data, so this is the live Block 0.
- **Max supply — proposal only, not final:** 10,000,000,000 RONI (10B).
  Proposed so more people can acquire RONI and use it, driving utility
  and demand. Not hashed into Block 0, so it can change without
  re-mining. Alternatives: 1B / 10B / 100B — Mac to confirm.
  100,000 to start is 0.001% of the 10B proposal.
- **Backing — roadmap only:** Mac wants real-world physical + digital
  assets to back value where possible. That needs custodians, audits,
  and legal structure — none exist yet. Do NOT claim RONI is backed.
- **First trade pair — proposal:** RONI/USD first, before any other pair.
  Needs an exchange listing, liquidity, and compliance — not built yet.
- **Ticker note:** RONI already exists as a tiny token on another chain
  (51 holders, ~$6,248 market cap, checked 2026-11-19). Mac chose to
  proceed with RONI for this chain anyway.

## Run it

```bash
python3 evochain_genesis.py
```

That re-mines a genesis block with the current time. To verify the saved block,
the script's `verify()` recomputes the hash from the header and checks the
`0000` prefix and the all-zero previous hash.

## EvoHash-11

One pass through the same 11 functions, in the same order, as EvoKDF-11 in
EvoCrypt v0.2:

BLAKE2b-512, SHA3-512, SHA-512, SHA-256, BLAKE2s-256, SHA3-256, SHAKE-256,
SHA-512/256-mix, BLAKE2b-256, SHA3-384-mix, SHA-512-final

Output is 64 bytes = 128 hex chars. EvoCrypt's KDF runs this chain 1,000
rounds to derive keys — too slow for mining, so the block hash uses 1 pass.

Python's stdlib does not have the real BMW / Groestl / JH / Skein etc. from
X11, so each step is mapped to a stdlib hash and labelled in the source,
as in EvoCrypt v0.2.

## License

To be decided by Mac — no license file is included yet on purpose.
Do not treat this as open-source permission until he chooses one.

## Next decisions for Mac

- Max supply: confirm 10B, or pick 1B / 100B?
- Purpose: learning/demo, payments, data, or something else?
- Block reward / emission: how is RONI issued after Block 0?
- Consensus: stay proof-of-work, add difficulty adjustment, block time target?
- Transactions and wallets: what goes in a block's data, and how are keys handled?
- Network: stay single-node, or add peers, nodes, and sync?
- Backing: which physical / digital assets, who custodies, who audits?
- Repo: public or private on GitHub once the account exists?
