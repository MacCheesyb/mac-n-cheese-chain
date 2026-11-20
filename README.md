# Mac 'N Cheese Chain — R0NI

Prototype blockchain by Mac (MacCheesyb) and AI "Agent: Destiny's Child".
Built from the EvoCrypt / ai.evo work: an X11-style 11-step hash chain.

**Status: prototype only — not audited, no real value, do not use for real secrets or real money. R0NI is NOT backed today.**

**Ticker rename (2026-11-19): RONI → R0NI** — the number 0 in place of
the letter O, to avoid confusion with an existing RONI token on another
chain. Everything current-facing now says R0NI. The Genesis Block 0
hashed data still reads "RONI" — it is a historical record, and changing
it would change the block hash, so Block 0 was NOT re-mined.

## What is here

- `evochain_genesis.py` — mines and verifies Genesis Block 0 using EvoHash-11
- `evochain_genesis_block.json` — the mined genesis block
- `evocrypt_hybrid_v02.py` — EvoCrypt Hybrid Prototype v0.2 (EvoKDF-11, AES-256-GCM + ChaCha20-Poly1305, HMAC-SHA3-512)
- `evocrypt_hybrid_prototype.py` — EvoCrypt v0.1
- `roni_wallet.py` — R0NI Wallet v0.2 (CLI, Ed25519, EvoHash-11 addresses, local ledger)
- `genesis_allocation.json` — local ledger: genesis supply, allocations, signed transfers
- `wallet-app.html` — **downloadable wallet app** (single file, works offline): create wallet, send / receive, paper wallet with QR codes, export / import
- `extension/` — R0NI Wallet browser extension v0.3 (Manifest V3)
- `EVOCHAIN-WHITE-PAPER-DRAFT.md` — white paper draft (see PDF, Draft v0.4)
- `logo-options/roni-logo-r0ni.webp` — R0NI logo (slashed zero)

## Genesis Block 0 — verified (restarted 2026-11-19, supersedes earlier Block 0s)

- Chain: Mac 'N Cheese Chain
- Ticker: R0NI (formerly RONI — the genesis data below still says RONI, see above)
- Timestamp: 1795132723 — 2026-11-19T23:58:43Z / 2026-11-19 15:58:43 PST
- Data: `Mac 'N Cheese Chain genesis — RONI — circulating supply 100000 to start — created by Mac & Destiny's Child in ai.evo`
- Previous hash: 128 zeros
- Nonce: 23976 — 23,977 attempts, 0.369s
- Difficulty: hash starts with `0000`
- Hash: `0000adbc0f16c14cc2540a4a259339fd0b02a1503bad43f0bbb484eb5007c36d68f9d825875297db1b26be6eb2a0532496c6a31317f6ce9a9fc7cf6a8591c1b0`
- Hash function: EvoHash-11 — 1-pass EvoKDF-11 chain from ai.evo / EvoCrypt v0.2
- Circulating supply to start: 100,000 R0NI

Superseded blocks, kept for audit only — not live:
- Mac 'N Cheese Chain Block 0 (no supply in data): 2026-11-19 15:57:37 PST, nonce 112867,
  hash `000015339905af898cc80dfb8c247c0df1c9461155341de47314cf2c782d74a28249c4b93dffe494241a59c02f4460542329fe7dc162c26c86880588b201a5f3`
- EvoChain Block 0: 2026-11-19 15:47:05 PST, nonce 4452,
  hash `000002d7954aef129e29b68b19fa44156d104edde9a335071a8c20267e83162683aab5e9d2428200ac8061b996f529e6aa51b6f1aa1e70d4a71d89df1a9ea06b`

## Wallet — how to get on board

There is no network / node yet, so wallets and balances live locally
for now. Pick one of these — they all use the same local ledger format
(`genesis_allocation.json`):

