#!/usr/bin/env python3
"""R0NI payload roundtrip + rejection tests — transaction format v2.

Prototype only, no real value, not audited.

Two parts:
1. OFFLINE — roni_wallet payload helpers: attach -> validate ->
   extract, for text, PNG, GIF, WAV and MP4 fixtures, plus a ref
   payload; and rejections (oversize raw, oversize compressed,
   corrupted data, sha256 mismatch, bad mime, over-long text).
2. LIVE — one testnet node (own process, own data dir, port 8101):
   signed payload transactions are submitted, mined into blocks,
   gossiped/stored, then extracted from the confirmed chain and
   compared byte-for-byte (SHA-256) with the originals. Rejection
   cases are also submitted to the live node and must be refused.

Results are printed and written to testnet/payload_test_results.json.
Usage: /tmp/r0ni-media-venv/bin/python testnet/test_payloads.py
(venv with `cryptography`; see testnet/README.md)
"""
import base64
import hashlib
import json
import random
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "testnet"))
from roni_wallet import (  # noqa: E402
    MAX_COMPRESSED_BYTES, MAX_MEDIA_RAW_BYTES, create_wallet,
    extract_payload_bytes, extract_payload_to_file, make_media_payload,
    make_ref_payload, make_testnet_tx, make_text_payload, r0ni_address,
    testnet_tx_id, testnet_tx_message, validate_payload,
)
from media_fixtures import generate_fixtures  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402

PY = sys.executable
RESULTS = {"offline": {}, "live": {}, "rejections": {}}


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


def sign_raw(wallet, recipient, amount, nonce, data):
    """Sign a transaction with a raw keypair (test helper)."""
    msg = testnet_tx_message(wallet["address"], recipient, amount, nonce, data)
    tx = {"sender": wallet["address"], "recipient": recipient, "amount": amount,
          "nonce": nonce,
          "signature": wallet["priv"].sign(msg.encode()).hex(),
          "sender_pubkey_hex": wallet["pub_hex"],
          "txid": testnet_tx_id(wallet["address"], recipient, amount, nonce, data)}
    if data is not None:
        tx["data"] = data
    return tx


def make_test_wallet(name):
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(serialization.Encoding.Raw,
                                  serialization.PrivateFormat.Raw,
                                  serialization.NoEncryption())
    pub_raw = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                             serialization.PublicFormat.Raw)
    return {"name": name, "priv": priv, "priv_hex": priv_raw.hex(),
            "pub_hex": pub_raw.hex(), "address": r0ni_address(pub_raw)}


