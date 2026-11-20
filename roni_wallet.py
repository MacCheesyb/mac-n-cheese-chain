#!/usr/bin/env python3
"""
R0NI Wallet — software wallet prototype v0.2
=============================================
Mac 'N Cheese Chain — R0NI
Ticker renamed 2026-11-19: RONI -> R0NI (the number 0 in place of the
letter O), to avoid confusion with an existing RONI token. The Genesis
Block 0 hashed data still reads "RONI" — it is a historical record and
changing it would change the block hash, so it is NOT re-mined.

Prototype only — NOT audited, DO NOT use for real funds / real value.

What it does:
  * Generate an Ed25519 keypair (cryptography library)
  * Address = "R0NI-" + first 40 hex chars of EvoHash-11(public key)
    EvoHash-11 is the same 1-pass 11-step chain as Block 0.
  * Private key is stored ENCRYPTED with a password, using
    EvoCrypt v0.2 (evocrypt_hybrid_v02.py, in this repo).
    The wallet file itself only holds the public key, address,
    and the EvoCrypt-encrypted private key — never plaintext.
  * Sign a message, verify a signature.
  * Message / media payloads (transaction format v2, see
    "Payloads" below): attach a text message or a picture, song,
    short video, GIF, or other file to a signed transaction, and
    extract it back byte-identically, with SHA-256 verification.
  * Local ledger (genesis_allocation.json): show a balance and
    record a signed local transfer. There is no network / node yet,
    so the ledger is a local file — a demo of the accounting, not
    a live chain. The genesis allocation starts EMPTY: the first
    wallet Mac creates in the wallet app (wallet-app.html) is
    allocated the 100,000 R0NI genesis supply. No address is
    invented or pre-filled here.
  * Asset certifications / NFTs (v0.3, see "Certificates" below):
    mint a signed certificate for a real asset or document — the
    asset's SHA-256, issuer, owner, issue date and optional expiry
    — verifiable by anyone from the file + the certificate, and
    transferable only by the current owner. The asset file itself
    travels in a v2 media payload (inline or "ref").

Payloads (transaction format v2 — backward compatible):
  A transaction may carry an optional "data" field:
    {"kind": "text"|"image"|"audio"|"video"|"gif"|"other"|"ref",
     "mime": "image/png", "filename": "photo.png",
     "original_size": 12345, "compressed_size": 6789,
     "sha256_of_original": "<64 hex of the ORIGINAL bytes>",
     "compression": "zlib" | "none", "data_b64": "<base64>",
     "uri": "<only for kind 'ref'>"}
  Transactions without "data" are format v1 and still validate.
  Why it is designed this way:
  - Lossless delivery: the payload is stored compressed (zlib
    level 9) and the node decompresses it and checks BOTH the
    SHA-256 of the original bytes AND the decompressed size
    before accepting it. Extraction re-checks the hash, so what
    comes out is byte-identical to what went in, or it is
    rejected — never silently corrupted.
  - Storage is bounded: raw media max 5 MB, compressed on-chain
    max 1 MB. A chain that stores every song and video inline
    would bloat beyond what phones can sync, so anything bigger
    is REJECTED with a message telling the user to use kind
    "ref" instead: store only the SHA-256 + a URI on-chain and
    keep the media itself off-chain, then hash-check it after
    fetching it. Text is capped at 1,000 characters and stored
    uncompressed (compression "none") so it stays readable.
  - The payload is covered by the signature: a v2 transaction
    is signed over sender|recipient|amount|nonce|<sha256 of the
    canonical payload JSON>, so tampering with the payload
    breaks the signature AND the txid. A v1 transaction is
    signed over sender|recipient|amount|nonce, as before.
  - Decompression is capped: a node aborts decompression if the
    output would exceed the 5 MB raw limit, so a small
    compressed bomb cannot expand into gigabytes of memory.
  - MIME allowlist per kind (see PAYLOAD_MIMES): a payload that
    claims to be an image but carries text/plain is rejected.

What it does NOT do yet:
  * No network / node, no RPC, no block building.
  * No MetaMask connection yet — see extension/ and README.
  * No seed phrase / mnemonic yet. Back up the wallet file
    AND the password separately; losing either loses the key.

Ledger file format (genesis_allocation.json):
  {
    "chain": "Mac 'N Cheese Chain",
    "ticker": "R0NI",
    "genesis_block_hash": "0000adbc...c1b0",   # Block 0, unchanged
    "genesis_supply": 100000,
    "allocations": [],                          # {address, amount, source}
    "transfers": []                             # signed local transfers
  }

Run:
  python3 roni_wallet.py
    # self-test: wallet, sign/verify, ledger balance + transfer
  python3 roni_wallet.py create my-wallet.json "your-password"
  python3 roni_wallet.py show my-wallet.json
  python3 roni_wallet.py sign my-wallet.json "your-password" "hello R0NI"
  python3 roni_wallet.py verify <public-key-hex> "hello R0NI" <signature-hex>
  python3 roni_wallet.py init-ledger [genesis_allocation.json]
  python3 roni_wallet.py allocate-genesis <ledger.json> <wallet.json>
  python3 roni_wallet.py balance <ledger.json> <address>
  python3 roni_wallet.py transfer <ledger.json> <wallet.json> <password> <to-address> <amount>
  # Payloads (format v2 — text / media / off-chain ref):
  python3 roni_wallet.py payload-text "hello, chain"
  python3 roni_wallet.py payload-file photo.png [--kind image] [--mime image/png]
  python3 roni_wallet.py payload-ref https://example.com/song.mp3 audio/mpeg 12000000 <sha256-hex> [--filename song.mp3]
  python3 roni_wallet.py validate-payload payload.json
  python3 roni_wallet.py make-tx <wallet.json> <password> <to> <amount> <nonce> [payload.json]
  python3 roni_wallet.py extract <tx.json> <output-path>   # verifies SHA-256, writes original bytes
  # Certificates / NFTs (v0.3 — asset certification):
  python3 roni_wallet.py cert-mint <wallet.json> <password> <asset-file> <owner-address> <description> <nonce> [--expires <unix>] [--registry certs.json]
  python3 roni_wallet.py cert-verify <cert.json> [asset-file] [--registry certs.json]
  python3 roni_wallet.py cert-transfer <wallet.json> <password> <cert.json> <to-address> <nonce> [--registry certs.json]

MetaMask note:
  MetaMask speaks EVM (Ethereum-style secp256k1 addresses,
  JSON-RPC, chain ID). This chain is NOT EVM today, so MetaMask
  cannot talk to it directly. Three routes, Mac to choose:
  A. Own browser extension (scaffold in extension/) — talks
     directly to a Mac 'N Cheese node, uses R0NI addresses above.
  B. MetaMask Snap — a Snap can add custom chain support inside
     MetaMask, but needs a Snap audit / distribution path.
  C. Make the chain EVM-compatible, or issue R0NI as an ERC-20
     on an existing EVM chain — then MetaMask works natively,
     but the chain is no longer purely EvoHash-11 / custom.
  Route A is the default in this prototype.
"""

import base64
import json
import sys
from pathlib import Path

# EvoHash-11, same chain as evochain_genesis.py (copied, 1 pass)
import hashlib

def _b2b(d):    return hashlib.blake2b(d, digest_size=64).digest()
def _sha3_512(d): return hashlib.sha3_512(d).digest()
def _sha512(d): return hashlib.sha512(d).digest()
def _sha256(d): return hashlib.sha256(d).digest()
def _b2s(d):    return hashlib.blake2s(d, digest_size=32).digest()
def _sha3_256(d): return hashlib.sha3_256(d).digest()
def _shake256(d): return hashlib.shake_256(d).digest(64)
def _sha512_256(d): return hashlib.sha512(d).digest()[:32] + hashlib.sha256(d).digest()
def _b2b_32(d): return hashlib.blake2b(d, digest_size=32).digest()
def _sha3_384(d): return hashlib.sha3_384(d).digest() + hashlib.sha256(d).digest()[:16]
def _sha512_b(d): return hashlib.sha512(d).digest()

CHAIN = [
    _b2b, _sha3_512, _sha512, _sha256, _b2s, _sha3_256,
    _shake256, _sha512_256, _b2b_32, _sha3_384, _sha512_b,
]

