# R0NI Wallet — browser extension v0.3

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

What is next, in order:
1. EvoHash-11 addresses in the browser, so extension addresses match
   `roni_wallet.py` (the canonical `R0NI-` + EvoHash-11(public key)).
   Today the extension uses an interim SHA-512 address — the two will
   differ for the same key, so do not mix them.
2. A Mac 'N Cheese node with a JSON-RPC endpoint, so the extension
   can ask for a balance and submit a signed transaction
3. Sign-transaction approval screen in the popup
4. MetaMask decision: own extension (this), a MetaMask Snap, or
   EVM compatibility — see the main README / white paper

For sending R0NI today, use the standalone app `wallet-app.html` in
the repo root — it has the same key storage plus a local signed
ledger, paper wallet, and export / import.

Do not load this with real funds, and do not paste a real private key into it.
