# RONI Wallet — browser extension scaffold v0.1

Prototype only — not audited, do not use for real funds.

This is a Manifest V3 skeleton for Chrome / Chromium / Edge / Brave.
Load it unpacked at `chrome://extensions` → Developer mode → Load unpacked → this folder.

What works now:
- Popup opens, shows placeholder address / balance
- Buttons are stubs — no keys are created or stored, no node is connected

What is next, in order:
1. Encrypted key storage in the extension, mirroring `roni_wallet.py`
   (EvoCrypt-encrypted private key, password unlock)
2. A Mac 'N Cheese node with a JSON-RPC endpoint, so the extension
   can ask for a balance and submit a signed transaction
3. Sign-message / sign-transaction approval screen in the popup
4. MetaMask decision: own extension (this), a MetaMask Snap, or
   EVM compatibility — see the main README / white paper

Do not load this with real funds, and do not paste a real private key into it.
