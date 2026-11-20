#!/usr/bin/env python3
"""
Run the R0NI multi-node testnet: 3 nodes (separate processes,
separate data dirs, localhost P2P), test transactions, performance
and security tests, analytics. Prototype only, no real value.

Honest limits:
- ONE Linux VM here, not multiple real VMs. Nodes are separate
  OS processes on 127.0.0.1 (ports 8001-8003). Docker is not
  available on this machine.
- Mac's address R0NI-ebeb98a5aeea016f49e6abf1c8b1e492317a102d
  receives inbound test transactions ONLY. We do NOT have his
  private key, never asked for it, and never sign from it.
  A transaction FROM Mac's address is recorded as
  "requires Mac to sign in his own wallet app" — not simulated.
- Test wallets are generated fresh per run into /tmp (never
  committed to the repo). Genesis test funds are test-only.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from roni_wallet import evo_hash_11, r0ni_address  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402

MAC_ADDR = "R0NI-ebeb98a5aeea016f49e6abf1c8b1e492317a102d"
VENV_PY = "/tmp/r0ni-testnet-venv/bin/python"
RUN_DIR = Path("/tmp/r0ni-testnet-run")
PORTS = [8001, 8002, 8003]
TEST_FUNDS = 1_000_000


def http(method, port, path, payload=None, timeout=10):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def wait_up(port, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s, _ = http("GET", port, "/status", timeout=3)
        if s == 200:
            return True
        time.sleep(0.5)
    return False


def wait_height(port, height, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s, st = http("GET", port, "/status", timeout=3)
        if s == 200 and st.get("height", 0) >= height:
            return time.time() - t0
        time.sleep(0.3)
    return None


def wait_mempool_empty(port, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s, st = http("GET", port, "/status", timeout=3)
        if s == 200 and st.get("mempool", 1) == 0 and st.get("height", 0) > 1:
            return True
        time.sleep(0.3)
    return False


def make_wallet(name):
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(serialization.Encoding.Raw,
                                  serialization.PrivateFormat.Raw,
                                  serialization.NoEncryption())
    pub_raw = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                             serialization.PublicFormat.Raw)
    return {"name": name, "priv": priv, "priv_hex": priv_raw.hex(),
            "pub_hex": pub_raw.hex(), "address": r0ni_address(pub_raw)}


def sign_tx(wallet, recipient, amount, nonce):
    msg = f"{wallet['address']}|{recipient}|{amount}|{nonce}"
    sig = wallet["priv"].sign(msg.encode()).hex()
    tx = {"sender": wallet["address"], "recipient": recipient, "amount": amount,
          "nonce": nonce, "signature": sig, "sender_pubkey_hex": wallet["pub_hex"]}
    tx["txid"] = evo_hash_11(msg.encode()).hex()
    return tx


def mine_genesis(allocations):
    txs = [{"type": "genesis", "recipient": a, "amount": amt} for a, amt in allocations.items()]
    block = {"index": 0, "timestamp": int(time.time()),
             "previous_hash": "0" * 128, "transactions": txs, "nonce": 0}
    header = lambda b: "|".join([str(b["index"]), str(b["timestamp"]), b["previous_hash"],
                                 json.dumps(b["transactions"], sort_keys=True), str(b["nonce"])])
    nonce = 0
    while True:
        block["nonce"] = nonce
        h = evo_hash_11(header(block).encode()).hex()
        if h.startswith("0000"):
            block["hash"] = h
            return block
        nonce += 1


def main():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    for d in ["node1", "node2", "node3"]:
        import shutil
        shutil.rmtree(RUN_DIR / d, ignore_errors=True)

    wallets = [make_wallet(f"test-{c}") for c in "ABC"]
    for w in wallets:
        print(f"test wallet {w['name']}: {w['address']}")
    print(f"Mac address (inbound only): {MAC_ADDR}")

    allocations = {w["address"]: TEST_FUNDS for w in wallets}
    genesis = mine_genesis(allocations)
    genesis_path = REPO / "testnet" / "genesis.json"
    genesis_path.write_text(json.dumps(genesis, indent=2))
    print(f"genesis mined: nonce={genesis['nonce']} hash={genesis['hash'][:20]}...")

    # Start 3 nodes. Node 1 mines; nodes 2-3 sync (single miner avoids
    # competing forks in this demo; sync + validation are still tested).
    procs = []
    for i, port in enumerate(PORTS):
        peers = ",".join(f"http://127.0.0.1:{p}" for p in PORTS if p != port)
        cmd = [VENV_PY, str(REPO / "testnet" / "node.py"),
               "--port", str(port), "--data-dir", str(RUN_DIR / f"node{i+1}"),
               "--peers", peers, "--genesis", str(genesis_path)]
        if i == 0:
            cmd.append("--mine")
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True))
    try:
        for p in PORTS:
            assert wait_up(p), f"node {p} did not come up"
        print("all 3 nodes up")
        # sync check: all nodes at height 1 (genesis)
        time.sleep(2)

        nonces = {w["address"]: 0 for w in wallets}
        results = {"submitted": [], "accepted": [], "rejected": []}

        def send(wallet, recipient, amount, port=8001):
            tx = sign_tx(wallet, recipient, amount, nonces[wallet["address"]])
            s, r = http("POST", port, "/tx", tx)
            if s == 200 and r.get("accepted"):
                nonces[wallet["address"]] += 1
                results["accepted"].append(tx["txid"])
                return tx, True, r
            results["rejected"].append({"txid": tx["txid"], "status": s, "reason": r})
            return tx, False, r

        # --- Phase 1: 20 transactions --------------------------------
        t0 = time.time()
        phase1 = []
        # 8 to Mac's address, from each test wallet in rotation
        for i in range(8):
            w = wallets[i % 3]
            amt = 100 + i * 50
            phase1.append((w, MAC_ADDR, amt))
        # 12 between test wallets
        for i in range(12):
            w = wallets[i % 3]
            to = wallets[(i + 1) % 3]["address"]
            phase1.append((w, to, 200 + i * 25))
        latencies = []
        for w, to, amt in phase1:
            s = time.time()
            tx, ok, r = send(w, to, amt)
            latencies.append(time.time() - s)
            assert ok, f"phase1 tx rejected: {r}"
        print(f"phase 1: 20 txs submitted, mean submit latency {sum(latencies)/len(latencies)*1000:.1f} ms")
        assert wait_mempool_empty(8001, timeout=90), "mempool did not drain"
        h0 = http("GET", 8001, "/status")[1]["height"]

        # --- Phase 2: TPS burst (30 txs) ------------------------------
        burst_t0 = time.time()
        burst_lat = []
        for i in range(30):
            w = wallets[i % 3]
            to = wallets[(i + 2) % 3]["address"] if i % 4 else MAC_ADDR
            s = time.time()
            tx, ok, r = send(w, to, 10 + i)
            burst_lat.append(time.time() - s)
            assert ok, f"burst tx rejected: {r}"
        burst_submit = time.time() - burst_t0
        assert wait_mempool_empty(8001, timeout=90), "burst mempool did not drain"
        burst_done = time.time() - burst_t0
        h1 = http("GET", 8001, "/status")[1]["height"]
        confirmed_burst = 30
        tps = confirmed_burst / burst_done
        print(f"burst: 30 txs, submit {burst_submit:.2f}s, confirm {burst_done:.2f}s, TPS {tps:.2f}")

        # --- Restart / sync test --------------------------------------
        procs[2].terminate()
        procs[2].wait(timeout=10)
        print("node 3 stopped")
        # mine one more block while node 3 is down
        tx, ok, r = send(wallets[0], wallets[1]["address"], 777)
        assert ok, r
        assert wait_mempool_empty(8001, timeout=60)
        height_before = http("GET", 8001, "/status")[1]["height"]
        t_restart = time.time()
        procs[2] = subprocess.Popen(
            [VENV_PY, str(REPO / "testnet" / "node.py"), "--port", "8003",
             "--data-dir", str(RUN_DIR / "node3"),
             "--peers", "http://127.0.0.1:8001,http://127.0.0.1:8002",
             "--genesis", str(genesis_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        # Measure sync from the moment the process is launched, not
        # from after it is already up (the old code measured 0.00s
        # because the node had already synced while wait_up ran).
        sync_deadline = time.time() + 60
        sync_time = None
        while time.time() < sync_deadline:
            s, st = http("GET", 8003, "/status", timeout=3)
            if s == 200 and st.get("height", 0) >= height_before:
                sync_time = time.time() - t_restart
                break
            time.sleep(0.3)
        assert sync_time is not None, "node 3 did not sync in 60s"
        print(f"node 3 restarted, sync to height {height_before} in {sync_time:.2f}s")

        # --- Security tests -------------------------------------------
        sec = {}
        # (a) double-spend: same nonce, same funds, two recipients
        w = wallets[1]
        nonce = nonces[w["address"]]
        tx_a = sign_tx(w, wallets[0]["address"], 500, nonce)
        s, r = http("POST", 8001, "/tx", tx_a)
        assert s == 200, r
        nonces[w["address"]] += 1
        tx_b = sign_tx(w, wallets[2]["address"], 500, nonce)  # same nonce, same funds
        s, r = http("POST", 8001, "/tx", tx_b)
        sec["double_spend_same_nonce"] = {"accepted": s == 200, "status": s, "reason": r}
        print("double-spend (same nonce):", sec["double_spend_same_nonce"])
        # also: second tx with next nonce spending more than remaining balance
        bal = http("GET", 8001, f"/balance?address={w['address']}")[1]["balance"]
        tx_c = sign_tx(w, wallets[0]["address"], bal + 1_000_000, nonces[w["address"]])
        s, r = http("POST", 8001, "/tx", tx_c)
        sec["overspend"] = {"accepted": s == 200, "status": s, "reason": r}
        print("overspend:", sec["overspend"])
        # (b) forged signature: sign with a different key, claim sender is w
        forger = make_wallet("forger")
        msg = f"{w['address']}|{wallets[0]['address']}|100|{nonces[w['address']]}"
        forged = {"sender": w["address"], "recipient": wallets[0]["address"], "amount": 100,
                  "nonce": nonces[w["address"]],
                  "signature": forger["priv"].sign(msg.encode()).hex(),
                  "sender_pubkey_hex": w["pub_hex"]}
        forged["txid"] = evo_hash_11(msg.encode()).hex()
        s, r = http("POST", 8001, "/tx", forged)
        sec["forged_signature"] = {"accepted": s == 200, "status": s, "reason": r}
        print("forged signature:", sec["forged_signature"])
        # tampered amount after signing
        tampered = sign_tx(w, wallets[0]["address"], 100, nonces[w["address"]])
        tampered["amount"] = 99999  # change after signing
        s, r = http("POST", 8001, "/tx", tampered)
        sec["tampered_amount"] = {"accepted": s == 200, "status": s, "reason": r}
        print("tampered amount:", sec["tampered_amount"])
        # (c) tampered block: take a confirmed block, alter a tx, submit it
        chain = http("GET", 8001, "/chain")[1]
        bad_block = json.loads(json.dumps(chain[1]))
        if bad_block["transactions"] and bad_block["transactions"][0].get("type") != "genesis":
            bad_block["transactions"][0]["amount"] += 1
        elif len(chain) > 2:
            bad_block = json.loads(json.dumps(chain[2]))
            bad_block["transactions"][0]["amount"] += 1
        # re-index it as the next block so index/prev-hash pass, hash must fail
        bad_block["index"] = len(chain)
        bad_block["previous_hash"] = chain[-1]["hash"]
        s, r = http("POST", 8001, "/block", bad_block)
        sec["tampered_block"] = {"accepted": s == 200, "status": s, "reason": r}
        print("tampered block:", sec["tampered_block"])
        # wait for the legitimate tx_a to confirm, then gather chain
        assert wait_mempool_empty(8001, timeout=60)
        chain = http("GET", 8001, "/chain")[1]
        chain2 = http("GET", 8002, "/chain")[1]
        chain3 = http("GET", 8003, "/chain")[1]
        assert chain == chain2 == chain3, "nodes diverged!"

        # --- analytics -------------------------------------------------
        balances = {}
        for addr in [MAC_ADDR] + [w["address"] for w in wallets]:
            balances[addr] = http("GET", 8001, f"/balance?address={addr}")[1]["balance"]
        block_times = [chain[i]["timestamp"] - chain[i - 1]["timestamp"]
                       for i in range(1, len(chain))]
        block_times_sorted = sorted(block_times)
        median_bt = block_times_sorted[len(block_times_sorted) // 2] if block_times_sorted else 0
        mean_bt = sum(block_times) / len(block_times) if block_times else 0
        confirmed = sum(len(b["transactions"]) for b in chain
                        if b["index"] > 0)
        # confirmed non-genesis txs
        confirmed = sum(1 for b in chain for t in b["transactions"] if t.get("type") != "genesis")
        analytics = {
            "testnet": "R0NI testnet (prototype, simulated)",
            "simulation": "3 nodes as separate OS processes on ONE Linux VM (127.0.0.1:8001-8003), separate data dirs, localhost HTTP P2P. NOT multiple real VMs. Docker not available.",
            "miner": "node 1 only (single miner avoids competing forks in this demo)",
            "difficulty": "0000 (EvoHash-11)",
            "nodes": 3,
            "topology": "full mesh, ports 8001/8002/8003, each peered to the other two",
            "genesis_test_funds_per_test_wallet": TEST_FUNDS,
            "mac_address": MAC_ADDR,
            "mac_address_balance": balances[MAC_ADDR],
            "mac_address_note": "inbound only — no transaction was ever signed from Mac's address; we do not have his private key. A transaction FROM Mac's address requires Mac to sign in his own wallet app.",
            "test_wallets": [{"name": w["name"], "address": w["address"],
                              "balance": balances[w["address"]]} for w in wallets],
            "transactions_submitted_phase1": 20,
            "transactions_submitted_burst": 30,
            "transactions_confirmed_total": confirmed,
            "transactions_rejected_security_tests": sum(1 for v in sec.values() if not v["accepted"]),
            "mean_submit_latency_ms_phase1": round(sum(latencies) / len(latencies) * 1000, 1),
            "mean_submit_latency_ms_burst": round(sum(burst_lat) / len(burst_lat) * 1000, 1),
            "burst_tps_confirmed": round(tps, 2),
            "burst_submit_seconds": round(burst_submit, 2),
            "burst_confirm_seconds": round(burst_done, 2),
            "blocks": len(chain),
            "mean_block_time_seconds": round(mean_bt, 2),
            "median_block_time_seconds": median_bt,
            "node_restart_sync_seconds": round(sync_time, 2) if sync_time else None,
            "nodes_agree_on_chain": chain == chain2 == chain3,
            "security_tests": sec,
            "machine": "1 Linux VM, 4 vCPU (AMD EPYC 9D25), ~8 GB RAM, shared CPU",
            "from_mac_address": "NOT TESTED — requires Mac to sign in his own wallet app",
            "outbound_genesis_spend": "requires Mac to sign in his own wallet app (standalone wallet-app.html). The testnet NEVER holds or uses the genesis private key. A signed transaction he creates in-app can be submitted with testnet/accept_signed_tx.py, which verifies the signature and lets the node re-verify it before acceptance. No such signed transaction was provided in this run.",
            "recommended_path": "Mac makes ONE signed transfer in-app from genesis to a fresh disposable test wallet (small amount). The testnet then uses THAT disposable test wallet's keypair (test-only, generated by the testnet) for further spending tests — never the genesis key.",
        }
        (REPO / "testnet" / "analytics.json").write_text(json.dumps(analytics, indent=2))
        md = f"""# R0NI Testnet — Analytics