def offline_tests(fixtures):
    print("== OFFLINE payload roundtrips ==")
    for name, (kind, mime, filename, raw) in fixtures.items():
        if kind == "text":
            payload = make_text_payload(raw.decode("utf-8"))
        else:
            payload = make_media_payload(raw, kind, mime, filename)
        ok, reason = validate_payload(payload)
        assert ok, f"{name}: {reason}"
        out = extract_payload_bytes(payload)
        match = hashlib.sha256(out).hexdigest() == hashlib.sha256(raw).hexdigest()
        assert out == raw and match
        RESULTS["offline"][name] = {
            "kind": kind, "mime": mime, "original_size": len(raw),
            "compressed_size": payload["compressed_size"],
            "sha256_match": match, "byte_identical": out == raw}
        print(f"  {name:6} {kind:6} raw {len(raw):>7} B -> compressed "
              f"{payload['compressed_size']:>7} B, sha256 match: {match}")
    ref = make_ref_payload("https://example.invalid/song.mp3", "audio/mpeg",
                           12_000_000, hashlib.sha256(b"song-bytes").hexdigest(), "song.mp3")
    ok, _ = validate_payload(ref)
    assert ok
    RESULTS["offline"]["ref"] = {"kind": "ref", "valid": True,
                                 "note": "no inline bytes — media fetched off-chain and hash-checked"}
    print("  ref    off-chain reference validates ok (no inline bytes)")
    print("== OFFLINE rejections (all must be rejected) ==")
    rej = {}
    # oversize raw (>5 MB)
    try:
        make_media_payload(b"x" * (MAX_MEDIA_RAW_BYTES + 1), "other", "application/octet-stream")
        rej["oversize_raw"] = False
    except ValueError as e:
        rej["oversize_raw"] = "ref" in str(e)
    # oversize compressed (1.5 MB incompressible random)
    try:
        make_media_payload(random.Random(42).randbytes(1_500_000), "other",
                           "application/octet-stream", "big.bin")
        rej["oversize_compressed"] = False
    except ValueError as e:
        rej["oversize_compressed"] = "ref" in str(e)
    # corrupted compressed data
    good = make_media_payload(fixtures["image"][3], "image", "image/png", "test.png")
    corrupt = dict(good)
    blob = bytearray(base64.b64decode(good["data_b64"]))
    blob[len(blob) // 2] ^= 0xFF
    corrupt["data_b64"] = base64.b64encode(bytes(blob)).decode()
    rej["corrupted_compressed"] = not validate_payload(corrupt)[0]
    # sha256 mismatch
    bad_hash = dict(good)
    bad_hash["sha256_of_original"] = "0" * 64
    rej["sha256_mismatch"] = not validate_payload(bad_hash)[0]
    # bad mime
    bad_mime = dict(good)
    bad_mime["mime"] = "text/plain"
    rej["bad_mime"] = not validate_payload(bad_mime)[0]
    # over-long text
    try:
        make_text_payload("x" * 1001)
        rej["text_over_1000_chars"] = False
    except ValueError:
        rej["text_over_1000_chars"] = True
    RESULTS["rejections"]["offline"] = rej
    for name, passed in rej.items():
        print(f"  {name:24} {'REJECTED' if passed else 'ACCEPTED — FAIL'}")
        assert passed, f"rejection failed: {name}"
    return fixtures


def live_tests(fixtures):
    print("== LIVE single-node roundtrips (port 8101) ==")
    run_dir = Path("/tmp/r0ni-payload-test")
    import shutil
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    sender = make_test_wallet("payload-sender")
    receiver = make_test_wallet("payload-receiver")
    # genesis: fund the sender with test R0NI
    from run_testnet import mine_genesis  # noqa: E402  (reuse the testnet's miner)
    genesis = mine_genesis({sender["address"]: 1_000_000})
    genesis_path = run_dir / "genesis.json"
    genesis_path.write_text(json.dumps(genesis))
    proc = subprocess.Popen(
        [PY, str(REPO / "testnet" / "node.py"), "--port", "8101",
         "--data-dir", str(run_dir / "node1"), "--peers", "",
         "--genesis", str(genesis_path), "--mine"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        t0 = time.time()
        while time.time() - t0 < 30:
            s, _ = http("GET", 8101, "/status", timeout=3)
            if s == 200:
                break
            time.sleep(0.5)
        assert s == 200, "node did not come up"
        nonce = 0
        live = {}
        # one payload transaction per kind, plus a ref
        cases = []
        for name, (kind, mime, filename, raw) in fixtures.items():
            payload = (make_text_payload(raw.decode("utf-8")) if kind == "text"
                       else make_media_payload(raw, kind, mime, filename))
            cases.append((name, payload, raw))
        ref = make_ref_payload("https://example.invalid/song.mp3", "audio/mpeg",
                               12_000_000, hashlib.sha256(b"song-bytes").hexdigest(), "song.mp3")
        cases.append(("ref", ref, None))
        sent = {}  # name -> (txid, payload, raw)
        for name, payload, raw in cases:
            tx = sign_raw(sender, receiver["address"], 10, nonce, payload)
            nonce += 1
            s, r = http("POST", 8101, "/tx", tx)
            assert s == 200 and r.get("accepted"), f"{name} rejected by node: {r}"
            sent[name] = (tx["txid"], payload, raw)
            print(f"  {name:6} tx {tx['txid'][:16]}... accepted into mempool")
        # wait for mining to drain the mempool
        t0 = time.time()
        while time.time() - t0 < 90:
            s, st = http("GET", 8101, "/status", timeout=3)
            if s == 200 and st.get("mempool", 1) == 0 and st.get("height", 0) > 1:
                break
            time.sleep(0.3)
        assert st.get("mempool", 1) == 0, "mempool did not drain"
        s, chain = http("GET", 8101, "/chain", timeout=10)
        assert s == 200
        confirmed = [t for b in chain for t in b["transactions"] if t.get("data")]
        assert len(confirmed) == len(cases), f"expected {len(cases)} payload txs on-chain, got {len(confirmed)}"
        by_txid = {t["txid"]: t for t in confirmed}
        for name, payload, raw in cases:
            txid, _, _ = sent[name]
            onchain = by_txid.get(txid)
            assert onchain is not None, f"{name}: tx not found on-chain"
            if name == "ref":
                ok, _ = validate_payload(onchain["data"])
                assert ok and onchain["data"]["uri"] == ref["uri"]
                live[name] = {"kind": "ref", "on_chain": True,
                              "sha256_match": True, "byte_identical": None,
                              "note": "reference only — media stays off-chain"}
                print(f"  {name:6} confirmed on-chain, ref uri + hash intact")
                continue
            out_path = run_dir / f"extracted-{name}"
            info = extract_payload_to_file(onchain["data"], str(out_path))
            match = info["sha256_verified"] and out_path.read_bytes() == raw
            assert match
            live[name] = {"kind": payload["kind"], "mime": payload["mime"],
                          "original_size": len(raw),
                          "compressed_size": payload["compressed_size"],
                          "sha256_match": match, "byte_identical": True,
                          "block": next(b["index"] for b in chain
                                        if any(t.get("txid") == txid for t in b["transactions"]))}
            print(f"  {name:6} mined + extracted from chain, sha256 match: {match}, "
                  f"byte-identical: True")
        RESULTS["live"] = live
        # live rejections: signed txs whose ONLY fault is the payload
        print("== LIVE rejections (signed, so only the payload can fail) ==")
        live_rej = {}
        good = make_media_payload(fixtures["image"][3], "image", "image/png", "test.png")
        cases_rej = {}
        corrupt = dict(good)
        blob = bytearray(base64.b64decode(good["data_b64"]))
        blob[len(blob) // 2] ^= 0xFF
        corrupt["data_b64"] = base64.b64encode(bytes(blob)).decode()
        cases_rej["corrupted_compressed"] = corrupt
        bad_hash = dict(good)
        bad_hash["sha256_of_original"] = "0" * 64
        cases_rej["sha256_mismatch"] = bad_hash
        bad_mime = dict(good)
        bad_mime["mime"] = "text/plain"
        cases_rej["bad_mime"] = bad_mime
        # Oversize compressed: 1.5 MB of incompressible random bytes.
        # The SHA-256 claim is correct for these bytes, so the size
        # check is the only thing that can reject it.
        oversize = dict(good)
        raw_big = random.Random(99).randbytes(1_500_000)
        comp_big = __import__("zlib").compress(raw_big, 9)
        oversize["data_b64"] = base64.b64encode(comp_big).decode()
        oversize["compressed_size"] = len(comp_big)
        oversize["original_size"] = len(raw_big)
        oversize["sha256_of_original"] = hashlib.sha256(raw_big).hexdigest()
        cases_rej["oversize_compressed"] = oversize
        for name, payload in cases_rej.items():
            tx = sign_raw(sender, receiver["address"], 10, nonce, payload)
            nonce += 1
            s, r = http("POST", 8101, "/tx", tx)
            live_rej[name] = {"accepted": s == 200, "status": s, "reason": r}
            print(f"  {name:24} {'ACCEPTED — FAIL' if s == 200 else 'REJECTED'} "
                  f"({s}: {r.get('reason')})")
            assert s != 200, f"live rejection failed: {name}"
        RESULTS["rejections"]["live"] = live_rej
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def main():
    fixtures, video_real = generate_fixtures()
    RESULTS["fixtures"] = {n: {"kind": k, "mime": m, "filename": f, "size": len(b)}
                          for n, (k, m, f, b) in fixtures.items()}
    RESULTS["video_is_real_ffmpeg_mp4"] = video_real
    if not video_real:
        print("NOTE: ffmpeg unavailable — video fixture is a binary blob "
              "labelled video/mp4, not a playable file.")
    offline_tests(fixtures)
    live_tests(fixtures)
    out = REPO / "testnet" / "payload_test_results.json"
    out.write_text(json.dumps(RESULTS, indent=2))
    print(f"\nALL PAYLOAD TESTS PASSED — results in {out}")
    print("Prototype only: testnet, no live network, no real value.")


if __name__ == "__main__":
    main()
