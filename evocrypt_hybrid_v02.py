#!/usr/bin/env python3
"""
EvoCrypt Hybrid Prototype v0.2 — for Mac / ai.evo
==================================================
PROTOTYPE ONLY — NOT AUDITED, DO NOT USE FOR REAL SECRETS YET.
Custom crypto must be peer-reviewed before production use.

New in v0.2 (built 2026-11-13, held — not yet sent to Mac):
  * File mode: lock a whole file, not just short text.
      python3 evocrypt_hybrid_v02.py encrypt-file notes.txt notes.evoc "password"
      python3 evocrypt_hybrid_v02.py decrypt-file notes.evoc notes.txt "password"
    A .evoc file is the raw binary EvoCrypt package (no base64).
    It decrypts with the same password. Whole file is read into
    memory, so keep files modest on a phone (tested to 1 MB here).
  * Opt-in Argon2id KDF: --argon2 flag on encrypt / decrypt /
    encrypt-file / decrypt-file. Argon2id replaces EvoKDF-11 for
    key derivation only; the AES + ChaCha layers are unchanged.
    Argon2id packages use magic EVOC2, EvoKDF-11 packages use
    EVOC1, and decrypt auto-detects which one it is — so v0.1
    (EVOC1) packages still open in v0.2.
    Requires argon2-cffi, which is NOT in Termux's
    python-cryptography package:
      desktop:  pip install argon2-cffi
      Termux:   try `pkg install python-argon2-cffi` — NOT verified
                on the A17 yet; if that package does not exist,
                Argon2id will not run in Termux and EvoKDF-11
                (the default) is the one to use there.
    Default (no flag) is still EvoKDF-11, so v0.2 runs in Termux
    exactly like v0.1: `pkg install python python-cryptography`
    (never `pip install cryptography` on Termux).

What it does (unchanged core):
  Password -> EvoKDF-11 (X11-style chained hash) -> 3 keys
  Plaintext -> AES-256-GCM -> ChaCha20-Poly1305 -> HMAC-SHA3-512

Requires:  cryptography (Termux: pkg install python-cryptography)
Optional:  argon2-cffi, only for --argon2
Run:       python3 evocrypt_hybrid_v02.py
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
    raise SystemExit("Missing 'cryptography' package. Run: pip install cryptography "
                     "(on Termux: pkg install python-cryptography)") from e

MAGIC = b"EVOC1\x00"    # EvoKDF-11 package
MAGIC2 = b"EVOC2\x00"   # Argon2id package
ROUNDS = 1000  # demo speed. Production KDF should be slower (Argon2id / more rounds).
SALT_LEN = 16
NONCE_LEN = 12

# --- EvoKDF-11 chain (v0.1, unchanged) ------------------------------------
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
    """EvoKDF-11: 11-step chain, `rounds` times, SHAKE-256 expand to 96 bytes."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    state = salt + b"\x00" + password
    for r in range(rounds):
        state = state + r.to_bytes(4, "little")
        for _name, fn in CHAIN:
            state = fn(state)
    expanded = hashlib.shake_256(state).digest(96)
    return expanded[:32], expanded[32:64], expanded[64:96]


def derive_keys_argon2(password: str, salt: bytes):
    """Argon2id (opt-in): 96 bytes out, split into the same 3 keys."""
    try:
        from argon2.low_level import hash_secret_raw, Type
    except ImportError as e:
        raise SystemExit(
            "argon2-cffi is not installed, so --argon2 cannot run.\n"
            "  desktop: pip install argon2-cffi\n"
            "  Termux:  try `pkg install python-argon2-cffi` (not verified on the A17 yet)\n"
            "Without it, drop --argon2 and use the default EvoKDF-11."
        ) from e
    if isinstance(password, str):
        password = password.encode("utf-8")
    # time_cost=3, memory_cost=64 MiB, parallelism=4 — OWASP-ish baseline.
    raw = hash_secret_raw(password, salt, time_cost=3, memory_cost=65536,
                          parallelism=4, hash_len=96, type=Type.ID)
    return raw[:32], raw[32:64], raw[64:96]


