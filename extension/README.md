# R0NI Wallet — browser extension v0.5

## What is new in v0.5 — milli-R0NI (2026-11-23)

Amounts are integer **milli-R0NI** (1 R0NI = 1000 milli; smallest
unit **0.001 R0NI**), exactly as `roni_wallet.py` since commit
`e308fee` (Mac's choice: max supply ceiling 10,000,000,000 R0NI,
smallest denomination 0.001 R0NI).

- **Amounts module (`amounts.js`):** `parseAmount()` / `formatAmount()`
  mirror Python's `parse_amount()` / `format_amount()` exactly —
  decimal R0NI with at most 3 places, parsed once at the boundary
  into integer milli (`"1.500"` → 1500, `"0.001"` → 1, `"100000"` →
  100,000,000). Below 0.001 R0NI or more than 3 decimal places is
  rejected. Balances display with exactly 3 places
  (e.g. `100000.000 R0NI`). No binary floats anywhere in balances.
- **Sign a transfer (new):** recipient + amount (decimal R0NI) +
  nonce in the popup. The transaction is signed over
  `sender|recipient|<amount in milli>|nonce` with Ed25519, and the
  signed JSON carries `"amount_unit": "milli-R0NI"`. Submit it with
  `testnet/accept_signed_tx.py signed-tx.json` — the extension does
  not send transactions itself. A signed transaction without the
  marker is a pre-milli transaction and is **rejected** by
  `accept_signed_tx.py`, never silently converted (a silent
  conversion would be a 1000x error).
- **Legacy ledgers** (whole-R0NI amounts, no `amount_unit` marker)
  are migrated x1000 on load, idempotently, mirroring
  `roni_wallet.py load_ledger()`.
- Ed25519 signing, canonical EvoHash-11 addresses, the v0.4
  interim-address migration, and the keystore format are unchanged.

# R0NI Wallet — browser extension v0.4 (kept below for history)

Prototype only — not audited, do not use for real funds.

Ticker renamed 2026-11-19: RONI → R0NI (0 in place of O), to avoid
confusion with an existing RONI token. Addresses are now `R0NI-…`.

This is a Manifest V3 extension for Chrome / Chromium / Edge / Brave.
Load it unpacked at `chrome://extensions` → Developer mode → Load unpacked → this folder.

What works now:
- Create an Ed25519 keypair with WebCrypto, encrypted at rest with
  AES-GCM (PBKDF2, 100,000 iterations, SHA-256), unlock / lock / delete
- Sign a message and verify the signature in the popup
- **Balance display (new in v0.3):** use "Load local ledger" to load a
  `genesis_allocation.json` file (from the repo root, or exported from
  `wallet-app.html`). If this wallet's address is the genesis holder
  recorded in that ledger, the balance shows **100,000 R0NI**; otherwise
  it shows the balance computed from the ledger's allocations +
  transfers, or 0 when no ledger is loaded. There is no node yet, so
  the balance is only as current as the ledger file you load.

What works now (new in v0.4):
- **Unified address:** the address is now the canonical EvoHash-11
  address — `R0NI-` + first 40 hex of EvoHash-11(public key), the
  SAME address `roni_wallet.py` gives for the same key. Implemented
  with the vendored bundle `evo-hash-11.js` (@noble/hashes 1.8.0,
  bundled with esbuild, no CDN, no network). Verified against Python
  on 6 test vectors, including the 0x11×32 key →
  `R0NI-d867166b51a61bcbd4c498524fb8cd3008514823`.
- **Migration:** a wallet created by v0.3 with the old interim SHA-512
  address is migrated automatically when the popup loads: its address
  is recomputed from the stored public key, and any loaded ledger's
  allocation / transfer entries naming the old address are rewritten
  to the new one. A genesis 100,000 R0NI allocation recorded against
  the old address therefore keeps working — the balance does not
  change. Migration is idempotent: a wallet already at the canonical
  address is left alone.

What is next, in order:
1. A Mac 'N Cheese node with a JSON-RPC endpoint, so the extension
   can ask for a balance and submit a signed transaction
2. Sign-transaction approval screen in the popup
3. MetaMask decision: own extension (this), a MetaMask Snap, or
   EVM compatibility — see the main README / white paper

For sending R0NI today, use the standalone app `wallet-app.html` in
the repo root — it has the same key storage plus a local signed
ledger, paper wallet, and export / import.

Do not load this with real funds, and do not paste a real private key into it.
