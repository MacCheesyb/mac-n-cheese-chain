#!/usr/bin/env python3
"""
Test the R0NI asset certification / NFT layer (v0.3).

Runs offline in-process (no HTTP) plus a live single-node
roundtrip: mint a PNG certificate, a document certificate and
an audio certificate, verify each, transfer one to a new owner
and verify again, then test the rejections — forged issuer
signature, tampered asset file, duplicate certificate, and a
transfer by a non-owner.

Writes testnet-v2/cert_test_results.json. Exits non-zero on any
failure. Prototype only — not audited, no real value.

Usage: /tmp/r0ni-cert-venv/bin/python testnet/test_certs.py
"""
import hashlib
import json
import struct
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from roni_wallet import (  # noqa: E402
    create_wallet, make_media_payload, make_text_payload,
    make_certificate, make_cert_mint_tx, make_cert_transfer_tx,
    verify_certificate, verify_certificate_signature,
    new_cert_registry, registry_apply_mint, registry_apply_transfer,
    registry_owner, sign_certificate,
)
from node import Node  # noqa: E402

RESULTS = {"tests": [], "passed": 0, "failed": 0}


def check(name, ok, detail=""):
    RESULTS["tests"].append({"name": name, "passed": bool(ok), "detail": str(detail)})
    if ok:
        RESULTS["passed"] += 1
        print(f"PASS  {name}  {detail}")
    else:
        RESULTS["failed"] += 1
        print(f"FAIL  {name}  {detail}")


