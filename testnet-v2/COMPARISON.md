# R0NI Testnet v1 vs v2 — Security, Effectiveness, and Speed Comparison

**Date:** 2026-11-20 · **Status: LOCAL ONLY — not committed, not pushed to GitHub**
(per Mac's change of plan; the parent will deliver this as a local PDF).
Repo HEAD at measurement: `dd18b69`. Raw numbers:
[`comparison_results.json`](comparison_results.json).

**v1** = `testnet/` — plain hex block hashes, difficulty `0000`, ports 8001–8003.
**v2** = `testnet-v2/` — block hashes `"R-"` + 128 hex chars of EvoHash-11,
difficulty `0000` on the hex part after `R-`, ports 8021–8023.
The `R` is a label, NOT part of the hash — hex has no R (only 0–9 and a–f).

**One-line conclusion: the R- prefix costs nothing measurable. Security is
identical plus one extra check, effectiveness is identical, and hashing speed
is identical within run-to-run noise.**

## How it was measured

Same machine (1 Linux VM, shared CPU), matched workloads, all in one driver
(`/tmp/compare_v1_v2.py`, kept out of the repo):

1. **Benchmarks** — EvoHash-11 alone (10,000 hashes), `block_hash` on both
   code paths (10,000 each), mining 20 fresh blocks each at difficulty 0000,
   `validate_block` 200 times each, and the v2-only prefix rejections
   in-process.
2. **Fresh live run of testnet-v2 on its COMMITTED genesis**
   (`R-0000f268…`, nonce 2060, timestamp 1795209315) — 3 nodes on ports
   8031–8033, started with `--genesis testnet-v2/genesis.json`, **not
   re-mined**. The 3 funded test wallets in that genesis have no stored
   private keys, so this run drives blocks with amount-0 `gov-propose` /
   `cert-mint` transactions from fresh wallets (valid: no balance needed,
   nonce 0, signed). Regular transfers cannot be sent on that genesis
   without a funded key.
3. **Fresh matched live runs** of v1 then v2 via their `run_testnet.py`
   (20 phase-1 txs + 6 media payload txs + 30-tx burst + restart + security
   tests; v2 adds 1 `gov-propose` + 3 `gov-vote` txs, so 62 txs vs 58).
   These runs re-mine a genesis in memory by design; the committed
   `genesis.json` files were restored afterwards and are unchanged.
4. **Test suites** for both networks: payloads, certs, governance, plus
   v2's own `test_v2.py`.

## 1. Security — identical, plus one extra check on v2

| Attack / check | v1 (fresh run) | v2 (fresh run) | v2 committed-genesis run |
|---|---|---|---|
| Double-spend (same nonce) | rejected (400, bad nonce) | rejected (400, bad nonce) | rejected (400, bad nonce) |
| Overspend | rejected (400, insufficient balance) | rejected (400, insufficient balance) | rejected (400, insufficient balance) |
| Forged signature | rejected (400, signature verification failed) | rejected (400, signature verification failed) | rejected (400, signature verification failed) |
| Tampered amount (after signing) | rejected (400, txid mismatch) | rejected (400, txid mismatch) | rejected (400, txid mismatch) |
| Tampered block | rejected (400, hash does not match recomputed EvoHash-11) | rejected (400, hash does not match recomputed EvoHash-11) | rejected (400, hash does not match recomputed EvoHash-11) |
| Plain hex block hash (no `R-`) | n/a | **rejected** ("block hash must be 'R-' + 128 hex chars") | — |
| Wrong prefix (`X-…`) | n/a | **rejected** (same format error) | — |
| `R-` hash whose hex part lacks `0000` | n/a | **rejected** ("does not meet difficulty 0000 (hex part after 'R-')") | — |
| Zero-balance vote (snapshot rule) | rejected | rejected | rejected (400, "held 0 R0NI at the snapshot (block 1)") |

**Validation logic:** v2 adds exactly one check v1 lacks —
`is_valid_hash_format` (`"R-"` + 128 hex chars). Everything else — hash
recompute, difficulty on the hex part, `previous_hash` link, transaction
validation — is identical. The extra check can only reject, never accept
something v1 would reject: **v2 is strictly stricter than v1 on block
hashes.** A v1 node given an `R-` block hash rejects it too (hash does not
match recomputed EvoHash-11), so the two networks cannot accidentally
accept each other's blocks.

## 2. Effectiveness — identical

| Measure | v1 (fresh run) | v2 (fresh run) | Difference |
|---|---|---|---|
| Transactions confirmed | 58 | 62 (58 + 4 gov txs) | workload differs by design |
| Blocks | 10 (genesis + 9) | 12 (genesis + 11) | +2 (the 4 gov txs) |
| Nodes agreeing | 3/3, chain identical | 3/3, chain identical | none |
| Node restart sync | 0.30 s | 0.30 s | 0.00 s |
| Media payloads byte-identical | 5/5 (text, PNG, GIF, WAV, MP4; SHA-256 match on all 6 incl. ref) | 5/5, same | none |
| Cert mint / verify / transfer | 21/21 tests pass | 21/21 tests pass | none |
| Governance (proposal + vote + tally) | 32/32 tests pass | 32/32 tests pass | none |
| v2 format tests (`test_v2.py`) | n/a | 20/20 pass | — |
| Mac's address balance | 2,392 R0NI, inbound only | 2,392 R0NI, inbound only | none |

Governance tally on the fresh v2 run: proposal "v2 testnet: keep R- block
hashes?" — yes **1,998,740** / no **999,060**, total 2,997,800, quorum
10,000 met, winner yes, **passed**. (The v1 fresh run has no governance
phase; governance on v1 is covered by its 32/32 test suite, including the
whale tally 10,000 yes vs 1,000 no.)

### Live run on the committed v2 genesis (Mac's request)

- 3 nodes (ports 8031–8033) all started at height 1 on
  `R-0000f268031649e33f13d6868aab86cde180413818abc0c24cbcf766d156dd1f4f3c974284f9ffc0b5d43b7226304f6d21fd7fc82edd1c7f296dfe5255aecdb5`
  (nonce 2060) — same hash on all three nodes.
- `gov-propose` confirmed in 1.58 s
  (proposal `PROP-8f4206f7d82c3942046fb920fcfb6b1334da5763`, on-chain);
  `cert-mint` confirmed in 1.26 s
  (certificate `CERT-e5e0b91e6312bd4c722347a7455daeb7fd68634f`, on-chain).
- Final height **4, 6 transactions confirmed, all 3 nodes agree**,
  every block hash `R-0000…` (genesis + 3 mined):
  `R-0000dd1b…`, `R-0000acae…`, `R-0000f0fc…`.
- Node 3 restart sync: **0.30 s**.
- All 5 security probes rejected (table above); zero-balance vote rejected
  by the snapshot rule.

## 3. Speed — the R- prefix costs nothing measurable

| Metric | v1 | v2 | Difference |
|---|---|---|---|
| EvoHash-11 alone (10,000 hashes) | **13.80 µs/hash** (72,448 hashes/s) | same function, same number | 0 — the hash function is unchanged |
| `block_hash` (10,000 calls) | 19.54 µs/hash | 17.47 µs/hash | v2 10.6% *faster* this run; previous run was v1 17.41 vs v2 17.89 µs (+2.8%). The sign flips run to run — this is shared-CPU noise, not a real cost |
| `is_valid_hash_format` (v2 only) | — | 5.52 µs/check (10,000 checks) | one cheap string check per block |
| Mining, mean (20 blocks, difficulty 0000) | 56,372 attempts, **1.009 s/block** | 64,302 attempts, **1.152 s/block** | +14.1% attempts / +14.2% time — **not** a prefix cost (see below) |
| `validate_block` (200 validations) | 26.94 µs | 32.22 µs | +5.28 µs absolute; previous run was v1 31.53 vs v2 29.62 µs (v2 faster). Noise |
| Burst TPS (fresh live run) | 2.62 tx/s (30 txs, 11.46 s to confirm) | 4.34 tx/s (30 txs, 6.91 s to confirm) | v2 faster this run — but TPS here is dominated by Python PoW mining luck and shared-CPU noise (earlier runs ranged 1.84–9.18 tx/s); per-tx submit latency is the cleaner measure |
| Mean submit latency, phase 1 | 10.1 ms | 9.3 ms | −0.8 ms (v2 faster, within noise) |
| Mean submit latency, burst | 8.7 ms | 8.8 ms | +0.1 ms (identical) |
| Mean block time (fresh run) | 3.78 s (median 2 s) | 3.73 s (median 3 s) | −0.05 s (identical) |
| Node restart sync | 0.30 s | 0.30 s | 0.00 s |

**Why mining took 14% longer on v2 this time:** mining time is
(attempts × ~14 µs per hash), and attempts are luck — finding four leading
hex zeros is a random draw with expected mean 65,536 attempts (16⁴) and a
very wide spread (one run's 56k vs another's 64k is ordinary). The v2
headers hash different bytes (the `R-` in `previous_hash`), so v2 drew a
different random hand. The per-hash cost is proven identical above
(13.80 µs, same function), so the prefix adds **zero** work per hash.
The only real extra work v2 does is one `is_valid_hash_format` check per
block — 5.52 µs against ~1,000,000 µs of mining per block (0.0006%).

## Does adding the R- header mean redoing the Genesis block?

Yes — and that is exactly what v2 did, without touching v1. A block hash
covers its whole header, so changing the hash format changes the genesis
hash itself: v1's genesis (`00004777…`, nonce 333817) cannot be reused as
a v2 genesis. v2 therefore mined its own fresh genesis with the same
meaning ("circulating supply 100000 to start") in `R-` form
(`R-0000f268…`, nonce 2060, timestamp 1795209315). **The v1 genesis was
not re-mined or edited** — it is byte-identical in the repo, and v1 still
runs on it. The two networks are separate: v1 keeps its genesis, v2 has
its own.

## Limitations (applies to both)

- Prototype only, not audited, no real value, no live network: 3 nodes are
  separate processes on one VM, not separate machines; Docker was not
  available.
- Difficulty `0000` is very low — a laptop mines a block in ~1 s. More
  leading zeros would be harder (×16 per hex zero) but real security also
  needs many miners, which these testnets do not have.
- TPS and block times vary run to run on a shared-CPU VM; treat the live
  numbers as one matched pair, not a benchmark ceiling.
- The committed-genesis v2 run could not send regular transfers: the 3
  funded test wallets in that genesis have no stored private keys. It
  proves the chain runs, mines, and enforces its rules on that exact
  genesis; throughput numbers come from the fresh matched runs.
