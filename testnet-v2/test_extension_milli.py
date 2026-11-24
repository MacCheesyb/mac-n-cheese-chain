#!/usr/bin/env python3
"""
Test the extension (v0.5) + accept_signed_tx milli-R0NI match.

The wallet extension and accept_signed_tx must match the new
milli-R0NI unit (commit e308fee): amounts are integer milli-R0NI
(1 R0NI = 1000 milli, smallest unit 0.001 R0NI) and a signed tx
carries "amount_unit": "milli-R0NI". A tx signed in-app today
without that marker would be read by the node as milli — 1000x
smaller than intended — so accept_signed_tx REJECTS pre-milli
txs instead of silently converting them.

Proves, end to end:
  * the extension's JS amount module (extension/amounts.js)
    matches roni_wallet.py: parse/format, rejections, legacy
    ledger migration, tx message + txid vectors (Node harness
    extension/test_amounts.js, run from here),
  * an extension-style signed tx for 1.500 R0NI is accepted as
    1500 milli — including one REALLY signed by the extension's
    code path (WebCrypto Ed25519 in Node), verified by Python
    and confirmed on a live node,
  * a 0.001 R0NI tx is accepted as 1 milli,
  * a legacy whole-R0NI signed tx (amount 100, no marker) is
    REJECTED by accept_signed_tx with "pre-milli" — while the
    SAME numeric amount 100 WITH the marker is accepted as
    0.100 R0NI, proving the marker (not the number) is the
    discriminator, and a float amount is rejected too.

Runs the Node harness plus a live single-node roundtrip over
HTTP (port 8123). Writes testnet-v2/extension_milli_test_results.json.
Exits non-zero on any failure. Prototype only — not audited, no
real value. Fresh test wallets only; Mac's genesis key is never
involved.

Usage: /tmp/r0ni-venv/bin/python testnet-v2/test_extension_milli.py
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
    _load_private, create_wallet, make_testnet_tx, testnet_tx_id,
    testnet_tx_message, verify_signature,
)
from accept_signed_tx import verify_signed_tx  # noqa: E402
from run_testnet import http, wait_up, wait_mempool_empty, mine_genesis, VENV_PY  # noqa: E402

RESULTS = {"tests": [], "passed": 0, "failed": 0,
           "rules": {
               "milli_per_R0NI": 1000,
               "smallest_unit_R0NI": "0.001",
               "marker": "amount_unit == 'milli-R0NI'",
               "pre_milli_policy": "REJECT, never silently convert",
           }}


def check(name, ok, detail=""):
    RESULTS["tests"].append({"name": name, "passed": bool(ok), "detail": str(detail)})
    if ok:
        RESULTS["passed"] += 1
        print(f"PASS  {name}  {detail}")
    else:
        RESULTS["failed"] += 1
        print(f"FAIL  {name}  {detail}")


def main():
    pw = "test-password"
    with tempfile.TemporaryDirectory() as d:
        # --- 1. the extension's JS amount module ------------------
        js_tx_path = Path(d) / "extension-signed-tx.json"
        r = subprocess.run(["node", str(REPO_ROOT / "extension" / "test_amounts.js"),
                            str(js_tx_path)], capture_output=True, text=True)
        check("extension JS harness: 31 checks pass (parse/format, "
              "migration, txid vectors, WebCrypto sign)",
              r.returncode == 0 and "31 passed, 0 failed" in r.stdout,
              (r.stdout.strip().splitlines() or [""])[-1] if r.returncode == 0
              else (r.stdout + r.stderr)[-500:])
        js_tx = json.loads(js_tx_path.read_text())
        check("extension-style tx from Node: amount 1500 milli + marker",
              js_tx["amount"] == 1500 and js_tx["amount_unit"] == "milli-R0NI",
              f"amount={js_tx['amount']} unit={js_tx.get('amount_unit')}")
        check("extension-style tx: Python verifies its WebCrypto signature",
              verify_signature(js_tx["sender_pubkey_hex"],
                               testnet_tx_message(js_tx["sender"], js_tx["recipient"],
                                                  1500, 0, None),
                               js_tx["signature"]),
              f"sender {js_tx['sender'][:18]}...")

        # --- 2. Python extension-style txs ------------------------
        a_path, b_path = f"{d}/a.json", f"{d}/b.json"
        wa = create_wallet(pw, a_path)
        wb = create_wallet(pw, b_path)
        tx15 = make_testnet_tx(a_path, pw, wb["address"], "1.5", 0)
        check("make_testnet_tx: 1.500 R0NI -> amount 1500 milli + marker",
              tx15["amount"] == 1500 and tx15.get("amount_unit") == "milli-R0NI",
              f"amount={tx15['amount']} unit={tx15.get('amount_unit')}")
        ok, reason = verify_signed_tx(tx15)
        check("accept_signed_tx: extension-style 1.500 tx accepted",
              ok, reason)
        # NOTE: nonce 0 — tx15 above was only verified locally, never
        # submitted, so this is the first tx from wa on the live chain.
        tx0001 = make_testnet_tx(a_path, pw, wb["address"], "0.001", 0)
        check("make_testnet_tx: 0.001 R0NI -> amount 1 milli + marker",
              tx0001["amount"] == 1 and tx0001.get("amount_unit") == "milli-R0NI",
              f"amount={tx0001['amount']}")
        ok, reason = verify_signed_tx(tx0001)
        check("accept_signed_tx: extension-style 0.001 tx accepted",
              ok, reason)

        # --- 3. legacy pre-milli txs are REJECTED -----------------
        _, priv_a = _load_private(pw, a_path)
        legacy = {"sender": wa["address"], "recipient": wb["address"],
                  "amount": 100, "nonce": 2,
                  "signature": priv_a.sign(
                      testnet_tx_message(wa["address"], wb["address"], 100, 2, None)
                      .encode("utf-8")).hex(),
                  "sender_pubkey_hex": wa["public_key_hex"]}
        legacy["txid"] = testnet_tx_id(wa["address"], wb["address"], 100, 2, None)
        ok, reason = verify_signed_tx(legacy)
        check("accept_signed_tx: legacy whole-R0NI tx (amount 100, "
              "no marker) REJECTED as pre-milli",
              not ok and "pre-milli" in reason, reason[:160])
        marked100 = dict(legacy, amount_unit="milli-R0NI")
        ok, reason = verify_signed_tx(marked100)
        check("accept_signed_tx: SAME amount 100 WITH the marker is "
              "accepted — as 0.100 R0NI, proving the marker decides",
              ok, reason)
        float_tx = {"sender": wa["address"], "recipient": wb["address"],
                    "amount": 1.5, "amount_unit": "milli-R0NI", "nonce": 3,
                    "signature": priv_a.sign(
                        testnet_tx_message(wa["address"], wb["address"], 1.5, 3, None)
                        .encode("utf-8")).hex(),
                    "sender_pubkey_hex": wa["public_key_hex"]}
        float_tx["txid"] = testnet_tx_id(wa["address"], wb["address"], 1.5, 3, None)
        ok, reason = verify_signed_tx(float_tx)
        check("accept_signed_tx: float amount 1.5 (even WITH marker) rejected",
              not ok and "integer" in reason, reason[:120])
        forged = dict(tx15)
        forged["signature"] = "00" * 64
        ok, reason = verify_signed_tx(forged)
        check("accept_signed_tx: forged signature rejected",
              not ok and ("signature" in reason or "txid" in reason), reason[:120])

        # --- 4. live node: JS-signed 1.500 + Python 0.001 ---------
        run_dir = Path(d) / "live"
        run_dir.mkdir(parents=True, exist_ok=True)
        # Fund both the JS keypair's sender and the Python wallet.
        live_genesis = mine_genesis({js_tx["sender"]: 10000, wa["address"]: 10000})
        live_genesis_path = run_dir / "genesis.json"
        live_genesis_path.write_text(json.dumps(live_genesis))
        proc = subprocess.Popen(
            [VENV_PY, str(REPO_ROOT / "testnet-v2" / "node.py"),
             "--port", "8123", "--data-dir", str(run_dir / "node1"),
             "--peers", "", "--genesis", str(live_genesis_path), "--mine"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            assert wait_up(8123), "live node 8123 did not come up"
            check("live: single node up (port 8123)", True)
            # The JS-signed tx, submitted exactly as the CLI does it.
            js_file = Path(d) / "js-tx.json"
            js_file.write_text(json.dumps(js_tx))
            r = subprocess.run(
                [VENV_PY, str(REPO_ROOT / "testnet-v2" / "accept_signed_tx.py"),
                 str(js_file), "--port", "8123"],
                capture_output=True, text=True, timeout=30)
            check("live: accept_signed_tx CLI submits the JS-signed "
                  "1.500 R0NI tx (exit 0)",
                  r.returncode == 0 and "signature verified" in r.stdout,
                  (r.stdout + r.stderr).strip()[-200:])
            assert wait_mempool_empty(8123, timeout=60), "live mempool did not drain"
            # NOTE: the JS tx sends to its own fixed recipient
            # (the 0x22 test key), NOT to wb — check that address.
            js_recipient = js_tx["recipient"]
            s, bal = http("GET", 8123, f"/balance?address={js_recipient}")
            check("live: JS-signed 1.500 tx mined — recipient holds "
                  "1500 milli (1.500 R0NI)",
                  s == 200 and bal.get("balance") == 1500
                  and bal.get("balance_R0NI") == "1.500", str(bal))
            # The Python 0.001 tx, same path.
            py_file = Path(d) / "py-tx.json"
            py_file.write_text(json.dumps(tx0001))
            r = subprocess.run(
                [VENV_PY, str(REPO_ROOT / "testnet-v2" / "accept_signed_tx.py"),
                 str(py_file), "--port", "8123"],
                capture_output=True, text=True, timeout=30)
            check("live: accept_signed_tx CLI submits the 0.001 R0NI tx",
                  r.returncode == 0, (r.stdout + r.stderr).strip()[-200:])
            assert wait_mempool_empty(8123, timeout=60), "live mempool did not drain"
            s, bal = http("GET", 8123, f"/balance?address={wb['address']}")
            check("live: 0.001 tx mined — wb holds 1 milli (0.001 R0NI)",
                  s == 200 and bal.get("balance") == 1
                  and bal.get("balance_R0NI") == "0.001", str(bal))
            # The legacy tx, same path: CLI must refuse it, and the
            # node must never see it.
            legacy_file = Path(d) / "legacy-tx.json"
            legacy_file.write_text(json.dumps(legacy))
            r = subprocess.run(
                [VENV_PY, str(REPO_ROOT / "testnet-v2" / "accept_signed_tx.py"),
                 str(legacy_file), "--port", "8123"],
                capture_output=True, text=True, timeout=30)
            check("live: accept_signed_tx CLI REFUSES the legacy tx "
                  "(exit 1, pre-milli)",
                  r.returncode == 1 and "pre-milli" in (r.stdout + r.stderr),
                  (r.stdout + r.stderr).strip()[-200:])
            time.sleep(1)
            s, bal = http("GET", 8123, f"/balance?address={js_recipient}")
            check("live: legacy tx never reached the node — JS "
                  "recipient balance still 1500 milli",
                  s == 200 and bal.get("balance") == 1500, str(bal))
            s, bal = http("GET", 8123, f"/balance?address={wb['address']}")
            check("live: legacy tx never reached the node — wb balance "
                  "still 1 milli",
                  s == 200 and bal.get("balance") == 1, str(bal))
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    out = REPO_ROOT / "testnet-v2" / "extension_milli_test_results.json"
    out.write_text(json.dumps(RESULTS, indent=2) + "\n")
    print(f"\n{RESULTS['passed']} passed, {RESULTS['failed']} failed — wrote {out}")
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
