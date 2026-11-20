# R0NI Testnet v2 — R- Block Hashes

Prototype testnet, simulated on **one Linux VM** (3 nodes as separate
OS processes on 127.0.0.1:8021–8023, separate data dirs, localhost
HTTP P2P). **Not multiple real VMs** — Docker was not available.
No real value, not audited.

## What is different from v1?

**Only the block-hash format.** Everything else — EvoHash-11, Ed25519
transactions, media payloads (format v2), asset certification (v0.3),
governance voting (v0.4) — is the same code as `testnet/`, ported
unchanged. v1 (`testnet/`, ports 8001–8003, plain hex block hashes)
is **untouched**; v2 is a **separate test network**, not a replacement.

## The R- format

Every block hash is:

```
R- + 128 hex chars of EvoHash-11
```

Example (this run's genesis):

```
R-0000f268031649e33f13d6868aab86cde180413818abc0c24cbcf766d156dd1f4f3c974284f9ffc0b5d43b7226304f6d21fd7fc82edd1c7f296dfe5255aecdb5
```

- The **"R" is a label, NOT part of the hash.** Hex has no R
  (only 0–9 and a–f), so the hash function cannot output one.
- The **difficulty rule applies to the hex part**: it must start
  with `0000` immediately after `R-`.
- Validation rejects: plain hex hashes (no `R-`), wrong prefixes
  (e.g. `X-`), R- hashes whose hex part does not start with `0000`,
  and any block whose hash does not match a recomputation of
  EvoHash-11 over the header (without the prefix).
- `previous_hash` is also in R- form, so blocks link through
  R- hashes. The genesis `previous_hash` is `R-` + 128 zeros.
- **Transaction IDs are unchanged** — plain EvoHash-11 hex. No
  txid embeds a block hash in this design, so nothing about
  transactions needed the prefix.

## Genesis Block 0 (v2)

Mined by `testnet-v2/mine_v2_genesis.py` (a separate script — never
run the v1 `evochain_genesis.py` bare, it overwrites the v1 genesis):

- data: `R0NI testnet v2 genesis — R- block hashes — circulating supply 100000 to start`
- hash: `R-0000f268031649e33f13d6868aab86cde180413818abc0c24cbcf766d156dd1f4f3c974284f9ffc0b5d43b7226304f6d21fd7fc82edd1c7f296dfe5255aecdb5`
- nonce: 2060, timestamp: 1795209315
- Funds three fresh test wallets with 1,000,000 test R0NI each
  (test-only; the file in the repo is a snapshot from the latest run
  — `run_testnet.py` re-mines a fresh genesis on every run).

## Latest full run (see ANALYTICS.md / analytics.json)

- Nodes: 3 (full mesh, ports 8021/8022/8023), miner: node 1 only
- Blocks: 12 (genesis + 11 mined), all 3 nodes agree
- Transactions confirmed: 62 — 20 phase 1 + 6 media payload
  (text, PNG, GIF, WAV, MP4, ref — all extracted byte-identical)
  + 1 gov-propose + 3 gov-votes + 30 burst + 1 restart
  + 1 double-spend-test tx
- Burst TPS: 1.84 tx/s this run (9.08 in the first run — Python PoW
  mining is the bottleneck, so TPS varies run to run)
- Mean block time: 4.09s, median: 3s
- Node restart sync: 0.30s to catch up to height 11
- Governance: proposal "v2 testnet: keep R- block hashes?" —
  tally yes 1,998,740 / no 999,060, quorum 10,000 met, winner yes,
  **passed** (snapshot balances, so the numbers are not round —
  phase 1 and media moved funds before the proposal was filed)
- Mac's address: 2,392 R0NI, inbound only — nothing was ever
  signed from it; we do not have his private key
- Security tests — **all 5 rejected**: double-spend (bad nonce),
  overspend, forged signature, tampered amount (txid mismatch),
  tampered block (hash does not match recomputed EvoHash-11)

## Files

| File | What it is |
|---|---|
| `node.py` | v2 node — R- `block_hash` / validation, everything else as v1 |
| `run_testnet.py` | Full 3-node run: phases, media, governance, burst, restart, security, analytics |
| `mine_v2_genesis.py` | Mines a fresh v2 genesis Block 0 into `testnet-v2/genesis.json` |
| `genesis.json` | Snapshot of the latest run's v2 genesis (R- hash) |
| `accept_signed_tx.py` | Submit an externally signed tx (default port 8021) |
| `media_fixtures.py` | Real PNG/GIF/WAV/MP4 fixtures for payload tests |
| `test_v2.py` | 20 checks for the R- format (results: `v2_test_results.json`) |
| `test_certs.py` | 21 cert checks, ported to v2 |
| `test_governance.py` | 32 governance checks, ported to v2 |
| `test_payloads.py` | Payload checks, ported to v2 (live node on port 8111) |
| `analytics.json` / `ANALYTICS.md` | Latest full-run results |
| `README.md` | This file |

## Running it

```bash
# Full 3-node run (re-mines genesis, runs all phases, writes analytics)
/home/hatch/workspace/r0ni-v2-venv/bin/python testnet-v2/run_testnet.py

# R- format checks only (offline + live 3-node roundtrip, ports 8041-8043)
/home/hatch/workspace/r0ni-v2-venv/bin/python testnet-v2/test_v2.py

# Ported suites
/home/hatch/workspace/r0ni-v2-venv/bin/python testnet-v2/test_certs.py
/home/hatch/workspace/r0ni-v2-venv/bin/python testnet-v2/test_governance.py
/home/hatch/workspace/r0ni-v2-venv/bin/python testnet-v2/test_payloads.py
```

The venv at `~/workspace/r0ni-v2-venv` has `cryptography` installed.
System python does not — use the venv.

## Honest limits

- Prototype only, not audited, no real value, no live network.
- One VM, three processes — not three real machines.
- Mac's genesis key was never involved; test wallets only.
