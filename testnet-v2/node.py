#!/usr/bin/env python3
"""
R0NI testnet node v2 — prototype only, NOT audited, no real value.

v2 CHANGE: every block hash carries an "R-" prefix ahead of the
128 hex chars of EvoHash-11, e.g. "R-0000adbc...". The "R" is a
label, NOT part of the hash — hex has no R. The difficulty rule
applies to the hex part: it must start with "0000" immediately
after "R-". Plain hex hashes (no R-) are rejected, as are R-
hashes whose hex part does not start with 0000 or does not match
a recomputation of EvoHash-11 over the header (without prefix).
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

Message / media payloads (transaction format v2): a transaction
may carry an optional "data" payload (text, image, audio, video,
GIF, other, or an off-chain "ref"). The node validates the
payload on receipt — kind/mime, zlib integrity, decompressed
size, SHA-256 of the original bytes — and the payload is covered
by the signature, so tampering with it breaks the signature.
Limits: text 1,000 chars; media 5 MB raw / 1 MB compressed
on-chain; anything bigger is rejected (use a "ref" payload).
See roni_wallet.py for the format and the reasons.

Asset certifications / NFTs (v0.3): "cert-mint" transactions
(amount 0) record a certificate — deterministic cert ID from
asset SHA-256 + issuer address, issuer signature, owner, issue
date, optional expiry — and "cert-transfer" transactions move a
certificate to a new owner, signed by the CURRENT owner only.
The node rejects duplicate mints, transfers by non-owners, and
any certificate whose issuer signature does not verify. See
testnet/test_certs.py and roni_wallet.py ("Certificates").

Governance / voting (v0.4): "gov-propose" transactions (amount 0)
file a proposal — deterministic PROP- ID, options, voting window
[start, end), quorum (default 10% of genesis supply = 10,000
R0NI = 10,000,000 milli-units) — and "gov-vote" transactions (amount 0) cast one signed
vote per address. Voting power is 1 milli-R0NI = 1 vote-unit,
taken from the voter's balance at the proposal's SNAPSHOT (the
balances as of the block the proposal was filed in), so buying
after a proposal starts does not inflate power. The node rejects votes on unknown
or out-of-window proposals, duplicate votes, votes from
zero-balance-at-snapshot addresses, and any vote whose signature
does not verify. A proposal passes only if total votes >= quorum
AND the winning option has a strict majority — and the winner is
not the rejection option "no". See testnet/test_governance.py
and roni_wallet.py ("Governance") and GOVERNANCE.md.

Units — divisibility (2026-11-23): amounts are integer
milli-R0NI (1 R0NI = 1000 milli, smallest unit 0.001 R0NI).
A transaction's "amount" is milli; a legacy testnet genesis
block with whole-R0NI amounts and no "amount_unit" marker is
migrated x1000 when the node loads it (the stored genesis hash
is not recomputed — the node never re-hashes the genesis block).
Max supply ceiling chosen by Mac 2026-11-23: 10,000,000,000 R0NI
(recorded decision only, not on-chain); a single payment above
that ceiling is rejected.

Usage:
  python3 node.py --port 8021 --data-dir /tmp/node1 \
      --peers http://127.0.0.1:8022,http://127.0.0.1:8023 \
      --mine --genesis testnet-v2/genesis.json
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
from roni_wallet import (  # noqa: E402
    evo_hash_11, r0ni_address, testnet_tx_message, validate_payload,
    cert_tx_message, cert_tx_id, verify_certificate_signature,
    cert_id_for, CERT_ID_PREFIX,
    gov_propose_message, gov_propose_tx_id, gov_vote_message,
    gov_vote_tx_id, validate_proposal, tally_proposal,
    proposal_status, GOV_ID_PREFIX, DEFAULT_QUORUM,
    format_amount, MAX_SUPPLY_MILLI, MILLI_PER_R0NI,
)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: E402

DIFFICULTY = "0000"
HASH_PREFIX = "R-"  # v2: label ahead of the hex hash, NOT part of it
GENESIS_PREVIOUS_HASH = HASH_PREFIX + "0" * 128  # R- + 128 zeros
MAX_TX_PER_BLOCK = 10
# A block holds at most 10 transactions, each payload at most 1 MB
# compressed, so a block can never exceed ~10 MB of payload plus
# overhead. Anything bigger is rejected — see validate_block().
MAX_BLOCK_BYTES = 11_000_000


def _migrate_legacy_genesis_amounts(chain):
    """Migrate a legacy genesis block (whole-R0NI amounts, no
    "amount_unit" marker) to milli-R0NI in memory: genesis tx
    amounts x1000, then mark the block "milli-R0NI" so a second
    load does not multiply again. The stored block hash is NOT
    recomputed — it was mined over the original transactions, and
    the node never re-hashes the genesis block (later blocks only
    link to its stored hash string)."""
    if not chain:
        return chain
    genesis = chain[0]
    if genesis.get("amount_unit") == "milli-R0NI":
        return chain
    txs = genesis.get("transactions") or []
    if any(t.get("type") == "genesis" for t in txs):
        for t in txs:
            if t.get("type") == "genesis":
                t["amount"] = int(t["amount"]) * MILLI_PER_R0NI
        genesis["amount_unit"] = "milli-R0NI"
    return chain


def block_hash_hex(block):
    """The raw 128-hex EvoHash-11 of the block header (no prefix)."""
    parts = [
        str(block["index"]),
        str(block["timestamp"]),
        block["previous_hash"],
        json.dumps(block["transactions"], sort_keys=True),
        str(block["nonce"]),
    ]
    if "data" in block and block["data"] is not None:
        parts.append(str(block["data"]))
    return evo_hash_11("|".join(parts).encode("utf-8")).hex()


def block_hash(block):
    """v2 block hash: "R-" + 128 hex chars of EvoHash-11. The R is a
    label; the hash function output is unchanged hex."""
    return HASH_PREFIX + block_hash_hex(block)


def is_valid_hash_format(h):
    """A valid v2 block hash is exactly "R-" + 128 hex chars."""
    return (isinstance(h, str) and h.startswith(HASH_PREFIX)
            and len(h) == len(HASH_PREFIX) + 128
            and all(c in "0123456789abcdef" for c in h[len(HASH_PREFIX):]))


def tx_message(tx):
    """The signed message for a transaction (shared with roni_wallet).

    v1 (no "data"): sender|recipient|amount|nonce — unchanged, so
    old transactions still validate. v2 (payload): the message also
    carries the SHA-256 of the canonical payload JSON, so tampering
    with the payload breaks the signature and the txid. Certificate
    transactions (cert-mint / cert-transfer, amount 0) are signed
    over the cert ID + asset hash (mint) or the cert ID + TRANSFER
    (transfer) — see roni_wallet.cert_tx_message. Governance
    transactions (gov-propose / gov-vote, amount 0): a proposal is
    signed over its whole canonical JSON, a vote over
    sender|GOV-VOTE|proposal_id|option — see roni_wallet."""
    if tx.get("type") == "cert-mint":
        return cert_tx_message(tx["sender"], tx["recipient"], tx["amount"],
                               tx["nonce"], tx.get("cert"), None, tx.get("data"))
    if tx.get("type") == "cert-transfer":
        return cert_tx_message(tx["sender"], tx["recipient"], tx["amount"],
                               tx["nonce"], None, tx.get("cert_id"), None)
    if tx.get("type") == "gov-propose":
        return gov_propose_message(tx["proposal"])
    if tx.get("type") == "gov-vote":
        return gov_vote_message(tx["sender"], tx["proposal_id"], tx["option"])
    return testnet_tx_message(tx["sender"], tx["recipient"], tx["amount"],
                              tx["nonce"], tx.get("data"))


def tx_id(tx):
    if tx.get("type") == "cert-mint":
        return cert_tx_id(tx["sender"], tx["recipient"], tx["amount"],
                          tx["nonce"], tx.get("cert"), None, tx.get("data"))
    if tx.get("type") == "cert-transfer":
        return cert_tx_id(tx["sender"], tx["recipient"], tx["amount"],
                          tx["nonce"], None, tx.get("cert_id"), None)
    if tx.get("type") == "gov-propose":
        return gov_propose_tx_id(tx["sender"], tx["proposal"], tx["nonce"])
    if tx.get("type") == "gov-vote":
        return gov_vote_tx_id(tx["sender"], tx["proposal_id"], tx["option"])
    return evo_hash_11(tx_message(tx).encode("utf-8")).hex()


def verify_cert_tx(tx):
    """Stateless checks for a certificate transaction. Returns
    (ok, reason). Ownership and duplicate checks need chain state
    and live in Node.validate_tx / validate_block, not here."""
    tx_type = tx.get("type")
    if tx_type == "cert-mint":
        cert = tx.get("cert")
        if not isinstance(cert, dict):
            return False, "cert-mint needs a 'cert' object"
        if tx["amount"] != 0:
            return False, "cert-mint amount must be 0 — no R0NI moves, only the record"
        if cert.get("issuer") != tx["sender"]:
            return False, "cert issuer must be the transaction sender"
        if cert.get("owner") != tx["recipient"]:
            return False, "cert owner must be the transaction recipient"
        try:
            if cert_id_for(cert["asset_sha256"], cert["issuer"]) != cert["cert_id"]:
                return False, "cert_id does not match asset hash + issuer"
        except Exception as e:
            return False, f"bad certificate: {e}"
        if cert.get("expires_at") is not None and cert["expires_at"] <= cert["issued_at"]:
            return False, "cert expires_at must be after issued_at"
        if not verify_certificate_signature(cert):
            return False, "certificate issuer signature does not verify"
        if "data" in tx and tx["data"] is not None:
            if tx["data"].get("sha256_of_original") != cert["asset_sha256"]:
                return False, "payload hash does not match the certificate's asset_sha256"
        return True, "ok"
    if tx_type == "cert-transfer":
        cert = tx.get("cert")
        if not isinstance(cert, dict) or tx.get("cert_id") != cert.get("cert_id"):
            return False, "cert-transfer needs a 'cert' matching 'cert_id'"
        if tx["amount"] != 0:
            return False, "cert-transfer amount must be 0 — no R0NI moves, only the record"
        if not verify_certificate_signature(cert):
            return False, "certificate issuer signature does not verify"
        return True, "ok"
    return False, f"unknown certificate transaction type {tx_type!r}"


def verify_gov_tx(tx):
    """Stateless checks for a governance transaction. Returns
    (ok, reason). Proposal existence, voting window, snapshot
    balance and duplicate votes need chain state and live in
    Node.validate_tx / validate_block, not here."""
    tx_type = tx.get("type")
    if tx_type == "gov-propose":
        proposal = tx.get("proposal")
        if not isinstance(proposal, dict):
            return False, "gov-propose needs a 'proposal' object"
        ok, reason = validate_proposal(proposal)
        if not ok:
            return False, reason
        if tx["amount"] != 0:
            return False, "gov-propose amount must be 0 — no R0NI moves, only the record"
        if proposal.get("creator") != tx["sender"]:
            return False, "proposal creator must be the transaction sender"
        if tx.get("recipient") != proposal["proposal_id"]:
            return False, "gov-propose recipient must be the proposal ID"
        return True, "ok"
    if tx_type == "gov-vote":
        if tx["amount"] != 0:
            return False, "gov-vote amount must be 0 — no R0NI moves, only the vote"
        if not isinstance(tx.get("proposal_id"), str) or not tx["proposal_id"].startswith(GOV_ID_PREFIX):
            return False, "gov-vote needs a proposal_id starting with 'PROP-'"
        if tx.get("recipient") != tx["proposal_id"]:
            return False, "gov-vote recipient must be the proposal ID"
        if not isinstance(tx.get("option"), str) or not tx["option"]:
            return False, "gov-vote needs a non-empty option"
        return True, "ok"
    return False, f"unknown governance transaction type {tx_type!r}"


def verify_tx(tx):
    """Return (ok, reason). Checks address/pubkey match, signature,
    format — and, for v2 transactions, the payload (see
    roni_wallet.validate_payload): kind/mime, zlib integrity,
    decompressed size, and SHA-256 of the original bytes. For
    certificate transactions (cert-mint / cert-transfer) it checks
    the certificate itself — ID derivation, issuer signature, and
    that the payload hash matches the certified asset."""
    try:
        if set(tx) < {"sender", "recipient", "amount", "nonce", "signature", "sender_pubkey_hex"}:
            return False, "missing fields"
        if (not isinstance(tx["amount"], int) or isinstance(tx["amount"], bool)
                or tx["amount"] < 0):
            return False, "amount must be a non-negative integer (milli-R0NI)"
        if tx.get("type") in ("cert-mint", "cert-transfer"):
            if tx["amount"] != 0:
                return False, "certificate transactions move 0 R0NI"
        elif tx.get("type") in ("gov-propose", "gov-vote"):
            if tx["amount"] != 0:
                return False, "governance transactions move 0 R0NI"
        elif tx["amount"] <= 0:
            return False, "amount must be a positive integer (milli-R0NI; smallest unit 1 milli = 0.001 R0NI)"
        elif tx["amount"] > MAX_SUPPLY_MILLI:
            return False, "amount exceeds the chosen max supply ceiling of 10,000,000,000 R0NI"
        if r0ni_address(bytes.fromhex(tx["sender_pubkey_hex"])) != tx["sender"]:
            return False, "address does not match sender public key"
        if tx.get("type") in ("cert-mint", "cert-transfer"):
            ok, reason = verify_cert_tx(tx)
            if not ok:
                return False, reason
        if tx.get("type") in ("gov-propose", "gov-vote"):
            ok, reason = verify_gov_tx(tx)
            if not ok:
                return False, reason
        if "data" in tx and tx["data"] is not None:
            ok, reason = validate_payload(tx["data"])
            if not ok:
                return False, f"invalid payload: {reason}"
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
        # Legacy whole-R0NI genesis amounts migrate x1000 on load
        # (idempotent via the "amount_unit" marker); the migrated
        # chain is what gets saved.
        self.chain = _migrate_legacy_genesis_amounts(self.chain)
        self.save()
        self.stop = False

    def save(self):
        self.chain_file.write_text(json.dumps(self.chain, indent=2))
        self.mempool_file.write_text(json.dumps(list(self.mempool.values()), indent=2))

    # ---- balances / validation -------------------------------------
    # Balances are integer milli-R0NI (see "Units" in the module
    # docstring). Genesis amounts are migrated x1000 on load.
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

    # ---- certificates ------------------------------------------------
    def certificates(self):
        """cert_id -> {"cert": {...}, "owner": ..., "minted_block": int,
        "transfers": [...]} — the current certificate state of the
        chain. Ownership lives HERE (and in the registry), not in
        the certificate document, which always names the owner AT
        MINT."""
        certs = {}
        for block in self.chain:
            for tx in block["transactions"]:
                if tx.get("type") == "cert-mint":
                    certs[tx["cert"]["cert_id"]] = {
                        "cert": tx["cert"], "owner": tx["cert"]["owner"],
                        "minted_block": block["index"], "transfers": []}
                elif tx.get("type") == "cert-transfer" and tx["cert_id"] in certs:
                    certs[tx["cert_id"]]["owner"] = tx["recipient"]
                    certs[tx["cert_id"]]["transfers"].append(
                        {"from": tx["sender"], "to": tx["recipient"],
                         "txid": tx["txid"], "block": block["index"]})
        return certs

    def cert_owner(self, cert_id):
        entry = self.certificates().get(cert_id)
        return entry["owner"] if entry else None

    # ---- governance --------------------------------------------------
    def proposals(self):
        """proposal_id -> {"proposal": {...}, "snapshot_balances": {...},
        "snapshot_block": int, "votes": [...]} — the current
        governance state of the chain. The SNAPSHOT is the balances
        as of the block the proposal was filed in: the replay takes
        the balances at the moment the gov-propose tx is reached
        (amount 0, so filing a proposal moves nothing), and later
        transfers never change it — buying after a proposal starts
        does not inflate voting power on it."""
        proposals = {}
        bal = {}
        for block in self.chain:
            for tx in block["transactions"]:
                if tx.get("type") == "genesis":
                    bal[tx["recipient"]] = bal.get(tx["recipient"], 0) + tx["amount"]
                elif tx.get("type") == "gov-propose":
                    pid = tx["proposal"]["proposal_id"]
                    if pid not in proposals:
                        proposals[pid] = {
                            "proposal": tx["proposal"],
                            "snapshot_balances": dict(bal),
                            "snapshot_block": block["index"],
                            "votes": []}
                elif tx.get("type") == "gov-vote":
                    entry = proposals.get(tx["proposal_id"])
                    if entry is not None:
                        entry["votes"].append(tx)
                else:
                    bal[tx["sender"]] = bal.get(tx["sender"], 0) - tx["amount"]
                    bal[tx["recipient"]] = bal.get(tx["recipient"], 0) + tx["amount"]
        return proposals

    def proposal(self, proposal_id):
        return self.proposals().get(proposal_id)

    def proposal_tally(self, proposal_id):
        """Tally + status for one proposal at the current height
        (height = number of blocks in the chain, genesis = 1)."""
        entry = self.proposal(proposal_id)
        if entry is None:
            return None
        tally = tally_proposal(entry["proposal"], entry["votes"],
                               entry["snapshot_balances"])
        tally["status"] = proposal_status(entry["proposal"], entry["votes"],
                                          entry["snapshot_balances"], len(self.chain))
        tally["snapshot_block"] = entry["snapshot_block"]
        tally["votes"] = entry["votes"]
        return tally

    def chain_height(self):
        """Current height: number of blocks in the chain (genesis = 1)."""
        return len(self.chain)

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
        # Certificate state checks (ownership / duplicates need the
        # chain, so they live here, not in stateless verify_tx).
        if tx.get("type") == "cert-mint":
            cert_id = tx["cert"]["cert_id"]
            if cert_id in self.certificates():
                return False, f"duplicate certificate {cert_id} — already minted on this chain"
            for m in self.mempool.values():
                if m.get("type") == "cert-mint" and m.get("cert", {}).get("cert_id") == cert_id:
                    return False, f"duplicate certificate {cert_id} — already in mempool"
        if tx.get("type") == "cert-transfer":
            owner = self.cert_owner(tx["cert_id"])
            if owner is None:
                return False, f"unknown certificate {tx['cert_id']} — it was never minted"
            if owner != tx["sender"]:
                return False, (f"transfer rejected: current owner is {owner}, "
                               f"not {tx['sender']} — only the owner can transfer")
            for m in self.mempool.values():
                if m.get("type") == "cert-transfer" and m.get("cert_id") == tx["cert_id"]:
                    return False, f"certificate {tx['cert_id']} already has a pending transfer"
        # Governance state checks (proposal existence, voting window,
        # snapshot balance and one-vote-per-address need the chain).
        if tx.get("type") == "gov-propose":
            pid = tx["proposal"]["proposal_id"]
            if pid in self.proposals():
                return False, f"duplicate proposal {pid} — already filed on this chain"
            for m in self.mempool.values():
                if m.get("type") == "gov-propose" and m.get("proposal", {}).get("proposal_id") == pid:
                    return False, f"duplicate proposal {pid} — already in mempool"
            if tx["proposal"]["voting_start_block"] < self.chain_height():
                return False, (f"proposal voting_start_block "
                               f"{tx['proposal']['voting_start_block']} is in the past "
                               f"(chain height is {self.chain_height()})")
        if tx.get("type") == "gov-vote":
            entry = self.proposal(tx["proposal_id"])
            if entry is None:
                return False, (f"unknown proposal {tx['proposal_id']} — it was never "
                               "filed (or is still only in the mempool)")
            proposal = entry["proposal"]
            height = self.chain_height()
            if not (proposal["voting_start_block"] <= height < proposal["voting_end_block"]):
                return False, (f"vote outside voting window: proposal "
                               f"{tx['proposal_id']} votes in blocks "
                               f"[{proposal['voting_start_block']}, "
                               f"{proposal['voting_end_block']}), chain height is {height}")
            if tx["option"] not in proposal["options"]:
                return False, (f"option {tx['option']!r} is not on proposal "
                               f"{tx['proposal_id']} (options: {proposal['options']})")
            if any(v["sender"] == tx["sender"] for v in entry["votes"]):
                return False, (f"duplicate vote: {tx['sender']} has already voted on "
                               f"{tx['proposal_id']} — one vote per address, and votes "
                               "cannot be changed in v1")
            for m in self.mempool.values():
                if (m.get("type") == "gov-vote"
                        and m.get("proposal_id") == tx["proposal_id"]
                        and m.get("sender") == tx["sender"]):
                    return False, (f"duplicate vote: {tx['sender']} already has a "
                                   f"pending vote on {tx['proposal_id']}")
            if int(entry["snapshot_balances"].get(tx["sender"], 0)) <= 0:
                return False, (f"voter {tx['sender']} held 0 R0NI at the snapshot "
                               f"(block {entry['snapshot_block']}) — zero-balance "
                               "addresses cannot vote")
        if tx["nonce"] != self.sender_nonce(tx["sender"]):
            return False, f"bad nonce: expected {self.sender_nonce(tx['sender'])}, got {tx['nonce']}"
        if self.balance(tx["sender"]) - self.pending_spend(tx["sender"]) < tx["amount"]:
            return False, (f"insufficient balance (incl. pending spends): "
                           f"{format_amount(self.balance(tx['sender']) - self.pending_spend(tx['sender']))} "
                           f"R0NI available, {format_amount(tx['amount'])} R0NI requested")
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
        if len(json.dumps(block).encode("utf-8")) > MAX_BLOCK_BYTES:
            return False, f"block exceeds {MAX_BLOCK_BYTES} bytes"
        if block["previous_hash"] != self.chain[-1]["hash"]:
            return False, "previous_hash does not match chain tip"
        if not is_valid_hash_format(block["hash"]):
            return False, "block hash must be 'R-' + 128 hex chars (v2 format)"
        if block["hash"] != block_hash(block):
            return False, "block hash does not match recomputed EvoHash-11"
        if not block["hash"][len(HASH_PREFIX):].startswith(DIFFICULTY):
            return False, "block does not meet difficulty 0000 (hex part after 'R-')"
        # validate every tx in order against the state before this block
        bal = self.balances()
        # Certificate ownership as of the chain tip, updated tx by tx
        # within this block (so a mint and a later transfer in the
        # same block validate in order, and a duplicate mint or a
        # transfer by a non-owner inside a block is rejected).
        cert_owners = {cid: e["owner"] for cid, e in self.certificates().items()}
        # Governance state as of the chain tip, updated tx by tx
        # within this block: proposals filed in this block get their
        # snapshot from the balances at that point in the replay,
        # and votes in this block are checked against it — so a
        # proposal and its first votes can land in the same block,
        # and a duplicate vote inside a block is rejected.
        gov_state = {}
        for pid, entry in self.proposals().items():
            gov_state[pid] = {
                "proposal": entry["proposal"],
                "snapshot_balances": dict(entry["snapshot_balances"]),
                "voters": {v["sender"] for v in entry["votes"]},
            }
        height = block["index"]  # == len(self.chain) for the next block
        seen_nonces = {}
        for tx in block["transactions"]:
            if tx.get("type") == "genesis":
                continue
            ok, reason = verify_tx(tx)
            if not ok:
                return False, f"bad tx in block: {reason}"
            if tx.get("type") == "cert-mint":
                cert_id = tx["cert"]["cert_id"]
                if cert_id in cert_owners:
                    return False, f"duplicate certificate {cert_id} in block"
                cert_owners[cert_id] = tx["cert"]["owner"]
            if tx.get("type") == "cert-transfer":
                if cert_owners.get(tx["cert_id"]) != tx["sender"]:
                    return False, (f"cert transfer in block rejected: current owner of "
                                   f"{tx['cert_id']} is {cert_owners.get(tx['cert_id'])}, "
                                   f"not {tx['sender']}")
                cert_owners[tx["cert_id"]] = tx["recipient"]
            if tx.get("type") == "gov-propose":
                pid = tx["proposal"]["proposal_id"]
                ok, reason = validate_proposal(tx["proposal"])
                if not ok:
                    return False, f"bad proposal in block: {reason}"
                if pid in gov_state:
                    return False, f"duplicate proposal {pid} in block"
                if tx["proposal"]["creator"] != tx["sender"]:
                    return False, "proposal creator in block is not the sender"
                if tx["proposal"]["voting_start_block"] < height:
                    return False, (f"proposal {pid} in block starts voting at block "
                                   f"{tx['proposal']['voting_start_block']}, before this "
                                   f"block {height}")
                gov_state[pid] = {
                    "proposal": tx["proposal"],
                    "snapshot_balances": dict(bal),
                    "voters": set(),
                }
            if tx.get("type") == "gov-vote":
                pid = tx["proposal_id"]
                entry = gov_state.get(pid)
                if entry is None:
                    return False, f"vote in block for unknown proposal {pid}"
                proposal = entry["proposal"]
                if not (proposal["voting_start_block"] <= height < proposal["voting_end_block"]):
                    return False, (f"vote in block outside voting window for {pid}: "
                                   f"blocks [{proposal['voting_start_block']}, "
                                   f"{proposal['voting_end_block']}), this block {height}")
                if tx["option"] not in proposal["options"]:
                    return False, f"vote in block for option {tx['option']!r} not on {pid}"
                if tx["sender"] in entry["voters"]:
                    return False, f"duplicate vote in block: {tx['sender']} already voted on {pid}"
                if int(entry["snapshot_balances"].get(tx["sender"], 0)) <= 0:
                    return False, (f"vote in block from zero-balance-at-snapshot address "
                                   f"{tx['sender']} on {pid}")
                entry["voters"].add(tx["sender"])
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
            if h[len(HASH_PREFIX):].startswith(DIFFICULTY):
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
                bal = node.balance(addr)
                self.send_json({"address": addr, "balance": bal,
                                "balance_R0NI": format_amount(bal)})
            elif self.path == "/certs":
                self.send_json(node.certificates())
            elif self.path.startswith("/cert"):
                from urllib.parse import urlparse, parse_qs
                cert_id = parse_qs(urlparse(self.path).query).get("cert_id", [""])[0]
                entry = node.certificates().get(cert_id)
                if entry is None:
                    self.send_json({"error": "certificate not found"}, 404)
                else:
                    self.send_json(entry)
            elif self.path == "/proposals":
                out = []
                for pid, entry in node.proposals().items():
                    tally = node.proposal_tally(pid)
                    out.append({"proposal_id": pid,
                                "proposal": entry["proposal"],
                                "snapshot_block": entry["snapshot_block"],
                                "tally": {k: v for k, v in tally.items() if k != "votes"},
                                "status": tally["status"]})
                self.send_json(out)
            elif self.path.startswith("/proposal"):
                from urllib.parse import urlparse, parse_qs
                pid = parse_qs(urlparse(self.path).query).get("proposal_id", [""])[0]
                entry = node.proposal(pid)
                if entry is None:
                    self.send_json({"error": "proposal not found"}, 404)
                else:
                    tally = node.proposal_tally(pid)
                    self.send_json({"proposal": entry["proposal"],
                                    "snapshot_block": entry["snapshot_block"],
                                    "snapshot_balances": entry["snapshot_balances"],
                                    "votes": entry["votes"],
                                    "tally": tally,
                                    "status": tally["status"]})
            elif self.path.startswith("/tally"):
                from urllib.parse import urlparse, parse_qs
                pid = parse_qs(urlparse(self.path).query).get("proposal_id", [""])[0]
                tally = node.proposal_tally(pid)
                if tally is None:
                    self.send_json({"error": "proposal not found"}, 404)
                else:
                    self.send_json({k: v for k, v in tally.items() if k != "votes"})
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