def main():
    with tempfile.TemporaryDirectory() as d:
        pw = "test-password"
        issuer = f"{d}/issuer.json"
        owner = f"{d}/owner.json"
        buyer = f"{d}/buyer.json"
        w_issuer = create_wallet(pw, issuer)
        w_owner = create_wallet(pw, owner)
        w_buyer = create_wallet(pw, buyer)

        # --- real example files -------------------------------------
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
               b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
               b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
               b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
        doc = ("CERTIFICATE OF OWNERSHIP\nAsset: 1967 Ford Mustang, "
               "VIN 7T02C123456\nOwner: Mac Beck\n").encode("utf-8")
        wav = (b"RIFF" + struct.pack("<I", 44) + b"WAVEfmt "
               + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
               + b"data" + struct.pack("<I", 8) + b"\x00\x00" * 4)

        reg = new_cert_registry()
        certs = {}

        # 1. PNG certificate (image, inline media payload).
        png_hash = hashlib.sha256(png).hexdigest()
        png_payload = make_media_payload(png, "image", "image/png", "mustang.png")
        cert_png = make_certificate(png_hash, w_issuer["address"], w_issuer["public_key_hex"],
                                    w_owner["address"], "1967 Ford Mustang — photo",
                                    "image", "image/png", "mustang.png")
        mint_png = make_cert_mint_tx(issuer, pw, w_owner["address"], cert_png, 0, png_payload)
        ok, st = verify_certificate(mint_png["cert"], png)
        check("png: mint + verify (asset SHA-256 matches)", ok, mint_png["cert"]["cert_id"])
        registry_apply_mint(reg, mint_png)
        certs["png"] = mint_png["cert"]

        # 2. Document certificate (text payload carrying the document).
        doc_hash = hashlib.sha256(doc).hexdigest()
        doc_payload = make_text_payload(doc.decode("utf-8"))
        cert_doc = make_certificate(doc_hash, w_issuer["address"], w_issuer["public_key_hex"],
                                    w_owner["address"], "Mustang ownership document",
                                    "document", "text/plain", "ownership.txt")
        mint_doc = make_cert_mint_tx(issuer, pw, w_owner["address"], cert_doc, 1, doc_payload)
        ok, st = verify_certificate(mint_doc["cert"], doc)
        check("document: mint + verify (asset SHA-256 matches)", ok, mint_doc["cert"]["cert_id"])
        registry_apply_mint(reg, mint_doc)
        certs["doc"] = mint_doc["cert"]

        # 3. Audio certificate (WAV, inline media payload).
        wav_hash = hashlib.sha256(wav).hexdigest()
        wav_payload = make_media_payload(wav, "audio", "audio/wav", "song.wav")
        cert_wav = make_certificate(wav_hash, w_issuer["address"], w_issuer["public_key_hex"],
                                    w_owner["address"], "Original song demo",
                                    "audio", "audio/wav", "song.wav")
        mint_wav = make_cert_mint_tx(issuer, pw, w_owner["address"], cert_wav, 2, wav_payload)
        ok, st = verify_certificate(mint_wav["cert"], wav)
        check("audio: mint + verify (asset SHA-256 matches)", ok, mint_wav["cert"]["cert_id"])
        registry_apply_mint(reg, mint_wav)
        certs["wav"] = mint_wav["cert"]

        # 4. Transfer the audio certificate owner -> buyer, verify under new owner.
        xfer = make_cert_transfer_tx(owner, pw, mint_wav["cert"], w_buyer["address"], 0)
        registry_apply_transfer(reg, xfer)
        check("audio: transfer owner -> buyer recorded in registry",
              registry_owner(reg, cert_wav["cert_id"]) == w_buyer["address"])
        ok, st = verify_certificate(mint_wav["cert"], wav,
                                    current_owner=registry_owner(reg, cert_wav["cert_id"]))
        check("audio: verify under new owner after transfer", ok, st.get("status"))

        # 5. Rejection: forged issuer signature.
        forged = dict(mint_png["cert"])
        forged["signature"] = "00" * 64
        check("reject: forged issuer signature", not verify_certificate_signature(forged))

        # 6. Rejection: tampered asset file.
        tampered = bytearray(png)
        tampered[-1] ^= 0xFF
        ok, st = verify_certificate(mint_png["cert"], bytes(tampered))
        check("reject: tampered asset file (SHA-256 mismatch)",
              not ok and st["status"] == "asset_hash_mismatch", st.get("reason", ""))

        # 7. Rejection: duplicate certificate (same asset + same issuer).
        try:
            registry_apply_mint(reg, mint_png)
            check("reject: duplicate certificate", False, "duplicate was accepted")
        except ValueError as e:
            check("reject: duplicate certificate", "duplicate" in str(e), str(e))

        # 8. Rejection: transfer by a non-owner (issuer is not the owner).
        try:
            make_cert_transfer_tx(issuer, pw, mint_png["cert"], w_buyer["address"], 5)
            check("reject: transfer by non-owner", False, "non-owner transfer was signed")
        except ValueError as e:
            check("reject: transfer by non-owner", "current owner" in str(e), str(e))

        # 9. Expiry: a certificate past its expiry verifies as expired, not valid.
        now = int(time.time())
        old = make_certificate(png_hash, w_issuer["address"], w_issuer["public_key_hex"],
                               w_owner["address"], "expired example", "image",
                               "image/png", "mustang.png",
                               expires_at=now - 10, issued_at=now - 3600)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64
        from evocrypt_hybrid_v02 import decrypt_b64
        priv_raw = base64.b64decode(decrypt_b64(
            pw, json.loads(Path(issuer).read_text())["encrypted_private_key"]))
        old_signed = sign_certificate(Ed25519PrivateKey.from_private_bytes(priv_raw), old)
        ok, st = verify_certificate(old_signed, png)
        check("reject-as-expired: past-expiry certificate reports 'expired'",
              not ok and st["status"] == "expired", st.get("status"))

        # --- live single-node roundtrip ------------------------------
        genesis = {
            "index": 0, "timestamp": int(time.time()),
            "previous_hash": "R-" + "0" * 128, "transactions": [],
            "nonce": 0, "hash": "R-" + "0" * 128,
        }
        # The node expects a genesis block whose hash is its own
        # "previous_hash" anchor; use the testnet genesis file when
        # present, else the empty anchor above (chain validation
        # only requires blocks after genesis to link correctly).
        node_dir = Path(d) / "node1"
        node = Node(str(node_dir), [], None, mine=False)
        node.chain = [genesis]
        node.save()

        # Node accepts the PNG mint tx into the mempool, mines it.
        ok, reason = node.add_tx(mint_png)
        check("node: cert-mint accepted into mempool", ok, reason)
        block = node.mine_one()
        check("node: cert-mint block mined", block is not None)
        ok, reason = node.add_block(block)
        check("node: cert-mint block accepted", ok, reason)
        check("node: certificate owner after mint",
              node.cert_owner(cert_png["cert_id"]) == w_owner["address"])

        # Node rejects a duplicate mint of the same certificate.
        ok, reason = node.add_tx(mint_png)
        check("node: duplicate cert-mint rejected", not ok, reason)

        # Node accepts a transfer by the owner, mines it, owner changes.
        xfer2 = make_cert_transfer_tx(owner, pw, mint_png["cert"], w_buyer["address"], 0)
        ok, reason = node.add_tx(xfer2)
        check("node: cert-transfer by owner accepted", ok, reason)
        block2 = node.mine_one()
        ok, reason = node.add_block(block2)
        check("node: cert-transfer block accepted", ok, reason)
        check("node: certificate owner after transfer",
              node.cert_owner(cert_png["cert_id"]) == w_buyer["address"])

        # Node rejects a transfer by a non-owner (issuer, who is not
        # the owner any more — buyer is).
        # make_cert_transfer_tx itself refuses (wallet is not owner),
        # so build the forged transfer tx by hand to test the NODE:
        # sign it with the issuer's key over the transfer message.
        # Nonce 1 is the issuer's correct next nonce on this node
        # (one confirmed mint), so the node must reject it on
        # ownership — not on a bad nonce.
        from roni_wallet import cert_tx_message, cert_tx_id
        msg = cert_tx_message(w_issuer["address"], w_owner["address"], 0, 1,
                              None, cert_png["cert_id"], None)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey as _PK
        sig = _PK.from_private_bytes(priv_raw).sign(msg.encode("utf-8")).hex()
        forged_xfer = {
            "type": "cert-transfer", "sender": w_issuer["address"],
            "recipient": w_owner["address"], "amount": 0, "nonce": 1,
            "cert_id": cert_png["cert_id"], "cert": mint_png["cert"],
            "signature": sig, "sender_pubkey_hex": w_issuer["public_key_hex"],
            "txid": cert_tx_id(w_issuer["address"], w_owner["address"], 0, 1,
                               None, cert_png["cert_id"], None),
        }
        ok, reason = node.add_tx(forged_xfer)
        check("node: transfer by non-owner rejected", not ok, reason)

        # Node rejects a mint with a forged issuer signature.
        forged_mint = json.loads(json.dumps(mint_doc))
        forged_mint["cert"] = dict(mint_doc["cert"])
        forged_mint["cert"]["signature"] = "00" * 64
        # Re-sign the tx over the forged cert so the tx signature
        # itself is valid — the node must still reject it on the
        # certificate signature.
        msg = cert_tx_message(w_issuer["address"], w_owner["address"], 0, 1,
                              forged_mint["cert"], None, doc_payload)
        forged_mint["signature"] = _PK.from_private_bytes(priv_raw).sign(msg.encode("utf-8")).hex()
        forged_mint["txid"] = cert_tx_id(w_issuer["address"], w_owner["address"], 0, 1,
                                         forged_mint["cert"], None, doc_payload)
        ok, reason = node.add_tx(forged_mint)
        check("node: mint with forged issuer signature rejected", not ok, reason)

        # Node still serves the certificate over its registry view.
        entry = node.certificates().get(cert_png["cert_id"])
        check("node: /certs view shows transferred certificate",
              entry is not None and entry["owner"] == w_buyer["address"]
              and len(entry["transfers"]) == 1)

    RESULTS["cert_ids"] = {k: v["cert_id"] for k, v in certs.items()}
    out = Path(REPO_ROOT) / "testnet-v2" / "cert_test_results.json"
    out.write_text(json.dumps(RESULTS, indent=2) + "\n")
    print(f"\n{RESULTS['passed']} passed, {RESULTS['failed']} failed — wrote {out}")
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
