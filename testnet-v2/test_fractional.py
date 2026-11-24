#!/usr/bin/env python3
"""
Test R0NI divisibility — milli-R0NI amounts (2026-11-23).

Chosen by Mac 2026-11-23: max supply ceiling 10,000,000,000 R0NI
(10B, recorded decision only — not on-chain until the proposal is
filed and passes) and smallest denomination 0.001 R0NI.

Canonical stored unit: integer milli-R0NI (1 R0NI = 1000 milli).
Human amounts are parsed once at the boundary by parse_amount():
an int is a legacy whole-R0NI amount, a str/float/Decimal may
carry up to 3 decimal places. Anything below 0.001 R0NI, or with
more than 3 decimal places, is rejected. Voting power is in
milli-units (1 milli = 1 vote-unit), so a 0.001 R0NI holding
still votes; default quorum 10,000 R0NI = 10,000,000 milli-units.

Runs offline (wallet + ledger + registry + single Node) plus a
live single-node roundtrip over HTTP (port 8131): a 0.001 R0NI
transfer with a text payload is submitted, mined, and read back
from the chain with its amount intact.

Writes testnet-v2/fractional_test_results.json. Exits non-zero on any
failure. Prototype only — not audited, no real value. Fresh test
wallets only; Mac's genesis key is never involved.

Usage: /tmp/r0ni-venv/bin/python testnet-v2/test_fractional.py
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

from roni_wallet import (  # noqa: E402
    GENESIS_BLOCK_HASH, GENESIS_SUPPLY_MILLI, MAX_SUPPLY_MILLI,
    allocate_genesis, create_wallet, format_amount, load_ledger,
    ledger_balance, make_cert_mint_tx, make_certificate,
    make_media_payload, make_proposal, make_testnet_tx,
    make_text_payload, new_ledger, parse_amount, record_transfer,
    save_ledger, tally_proposal, testnet_tx_message, verify_signature,
)
from node import Node  # noqa: E402
from run_testnet import (  # noqa: E402
    http, wait_up, wait_mempool_empty, mine_genesis, VENV_PY,
)

RESULTS = {"tests": [], "passed": 0, "failed": 0,
           "rules": {
               "milli_per_R0NI": 1000,
               "smallest_unit_R0NI": "0.001",
               "max_supply_R0NI": 10_000_000_000,
               "max_supply_milli": 10_000_000_000_000,
               "genesis_supply_R0NI": 100000,
               "genesis_supply_milli": 100_000_000,
               "default_quorum_R0NI": 10000,
               "default_quorum_milli": 10_000_000,
               "voting_power": "1 milli-R0NI = 1 vote-unit",
           }}


def check(name, ok, detail=""):
    RESULTS["tests"].append({"name": name, "passed": bool(ok), "detail": str(detail)})
    if ok:
        RESULTS["passed"] += 1
        print(f"PASS  {name}  {detail}")
    else:
        RESULTS["failed"] += 1
        print(f"FAIL  {name}  {detail}")


def expect_reject(name, fn, needle=""):
    try:
        fn()
    except (ValueError, SystemExit) as e:
        check(name, not needle or needle in str(e), str(e)[:120])
        return
    check(name, False, "was accepted, should have been rejected")


def main():
    pw = "test-password"
    with tempfile.TemporaryDirectory() as d:
        # --- parse_amount / format_amount --------------------------
        cases = [("0.001", 1), ("1.5", 1500), ("1.500", 1500),
                 ("100000", 100_000_000), (1, 1000), (25000, 25_000_000),
                 (0.001, 1), (1.5, 1500), ("0.002", 2)]
        ok = all(parse_amount(v) == want for v, want in cases)
        check("parse_amount: decimals + legacy whole ints -> milli",
              ok, f"{len(cases)} cases, e.g. '0.001'->1, '1.5'->1500, 25000->25,000,000")
        for bad in ("0.0005", "0.0001", "1.0005", "0", "-1", "", "abc",
                    0.0005, -0.001, True):
            expect_reject(f"parse_amount rejects {bad!r}", lambda b=bad: parse_amount(b))
        expect_reject("parse_amount rejects above the 10B ceiling",
                      lambda: parse_amount("10000000001"), "max supply")
        fmt = [(1, "0.001"), (1500, "1.500"), (100_000_000, "100000.000"),
               (0, "0.000"), (2, "0.002"), (10_000_000, "10000.000")]
        check("format_amount: milli -> decimal R0NI, exactly 3 places",
              all(format_amount(m) == want for m, want in fmt),
              "1->0.001, 1500->1.500, 100,000,000->100000.000")
        check("parse/format roundtrip is exact",
              all(parse_amount(format_amount(m)) == m
                  for m in (1, 2, 999, 1000, 1500, 10_000_000, 100_000_000)),
              "7 milli values survive format -> parse unchanged")

        # --- ledger: genesis + fractional transfers ----------------
        a_path, b_path, c_path = (f"{d}/{n}.json" for n in ("a", "b", "c"))
        wa = create_wallet(pw, a_path)
        wb = create_wallet(pw, b_path)
        wc = create_wallet(pw, c_path)
        ledger_path = f"{d}/ledger.json"
        save_ledger(ledger_path, new_ledger())
        alloc = allocate_genesis(ledger_path, a_path)
        check("genesis 100,000 R0NI still exact after divisibility",
              alloc["amount"] == GENESIS_SUPPLY_MILLI == 100_000_000
              and alloc["amount_R0NI"] == "100000.000"
              and ledger_balance(load_ledger(ledger_path), wa["address"]) == 100_000_000,
              f"allocated {alloc['amount_R0NI']} R0NI ({alloc['amount']} milli)")
        record_transfer(ledger_path, a_path, pw, wb["address"], "0.001")
        record_transfer(ledger_path, a_path, pw, wb["address"], "1.5")
        record_transfer(ledger_path, a_path, pw, wc["address"], "0.001")
        led = load_ledger(ledger_path)
        check("ledger: transfer 0.001 + 1.5 exact in milli-units",
              ledger_balance(led, wb["address"]) == 1501
              and ledger_balance(led, wc["address"]) == 1
              and ledger_balance(led, wa["address"]) == 100_000_000 - 1502,
              f"b={ledger_balance(led, wb['address'])} c={ledger_balance(led, wc['address'])} "
              f"a={ledger_balance(led, wa['address'])} milli")
        check("ledger: balances sum to exactly the genesis supply",
              sum(ledger_balance(led, x["address"]) for x in (wa, wb, wc)) == 100_000_000,
              "100,000,000 milli, no dust lost to rounding")
        expect_reject("ledger: transfer 0.0005 rejected",
                      lambda: record_transfer(ledger_path, a_path, pw, wb["address"], "0.0005"),
                      "3 decimal places")
        expect_reject("ledger: transfer 0.0001 rejected",
                      lambda: record_transfer(ledger_path, a_path, pw, wb["address"], "0.0001"),
                      "3 decimal places")

        # --- legacy ledger migration -------------------------------
        legacy_path = f"{d}/legacy.json"
        Path(legacy_path).write_text(json.dumps({
            "chain": "Mac 'N Cheese Chain", "ticker": "R0NI",
            "genesis_block_hash": GENESIS_BLOCK_HASH,
            "genesis_supply": 100000,
            "allocations": [{"address": wa["address"], "amount": 100000,
                             "source": "genesis"}],
            "transfers": [{"from": wa["address"], "to": wb["address"],
                           "amount": 25000, "message": "legacy",
                           "signature_hex": "00",
                           "public_key_hex": wa["public_key_hex"]}],
        }) + "\n", encoding="utf-8")
        leg = load_ledger(legacy_path)
        check("legacy ledger migrates whole R0NI x1000 on load",
              leg["amount_unit"] == "milli-R0NI"
              and ledger_balance(leg, wa["address"]) == 75_000_000
              and ledger_balance(leg, wb["address"]) == 25_000_000,
              "100,000 -> 100,000,000 milli; 25,000 -> 25,000,000 milli")
        save_ledger(legacy_path, leg)
        leg2 = load_ledger(legacy_path)
        check("legacy migration is idempotent (no double x1000)",
              ledger_balance(leg2, wa["address"]) == 75_000_000
              and ledger_balance(leg2, wb["address"]) == 25_000_000,
              "reload after save keeps the same balances")

        # --- fractional testnet transactions ------------------------
        tx1 = make_testnet_tx(a_path, pw, wb["address"], "0.001", 0)
        check("make_testnet_tx: 0.001 R0NI -> amount 1 milli, signs + verifies",
              tx1["amount"] == 1 and verify_signature(
                  tx1["sender_pubkey_hex"],
                  testnet_tx_message(tx1["sender"], tx1["recipient"], 1, 0, None),
                  tx1["signature"]),
              f"txid {tx1['txid'][:16]}...")
        tx15 = make_testnet_tx(a_path, pw, wb["address"], "1.5", 1)
        check("make_testnet_tx: 1.5 R0NI -> amount 1500 milli",
              tx15["amount"] == 1500, f"amount={tx15['amount']}")
        expect_reject("make_testnet_tx rejects 0.0001 R0NI",
                      lambda: make_testnet_tx(a_path, pw, wb["address"], "0.0001", 2),
                      "3 decimal places")
        expect_reject("make_testnet_tx rejects 0 R0NI",
                      lambda: make_testnet_tx(a_path, pw, wb["address"], 0, 2))

        # --- governance: fractional voting power --------------------
        prop = make_proposal("Tiny vote", "Does 0.001 R0NI vote?",
                             ["yes", "no"], wa["address"], wa["public_key_hex"],
                             created_at=1795132723, voting_start_block=1,
                             voting_end_block=10, quorum=1)
        check("governance: default quorum is 10,000 R0NI = 10,000,000 milli",
              make_proposal("Q", "q?", ["yes", "no"], wa["address"],
                            wa["public_key_hex"], created_at=1795132723,
                            voting_start_block=1, voting_end_block=10)["quorum"] == 10_000_000,
              "DEFAULT_QUORUM = 10,000,000 milli-units")
        tiny = tally_proposal(prop, [{"sender": wb["address"], "option": "yes"}],
                              {wb["address"]: 1})
        check("governance: 0.001 R0NI holder votes with 1 milli-unit",
              tiny["per_option"] == {"yes": 1, "no": 0}
              and tiny["total_voting_power"] == 1 and tiny["quorum_met"]
              and tiny["passed"], f"per_option={tiny['per_option']}")
        frac_tally = tally_proposal(
            make_proposal("Frac", "f?", ["yes", "no"], wa["address"],
                          wa["public_key_hex"], created_at=1795132723,
                          voting_start_block=1, voting_end_block=10, quorum=1),
            [{"sender": wa["address"], "option": "yes"},
             {"sender": wb["address"], "option": "no"}],
            {wa["address"]: 10_000_001, wb["address"]: 500})
        check("governance: fractional tally exact in milli-units",
              frac_tally["per_option"] == {"yes": 10_000_001, "no": 500}
              and frac_tally["total_voting_power"] == 10_000_501
              and frac_tally["total_voting_power_R0NI"] == "10000.501",
              "yes 10000.001 R0NI vs no 0.500 R0NI")

        # --- certificates still move 0 ------------------------------
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
               b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
               b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
               b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
        import hashlib
        png_hash = hashlib.sha256(png).hexdigest()
        payload = make_media_payload(png, "image", "image/png", "t.png")
        cert = make_certificate(png_hash, wa["address"], wa["public_key_hex"],
                                wb["address"], "fractional-era cert",
                                "image", "image/png", "t.png")
        mint = make_cert_mint_tx(a_path, pw, wb["address"], cert, 0, payload)
        check("certificates: cert-mint still moves 0 R0NI",
              mint["type"] == "cert-mint" and mint["amount"] == 0,
              f"cert {cert['cert_id'][:14]}...")

        # --- offline node: fractional transfers + rejections --------
        genesis = mine_genesis({wa["address"]: 10000, wb["address"]: 100})
        node = Node(f"{d}/node1", [], None, mine=False)
        node.chain = [genesis]
        node.save()
        check("node: genesis balances are milli (10,000 / 100 R0NI)",
              node.balance(wa["address"]) == 10_000_000
              and node.balance(wb["address"]) == 100_000,
              f"a={node.balance(wa['address'])} b={node.balance(wb['address'])} milli")

        def mine_all(n):
            while n.mempool:
                block = n.mine_one()
                assert block is not None
                ok, reason = n.add_block(block)
                assert ok, f"mined block rejected: {reason}"

        ftx = make_testnet_tx(a_path, pw, wb["address"], "0.001", 0)
        ok, reason = node.add_tx(ftx)
        check("node: 0.001 R0NI transfer accepted into mempool", ok, reason)
        mine_all(node)
        check("node: 0.001 R0NI transfer mined, balances exact",
              node.balance(wb["address"]) == 100_001
              and node.balance(wa["address"]) == 10_000_000 - 1,
              f"b={node.balance(wb['address'])} a={node.balance(wa['address'])} milli")
        ftx2 = make_testnet_tx(a_path, pw, wb["address"], "1.5", 1)
        assert node.add_tx(ftx2)[0]
        mine_all(node)
        check("node: 1.5 R0NI transfer mined, balances exact",
              node.balance(wb["address"]) == 101_501
              and node.balance(wa["address"]) == 10_000_000 - 1501,
              "b=101,501 milli (101.501 R0NI)")
        # Raw tx with a float amount is not an integer milli amount.
        from roni_wallet import _load_private
        _, priv_a = _load_private(pw, a_path)
        float_tx = {"sender": wa["address"], "recipient": wb["address"],
                    "amount": 1.5, "nonce": 2,
                    "signature": priv_a.sign(
                        testnet_tx_message(wa["address"], wb["address"], 1.5, 2, None)
                        .encode("utf-8")).hex(),
                    "sender_pubkey_hex": wa["public_key_hex"]}
        from roni_wallet import testnet_tx_id
        float_tx["txid"] = testnet_tx_id(wa["address"], wb["address"], 1.5, 2, None)
        ok, reason = node.add_tx(float_tx)
        check("node: raw tx with float amount 1.5 rejected (must be int milli)",
              not ok and "integer" in reason, reason)
        # A payment of 0 milli, hand-built and signed, is rejected.
        zero = {"sender": wa["address"], "recipient": wb["address"],
                "amount": 0, "nonce": 2,
                "signature": priv_a.sign(
                    testnet_tx_message(wa["address"], wb["address"], 0, 2, None)
                    .encode("utf-8")).hex(),
                "sender_pubkey_hex": wa["public_key_hex"]}
        zero["txid"] = testnet_tx_id(wa["address"], wb["address"], 0, 2, None)
        ok, reason = node.add_tx(zero)
        check("node: payment of 0 milli rejected", not ok and "positive" in reason, reason)
        huge = {"sender": wa["address"], "recipient": wb["address"],
                "amount": MAX_SUPPLY_MILLI + 1, "nonce": 2,
                "signature": priv_a.sign(
                    testnet_tx_message(wa["address"], wb["address"],
                                       MAX_SUPPLY_MILLI + 1, 2, None)
                    .encode("utf-8")).hex(),
                "sender_pubkey_hex": wa["public_key_hex"]}
        huge["txid"] = testnet_tx_id(wa["address"], wb["address"],
                                     MAX_SUPPLY_MILLI + 1, 2, None)
        ok, reason = node.add_tx(huge)
        check("node: payment above the 10B ceiling rejected",
              not ok and "max supply" in reason, reason)
        # Cert-mint (amount 0) still accepted on the node. The mint
        # is rebuilt with the sender's current nonce (2: two
        # fractional transfers already confirmed from wa).
        mint2 = make_cert_mint_tx(a_path, pw, wb["address"], cert, 2, payload)
        ok, reason = node.add_tx(mint2)
        check("node: cert-mint (amount 0) accepted with fractional balances live",
              ok, reason)

        # --- legacy testnet genesis migrates on node load -----------
        legacy_genesis = json.loads(json.dumps(genesis))
        for t in legacy_genesis["transactions"]:
            t["amount"] = t["amount"] // 1000  # back to whole R0NI
        legacy_genesis.pop("amount_unit", None)
        # NOTE: the stored hash no longer matches a recomputation
        # over the downgraded txs — the node never re-hashes the
        # genesis block (later blocks only link to its stored hash),
        # so this is a faithful legacy-shape fixture.
        legacy_path = Path(d) / "legacy-genesis.json"
        legacy_path.write_text(json.dumps(legacy_genesis))
        node2 = Node(f"{d}/node2", [], str(legacy_path), mine=False)
        check("node: legacy genesis (whole R0NI) migrates x1000 on load",
              node2.balance(wa["address"]) == 10_000_000
              and node2.balance(wb["address"]) == 100_000
              and node2.chain[0].get("amount_unit") == "milli-R0NI",
              f"a={node2.balance(wa['address'])} milli after load")
        node2b = Node(f"{d}/node2", [], None, mine=False)
        check("node: reload from saved chain does not double-migrate",
              node2b.balance(wa["address"]) == 10_000_000
              and node2b.balance(wb["address"]) == 100_000,
              "same balances after restart")

        # --- live single node: fractional tx + payload over HTTP ----
        run_dir = Path(d) / "live"
        run_dir.mkdir(parents=True, exist_ok=True)
        live_genesis = mine_genesis({wa["address"]: 10000})
        live_genesis_path = run_dir / "genesis.json"
        live_genesis_path.write_text(json.dumps(live_genesis))
        proc = subprocess.Popen(
            [VENV_PY, str(REPO_ROOT / "testnet-v2" / "node.py"),
             "--port", "8131", "--data-dir", str(run_dir / "node1"),
             "--peers", "", "--genesis", str(live_genesis_path), "--mine"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            assert wait_up(8131), "live node 8131 did not come up"
            check("live: single node up (port 8131)", True)
            text = make_text_payload("hello, fractional chain — 0.001 R0NI")
            live_tx = make_testnet_tx(a_path, pw, wb["address"], "0.001", 0, text)
            s, r = http("POST", 8131, "/tx", live_tx)
            check("live: 0.001 R0NI payload tx accepted via HTTP",
                  s == 200 and r.get("accepted"), str(r))
            assert wait_mempool_empty(8131, timeout=60), "live mempool did not drain"
            s, chain = http("GET", 8131, "/chain")
            onchain = [t for b in chain for t in b["transactions"]
                       if t.get("txid") == live_tx["txid"]]
            check("live: 0.001 R0NI tx mined with amount 1 milli + payload intact",
                  s == 200 and len(onchain) == 1 and onchain[0]["amount"] == 1
                  and onchain[0]["data"]["kind"] == "text",
                  f"amount on-chain={onchain[0]['amount'] if onchain else None}")
            s, bal = http("GET", 8131, f"/balance?address={wb['address']}")
            check("live: /balance reports milli + formatted R0NI",
                  s == 200 and bal.get("balance") == 1
                  and bal.get("balance_R0NI") == "0.001", str(bal))
            s, r = http("POST", 8131, "/tx", float_tx)
            check("live: raw float-amount tx rejected via HTTP",
                  s == 400 and "integer" in str(r.get("reason", "")), str(r))
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    out = REPO_ROOT / "testnet-v2" / "fractional_test_results.json"
    out.write_text(json.dumps(RESULTS, indent=2) + "\n")
    print(f"\n{RESULTS['passed']} passed, {RESULTS['failed']} failed — wrote {out}")
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