def evo_hash_11(data: bytes) -> bytes:
    state = data
    for fn in CHAIN:
        state = fn(state)
    return state

GENESIS_BLOCK_HASH = (
    "0000adbc0f16c14cc2540a4a259339fd0b02a1503bad43f0bbb484eb5007c36d68f9d"
    "825875297db1b26be6eb2a0532496c6a31317f6ce9a9fc7cf6a8591c1b0"
)
GENESIS_SUPPLY = 100000
TICKER = "R0NI"


def r0ni_address(public_key_bytes: bytes) -> str:
    return "R0NI-" + evo_hash_11(public_key_bytes).hex()[:40]


# Backwards-compatible alias (v0.1 name).
roni_address = r0ni_address


try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
except ImportError as e:
    raise SystemExit("Missing 'cryptography'. pip install cryptography "
                     "(Termux: pkg install python-cryptography)") from e

# EvoCrypt for encrypting the private key at rest
try:
    from evocrypt_hybrid_v02 import encrypt_b64, decrypt_b64
except ImportError:
    encrypt_b64 = decrypt_b64 = None


def create_wallet(password: str, path: str) -> dict:
    if encrypt_b64 is None:
        raise SystemExit("evocrypt_hybrid_v02.py must be in the same folder — "
                         "it encrypts the private key.")
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption())
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    wallet = {
        "chain": "Mac 'N Cheese Chain",
        "ticker": TICKER,
        "address": r0ni_address(pub_raw),
        "public_key_hex": pub_raw.hex(),
        "encrypted_private_key": encrypt_b64(password, base64.b64encode(priv_raw).decode("ascii")),
        "warning": "Prototype only — not audited. Do not use for real funds.",
    }
    Path(path).write_text(json.dumps(wallet, indent=2) + "\n", encoding="utf-8")
    return wallet


def _load_private(password: str, path: str):
    wallet = json.loads(Path(path).read_text(encoding="utf-8"))
    priv_b64 = decrypt_b64(password, wallet["encrypted_private_key"])
    priv_raw = base64.b64decode(priv_b64.encode("ascii"))
    return wallet, Ed25519PrivateKey.from_private_bytes(priv_raw)


def show_wallet(path: str) -> dict:
    wallet = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "chain": wallet.get("chain"),
        "ticker": wallet.get("ticker"),
        "address": wallet["address"],
        "public_key_hex": wallet["public_key_hex"],
    }


def sign_message(password: str, path: str, message: str) -> str:
    _wallet, priv = _load_private(password, path)
    return priv.sign(message.encode("utf-8")).hex()