1. **Wallet app (easiest):** download `wallet-app.html` from this repo
   and open it in any modern browser — it works offline, straight from
   the file. Create a wallet with a password (Ed25519 key, private key
   encrypted with AES-GCM). The **first wallet created is the genesis
   holder: it is allocated the 100,000 R0NI genesis supply** in the
   local ledger. From there you can send R0NI (signed, balance-checked,
   recorded in the ledger), receive (address + QR code), and print a
   **paper wallet** — address and public key with QR codes, plus the
   encrypted private key (your password is still required to use it).
   Export the wallet and ledger files to back them up or move them.
2. **Browser extension:** load `extension/` unpacked in Chrome / Edge /
   Brave. Same key storage, plus a balance display from a ledger file
   you load. No sending yet — sending lives in the wallet app.
3. **Command line:** `python3 roni_wallet.py` — see its usage for
   `create`, `show`, `sign`, `verify`, `init-ledger`,
   `allocate-genesis`, `balance`, and `transfer`. Addresses here are
   the canonical EvoHash-11 addresses (`R0NI-` + EvoHash-11 of the
   public key). The browser extension and the wallet app now use the
   SAME canonical address (unified 2026-11-19, extension v0.4 /
   wallet-app.html v0.4, via the vendored `@noble/hashes` 1.8.0
   EvoHash-11 bundle in `extension/evo-hash-11.js`).

### Message / media payloads — transactions can carry content

A transaction can include a message or media (transaction
format v2, 2026-11-19): a text message, picture, song, short
video, GIF, or other digital file — so the chain has utility
beyond moving numbers. The payload is an optional `"data"`
field on the transaction, and transactions without one are
still valid (format v1).

- **Text:** up to 1,000 characters, stored uncompressed.
- **Media:** up to 5 MB raw, zlib level 9, max 1 MB compressed
  on-chain. Anything bigger is rejected — use a `ref` payload
  instead (SHA-256 + URI on-chain, media itself off-chain).
- **Lossless:** nodes decompress and check the SHA-256 and
  size on receipt, extraction re-checks the hash, and the
  payload is covered by the transaction signature — what comes
  out is byte-identical to what went in, or it is rejected.
- **Attach / extract:** `python3 roni_wallet.py payload-text`,
  `payload-file`, `payload-ref`, `make-tx`, `extract` — see
  `roni_wallet.py` usage and `testnet/README.md`. Tested
  end-to-end on the testnet: text, PNG, GIF, WAV and a real
  1-second MP4 all round-tripped byte-identical through mined
  blocks (see `testnet/ANALYTICS.md`).

### Asset certifications / NFTs — certificates on the chain (v0.3)

A certificate is a signed record that a real asset — a photo,
a document, a song, any file — belongs to an owner at a point
in time, issued by someone. It is built on the v2 media
payloads above, and it is the basis for NFTs and for
certifying real-world assets and documents.

- **What is recorded:** the asset's SHA-256 (never the bytes
  themselves, unless the asset also travels as a v2 payload),
  the issuer, the owner, the issue date, and an optional
  expiry. Certificate ID is deterministic: `CERT-` + first 40
  hex of EvoHash-11(asset SHA-256 + `|` + issuer address) —
  the same asset certified by the same issuer always has the
  same ID, so a duplicate mint is detectable and rejected.
- **How anyone verifies it:** take the file + the certificate,
  recompute the file's SHA-256 and check it matches, check the
  certificate ID, check the issuer's Ed25519 signature, and
  check the current owner in the chain — `cert-verify` does
  all of this, and reports an expired certificate as
  "expired" (authentic, but no longer current), never as
  valid.
- **Transfers:** a certificate moves only by a `cert-transfer`
  transaction signed by the CURRENT owner. The node rejects a
  transfer by anyone else, a mint of an already-certified
  asset + issuer, and any certificate whose issuer signature
  does not verify. Ownership lives in the chain / registry —
  the certificate document always names the owner AT MINT.
- **Minting moves 0 R0NI:** a `cert-mint` transaction records
  the certificate only; no money moves. The asset file itself
  travels in the transaction's v2 payload (inline up to the
  media limits, or a `ref` payload for large/off-chain media).
