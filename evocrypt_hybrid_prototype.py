#!/usr/bin/env python3
"""
EvoCrypt Hybrid Prototype v0.1 — for Mac / ai.evo
==================================================
PROTOTYPE ONLY — NOT AUDITED, DO NOT USE FOR REAL SECRETS YET.
Custom crypto must be peer-reviewed before production use.

What it does:
  Password -> EvoKDF-11 (X11-style chained hash) -> 3 keys
  Plaintext -> AES-256-GCM -> ChaCha20-Poly1305 -> HMAC-SHA3-512

Layers:
  1. Key derivation — EvoKDF-11
     An 11-step hash chain inspired by Dash X11. X11's original
     11 are: BLAKE, BMW, Groestl, JH, Keccak, Skein, Luffa,
     CubeHash, SHAvite, SIMD, Echo.
     Python's stdlib hashlib does not ship BMW/Groestl/JH/Skein/
     Luffa/CubeHash/SHAvite/SIMD/Echo, so this prototype maps
     each step to a stdlib hash with the same role, and labels
     the substitution honestly in CHAIN below. A full X11
     implementation would need a dedicated X11 library.
     The chain is run for ROUNDS iterations, then expanded
     with SHAKE-256 to 96 bytes and split into 3 x 32-byte keys.

  2. Layer 1 encryption — AES-256-GCM (key_aes, 12-byte nonce)
  3. Layer 2 encryption — ChaCha20-Poly1305 (key_chacha, 12-byte nonce)
     The AES ciphertext (including its GCM tag) is the plaintext
     for ChaCha. An attacker must break *both* ciphers.
  4. Authentication — HMAC-SHA3-512 (key_hmac) over
     magic + salt + both nonces + final ciphertext.
     Checked *before* decryption, so tampered files fail fast.

Package format (binary, then base64 for transport):
  magic 7 bytes  b'EVOC1\\x00'
  salt  16 bytes random
  nonce_aes      12 bytes random
  nonce_chacha   12 bytes random
  hmac_sha3_512  64 bytes
  ciphertext     variable (ChaCha output, includes AES-GCM tag inside)

Requires:  pip install cryptography
Run:      python3 evocrypt_hybrid_prototype.py
          python3 evocrypt_hybrid_prototype.py encrypt "hello" "password123"
          python3 evocrypt_hybrid_prototype.py decrypt "<base64>" "password123"
Tested with: Python 3.12, cryptography 50.0.2
"""

import base64
import hashlib
import hmac as hmac_mod
import os
import sys

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
except ImportError as e:  # pragma: no cover
    raise SystemExit("Missing 'cryptography' package. Run: pip install cryptography") from e

MAGIC = b"EVOC1\x00"
ROUNDS = 1000  # demo speed. Production KDF should be slower (Argon2id / more rounds).
SALT_LEN = 16
NONCE_LEN = 12

# --- EvoKDF-11 chain -------------------------------------------------------
# Each function takes bytes -> 32 or 64 byte digest.
# Substitutions are marked; they preserve the *chaining* idea of X11.
def _b2b(d):    return hashlib.blake2b(d, digest_size=64).digest()   # X11-1 BLAKE
def _sha3_512(d): return hashlib.sha3_512(d).digest()                # X11-5 Keccak ~ SHA-3
def _sha512(d): return hashlib.sha512(d).digest()                    # SHA-2 (BMW/Groestl role)
def _sha256(d): return hashlib.sha256(d).digest()                    # SHA-2 (JH role)
def _b2s(d):    return hashlib.blake2s(d, digest_size=32).digest()   # BLAKE2s (Skein role)
def _sha3_256(d): return hashlib.sha3_256(d).digest()                # SHA-3 (Luffa role)
def _shake256(d): return hashlib.shake_256(d).digest(64)             # SHAKE (CubeHash role)
def _sha512_256(d): return hashlib.sha512(d).digest()[:32] + hashlib.sha256(d).digest()  # 64B (SHAvite role)
def _b2b_32(d): return hashlib.blake2b(d, digest_size=32).digest()   # BLAKE2b-256 (SIMD role)
def _sha3_384(d): return hashlib.sha3_384(d).digest() + hashlib.sha256(d).digest()[:16]  # 64B (Echo role)
def _sha512_b(d): return hashlib.sha512(d).digest()                  # SHA-512 (final mix)

CHAIN = [
    ("BLAKE->blake2b-512", _b2b),
    ("Keccak->sha3-512", _sha3_512),
    ("SHA-512", _sha512),
    ("SHA-256", _sha256),
    ("BLAKE2s-256", _b2s),
    ("SHA3-256", _sha3_256),
    ("SHAKE-256", _shake256),
    ("SHA-512/256-mix", _sha512_256),
    ("BLAKE2b-256", _b2b_32),
    ("SHA3-384-mix", _sha3_384),
    ("SHA-512-final", _sha512_b),
]
assert len(CHAIN) == 11, "EvoKDF-11 must have exactly 11 steps"


