#!/usr/bin/env python3
"""
Test the R0NI testnet v2 R- block-hash format.

v2 rule: every block hash is "R-" + 128 hex chars of EvoHash-11.
The "R" is a label, NOT part of the hash (hex has no R). The
difficulty rule applies to the hex part: it must start with "0000"
immediately after "R-". Plain hex hashes are rejected, as are
R- hashes whose hex part does not start with 0000 or does not
match a recomputation of EvoHash-11 over the header.

Runs offline in-process (single Node) plus a live 3-node roundtrip
over HTTP on ports 8041-8043, with all nodes agreeing on a chain
of R- hashes.

Writes testnet-v2/v2_test_results.json. Exits non-zero on any
failure. Prototype only — not audited, no real value.

Usage: /home/hatch/workspace/r0ni-v2-venv/bin/python testnet-v2/test_v2.py
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from node import Node, block_hash, block_hash_hex, is_valid_hash_format, HASH_PREFIX  # noqa: E402
from run_testnet import (  # noqa: E402
    http, wait_up, wait_mempool_empty, mine_genesis, make_wallet,
    sign_tx, VENV_PY, MAC_ADDR,
)

RESULTS = {"tests": [], "passed": 0, "failed": 0}


def check(name, ok, detail=""):
    RESULTS["tests"].append({"name": name, "passed": bool(ok), "detail": str(detail)})
    if ok:
        RESULTS["passed"] += 1
        print(f"PASS  {name}  {detail}")
    else:
        RESULTS["failed"] += 1
        print(f"FAIL  {name}  {detail}")


def mine_all(node):
    mined = 0
    while node.mempool:
        block = node.mine_one()
        if block is None:
            break
        ok, reason = node.add_block(block)
        assert ok, f"mined block rejected: {reason}"
        mined += 1
    return mined


def main():
    with tempfile.TemporaryDirectory() as d:
        wallets = [make_wallet(f"v2-{c}") for c in "ABC"]
        allocations = {w["address"]: 1_000_000 for w in wallets}
        genesis = mine_genesis(allocations)

        # --- 1. R- format -------------------------------------------
        h = genesis["hash"]
        check("R- format: genesis hash is 'R-' + 128 hex chars",
              h.startswith("R-") and len(h) == 130
              and all(c in "0123456789abcdef" for c in h[2:]), h)
        check("R- format: is_valid_hash_format accepts the genesis hash",
              is_valid_hash_format(h), h[:12] + "...")

        # --- 2. difficulty on the hex part ---------------------------
        check("difficulty: hex part after 'R-' starts with 0000",
              h[2:].startswith("0000"), h[:8])

        # --- 3. recompute matches ------------------------------------
        check("recompute: EvoHash-11 over the header (no prefix) matches hex part",
              block_hash_hex(genesis) == h[2:] and block_hash(genesis) == h,
              f"recomputed {block_hash_hex(genesis)[:12]}...")

        # --- 4. genesis anchors --------------------------------------
        check("genesis: previous_hash is 'R-' + 128 zeros",
              genesis["previous_hash"] == "R-" + "0" * 128, genesis["previous_hash"][:8])
        check("genesis: data names v2 / R- hashes / 100,000 to start",
              "v2" in genesis["data"] and "R-" in genesis["data"]
              and "100000" in genesis["data"], genesis["data"])
        check("txids unchanged: genesis txs carry no txid, plain txids stay hex",
              all("txid" not in t for t in genesis["transactions"])
              and HASH_PREFIX == "R-", "txids are EvoHash-11 hex; only block hashes carry R-")

        # --- offline node --------------------------------------------
        node = Node(f"{d}/node1", [], None, mine=False)
        node.chain = [genesis]
        node.save()
        check("offline node starts at height 1 (genesis only)", node.chain_height() == 1)

        # Mine one real block so later rejection tests have a valid block.
        tx = sign_tx(wallets[0], wallets[1]["address"], 100, 0)
        assert node.add_tx(tx)[0]
        mined = mine_all(node)
        assert mined == 1
        good = node.chain[1]
        check("mined block carries an R- hash meeting difficulty",
              good["hash"].startswith("R-0000"), good["hash"][:10])

        # Rejection checks run against a fresh node holding only the
        # genesis block, so the test block's index (1) is the expected
        # next index and the R- checks are what decide, not "bad index".
        node1 = Node(f"{d}/node1b", [], None, mine=False)
        node1.chain = [genesis]
        node1.save()

        # --- 5. plain-hex rejection ----------------------------------
        plain = json.loads(json.dumps(good))
        plain["hash"] = plain["hash"][2:]  # strip the R- prefix
        ok, reason = node1.validate_block(plain)
        check("reject: plain hex hash (no R- prefix)",
              not ok and "R-" in reason, reason)

        # --- 6. wrong-prefix rejection -------------------------------
        wrong = json.loads(json.dumps(good))
        wrong["hash"] = "X-" + wrong["hash"][2:]
        ok, reason = node1.validate_block(wrong)
        check("reject: wrong prefix 'X-' instead of 'R-'",
              not ok and "R-" in reason, reason)

        # --- 7. difficulty failure (recompute matches, 0000 missing) -
        # Find a nonce whose recomputed hash does NOT start with 0000,
        # then present that exact hash: recompute passes, difficulty fails.
        probe = json.loads(json.dumps(good))
        found = None
        for nonce in range(0, 100000):
            probe["nonce"] = nonce
            if not block_hash_hex(probe).startswith("0000"):
                found = (nonce, block_hash_hex(probe))
                break
        assert found is not None
        probe["hash"] = "R-" + found[1]
        ok, reason = node1.validate_block(probe)
        check("reject: R- hash whose hex part does not start with 0000",
              not ok and "difficulty" in reason, reason)

        # --- 8. tampered block rejection -----------------------------
        tampered = json.loads(json.dumps(good))
        tampered["transactions"][0]["amount"] += 1
        ok, reason = node1.validate_block(tampered)
        check("reject: tampered block (tx changed, hash no longer matches)",
              not ok and "recomputed" in reason, reason)

        # --- 9. chain linking via R- previous_hash -------------------
        tx2 = sign_tx(wallets[1], wallets[2]["address"], 50, 0)
        assert node.add_tx(tx2)[0]
        assert mine_all(node) == 1
        second = node.chain[2]
        check("chain linking: block 2 previous_hash is block 1's R- hash",
              second["previous_hash"] == good["hash"]
              and second["previous_hash"].startswith("R-"), second["previous_hash"][:10])
        bad_link = json.loads(json.dumps(second))
        bad_link["index"] = 3
        bad_link["previous_hash"] = good["hash"][2:]  # plain hex, not R-
        bad_link["hash"] = block_hash(bad_link)
        ok, reason = node.validate_block(bad_link)
        check("reject: block whose previous_hash is plain hex, not R-",
              not ok and "previous_hash" in reason, reason)

        # --- 10. live 3-node roundtrip (ports 8041-8043) -------------
        run_dir = Path(d) / "live"
        ports = [8041, 8042, 8043]
        live_genesis = mine_genesis(allocations)
        genesis_path = Path(d) / "genesis.json"
        genesis_path.write_text(json.dumps(live_genesis))
        procs = []
        try:
            for i, port in enumerate(ports):
                peers = ",".join(f"http://127.0.0.1:{p}" for p in ports if p != port)
                cmd = [VENV_PY, str(REPO_ROOT / "testnet-v2" / "node.py"),
                       "--port", str(port), "--data-dir", str(run_dir / f"node{i+1}"),
                       "--peers", peers, "--genesis", str(genesis_path)]
                if i == 0:
                    cmd.append("--mine")
                procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                              stderr=subprocess.STDOUT, text=True))
            for p in ports:
                assert wait_up(p), f"live node {p} did not come up"
            check("live: 3 v2 nodes up (ports 8041-8043)", True)
            time.sleep(1)
            for i, (w, to) in enumerate([(wallets[0], MAC_ADDR),
                                         (wallets[1], wallets[0]["address"]),
                                         (wallets[2], wallets[1]["address"])]):
                t = sign_tx(w, to, 100 + i * 10, 0)
                s, r = http("POST", 8041, "/tx", t)
                assert s == 200 and r.get("accepted"), f"live tx rejected: {r}"
            assert wait_mempool_empty(8041, timeout=60), "live mempool did not drain"
            chains = [http("GET", p, "/chain")[1] for p in ports]
            check("live: all 3 nodes agree on the same chain",
                  chains[0] == chains[1] == chains[2],
                  f"heights {[len(c) for c in chains]}")
            chain = chains[0]
            check("live: every block hash is R- + 128 hex, hex part starts 0000",
                  len(chain) >= 2
                  and all(is_valid_hash_format(b["hash"])
                          and b["hash"][2:].startswith("0000") for b in chain),
                  f"{len(chain)} blocks, tip {chain[-1]['hash'][:10]}...")
            check("live: every block links via its predecessor's R- hash",
                  all(chain[i]["previous_hash"] == chain[i - 1]["hash"]
                      for i in range(1, len(chain)))
                  and chain[0]["previous_hash"] == "R-" + "0" * 128,
                  f"genesis {chain[0]['hash'][:10]}...")
            s, status = http("GET", 8041, "/status")
            check("live: /status tip is the R- tip hash",
                  s == 200 and status.get("tip") == chain[-1]["hash"],
                  str(status.get("tip", ""))[:12])
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

    out = REPO_ROOT / "testnet-v2" / "v2_test_results.json"
    out.write_text(json.dumps({"testnet": "R0NI testnet v2 (R- block hashes)",
                               "passed": RESULTS["passed"], "failed": RESULTS["failed"],
                               "tests": RESULTS["tests"]}, indent=2))
    print(f"\n{RESULTS['passed']} passed, {RESULTS['failed']} failed — results in {out}")
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
