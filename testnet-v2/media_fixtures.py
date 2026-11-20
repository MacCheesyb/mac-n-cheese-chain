#!/usr/bin/env python3
"""Generate small, real media files for R0NI payload roundtrip tests.

No external assets are needed: the PNG and GIF are hand-built with
the stdlib (zlib + struct + wave), the WAV is a sine tone written
with the stdlib `wave` module, and the MP4 is generated with ffmpeg
(`ffmpeg -f lavfi -i testsrc=...`), which is present on this machine.
If ffmpeg is missing or fails, the video fixture falls back to a
small binary blob labelled video/mp4 — flagged by `video_real`
so the test report says so honestly.

Each fixture is (kind, mime, filename, bytes). All of them are
small and compressible enough to fit the 1 MB on-chain limit.
"""
import math
import struct
import subprocess
import wave
import zlib
from pathlib import Path


def make_png(width=16, height=16):
    """A valid PNG: signature, IHDR, IDAT (zlib scanlines), IEND."""
    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b""
    for y in range(height):
        raw += b"\x00" + bytes((x * 16) % 256 for x in range(width * 3))
    idat = zlib.compress(raw, 9)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def make_gif():
    """A valid 1x1 GIF89a (black pixel, minimal global colour table)."""
    return bytes([
        0x47, 0x49, 0x46, 0x38, 0x39, 0x61,       # GIF89a
        0x01, 0x00, 0x01, 0x00, 0x80, 0x00, 0x00,  # LSD, 1x1, GCT flag
        0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF,       # GCT: black, white
        0x2C, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,  # image descriptor
        0x02, 0x02, 0x44, 0x01, 0x00, 0x3B,       # image data + trailer
    ])


def make_wav(seconds=0.5, freq=440.0, rate=8000):
    """A 0.5 s 440 Hz sine tone, mono 16-bit, written with stdlib wave."""
    path = Path("/tmp/r0ni-media-fixture.wav")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * seconds)))
        w.writeframes(frames)
    return path.read_bytes()


def make_mp4():
    """A 1 s 160x120 test-pattern MP4 via ffmpeg. Returns (bytes, real).

    Falls back to a small binary blob labelled video/mp4 if ffmpeg
    is missing or fails — the caller must report that honestly."""
    out = Path("/tmp/r0ni-media-fixture.mp4")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ], check=True, timeout=60)
        return out.read_bytes(), True
    except Exception:
        return b"\x00\x00\x00\x18ftypisom" + bytes(range(256)) * 20, False


def generate_fixtures():
    """Return {name: (kind, mime, filename, bytes)} plus a video flag."""
    mp4, video_real = make_mp4()
    fixtures = {
        "text": ("text", "text/plain", "message.txt",
                 "Hello R0NI — a picture, a song and a short video can all "
                 "ride on a transaction now. This message is stored on-chain, "
                 "signed, and extractable byte-for-byte.".encode("utf-8")),
        "image": ("image", "image/png", "test.png", make_png()),
        "gif": ("gif", "image/gif", "test.gif", make_gif()),
        "audio": ("audio", "audio/wav", "tone.wav", make_wav()),
        "video": ("video", "video/mp4", "test.mp4", mp4),
    }
    return fixtures, video_real