Prototype testnet, simulated on **one Linux VM** (3 nodes as separate
OS processes on 127.0.0.1:8001–8003, separate data dirs, localhost
HTTP P2P). **Not multiple real VMs** — Docker was not available.
No real value, not audited.

## Results
- Nodes: 3 (full mesh), miner: node 1 only
- Blocks: {len(chain)} (genesis + {len(chain)-1} mined), difficulty `0000`, EvoHash-11
- Transactions confirmed: {confirmed} (20 phase 1 + 30 burst + 1 restart + 1 double-spend-test tx)
- Burst TPS: **{tps:.2f} tx/s** (30 txs, {burst_done:.2f}s to confirm)
- Mean submit latency: phase 1 {sum(latencies)/len(latencies)*1000:.1f} ms, burst {sum(burst_lat)/len(burst_lat)*1000:.1f} ms
- Mean block time: {mean_bt:.2f}s, median: {median_bt}s
- Node restart sync: {sync_time:.2f}s to catch up to height {height_before}
- All 3 nodes agree on the same chain: {chain == chain2 == chain3}

## Balances after the run
- Mac's address `{MAC_ADDR}`: **{balances[MAC_ADDR]} R0NI** (inbound only — nothing was ever signed from it; we do not have his private key)
"""
        for w in wallets:
            md += f"- {w['name']} `{w['address']}`: {balances[w['address']]} R0NI\n"
        md += """
## Security tests (all must be rejected)
"""
        for name, v in sec.items():
            md += f"- {name}: {'ACCEPTED — FAIL' if v['accepted'] else 'REJECTED'} ({v['status']}: {v.get('reason')})\n"
        md += """
## From Mac's address (outbound genesis spend)
Not tested in this run — that would require Mac to sign in his own
wallet app. No signature from Mac's address was simulated or forged,
and the genesis private key was never in the testnet.

How it works if Mac wants it: he signs a transfer in his own wallet
app (standalone wallet-app.html — his key never leaves his device),
gives us the signed transaction JSON, and
`testnet/accept_signed_tx.py` verifies the signature and submits it
to a node, which re-verifies it before acceptance.

Recommended path: Mac makes ONE signed transfer in-app from genesis
to a fresh disposable test wallet (small amount). The testnet then
uses THAT disposable test wallet's keypair (test-only, generated by
the testnet) for further spending tests — never the genesis key.
"""
        (REPO / "testnet" / "ANALYTICS.md").write_text(md)
        print(md)
        print("analytics written to testnet/analytics.json and testnet/ANALYTICS.md")
        return analytics
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


if __name__ == "__main__":
    main()