- **CLI:** `python3 roni_wallet.py cert-mint <wallet.json>
  <password> <asset-file> <owner> <description> <nonce>
  [--expires <unix>] [--registry certs.json]`,
  `cert-verify <cert.json> [asset-file] [--registry certs.json]`,
  `cert-transfer <wallet.json> <password> <cert.json> <to>
  <nonce> [--registry certs.json]`. Tested in
  `testnet/test_certs.py` (21 checks): PNG, document and
  audio certificates minted and verified, one transferred
  and verified under the new owner, and forged signature,
  tampered asset, duplicate, non-owner transfer and expired
  certificates all rejected — on the CLI, in a local
  registry, and on a live testnet node.

### Genesis allocation — empty until Mac creates his wallet

`genesis_allocation.json` in this repo has `"allocations": []` on
purpose. No address is pre-filled and no wallet has been created for
Mac. The 100,000 R0NI genesis supply is allocated to the first wallet
Mac creates in the wallet app (or with
`roni_wallet.py allocate-genesis`), and only once — a second allocation
is rejected by the CLI and by the app.

**Migration (2026-11-19):** the first wallet was already created
before the address was unified, with the old interim SHA-512 address,
and its genesis allocation was recorded against that interim address.
The extension v0.4 and wallet-app.html v0.4 migrate it automatically
on load: the address is recomputed from the stored public key with
EvoHash-11, and ledger allocation / transfer entries naming the old
address are rewritten to the new canonical address for the same key.
The balance does not change, and migration is idempotent — a wallet
already at the canonical address is left alone. No address is
hard-coded anywhere in this repo; migration always uses whatever
wallet is stored on the device being migrated.

## Design direction — Mac, 2026-11-19

- **Mobile-lightweight:** EvoHash-11 is CPU-only, stdlib hashes, 1 pass,
  no ASIC/GPU/large-memory requirement. Genesis difficulty `0000` is
  phone-feasible in a demo. Difficulty must adjust before any real
  network, or phones would be outrun.
- **Circulating supply to start:** 100,000 R0NI, set by Mac 2026-11-19.
  Recorded in the hashed genesis data, so this is the live Block 0.
- **Max supply — proposal only, not final:** 10,000,000,000 R0NI (10B).
  Proposed so more people can acquire R0NI and use it, driving utility
  and demand. Not hashed into Block 0, so it can change without
  re-mining. Alternatives: 1B / 10B / 100B — Mac to confirm.
  100,000 to start is 0.001% of the 10B proposal.
- **Backing — roadmap only:** Mac wants real-world physical + digital
  assets to back value where possible. That needs custodians, audits,
  and legal structure — none exist yet. Do NOT claim R0NI is backed.
- **First trade pair — proposal:** R0NI/USD first, before any other pair.
  Needs an exchange listing, liquidity, and compliance — not built yet.
- **Ticker note:** RONI already exists as a tiny token on another chain
  (51 holders, ~$6,248 market cap, checked 2026-11-19). The ticker for
  this chain was therefore changed to R0NI (0 in place of O) on
  2026-11-19 to avoid collisions and confusion.

## Run it

```bash
python3 evochain_genesis.py
```

That re-mines a genesis block with the current time. To verify the saved block,
the script's `verify()` recomputes the hash from the header and checks the
`0000` prefix and the all-zero previous hash.

```bash
python3 roni_wallet.py            # self-test: wallet + ledger
```

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
- Block reward / emission: how is R0NI issued after Block 0?
- Consensus: stay proof-of-work, add difficulty adjustment, block time target?
- Transactions and wallets: what goes in a block's data, and how are keys handled? (Local ledger exists now — a live chain / node is the next step.)
- Network: stay single-node, or add peers, nodes, and sync?
- Backing: which physical / digital assets, who custodies, who audits?
- License: choose one, or keep the repo unlicensed?
