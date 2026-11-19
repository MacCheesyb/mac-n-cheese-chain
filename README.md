# EvoChain

Prototype blockchain by Mac (MacCheezyb) and Destiny's Child.
Built from the EvoCrypt / ai.evo work: an X11-style 11-step hash chain.

**Status: prototype only — not audited, no real value, do not use for real secrets or real money.**

## What is here

- `evochain_genesis.py` — mines and verifies Genesis Block 0 using EvoHash-11
- `evochain_genesis_block.json` — the mined genesis block
- `evocrypt_hybrid_v02.py` — EvoCrypt Hybrid Prototype v0.2 (EvoKDF-11, AES-256-GCM + ChaCha20-Poly1305, HMAC-SHA3-512)
- `evocrypt_hybrid_prototype.py` — EvoCrypt v0.1
- `EVOCHAIN-WHITE-PAPER-DRAFT.md` — white paper draft v0.1 (see also the PDF in this chat)

## Genesis Block 0 — verified

- Chain: EvoChain (provisional name)
- Timestamp: 1795132025 — 2026-11-19T23:47:05Z / 2026-11-19 15:47:05 PST
- Data: `EvoChain genesis — created by Mac & Destiny's Child in ai.evo`
- Previous hash: 128 zeros
- Nonce: 4452 — 4,453 attempts, 0.068s
- Difficulty: hash starts with `0000`
- Hash: `000002d7954aef129e29b68b19fa44156d104edde9a335071a8c20267e83162683aab5e9d2428200ac8061b996f529e6aa51b6f1aa1e70d4a71d89df1a9ea06b`
- Hash function: EvoHash-11 — 1-pass EvoKDF-11 chain from ai.evo / EvoCrypt v0.2

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

- Chain name: keep EvoChain, or rename?
- Purpose: learning/demo, payments, data, or something else?
- Token / economics: any token, supply, or none?
- Consensus: stay proof-of-work, change difficulty, add difficulty adjustment?
- Network: single-node demo now — peers, nodes, and wallet next?
- Repo: public or private on GitHub once the account exists?
