#!/usr/bin/env python3
"""
R0NI testnet node — prototype only, NOT audited, no real value.
================================================================
Simulated multi-node testnet on ONE machine: each node is a
separate OS process with its own data directory, talking to
peers over localhost HTTP. This is NOT multiple real VMs —
Docker is not available here, and no real VMs were created.

Chain: EvoHash-11 (imported from roni_wallet.py — the exact
chain used by Block 0, NOT a reimplementation). Difficulty
"0000" for the demo. Transactions are Ed25519-signed and
verified before acceptance. No transaction is ever signed
from Mac's address — the testnet has no private key for it;
transactions TO Mac's address are inbound only.

Usage:
  python3 node.py --port 8001 --data-dir /tmp/node1 \
      --peers http://127.0.0.1:8002,http://127.0.0.1:8003 \
      --mine --genesis testnet/genesis.json
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Reuse the exact EvoHash-11 from the repo (roni_wallet.py).
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from roni_wallet import evo_hash_11, r0ni_address  # noqa: E402

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: E402

DIFFICULTY = "0000"
MAX_TX_PER_BLOCK = 10


def block_hash(block):
    header = "|".join([
        str(block["index"]),
        str(block["timestamp"]),
        block["previous_hash"],
        json.dumps(block["transactions"], sort_keys=True),
        str(block["nonce"]),
    ])
    return evo_hash_11(header.encode("utf-8")).hex()


def tx_message(tx):
    return f"{tx['sender']}|{tx['recipient']}|{tx['amount']}|{tx['nonce']}"


def tx_id(tx):
    return evo_hash_11(tx_message(tx).encode("utf-8")).hex()


def verify_tx(tx):
    """Return (ok, reason). Checks address/pubkey match, signature, format."""
    try:
        if set(tx) < {"sender", "recipient", "amount", "nonce", "signature", "sender_pubkey_hex"}:
            return False, "missing fields"
        if not isinstance(tx["amount"], int) or tx["amount"] <= 0:
            return False, "amount must be a positive integer"
        if r0ni_address(bytes.fromhex(tx["sender_pubkey_hex"])) != tx["sender"]:
            return False, "address does not match sender public key"
        if tx_id(tx) != tx.get("txid", tx_id(tx)) and "txid" in tx:
            return False, "txid mismatch"
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx["sender_pubkey_hex"]))
        pub.verify(bytes.fromhex(tx["signature"]), tx_message(tx).encode("utf-8"))
        return True, "ok"
    except Exception as e:
        return False, f"signature verification failed: {e}"


class Node:
    def __init__(self, data_dir, peers, genesis_path, mine):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.peers = [p.rstrip("/") for p in peers if p]
        self.mine = mine
        self.lock = threading.Lock()
        self.chain = []
        self.mempool = {}  # txid -> tx
        self.chain_file = self.data_dir / "chain.json"
        self.mempool_file = self.data_dir / "mempool.json"
        if self.chain_file.exists():
            self.chain = json.loads(self.chain_file.read_text())
        elif genesis_path:
            genesis = json.loads(Path(genesis_path).read_text())
            self.chain = [genesis]
            self.save()
        self.stop = False

    def save(self):
        self.chain_file.write_text(json.dumps(self.chain, indent=2))
        self.mempool_file.write_text(json.dumps(list(self.mempool.values()), indent=2))

    # ---- balances / validation -------------------------------------
    def balances(self):
        bal = {}
        for block in self.chain:
            for tx in block["transactions"]:
                if tx.get("type") == "genesis":
                    bal[tx["recipient"]] = bal.get(tx["recipient"], 0) + tx["amount"]
                else:
                    bal[tx["sender"]] = bal.get(tx["sender"], 0) - tx["amount"]
                    bal[tx["recipient"]] = bal.get(tx["recipient"], 0) + tx["amount"]
        return bal

    def balance(self, address):
        return self.balances().get(address, 0)

    def sender_nonce(self, sender):
        n = 0
        for block in self.chain:
            for tx in block["transactions"]:
                if tx.get("sender") == sender:
                    n += 1
        for tx in self.mempool.values():
            if tx["sender"] == sender:
                n += 1
        return n

    def pending_spend(self, sender):
        return sum(tx["amount"] for tx in self.mempool.values() if tx["sender"] == sender)

    def validate_tx(self, tx):
        ok, reason = verify_tx(tx)
        if not ok:
            return False, reason
        if tx["txid"] in self.mempool:
            return False, "duplicate: already in mempool"
        for block in self.chain:
            for c in block["transactions"]:
                if c.get("txid") == tx["txid"]:
                    return False, "duplicate: already confirmed"
        if tx["nonce"] != self.sender_nonce(tx["sender"]):
            return False, f"bad nonce: expected {self.sender_nonce(tx['sender'])}, got {tx['nonce']}"
        if self.balance(tx["sender"]) - self.pending_spend(tx["sender"]) < tx["amount"]:
            return False, "insufficient balance (incl. pending spends)"
        return True, "ok"

    def add_tx(self, tx):
        with self.lock:
            if "txid" not in tx:
                tx["txid"] = tx_id(tx)
            ok, reason = self.validate_tx(tx)
            if not ok:
                return False, reason
            self.mempool[tx["txid"]] = tx
            self.save()
        return True, "accepted into mempool"

    # ---- blocks ------------------------------------------------------
    def validate_block(self, block):
        if block["index"] != len(self.chain):
            return False, f"bad index: expected {len(self.chain)}, got {block['index']}"
        if block["previous_hash"] != self.chain[-1]["hash"]:
            return False, "previous_hash does not match chain tip"
        if block["hash"] != block_hash(block):
            return False, "block hash does not match recomputed EvoHash-11"
        if not block["hash"].startswith(DIFFICULTY):
            return False, "block does not meet difficulty 0000"
        # validate every tx in order against the state before this block
        bal = self.balances()
        seen_nonces = {}
        for tx in block["transactions"]:
            ok, reason = verify_tx(tx)
            if not ok:
                return False, f"bad tx in block: {reason}"
            seen_nonces[tx["sender"]] = seen_nonces.get(tx["sender"], 0)
            if tx["nonce"] != sum(1 for b in self.chain for t in b["transactions"] if t.get("sender") == tx["sender"]) + seen_nonces[tx["sender"]]:
                return False, "bad tx nonce in block"
            seen_nonces[tx["sender"]] += 1
            if bal.get(tx["sender"], 0) < tx["amount"]:
                return False, "tx in block exceeds sender balance"
            bal[tx["sender"]] = bal.get(tx["sender"], 0) - tx["amount"]
            bal[tx["recipient"]] = bal.get(tx["recipient"], 0) + tx["amount"]
        return True, "ok"

    def add_block(self, block):
        with self.lock:
            ok, reason = self.validate_block(block)
            if not ok:
                return False, reason
            self.chain.append(block)
            for tx in block["transactions"]:
                self.mempool.pop(tx.get("txid", ""), None)
            self.save()
        return True, "block accepted"

    def validate_chain(self, chain):
        if not chain:
            return False, "empty chain"
        if chain[0] != self.chain[0]:
            return False, "genesis block differs"
        tmp = Node.__new__(Node)
        tmp.chain = [chain[0]]
        tmp.mempool = {}
        tmp.lock = threading.Lock()
        for block in chain[1:]:
            ok, reason = tmp.validate_block(block)
            if not ok:
                return False, f"block {block.get('index')}: {reason}"
            tmp.chain.append(block)
        return True, "ok"

    def adopt_chain(self, chain):
        with self.lock:
            if len(chain) <= len(self.chain):
                return False
            ok, reason = self.validate_chain(chain)
            if not ok:
                return False
            self.chain = chain
            # drop mempool txs now confirmed
            confirmed = {t.get("txid") for b in chain for t in b["transactions"]}
            self.mempool = {k: v for k, v in self.mempool.items() if k not in confirmed}
            self.save()
            return True

    # ---- mining ------------------------------------------------------
    def mine_one(self):
        with self.lock:
            if not self.mempool:
                return None
            txs = sorted(self.mempool.values(), key=lambda t: t["nonce"])[:MAX_TX_PER_BLOCK]
            block = {
                "index": len(self.chain),
                "timestamp": int(time.time()),
                "previous_hash": self.chain[-1]["hash"],
                "transactions": txs,
                "nonce": 0,
            }
        nonce = 0
        while not self.stop:
            block["nonce"] = nonce
            h = block_hash(block)
            if h.startswith(DIFFICULTY):
                block["hash"] = h
                return block
            nonce += 1
        return None

    def miner_loop(self):
        while not self.stop:
            if self.mine:
                block = self.mine_one()
                if block:
                    ok, _ = self.add_block(block)
                    if ok:
                        self.broadcast_block(block)
            time.sleep(0.5)

    # ---- p2p ---------------------------------------------------------
    def post(self, peer, path, payload):
        try:
            req = urllib.request.Request(
                peer + path, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read() or b"{}")
        except Exception:
            return None

    def get_chain(self, peer):
        try:
            with urllib.request.urlopen(peer + "/chain", timeout=5) as r:
                return json.loads(r.read())
        except Exception:
            return None

    def broadcast_tx(self, tx):
        for p in self.peers:
            threading.Thread(target=self.post, args=(p, "/tx", tx), daemon=True).start()

    def broadcast_block(self, block):
        for p in self.peers:
            threading.Thread(target=self.post, args=(p, "/block", block), daemon=True).start()

    def sync_loop(self):
        while not self.stop:
            for p in self.peers:
                chain = self.get_chain(p)
                if chain and len(chain) > len(self.chain):
                    if self.adopt_chain(chain):
                        pass
            time.sleep(2)


def make_handler(node):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send_json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/chain":
                self.send_json(node.chain)
            elif self.path == "/mempool":
                self.send_json(list(node.mempool.values()))
            elif self.path == "/status":
                self.send_json({"height": len(node.chain), "mempool": len(node.mempool),
                                "peers": node.peers, "tip": node.chain[-1]["hash"] if node.chain else None})
            elif self.path.startswith("/balance"):
                from urllib.parse import urlparse, parse_qs
                addr = parse_qs(urlparse(self.path).query).get("address", [""])[0]
                self.send_json({"address": addr, "balance": node.balance(addr)})
            else:
                self.send_json({"error": "not found"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/tx":
                ok, reason = node.add_tx(payload)
                if ok:
                    node.broadcast_tx(payload)
                self.send_json({"accepted": ok, "reason": reason}, 200 if ok else 400)
            elif self.path == "/block":
                ok, reason = node.add_block(payload)
                if ok:
                    node.broadcast_block(payload)
                self.send_json({"accepted": ok, "reason": reason}, 200 if ok else 400)
            else:
                self.send_json({"error": "not found"}, 404)
    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--peers", default="")
    ap.add_argument("--mine", action="store_true")
    ap.add_argument("--genesis", default="")
    args = ap.parse_args()
    peers = [p for p in args.peers.split(",") if p]
    node = Node(args.data_dir, peers, args.genesis or None, args.mine)
    threading.Thread(target=node.miner_loop, daemon=True).start()
    threading.Thread(target=node.sync_loop, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(node))
    print(f"R0NI testnet node on 127.0.0.1:{args.port} height={len(node.chain)} mine={args.mine} peers={peers}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        node.stop = True


if __name__ == "__main__":
    main()