def verify_signature(public_key_hex: str, message: str, signature_hex: str) -> bool:
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    try:
        pub.verify(bytes.fromhex(signature_hex), message.encode("utf-8"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Message / media payloads — transaction format v2.
#
# Design (see docstring): optional "data" on a transaction, zlib
# level 9 for media, bounded storage, SHA-256 + size checked on
# receipt and again on extraction, payload covered by the signature.
# ---------------------------------------------------------------------------
import zlib  # noqa: E402

MAX_TEXT_CHARS = 1000
MAX_MEDIA_RAW_BYTES = 5_000_000          # 5 MB raw, per payload
MAX_COMPRESSED_BYTES = 1_000_000         # 1 MB compressed, on-chain
PAYLOAD_KINDS = ("text", "image", "audio", "video", "gif", "other", "ref")
PAYLOAD_MIMES = {
    "text": {"text/plain"},
    "image": {"image/png", "image/jpeg", "image/webp"},
    "gif": {"image/gif"},
    "audio": {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/ogg",
              "audio/mp4", "audio/webm"},
    "video": {"video/mp4", "video/webm", "video/quicktime"},
    # "other" also carries documents (e.g. PDF certificates' source
    # files) — the mime is checked, the bytes are hashed, same as
    # any other payload. Added for the certification layer (v0.3).
    "other": {"application/octet-stream", "application/pdf",
              "text/plain", "text/markdown"},
    # "ref": any mime of the referenced media (must contain "/").
}
# Kinds whose bytes are stored inline, compressed with zlib.
MEDIA_KINDS = ("image", "audio", "video", "gif", "other")


def _is_hex64(s) -> bool:
    return (isinstance(s, str) and len(s) == 64
            and all(c in "0123456789abcdef" for c in s))


def _clean_filename(filename):
    if filename is None:
        return None
    if not isinstance(filename, str) or not filename or len(filename) > 255:
        raise ValueError("filename must be a non-empty string of at most 255 characters")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("filename must not contain a path — give a plain file name")
    return filename


def payload_sha256_hex(data: dict) -> str:
    """SHA-256 of the canonical JSON of a payload (sorted keys, no spaces).

    This is what a v2 transaction signs over, so any change to the
    payload — bytes, hash claim, size claim, mime — breaks the
    signature and the txid."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def make_text_payload(message: str) -> dict:
    """A text message payload, stored uncompressed. Max 1,000 characters."""
    if not isinstance(message, str):
        raise ValueError("message must be a string")
    if len(message) > MAX_TEXT_CHARS:
        raise ValueError(
            f"text payload is {len(message)} characters — max is "
            f"{MAX_TEXT_CHARS}. Split it across transactions, or use a "
            "media/ref payload for longer content.")
    raw = message.encode("utf-8")
    return {
        "kind": "text",
        "mime": "text/plain",
        "filename": "message.txt",
        "original_size": len(raw),
        "compressed_size": len(raw),
        "sha256_of_original": hashlib.sha256(raw).hexdigest(),
        "compression": "none",
        "data_b64": base64.b64encode(raw).decode("ascii"),
    }


def make_media_payload(raw: bytes, kind: str, mime: str, filename=None) -> dict:
    """A media payload: raw bytes -> zlib level 9, with SHA-256 of the original.

    Rejects raw input over 5 MB, and rejects anything that still
    compresses to over 1 MB — in both cases the error tells the
    caller to use make_ref_payload() instead (hash + URI on-chain,
    media itself off-chain)."""
    if kind not in MEDIA_KINDS:
        raise ValueError(f"kind must be one of {MEDIA_KINDS}, got {kind!r}")
    if mime not in PAYLOAD_MIMES[kind]:
        raise ValueError(f"mime {mime!r} is not allowed for kind {kind!r} "
                         f"(allowed: {sorted(PAYLOAD_MIMES[kind])})")
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("raw media must be bytes")
    raw = bytes(raw)
    if len(raw) > MAX_MEDIA_RAW_BYTES:
        raise ValueError(
            f"media is {len(raw)} bytes raw — max is {MAX_MEDIA_RAW_BYTES} "
            "bytes (5 MB). Store the media off-chain and use a 'ref' "
            "payload instead: make_ref_payload(uri, mime, size, sha256).")
    compressed = zlib.compress(raw, 9)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise ValueError(
            f"media compresses to {len(compressed)} bytes — max on-chain "
            f"is {MAX_COMPRESSED_BYTES} bytes (1 MB). It does not compress "
            "well enough to store inline. Store the media off-chain and "
            "use a 'ref' payload instead: make_ref_payload(uri, mime, "
            "size, sha256).")
    return {
        "kind": kind,
        "mime": mime,
        "filename": _clean_filename(filename),
        "original_size": len(raw),
        "compressed_size": len(compressed),
        "sha256_of_original": hashlib.sha256(raw).hexdigest(),
        "compression": "zlib",
        "data_b64": base64.b64encode(compressed).decode("ascii"),
    }


def make_ref_payload(uri: str, mime: str, original_size: int,
                     sha256_hex: str, filename=None) -> dict:
    """An off-chain reference payload: only the SHA-256 + URI go on-chain.

    Use this for media over the inline limits, or for media you do not
    want replicated to every node. The media itself is NOT stored or
    delivered by the chain — whoever fetches it from the URI must
    hash-check it against sha256_of_original before trusting it."""
    if not isinstance(uri, str) or not uri:
        raise ValueError("uri must be a non-empty string")
    if not uri.startswith(("http://", "https://", "ipfs://", "magnet:")):
        raise ValueError("uri must start with http://, https://, ipfs:// or magnet:")
    if not isinstance(mime, str) or "/" not in mime or any(c.isspace() for c in mime):
        raise ValueError(f"mime {mime!r} is not a valid media type")
    if not isinstance(original_size, int) or original_size <= 0:
        raise ValueError("original_size must be a positive whole number of bytes")
    if not _is_hex64(sha256_hex):
        raise ValueError("sha256_of_original must be 64 lowercase hex characters")
    return {
        "kind": "ref",
        "mime": mime,
        "filename": _clean_filename(filename),
        "original_size": original_size,
        "compressed_size": 0,
        "sha256_of_original": sha256_hex,
        "compression": "none",
        "data_b64": "",
        "uri": uri,
    }


def validate_payload(data) -> tuple:
    """Validate a payload dict. Returns (True, "ok") or (False, reason).

    Checks kind/mime, filename, sizes, the SHA-256 and the size of
    the DECOMPRESSED bytes — so a node never accepts a payload whose
    bytes do not match its hash claim, however it was compressed.
    Decompression is capped so a compressed bomb cannot expand
    past the 5 MB raw limit in memory."""
    if not isinstance(data, dict):
        return False, "payload must be an object"
    kind = data.get("kind")
    if kind not in PAYLOAD_KINDS:
        return False, f"unknown payload kind {kind!r} (allowed: {list(PAYLOAD_KINDS)})"
    mime = data.get("mime")
    if kind == "ref":
        if not isinstance(mime, str) or "/" not in mime:
            return False, f"bad mime {mime!r} for ref payload"
        uri = data.get("uri")
        if not isinstance(uri, str) or not uri.startswith(("http://", "https://", "ipfs://", "magnet:")):
            return False, "ref payload needs a uri starting with http://, https://, ipfs:// or magnet:"
        if data.get("data_b64") not in ("", None):
            return False, "ref payload must not carry inline data — the media is off-chain"
    else:
        if mime not in PAYLOAD_MIMES.get(kind, set()):
            return False, f"mime {mime!r} is not allowed for kind {kind!r}"
    if data.get("filename") is not None:
        try:
            _clean_filename(data.get("filename"))
        except ValueError as e:
            return False, f"bad filename: {e}"
    original_size = data.get("original_size")
    compressed_size = data.get("compressed_size")
    if not isinstance(original_size, int) or original_size < 0:
        return False, "original_size must be a non-negative integer"
    if not isinstance(compressed_size, int) or compressed_size < 0:
        return False, "compressed_size must be a non-negative integer"
    if not _is_hex64(data.get("sha256_of_original")):
        return False, "sha256_of_original must be 64 lowercase hex characters"
    if data.get("compression") not in ("none", "zlib"):
        return False, f"unknown compression {data.get('compression')!r}"
    if kind == "ref":
        if original_size <= 0:
            return False, "ref payload original_size must be positive"
        return True, "ok"
    # Inline payloads: decode, decompress (capped), and verify.
    try:
        blob = base64.b64decode(data.get("data_b64", ""), validate=True)
    except Exception:
        return False, "data_b64 is not valid base64"
    if kind == "text":
        if data.get("compression") != "none":
            return False, "text payloads are stored uncompressed (compression 'none')"
        if len(blob) != original_size or len(blob) != compressed_size:
            return False, "text payload size does not match original_size/compressed_size"
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            return False, "text payload is not valid UTF-8"
        if len(text) > MAX_TEXT_CHARS:
            return False, f"text payload is {len(text)} characters — max is {MAX_TEXT_CHARS}"
    else:
        if data.get("compression") != "zlib":
            return False, "media payloads must use compression 'zlib'"
        if len(blob) > MAX_COMPRESSED_BYTES:
            return False, (f"compressed media is {len(blob)} bytes — max on-chain "
                           f"is {MAX_COMPRESSED_BYTES} bytes; use a 'ref' payload instead")
        if len(blob) != compressed_size:
            return False, "compressed size does not match compressed_size"
        if original_size > MAX_MEDIA_RAW_BYTES:
            return False, (f"media is {original_size} bytes raw — max is "
                           f"{MAX_MEDIA_RAW_BYTES} bytes; use a 'ref' payload instead")
        try:
            decomp = zlib.decompressobj()
            out = decomp.decompress(blob, MAX_MEDIA_RAW_BYTES + 1)
            out += decomp.flush()
            if decomp.unconsumed_tail:
                return False, "compressed data expands past the 5 MB raw limit"
        except Exception as e:
            return False, f"compressed data is corrupt (zlib error: {e})"
        blob = out
        if len(blob) != original_size:
            return False, (f"decompressed size {len(blob)} does not match "
                           f"original_size {original_size}")
    if hashlib.sha256(blob).hexdigest() != data["sha256_of_original"]:
        return False, "sha256 mismatch — payload bytes do not match sha256_of_original"
    return True, "ok"


def extract_payload_bytes(data: dict) -> bytes:
    """Return the ORIGINAL bytes of a payload, after full validation.

    Raises ValueError on any mismatch. For kind 'ref' there are no
    inline bytes — it raises ValueError telling the caller to fetch
    the media from data['uri'] and hash-check it themselves."""
    ok, reason = validate_payload(data)
    if not ok:
        raise ValueError(f"invalid payload: {reason}")
    if data["kind"] == "ref":
        raise ValueError(
            "ref payload has no inline bytes — fetch the media from "
            f"{data['uri']!r} and check its SHA-256 against "
            f"{data['sha256_of_original']}")
    blob = base64.b64decode(data["data_b64"])
    if data["compression"] == "zlib":
        return zlib.decompress(blob)
    return blob


def extract_payload_to_file(data: dict, out_path: str) -> dict:
    """Write a payload's original bytes to disk, verifying the hash.

    The file is written, re-read, and re-hashed; if the hash of the
    written file does not match sha256_of_original, the file is
    removed and ValueError is raised. Returns an info dict."""
    raw = extract_payload_bytes(data)
    out = Path(out_path)
    out.write_bytes(raw)
    written_hash = hashlib.sha256(out.read_bytes()).hexdigest()
    if written_hash != data["sha256_of_original"]:
        out.unlink(missing_ok=True)
        raise ValueError("written file hash does not match sha256_of_original — file removed")
    return {
        "kind": data["kind"],
        "mime": data["mime"],
        "filename": data.get("filename"),
        "original_size": data["original_size"],
        "compressed_size": data["compressed_size"],
        "sha256_of_original": data["sha256_of_original"],
        "path": str(out),
        "sha256_verified": True,
    }


# --- testnet transaction signing (format v1 / v2) -------------------

def testnet_tx_message(sender: str, recipient: str, amount: int, nonce: int,
                      data=None) -> str:
    """The message a testnet transaction is signed over.

    v1 (no payload): sender|recipient|amount|nonce — unchanged.
    v2 (payload):    sender|recipient|amount|nonce|<payload sha256>,
    where the payload hash is the SHA-256 of the canonical payload
    JSON. Tampering with any byte of the payload therefore breaks
    both the signature and the txid."""
    base = f"{sender}|{recipient}|{amount}|{nonce}"
    if data is None:
        return base
    return f"{base}|{payload_sha256_hex(data)}"


def testnet_tx_id(sender: str, recipient: str, amount: int, nonce: int,
                  data=None) -> str:
    return evo_hash_11(testnet_tx_message(sender, recipient, amount, nonce, data).encode("utf-8")).hex()


def make_testnet_tx(wallet_path: str, password: str, recipient: str,
                    amount: int, nonce: int, data=None) -> dict:
    """Build a signed testnet transaction, optionally with a payload.

    The payload is validated before signing, so a bad payload is
    never signed. The wallet's private key is only loaded to sign;
    it is never written into the transaction."""
    if amount <= 0:
        raise ValueError("amount must be a positive whole number of R0NI")
    if data is not None:
        ok, reason = validate_payload(data)
        if not ok:
            raise ValueError(f"invalid payload: {reason}")
    wallet, priv = _load_private(password, wallet_path)
    sender = wallet["address"]
    message = testnet_tx_message(sender, recipient, amount, nonce, data)
    tx = {
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "nonce": nonce,
        "signature": priv.sign(message.encode("utf-8")).hex(),
        "sender_pubkey_hex": wallet["public_key_hex"],
        "txid": testnet_tx_id(sender, recipient, amount, nonce, data),
    }
    if data is not None:
        tx["data"] = data
    return tx


# ---------------------------------------------------------------------------
# Asset certifications / NFTs — v0.3, built on transaction format v2.
#
# A certificate is a signed record that a real asset (a photo, a
# document, a song, any file) belongs to an owner at a point in time,
# issued by someone. It is the on-chain basis for NFTs and for
# certifying real-world assets and documents:
#   * The ASSET itself is carried by a v2 media payload (inline, or a
#     "ref" payload for large/off-chain media) — so the asset bytes
#     are delivered losslessly and hash-checked, exactly as in v2.
#   * The CERTIFICATE records only the asset's SHA-256 (never the
#     bytes themselves), plus who issued it, who owns it, when it
#     was issued, and an optional expiry. Anyone can verify it
#     without trusting the issuer: recompute the file's SHA-256,
#     check the certificate ID, check the issuer's Ed25519
#     signature, and check the current owner in the chain ledger.
#   * The certificate ID is deterministic: CERT- + first 40 hex of
#     EvoHash-11(asset_sha256 + "|" + issuer_address). The same
#     asset certified by the same issuer always has the same ID —
#     so a duplicate mint of the same asset by the same issuer is
#     detectable and rejected by the node. A different issuer
#     certifying the same asset gets a different ID (a different
#     attestation, not a duplicate).
#   * A certificate is minted by a "cert-mint" transaction
#     (amount 0 R0NI — no money moves, only the record) and moved
#     by a "cert-transfer" transaction signed by the CURRENT owner.
#     The node rejects a transfer signed by anyone else, a mint of
#     an already-certified asset/issuer pair, and any certificate
#     whose issuer signature does not verify.
#   * Expiry: if expires_at is set and now > expires_at, the
#     certificate verifies as EXPIRED — still authentic (the
#     signature and hash still check out), but no longer current.
#     Verification reports that explicitly, it never silently
#     passes an expired certificate as current.
# ---------------------------------------------------------------------------

CERT_ID_PREFIX = "CERT-"
CERT_ASSET_KINDS = ("image", "audio", "video", "gif", "document", "other")
CERT_ASSET_MIMES = {
    "image": {"image/png", "image/jpeg", "image/webp"},
    "gif": {"image/gif"},
    "audio": {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/ogg",
              "audio/mp4", "audio/webm"},
    "video": {"video/mp4", "video/webm", "video/quicktime"},
    "document": {"text/plain", "text/markdown", "application/pdf",
                 "application/octet-stream"},
    "other": {"application/octet-stream", "application/pdf", "text/plain"},
}
MAX_CERT_DESCRIPTION_CHARS = 500


def cert_id_for(asset_sha256_hex: str, issuer_address: str) -> str:
    """Deterministic certificate ID from asset hash + issuer address."""
    if not _is_hex64(asset_sha256_hex):
        raise ValueError("asset_sha256 must be 64 lowercase hex characters")
    if not isinstance(issuer_address, str) or not issuer_address.startswith("R0NI-"):
        raise ValueError("issuer_address must be an R0NI- address")
    material = f"{asset_sha256_hex}|{issuer_address}".encode("utf-8")
    return CERT_ID_PREFIX + evo_hash_11(material).hex()[:40]


def cert_message(cert: dict) -> str:
    """The message the issuer signs: canonical JSON of the cert
    without its signature, sorted keys, no spaces."""
    unsigned = {k: v for k, v in cert.items() if k != "signature"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"))


def make_certificate(asset_sha256_hex: str, issuer_address: str,
                     issuer_pubkey_hex: str, owner_address: str,
                     description: str, asset_kind: str, asset_mime: str,
                     asset_filename=None, expires_at=None,
                     issued_at=None) -> dict:
    """Build an UNSIGNED certificate. Sign it with sign_certificate()."""
    if asset_kind not in CERT_ASSET_KINDS:
        raise ValueError(f"asset_kind must be one of {CERT_ASSET_KINDS}, got {asset_kind!r}")
    if asset_mime not in CERT_ASSET_MIMES[asset_kind]:
        raise ValueError(f"mime {asset_mime!r} is not allowed for asset kind {asset_kind!r}")
    if not isinstance(description, str) or not description:
        raise ValueError("description must be a non-empty string")
    if len(description) > MAX_CERT_DESCRIPTION_CHARS:
        raise ValueError(f"description is {len(description)} characters — "
                         f"max is {MAX_CERT_DESCRIPTION_CHARS}")
    if not isinstance(owner_address, str) or not owner_address.startswith("R0NI-"):
        raise ValueError("owner_address must be an R0NI- address")
    issued = int(issued_at) if issued_at is not None else int(__import__("time").time())
    if expires_at is not None:
        expires_at = int(expires_at)
        if expires_at <= issued:
            raise ValueError("expires_at must be after issued_at")
    return {
        "cert_id": cert_id_for(asset_sha256_hex, issuer_address),
        "asset_sha256": asset_sha256_hex,
        "asset_kind": asset_kind,
        "asset_mime": asset_mime,
        "asset_filename": _clean_filename(asset_filename),
        "description": description,
        "issuer": issuer_address,
        "issuer_pubkey_hex": issuer_pubkey_hex,
        "owner": owner_address,
        "issued_at": issued,
        "expires_at": expires_at,
    }


def sign_certificate(priv, cert: dict) -> dict:
    """Return a copy of the cert with the issuer's Ed25519 signature."""
    signed = dict(cert)
    signed["signature"] = priv.sign(cert_message(cert).encode("utf-8")).hex()
    return signed


def verify_certificate_signature(cert: dict) -> bool:
    """Check the issuer's signature and that the cert ID matches the
    asset hash + issuer address. Does NOT check ownership or expiry
    — use verify_certificate() for the full check."""
    try:
        if cert.get("cert_id") != cert_id_for(cert["asset_sha256"], cert["issuer"]):
            return False
        if r0ni_address(bytes.fromhex(cert["issuer_pubkey_hex"])) != cert["issuer"]:
            return False
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(cert["issuer_pubkey_hex"]))
        pub.verify(bytes.fromhex(cert["signature"]), cert_message(cert).encode("utf-8"))
        return True
    except Exception:
        return False


def verify_certificate(cert: dict, asset_bytes=None, current_owner=None,
                       now=None) -> tuple:
    """Full verification of a certificate. Returns (ok, status dict).

    Checks, in order: cert ID derivation, issuer signature, asset
    hash (if the file bytes are supplied), expiry, and current
    owner (if supplied, e.g. from the chain). An expired certificate
    returns ok=False with status "expired" — authentic, but not
    current. A hash mismatch returns "asset_hash_mismatch" — the
    file presented is NOT the file that was certified."""
    if not isinstance(cert, dict):
        return False, {"status": "invalid", "reason": "certificate must be an object"}
    if not verify_certificate_signature(cert):
        return False, {"status": "invalid", "reason": "issuer signature or cert_id does not verify"}
    if asset_bytes is not None:
        if hashlib.sha256(asset_bytes).hexdigest() != cert.get("asset_sha256"):
            return False, {"status": "asset_hash_mismatch",
                           "reason": "the file's SHA-256 does not match asset_sha256 — "
                                     "this is not the certified file"}
    now = int(now) if now is not None else int(__import__("time").time())
    if cert.get("expires_at") is not None and now > int(cert["expires_at"]):
        return False, {"status": "expired",
                       "reason": f"certificate expired at {cert['expires_at']} "
                                 f"(now {now}) — authentic, but no longer current"}
    # Ownership after a transfer lives in the chain / registry, NOT in
    # the certificate document: the cert always names the owner AT
    # MINT, and transfers are separate signed transactions recorded
    # against the cert ID. So a current_owner supplied by the caller
    # (from the registry/chain) is reported, never compared against
    # cert["owner"] — comparing them would wrongly fail every
    # legitimately transferred certificate.
    return True, {"status": "valid", "cert_id": cert.get("cert_id"),
                  "owner_at_mint": cert.get("owner"),
                  "current_owner": current_owner if current_owner is not None
                                   else cert.get("owner"),
                  "issuer": cert.get("issuer"),
                  "issued_at": cert.get("issued_at"),
                  "expires_at": cert.get("expires_at")}


# --- certificate transactions (cert-mint / cert-transfer) -------------

def cert_tx_message(sender: str, recipient: str, amount: int, nonce: int,
                    cert=None, cert_id=None, data=None) -> str:
    """Signed message for a certificate transaction.

    cert-mint:    sender|recipient|amount|nonce|CERT:<cert_id>|ASSET:<asset_sha256>[|PAYLOAD:<payload sha256>]
    cert-transfer: sender|recipient|amount|nonce|CERT:<cert_id>|TRANSFER
    The cert ID and asset hash are in the signed message, so neither
    can be swapped without breaking the signature and the txid."""
    base = f"{sender}|{recipient}|{amount}|{nonce}"
    if cert is not None:
        base += f"|CERT:{cert['cert_id']}|ASSET:{cert['asset_sha256']}"
        if data is not None:
            base += f"|PAYLOAD:{payload_sha256_hex(data)}"
        return base
    if cert_id is not None:
        return base + f"|CERT:{cert_id}|TRANSFER"
    return testnet_tx_message(sender, recipient, amount, nonce, data)


def cert_tx_id(sender: str, recipient: str, amount: int, nonce: int,
               cert=None, cert_id=None, data=None) -> str:
    return evo_hash_11(cert_tx_message(
        sender, recipient, amount, nonce, cert, cert_id, data).encode("utf-8")).hex()


def make_cert_mint_tx(wallet_path: str, password: str, owner_address: str,
                      cert: dict, nonce: int, data=None) -> dict:
    """Mint a certificate: a signed cert-mint transaction (amount 0).

    The wallet is the ISSUER: its address must be cert["issuer"] and
    its key signs BOTH the certificate and the transaction. The
    payload (the asset file, inline or ref) is validated first and
    its hash must match the certificate's asset_sha256."""
    if data is not None:
        ok, reason = validate_payload(data)
        if not ok:
            raise ValueError(f"invalid payload: {reason}")
        if data.get("sha256_of_original") != cert["asset_sha256"]:
            raise ValueError("payload sha256_of_original does not match "
                             "the certificate's asset_sha256")
    wallet, priv = _load_private(password, wallet_path)
    if wallet["address"] != cert["issuer"]:
        raise ValueError("issuing wallet address does not match cert['issuer'] — "
                         "only the issuer can mint their own certificate")
    signed_cert = sign_certificate(priv, cert) if "signature" not in cert else cert
    if not verify_certificate_signature(signed_cert):
        raise ValueError("certificate signature did not verify after signing")
    sender = wallet["address"]
    message = cert_tx_message(sender, owner_address, 0, nonce, signed_cert, None, data)
    tx = {
        "type": "cert-mint",
        "sender": sender,
        "recipient": owner_address,
        "amount": 0,
        "nonce": nonce,
        "cert": signed_cert,
        "signature": priv.sign(message.encode("utf-8")).hex(),
        "sender_pubkey_hex": wallet["public_key_hex"],
        "txid": cert_tx_id(sender, owner_address, 0, nonce, signed_cert, None, data),
    }
    if data is not None:
        tx["data"] = data
    return tx


def make_cert_transfer_tx(wallet_path: str, password: str, cert: dict,
                          to_address: str, nonce: int) -> dict:
    """Transfer a certificate to a new owner. The wallet must be the
    CURRENT owner — the node and the registry both check this, and
    this function checks it too before signing."""
    wallet, priv = _load_private(password, wallet_path)
    if wallet["address"] != cert.get("owner"):
        raise ValueError("transferring wallet is not the certificate's "
                         "current owner — only the owner can transfer it")
    if not verify_certificate_signature(cert):
        raise ValueError("certificate issuer signature does not verify — "
                         "refusing to transfer a bad certificate")
    sender = wallet["address"]
    message = cert_tx_message(sender, to_address, 0, nonce, None, cert["cert_id"], None)
    return {
        "type": "cert-transfer",
        "sender": sender,
        "recipient": to_address,
        "amount": 0,
        "nonce": nonce,
        "cert_id": cert["cert_id"],
        "cert": cert,
        "signature": priv.sign(message.encode("utf-8")).hex(),
        "sender_pubkey_hex": wallet["public_key_hex"],
        "txid": cert_tx_id(sender, to_address, 0, nonce, None, cert["cert_id"], None),
    }


# --- certificate registry (local file, mirrors the chain state) -------

def new_cert_registry() -> dict:
    return {"chain": "Mac 'N Cheese Chain", "ticker": TICKER,
            "certificates": {},  # cert_id -> {"cert": {...}, "owner": ..., "history": [...]}
            "warning": "Prototype local registry only — not a live chain. "
                       "Do not use for real funds or real legal proof."}


def load_cert_registry(path: str) -> dict:
    reg = json.loads(Path(path).read_text(encoding="utf-8"))
    reg.setdefault("certificates", {})
    return reg


def save_cert_registry(path: str, registry: dict) -> None:
    Path(path).write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def registry_apply_mint(registry: dict, tx: dict) -> dict:
    """Apply a cert-mint tx to a registry. Rejects duplicates."""
    cert = tx["cert"]
    if cert["cert_id"] in registry["certificates"]:
        raise ValueError(f"duplicate certificate {cert['cert_id']} — "
                         "this asset + issuer is already certified")
    if not verify_certificate_signature(cert):
        raise ValueError("certificate issuer signature does not verify")
    registry["certificates"][cert["cert_id"]] = {
        "cert": cert, "owner": cert["owner"],
        "history": [{"event": "minted", "owner": cert["owner"],
                     "issued_at": cert["issued_at"], "txid": tx["txid"]}],
    }
    return registry["certificates"][cert["cert_id"]]


def registry_apply_transfer(registry: dict, tx: dict) -> dict:
    """Apply a cert-transfer tx. Rejects transfers by a non-owner."""
    entry = registry["certificates"].get(tx["cert_id"])
    if entry is None:
        raise ValueError(f"unknown certificate {tx['cert_id']} — "
                         "it was never minted (in this registry)")
    if entry["owner"] != tx["sender"]:
        raise ValueError(f"transfer rejected: current owner is "
                         f"{entry['owner']}, not {tx['sender']}")
    entry["owner"] = tx["recipient"]
    entry["history"].append({"event": "transferred", "owner": tx["recipient"],
                             "from": tx["sender"], "txid": tx["txid"]})
    return entry


def registry_owner(registry: dict, cert_id: str):
    entry = registry["certificates"].get(cert_id)
    return entry["owner"] if entry else None


# ---------------------------------------------------------------------------
# Local ledger (genesis_allocation.json) — demo accounting, no live chain yet.
# ---------------------------------------------------------------------------

def new_ledger() -> dict:
    return {
        "chain": "Mac 'N Cheese Chain",
        "ticker": TICKER,
        "genesis_block_hash": GENESIS_BLOCK_HASH,
        "genesis_supply": GENESIS_SUPPLY,
        "allocations": [],
        "transfers": [],
        "warning": "Prototype local ledger only — not a live chain. "
                   "Do not use for real funds.",
    }


def load_ledger(path: str) -> dict:
    ledger = json.loads(Path(path).read_text(encoding="utf-8"))
    if ledger.get("ticker") not in (TICKER, "RONI"):
        raise ValueError(f"ledger ticker {ledger.get('ticker')!r} is not R0NI")
    ledger.setdefault("allocations", [])
    ledger.setdefault("transfers", [])
    return ledger


def save_ledger(path: str, ledger: dict) -> None:
    Path(path).write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def ledger_balance(ledger: dict, address: str) -> int:
    balance = 0
    for alloc in ledger.get("allocations", []):
        if alloc.get("address") == address:
            balance += int(alloc.get("amount", 0))
    for tx in ledger.get("transfers", []):
        if tx.get("to") == address:
            balance += int(tx.get("amount", 0))
        if tx.get("from") == address:
            balance -= int(tx.get("amount", 0))
    return balance


def allocate_genesis(ledger_path: str, wallet_path: str) -> dict:
    """Give the whole 100,000 R0NI genesis supply to one wallet address.

    Only allowed while allocations is empty — the first wallet Mac
    creates is the genesis holder. No address is pre-filled anywhere.
    """
    ledger = load_ledger(ledger_path)
    if ledger["allocations"]:
        raise SystemExit("genesis supply is already allocated — "
                         f"see {ledger['allocations']}")
    wallet = show_wallet(wallet_path)
    total = sum(int(a.get("amount", 0)) for a in ledger["allocations"])
    if total + GENESIS_SUPPLY > GENESIS_SUPPLY:
        raise SystemExit("genesis supply would be exceeded")
    ledger["allocations"].append({
        "address": wallet["address"],
        "amount": GENESIS_SUPPLY,
        "source": "genesis",
        "genesis_block_hash": GENESIS_BLOCK_HASH,
    })
    save_ledger(ledger_path, ledger)
    return {"address": wallet["address"], "amount": GENESIS_SUPPLY}


def record_transfer(ledger_path: str, wallet_path: str, password: str,
                    to_address: str, amount: int) -> dict:
    """Sign a local transfer with the sender's key, verify it, and record it.

    The transfer message is signed, the signature is verified against the
    sender's public key, and the sender's ledger balance is checked first.
    """
    if amount <= 0:
        raise SystemExit("amount must be a positive whole number of R0NI")
    ledger = load_ledger(ledger_path)
    wallet, priv = _load_private(password, wallet_path)
    from_address = wallet["address"]
    if to_address == from_address:
        raise SystemExit("cannot transfer to your own address")
    if ledger_balance(ledger, from_address) < amount:
        raise SystemExit(
            f"insufficient balance: {ledger_balance(ledger, from_address)} "
            f"R0NI available, {amount} R0NI requested")
    message = f"R0NI transfer {from_address} -> {to_address} : {amount}"
    signature_hex = priv.sign(message.encode("utf-8")).hex()
    if not verify_signature(wallet["public_key_hex"], message, signature_hex):
        raise SystemExit("internal error: fresh signature did not verify")
    tx = {
        "from": from_address,
        "to": to_address,
        "amount": amount,
        "message": message,
        "signature_hex": signature_hex,
        "public_key_hex": wallet["public_key_hex"],
    }
    ledger["transfers"].append(tx)
    save_ledger(ledger_path, ledger)
    return tx


def self_test():
    import tempfile
    print("R0NI Wallet prototype v0.2 — self-test")
    with tempfile.TemporaryDirectory() as d:
        p = f"{d}/test-wallet.json"
        w = create_wallet("test-password", p)
        print(f"1. created wallet, address {w['address']}")
        assert w["address"].startswith("R0NI-") and len(w["address"]) == 45
        assert w["ticker"] == "R0NI"
        assert show_wallet(p)["address"] == w["address"]
        print("2. show wallet ok")
        sig = sign_message("test-password", p, "hello R0NI")
        assert verify_signature(w["public_key_hex"], "hello R0NI", sig)
        print("3. sign + verify ok")
        assert not verify_signature(w["public_key_hex"], "tampered", sig)
        print("4. tampered message correctly rejected")
        try:
            sign_message("wrong-password", p, "hello R0NI")
            print("5. FAIL: wrong password signed!")
            raise SystemExit(1)
        except SystemExit:
            raise
        except Exception:
            print("5. wrong password correctly rejected")
        # Ledger: empty genesis allocation, then allocate + transfer.
        ledger_path = f"{d}/genesis_allocation.json"
        ledger = new_ledger()
        assert ledger["allocations"] == [] and ledger["genesis_supply"] == 100000
        assert ledger["genesis_block_hash"] == GENESIS_BLOCK_HASH
        save_ledger(ledger_path, ledger)
        assert ledger_balance(load_ledger(ledger_path), w["address"]) == 0
        print("6. empty genesis ledger ok, balance 0")
        allocate_genesis(ledger_path, p)
        assert ledger_balance(load_ledger(ledger_path), w["address"]) == 100000
        print("7. genesis allocation ok, balance 100,000 R0NI")
        try:
            allocate_genesis(ledger_path, p)
            print("8. FAIL: second genesis allocation allowed!")
            raise SystemExit(1)
        except SystemExit as e:
            if "already allocated" not in str(e):
                raise
            print("8. second genesis allocation correctly rejected")
        q = f"{d}/test-wallet-2.json"
        w2 = create_wallet("test-password", q)
        tx = record_transfer(ledger_path, p, "test-password", w2["address"], 25000)
        assert verify_signature(tx["public_key_hex"], tx["message"], tx["signature_hex"])
        ledger = load_ledger(ledger_path)
        assert ledger_balance(ledger, w["address"]) == 75000
        assert ledger_balance(ledger, w2["address"]) == 25000
        print("9. signed transfer ok, balances 75,000 / 25,000 R0NI")
        try:
            record_transfer(ledger_path, p, "test-password", w2["address"], 999999)
            print("10. FAIL: overspend allowed!")
            raise SystemExit(1)
        except SystemExit as e:
            if "insufficient balance" not in str(e):
                raise
            print("10. overspend correctly rejected")
        # Payloads (format v2): roundtrips + rejections.
        import random
        text = make_text_payload("Hello R0NI — a message on the chain")
        assert validate_payload(text)[0] and extract_payload_bytes(text) == "Hello R0NI — a message on the chain".encode("utf-8")
        print("11. text payload roundtrip ok")
        try:
            make_text_payload("x" * 1001)
            print("12. FAIL: 1,001-char text accepted!")
            raise SystemExit(1)
        except ValueError as e:
            assert "max is 1000" in str(e)
            print("12. over-long text correctly rejected")
        png = b"\x89PNG\r\n\x1a\n" + bytes(random.Random(7).randrange(256) for _ in range(5000))
        img = make_media_payload(png, "image", "image/png", "test.png")
        assert validate_payload(img)[0] and extract_payload_bytes(img) == png
        info = extract_payload_to_file(img, f"{d}/out.png")
        assert info["sha256_verified"] and Path(f"{d}/out.png").read_bytes() == png
        print(f"13. image payload roundtrip ok (raw {len(png)} B, compressed {img['compressed_size']} B)")
        # Incompressible data: 1.5 MB random -> compressed stays > 1 MB.
        big_random = random.Random(42).randbytes(1_500_000)
        try:
            make_media_payload(big_random, "other", "application/octet-stream", "big.bin")
            print("14. FAIL: >1 MB compressed payload accepted!")
            raise SystemExit(1)
        except ValueError as e:
            assert "ref" in str(e)
            print("14. incompressible >1 MB compressed payload correctly rejected (use ref)")
        try:
            make_media_payload(b"x" * (MAX_MEDIA_RAW_BYTES + 1), "other", "application/octet-stream")
            print("15. FAIL: >5 MB raw payload accepted!")
            raise SystemExit(1)
        except ValueError as e:
            assert "5 MB" in str(e) or "ref" in str(e)
            print("15. >5 MB raw payload correctly rejected (use ref)")
        corrupt = dict(img)
        blob = bytearray(base64.b64decode(img["data_b64"]))
        blob[len(blob) // 2] ^= 0xFF
        corrupt["data_b64"] = base64.b64encode(bytes(blob)).decode()
        assert not validate_payload(corrupt)[0]
        print("16. corrupted compressed data correctly rejected")
        bad_hash = dict(img)
        bad_hash["sha256_of_original"] = "0" * 64
        assert not validate_payload(bad_hash)[0]
        print("17. sha256 mismatch correctly rejected")
        bad_mime = dict(img)
        bad_mime["mime"] = "text/plain"
        assert not validate_payload(bad_mime)[0]
        print("18. bad mime correctly rejected")
        ref = make_ref_payload("https://example.invalid/song.mp3", "audio/mpeg",
                               12_000_000, hashlib.sha256(b"song").hexdigest(), "song.mp3")
        assert validate_payload(ref)[0]
        print("19. off-chain ref payload validates ok")
        tx2 = make_testnet_tx(p, "test-password", w2["address"], 100, 0, text)
        assert tx2["data"] == text and tx2["txid"] == testnet_tx_id(
            tx2["sender"], tx2["recipient"], 100, 0, text)
        assert verify_signature(tx2["sender_pubkey_hex"],
                                testnet_tx_message(tx2["sender"], tx2["recipient"], 100, 0, text),
                                tx2["signature"])
        tx2_tampered = dict(tx2)
        tx2_tampered["data"] = make_text_payload("tampered")
        assert tx2_tampered["txid"] != testnet_tx_id(
            tx2_tampered["sender"], tx2_tampered["recipient"], 100, 0, tx2_tampered["data"])
        print("20. signed v2 tx ok; tampering the payload changes the txid (signature breaks)")
        tx1 = make_testnet_tx(p, "test-password", w2["address"], 100, 1)
        assert "data" not in tx1
        print("21. v1 tx without payload still works (backward compatible)")
        # Certificates / NFTs (v0.3): mint, verify, transfer, rejections.
        import struct as _struct
        # A minimal valid PNG (1x1) + a document + a small WAV.
        png_cert = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
                    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
                    b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
        doc_cert = ("CERTIFICATE OF OWNERSHIP\nAsset: 1967 Ford Mustang, "
                    "VIN 7T02C123456\nOwner: Mac Beck\n").encode("utf-8")
        wav_cert = (b"RIFF" + _struct.pack("<I", 44) + b"WAVEfmt "
                    + _struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
                    + b"data" + _struct.pack("<I", 8) + b"\x00\x00" * 4)
        reg = new_cert_registry()
        # PNG certificate: issuer w, owner w2.
        png_hash = hashlib.sha256(png_cert).hexdigest()
        png_payload = make_media_payload(png_cert, "image", "image/png", "mustang.png")
        cert_png = make_certificate(png_hash, w["address"], w["public_key_hex"],
                                    w2["address"], "1967 Ford Mustang — photo",
                                    "image", "image/png", "mustang.png")
        mint_png = make_cert_mint_tx(p, "test-password", w2["address"], cert_png, 0, png_payload)
        assert mint_png["type"] == "cert-mint" and mint_png["amount"] == 0
        assert verify_certificate(mint_png["cert"], png_cert)[0]
        assert registry_apply_mint(reg, mint_png)["owner"] == w2["address"]
        print(f"22. PNG certificate minted + verified (cert_id "
              f"{cert_png['cert_id'][:14]}…, asset SHA-256 matches)")
        # Document certificate.
        doc_hash = hashlib.sha256(doc_cert).hexdigest()
        doc_payload = make_text_payload(doc_cert.decode("utf-8"))
        cert_doc = make_certificate(doc_hash, w["address"], w["public_key_hex"],
                                    w2["address"], "Mustang ownership document",
                                    "document", "text/plain", "ownership.txt")
        mint_doc = make_cert_mint_tx(p, "test-password", w2["address"], cert_doc, 1, doc_payload)
        assert verify_certificate(mint_doc["cert"], doc_cert)[0]
        registry_apply_mint(reg, mint_doc)
        print("23. document certificate minted + verified")
        # Audio certificate, then transfer to a third wallet.
        wav_hash = hashlib.sha256(wav_cert).hexdigest()
        wav_payload = make_media_payload(wav_cert, "audio", "audio/wav", "song.wav")
        cert_wav = make_certificate(wav_hash, w["address"], w["public_key_hex"],
                                    w2["address"], "Original song demo",
                                    "audio", "audio/wav", "song.wav")
        mint_wav = make_cert_mint_tx(p, "test-password", w2["address"], cert_wav, 2, wav_payload)
        registry_apply_mint(reg, mint_wav)
        assert verify_certificate(mint_wav["cert"], wav_cert)[0]
        q3 = f"{d}/test-wallet-3.json"
        w3 = create_wallet("test-password", q3)
        xfer = make_cert_transfer_tx(q, "test-password", mint_wav["cert"], w3["address"], 0)
        assert xfer["type"] == "cert-transfer"
        registry_apply_transfer(reg, xfer)
        assert registry_owner(reg, cert_wav["cert_id"]) == w3["address"]
        ok, st = verify_certificate(mint_wav["cert"], wav_cert, current_owner=w3["address"])
        assert ok and st["status"] == "valid"
        print("24. audio certificate minted, transferred w2 -> w3, "
              "verified under the new owner")
        # Rejections: forged issuer signature.
        forged = dict(mint_png["cert"])
        forged["signature"] = "00" * 64
        assert not verify_certificate_signature(forged)
        print("25. forged issuer signature correctly rejected")
        # Tampered asset file (hash mismatch).
        tampered_png = bytearray(png_cert)
        tampered_png[-1] ^= 0xFF
        ok, st = verify_certificate(mint_png["cert"], bytes(tampered_png))
        assert not ok and st["status"] == "asset_hash_mismatch"
        print("26. tampered asset file correctly rejected (SHA-256 mismatch)")
        # Duplicate certificate (same asset + same issuer).
        try:
            registry_apply_mint(reg, mint_png)
            print("27. FAIL: duplicate certificate accepted!")
            raise SystemExit(1)
        except ValueError as e:
            assert "duplicate" in str(e)
            print("27. duplicate certificate correctly rejected")
        # Transfer by a non-owner (w, the issuer, is not the owner w2).
        try:
            make_cert_transfer_tx(p, "test-password", mint_png["cert"], w3["address"], 5)
            print("28. FAIL: transfer by non-owner signed!")
            raise SystemExit(1)
        except ValueError as e:
            assert "not the certificate's" in str(e) or "current owner" in str(e)
            print("28. transfer by non-owner correctly rejected")
        # Expired certificate verifies as expired, not valid.
        # (issued now, expiry 10 seconds ago — built via issued_at
        #  in the past so expires_at > issued_at still holds.)
        _now = int(__import__("time").time())
        old = make_certificate(png_hash, w["address"], w["public_key_hex"],
                               w2["address"], "expired example", "image",
                               "image/png", "mustang.png",
                               expires_at=_now - 10, issued_at=_now - 3600)
        old_signed = sign_certificate(
            Ed25519PrivateKey.from_private_bytes(
                base64.b64decode(decrypt_b64("test-password", json.loads(Path(p).read_text())["encrypted_private_key"]))),
            old)
        ok, st = verify_certificate(old_signed, png_cert)
        assert not ok and st["status"] == "expired"
        print("29. expired certificate correctly reports 'expired', not valid")
    print("ALL TESTS PASSED")


def _usage():
    print("usage:")
    print("  python3 roni_wallet.py                              # self-test")
    print("  python3 roni_wallet.py create <wallet.json> <password>")
    print("  python3 roni_wallet.py show <wallet.json>")
    print("  python3 roni_wallet.py sign <wallet.json> <password> <message>")
    print("  python3 roni_wallet.py verify <public-key-hex> <message> <signature-hex>")
    print("  python3 roni_wallet.py init-ledger [genesis_allocation.json]")
    print("  python3 roni_wallet.py allocate-genesis <ledger.json> <wallet.json>")
    print("  python3 roni_wallet.py balance <ledger.json> <address>")
    print("  python3 roni_wallet.py transfer <ledger.json> <wallet.json> <password> <to-address> <amount>")
    print("  python3 roni_wallet.py payload-text <message>")
    print("  python3 roni_wallet.py payload-file <path> [--kind K] [--mime M]")
    print("  python3 roni_wallet.py payload-ref <uri> <mime> <size> <sha256> [--filename F]")
    print("  python3 roni_wallet.py validate-payload <payload.json>")
    print("  python3 roni_wallet.py make-tx <wallet.json> <password> <to> <amount> <nonce> [payload.json]")
    print("  python3 roni_wallet.py extract <tx.json> <output-path>")
    print("  python3 roni_wallet.py cert-mint <wallet.json> <password> <asset-file> <owner> <description> <nonce> [--expires <unix>] [--registry certs.json]")
    print("  python3 roni_wallet.py cert-verify <cert.json> [asset-file] [--registry certs.json]")
    print("  python3 roni_wallet.py cert-transfer <wallet.json> <password> <cert.json> <to> <nonce> [--registry certs.json]")


_KIND_BY_EXT = {
    ".png": ("image", "image/png"), ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"), ".webp": ("image", "image/webp"),
    ".gif": ("gif", "image/gif"),
    ".wav": ("audio", "audio/wav"), ".mp3": ("audio", "audio/mpeg"),
    ".ogg": ("audio", "audio/ogg"),
    ".mp4": ("video", "video/mp4"), ".webm": ("video", "video/webm"),
    ".mov": ("video", "video/quicktime"),
    ".txt": ("text", "text/plain"),
}


def _parse_opts(argv):
    """Parse CLI options in both `--key=value` and `--key value` form.

    (The cert commands document `--registry certs.json` with a
    space; accepting only `--key=value` silently dropped it and the
    registry was never written — a real bug found by the CLI test.)"""
    opts = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if "=" in a:
                k, v = a[2:].split("=", 1)
                opts[k] = v
            elif i + 1 < len(argv):
                opts[a[2:]] = argv[i + 1]
                i += 1
        i += 1
    return opts


def _payload_file_cli(path, kind=None, mime=None):
    """Build a payload from a file on disk (payload-file CLI)."""
    raw = Path(path).read_bytes()
    ext = Path(path).suffix.lower()
    if ext == ".txt" and kind is None and mime is None:
        return make_text_payload(raw.decode("utf-8"))
    inferred_kind, inferred_mime = _KIND_BY_EXT.get(ext, ("other", "application/octet-stream"))
    kind = kind or inferred_kind
    mime = mime or inferred_mime
    return make_media_payload(raw, kind, mime, Path(path).name)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        self_test()
    elif args[0] == "create" and len(args) == 3:
        w = create_wallet(args[2], args[1])
        print(json.dumps(show_wallet(args[1]), indent=2))
    elif args[0] == "show" and len(args) == 2:
        print(json.dumps(show_wallet(args[1]), indent=2))
    elif args[0] == "sign" and len(args) == 4:
        print(sign_message(args[2], args[1], args[3]))
    elif args[0] == "verify" and len(args) == 4:
        print(verify_signature(args[1], args[2], args[3]))
    elif args[0] == "init-ledger" and len(args) in (1, 2):
        path = args[1] if len(args) == 2 else "genesis_allocation.json"
        if Path(path).exists():
            raise SystemExit(f"{path} already exists — refusing to overwrite")
        save_ledger(path, new_ledger())
        print(f"created {path} (allocations empty — allocate the genesis "
              "supply to Mac's wallet with allocate-genesis)")
    elif args[0] == "allocate-genesis" and len(args) == 3:
        print(json.dumps(allocate_genesis(args[1], args[2]), indent=2))
    elif args[0] == "balance" and len(args) == 3:
        ledger = load_ledger(args[1])
        print(json.dumps({
            "address": args[2],
            "balance_R0NI": ledger_balance(ledger, args[2]),
            "genesis_supply": ledger.get("genesis_supply"),
        }, indent=2))
    elif args[0] == "transfer" and len(args) == 6:
        try:
            amount = int(args[5])
        except ValueError:
            raise SystemExit("amount must be a whole number of R0NI") from None
        print(json.dumps(record_transfer(args[1], args[2], args[3], args[4], amount), indent=2))
    elif args[0] == "payload-text" and len(args) == 2:
        try:
            print(json.dumps(make_text_payload(args[1]), indent=2))
        except ValueError as e:
            raise SystemExit(str(e)) from None
    elif args[0] == "payload-file" and len(args) >= 2:
        opts = dict(a.split("=", 1) for a in args[2:] if a.startswith("--") and "=" in a)
        try:
            print(json.dumps(_payload_file_cli(args[1], opts.get("kind"), opts.get("mime")), indent=2))
        except (ValueError, UnicodeDecodeError) as e:
            raise SystemExit(str(e)) from None
    elif args[0] == "payload-ref" and len(args) >= 5:
        opts = dict(a.split("=", 1) for a in args[5:] if a.startswith("--") and "=" in a)
        try:
            size = int(args[3])
        except ValueError:
            raise SystemExit("original size must be a whole number of bytes") from None
        try:
            print(json.dumps(make_ref_payload(args[1], args[2], size, args[4],
                                              opts.get("filename")), indent=2))
        except ValueError as e:
            raise SystemExit(str(e)) from None
    elif args[0] == "validate-payload" and len(args) == 2:
        data = json.loads(Path(args[1]).read_text())
        ok, reason = validate_payload(data)
        print(json.dumps({"valid": ok, "reason": reason}, indent=2))
        raise SystemExit(0 if ok else 1)
    elif args[0] == "make-tx" and len(args) in (6, 7):
        try:
            amount, nonce = int(args[4]), int(args[5])
        except ValueError:
            raise SystemExit("amount and nonce must be whole numbers") from None
        data = None
        if len(args) == 7:
            data = json.loads(Path(args[6]).read_text())
        try:
            print(json.dumps(make_testnet_tx(args[1], args[2], args[3], amount, nonce, data), indent=2))
        except (ValueError, SystemExit) as e:
            raise SystemExit(str(e)) from None
    elif args[0] == "extract" and len(args) == 3:
        tx = json.loads(Path(args[1]).read_text())
        if "data" not in tx or tx["data"] is None:
            raise SystemExit("transaction has no payload (no 'data' field)")
        try:
            print(json.dumps(extract_payload_to_file(tx["data"], args[2]), indent=2))
        except ValueError as e:
            raise SystemExit(str(e)) from None
    elif args[0] == "cert-mint" and len(args) >= 7:
        opts = _parse_opts(args[7:])
        try:
            nonce = int(args[6])
        except ValueError:
            raise SystemExit("nonce must be a whole number") from None
        try:
            asset = Path(args[3]).read_bytes()
            payload = _payload_file_cli(args[3])
            # _payload_file_cli returns a text payload for .txt files;
            # for a certificate the asset kind is "document" then.
            asset_kind = "document" if payload["kind"] == "text" else payload["kind"]
            wallet = show_wallet(args[1])
            cert = make_certificate(
                hashlib.sha256(asset).hexdigest(), wallet["address"],
                wallet["public_key_hex"], args[4], args[5],
                asset_kind, payload["mime"], payload.get("filename"),
                expires_at=int(opts["expires"]) if "expires" in opts else None)
            tx = make_cert_mint_tx(args[1], args[2], args[4], cert, nonce, payload)
            if "registry" in opts:
                reg = (load_cert_registry(opts["registry"])
                       if Path(opts["registry"]).exists() else new_cert_registry())
                registry_apply_mint(reg, tx)
                save_cert_registry(opts["registry"], reg)
            print(json.dumps(tx, indent=2))
        except (ValueError, SystemExit) as e:
            raise SystemExit(str(e)) from None
    elif args[0] == "cert-verify" and len(args) >= 2:
        # Parse from args[2:]: the asset file (if any) sits at
        # args[2] and --registry may sit there too when no asset
        # file is given. _parse_opts skips non-option words.
        opts = _parse_opts(args[2:])
        cert = json.loads(Path(args[1]).read_text())
        cert = cert.get("cert", cert)  # accept a mint tx or a bare cert
        asset = Path(args[2]).read_bytes() if len(args) >= 3 and not args[2].startswith("--") else None
        current_owner = None
        if "registry" in opts and Path(opts["registry"]).exists():
            current_owner = registry_owner(load_cert_registry(opts["registry"]), cert["cert_id"])
        ok, status = verify_certificate(cert, asset, current_owner)
        print(json.dumps({"valid": ok, **status}, indent=2))
        raise SystemExit(0 if ok else 1)
    elif args[0] == "cert-transfer" and len(args) >= 6:
        opts = _parse_opts(args[6:])
        try:
            nonce = int(args[5])
        except ValueError:
            raise SystemExit("nonce must be a whole number") from None
        try:
            cert = json.loads(Path(args[3]).read_text())
            cert = cert.get("cert", cert)
            tx = make_cert_transfer_tx(args[1], args[2], cert, args[4], nonce)
            if "registry" in opts and Path(opts["registry"]).exists():
                reg = load_cert_registry(opts["registry"])
                registry_apply_transfer(reg, tx)
                save_cert_registry(opts["registry"], reg)
            print(json.dumps(tx, indent=2))
        except (ValueError, SystemExit) as e:
            raise SystemExit(str(e)) from None
    else:
        _usage()
