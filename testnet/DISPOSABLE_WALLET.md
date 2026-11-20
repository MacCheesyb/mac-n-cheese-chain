# Disposable test wallet — for Mac to fund

Test-only, no real value. This wallet is **disposable**: it exists so
the testnet can spend from it in performance/security tests, without
ever touching Mac's genesis key.

## Address to fund

- **Address: `R0NI-e56d2126ff80182ffd2a2f5dd7527ac9fa44dd38`**
- **Public key hex: `26a501d1fb5c48c97dac5ce59570bfdcf0e799cc6d0d790b697559165093f31e`**
- Suggested amount: **1,000 R0NI** (amount is Mac's choice)

## How Mac funds it

1. Open his genesis wallet in the standalone `wallet-app.html`
   (or the hosted R0NI Wallet app).
2. Send **1,000 R0NI** (or an amount of his choosing) to the address
   above. He signs that transfer in his own wallet app — his
   genesis private key never leaves his device and is never sent
   to the testnet.
3. Tell the testnet the amount he sent (or provide the signed
   transaction JSON, which `testnet/accept_signed_tx.py` can verify).

## How the testnet uses it

- The private key for this disposable wallet is **NOT in this repo**
  (the repo is public). It is stored only in the testnet operator's
  workspace at `~/workspace/r0ni-testnet/disposable-wallet.json`,
  test-only.
- `testnet/run_testnet.py --fund-disposable <amount>` mirrors the
  funding Mac made into the testnet genesis (same amount, same
  address), and the testnet then spends from this disposable wallet
  in its performance/security tests — never from the genesis key.
- Without funding, the disposable wallet's testnet balance is 0 and
  the run records it as "awaiting funding from Mac".