def _derive(password, salt, use_argon2):
    return derive_keys_argon2(password, salt) if use_argon2 else derive_keys(password, salt)


def encrypt(password: str, plaintext: bytes, use_argon2: bool = False) -> bytes:
    """Return the binary EvoCrypt package (EVOC1 or EVOC2 by KDF)."""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    magic = MAGIC2 if use_argon2 else MAGIC
    salt = os.urandom(SALT_LEN)
    nonce_aes = os.urandom(NONCE_LEN)
    nonce_chacha = os.urandom(NONCE_LEN)
    key_aes, key_chacha, key_hmac = _derive(password, salt, use_argon2)

    aad = magic + salt + nonce_aes + nonce_chacha
    layer1 = AESGCM(key_aes).encrypt(nonce_aes, plaintext, aad)
    layer2 = ChaCha20Poly1305(key_chacha).encrypt(nonce_chacha, layer1, aad)
    tag = hmac_mod.new(key_hmac, magic + salt + nonce_aes + nonce_chacha + layer2,
                       hashlib.sha3_512).digest()
    return magic + salt + nonce_aes + nonce_chacha + tag + layer2


def decrypt(password: str, package: bytes) -> bytes:
    """Auto-detect EVOC1 / EVOC2, verify HMAC, then unwrap ChaCha -> AES."""
    if package.startswith(MAGIC2):
        magic, use_argon2 = MAGIC2, True
    elif package.startswith(MAGIC):
        magic, use_argon2 = MAGIC, False
    else:
        raise ValueError("Not an EvoCrypt package (bad magic / too short)")
    min_len = len(magic) + SALT_LEN + NONCE_LEN * 2 + 64
    if len(package) < min_len:
        raise ValueError("Not an EvoCrypt package (bad magic / too short)")
    off = len(magic)
    salt = package[off:off + SALT_LEN]; off += SALT_LEN
    nonce_aes = package[off:off + NONCE_LEN]; off += NONCE_LEN
    nonce_chacha = package[off:off + NONCE_LEN]; off += NONCE_LEN
    tag = package[off:off + 64]; off += 64
    layer2 = package[off:]

    key_aes, key_chacha, key_hmac = _derive(password, salt, use_argon2)
    expected = hmac_mod.new(key_hmac, magic + salt + nonce_aes + nonce_chacha + layer2,
                            hashlib.sha3_512).digest()
    if not hmac_mod.compare_digest(tag, expected):
        raise ValueError("HMAC-SHA3-512 failed — wrong password or tampered data")

    aad = magic + salt + nonce_aes + nonce_chacha
    try:
        layer1 = ChaCha20Poly1305(key_chacha).decrypt(nonce_chacha, layer2, aad)
        plaintext = AESGCM(key_aes).decrypt(nonce_aes, layer1, aad)
    except Exception as e:
        raise ValueError(f"AEAD decryption failed — tampered data: {e}") from e
    return plaintext


def encrypt_b64(password: str, plaintext: str, use_argon2: bool = False) -> str:
    return base64.b64encode(encrypt(password, plaintext.encode("utf-8"), use_argon2)).decode("ascii")


def decrypt_b64(password: str, token_b64: str) -> str:
    return decrypt(password, base64.b64decode(token_b64.encode("ascii"))).decode("utf-8")


def encrypt_file(password: str, in_path: str, out_path: str, use_argon2: bool = False) -> int:
    with open(in_path, "rb") as f:
        data = f.read()
    package = encrypt(password, data, use_argon2)
    with open(out_path, "wb") as f:
        f.write(package)
    return len(data)


def decrypt_file(password: str, in_path: str, out_path: str) -> int:
    with open(in_path, "rb") as f:
        package = f.read()
    data = decrypt(password, package)
    with open(out_path, "wb") as f:
        f.write(data)
    return len(data)