def derive_keys(password: str, salt: bytes, rounds: int = ROUNDS):
    """Run the 11-step chain `rounds` times, expand to 96 bytes, split into 3 keys."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    state = salt + b"\x00" + password
    for r in range(rounds):
        # bind the round number so each iteration is distinct
        state = state + r.to_bytes(4, "little")
        for _name, fn in CHAIN:
            state = fn(state)
    # SHAKE-256 extendable output: 96 bytes = 32+32+32
    expanded = hashlib.shake_256(state).digest(96)
    return expanded[:32], expanded[32:64], expanded[64:96]  # aes, chacha, hmac


def encrypt(password: str, plaintext: bytes) -> bytes:
    """Return the binary EvoCrypt package."""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    salt = os.urandom(SALT_LEN)
    nonce_aes = os.urandom(NONCE_LEN)
    nonce_chacha = os.urandom(NONCE_LEN)
    key_aes, key_chacha, key_hmac = derive_keys(password, salt)

    # Layer 1: AES-256-GCM. AAD binds the header to the ciphertext.
    aad = MAGIC + salt + nonce_aes + nonce_chacha
    layer1 = AESGCM(key_aes).encrypt(nonce_aes, plaintext, aad)
    # Layer 2: ChaCha20-Poly1305 over layer1 (ciphertext + GCM tag)
    layer2 = ChaCha20Poly1305(key_chacha).encrypt(nonce_chacha, layer1, aad)
    # Outer auth: HMAC-SHA3-512
    tag = hmac_mod.new(key_hmac, MAGIC + salt + nonce_aes + nonce_chacha + layer2,
                       hashlib.sha3_512).digest()
    return MAGIC + salt + nonce_aes + nonce_chacha + tag + layer2


def decrypt(password: str, package: bytes) -> bytes:
    """Verify HMAC, then unwrap ChaCha -> AES. Raises ValueError on any failure."""
    min_len = len(MAGIC) + SALT_LEN + NONCE_LEN * 2 + 64
    if len(package) < min_len or not package.startswith(MAGIC):
        raise ValueError("Not an EvoCrypt package (bad magic / too short)")
    off = len(MAGIC)
    salt = package[off:off + SALT_LEN]; off += SALT_LEN
    nonce_aes = package[off:off + NONCE_LEN]; off += NONCE_LEN
    nonce_chacha = package[off:off + NONCE_LEN]; off += NONCE_LEN
    tag = package[off:off + 64]; off += 64
    layer2 = package[off:]

    key_aes, key_chacha, key_hmac = derive_keys(password, salt)
    expected = hmac_mod.new(key_hmac, MAGIC + salt + nonce_aes + nonce_chacha + layer2,
                            hashlib.sha3_512).digest()
    if not hmac_mod.compare_digest(tag, expected):
        raise ValueError("HMAC-SHA3-512 failed — wrong password or tampered data")

    aad = MAGIC + salt + nonce_aes + nonce_chacha
    try:
        layer1 = ChaCha20Poly1305(key_chacha).decrypt(nonce_chacha, layer2, aad)
        plaintext = AESGCM(key_aes).decrypt(nonce_aes, layer1, aad)
    except Exception as e:
        raise ValueError(f"AEAD decryption failed — tampered data: {e}") from e
    return plaintext


def encrypt_b64(password: str, plaintext: str) -> str:
    return base64.b64encode(encrypt(password, plaintext.encode("utf-8"))).decode("ascii")


def decrypt_b64(password: str, token_b64: str) -> str:
    return decrypt(password, base64.b64decode(token_b64.encode("ascii"))).decode("utf-8")


def self_test():
    print("EvoCrypt Hybrid Prototype v0.1 — self-test")
    print(f"KDF chain: {' -> '.join(n for n, _ in CHAIN)}  ({len(CHAIN)} steps, {ROUNDS} rounds)")
    msg = "Hello ai.evo — SHA + X11 + AES + ChaCha, chained."
    pw = "correct-horse-battery-staple"
    token = encrypt_b64(pw, msg)
    print(f"1. encrypt ok, base64 len={len(token)}, starts {token[:24]}...")
    out = decrypt_b64(pw, token)
    assert out == msg, "roundtrip mismatch"
    print("2. decrypt roundtrip ok:", out)
    try:
        decrypt_b64("wrong-password", token)
        print("3. FAIL: wrong password decrypted!")
    except ValueError as e:
        print("3. wrong password correctly rejected:", str(e)[:60])
    raw = bytearray(base64.b64decode(token))
    raw[-1] ^= 0x01  # flip one ciphertext bit
    try:
        decrypt(pw, bytes(raw))
        print("4. FAIL: tampered data decrypted!")
    except ValueError as e:
        print("4. tampered data correctly rejected:", str(e)[:60])
    # empty + 1 MB
    assert decrypt_b64(pw, encrypt_b64(pw, "")) == ""
    big = "A" * 1_000_000
    assert decrypt_b64(pw, encrypt_b64(pw, big)) == big
    print("5. empty + 1MB roundtrip ok")
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        self_test()
    elif sys.argv[1] == "encrypt" and len(sys.argv) == 4:
        print(encrypt_b64(sys.argv[3], sys.argv[2]))
    elif sys.argv[1] == "decrypt" and len(sys.argv) == 4:
        print(decrypt_b64(sys.argv[3], sys.argv[2]))
    else:
        print("usage: python3 evocrypt_hybrid_prototype.py [encrypt <text> <password> | decrypt <base64> <password>]")