def self_test():
    print("EvoCrypt Hybrid Prototype v0.2 — self-test")
    pw = "correct-horse-battery-staple"
    msg = "Hello ai.evo — SHA + X11 + AES + ChaCha, chained."
    # 1. v0.1 compat: an EVOC1 token made the v0.1 way still opens
    token = encrypt_b64(pw, msg)
    assert decrypt_b64(pw, token) == msg
    print("1. v0.1 (EVOC1) text roundtrip ok")
    # 2. wrong password / tamper still rejected
    try:
        decrypt_b64("wrong-password", token)
        print("2. FAIL: wrong password decrypted!")
    except ValueError:
        print("2. wrong password correctly rejected")
    raw = bytearray(base64.b64decode(token)); raw[-1] ^= 0x01
    try:
        decrypt(pw, bytes(raw))
        print("3. FAIL: tampered data decrypted!")
    except ValueError:
        print("3. tampered data correctly rejected")
    # 4. file mode: text + binary + empty + 1 MB, EvoKDF-11
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        src, enc, dec = f"{d}/a.bin", f"{d}/a.evoc", f"{d}/a.out"
        blob = bytes(range(256)) * 4000  # ~1 MB binary
        open(src, "wb").write(blob)
        n = encrypt_file(pw, src, enc)
        assert n == len(blob) and open(enc, "rb").read(len(MAGIC)) == MAGIC
        assert decrypt_file(pw, enc, dec) == len(blob) and open(dec, "rb").read() == blob
        print("4. file mode roundtrip ok (1 MB binary, EVOC1)")
        open(src, "wb").write(b"")
        encrypt_file(pw, src, enc); decrypt_file(pw, enc, dec)
        assert open(dec, "rb").read() == b""
        print("5. file mode empty-file roundtrip ok")
        # 6. Argon2id text + file (only if argon2-cffi is present)
        try:
            t2 = encrypt_b64(pw, msg, use_argon2=True)
            assert decrypt_b64(pw, t2) == msg
            open(src, "wb").write(b"argon2 file test")
            encrypt_file(pw, src, enc, use_argon2=True)
            assert open(enc, "rb").read(len(MAGIC2)) == MAGIC2
            decrypt_file(pw, enc, dec)
            assert open(dec, "rb").read() == b"argon2 file test"
            print("6. Argon2id (EVOC2) text + file roundtrip ok")
        except SystemExit as e:
            print("6. Argon2id skipped — argon2-cffi not installed:", str(e).splitlines()[0])
    print("ALL TESTS PASSED")


def _usage():
    print("usage:")
    print("  python3 evocrypt_hybrid_v02.py                                   # self-test")
    print("  python3 evocrypt_hybrid_v02.py encrypt <text> <password> [--argon2]")
    print("  python3 evocrypt_hybrid_v02.py decrypt <base64> <password>")
    print("  python3 evocrypt_hybrid_v02.py encrypt-file <in> <out.evoc> <password> [--argon2]")
    print("  python3 evocrypt_hybrid_v02.py decrypt-file <in.evoc> <out> <password>")


if __name__ == "__main__":
    args = sys.argv[1:]
    use_argon2 = "--argon2" in args
    args = [a for a in args if a != "--argon2"]
    if not args:
        self_test()
    elif args[0] == "encrypt" and len(args) == 3:
        print(encrypt_b64(args[2], args[1], use_argon2))
    elif args[0] == "decrypt" and len(args) == 3:
        print(decrypt_b64(args[2], args[1]))
    elif args[0] == "encrypt-file" and len(args) == 4:
        n = encrypt_file(args[3], args[1], args[2], use_argon2)
        print(f"encrypted {n} bytes -> {args[2]}")
    elif args[0] == "decrypt-file" and len(args) == 4:
        n = decrypt_file(args[3], args[1], args[2])
        print(f"decrypted {n} bytes -> {args[2]}")
    else:
        _usage()
