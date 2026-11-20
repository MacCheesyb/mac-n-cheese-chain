#!/usr/bin/env python3
"""
Mine the v2 testnet genesis Block 0 (R- block hashes).

Standalone script — do NOT run `python3 evochain_genesis.py` bare,
that overwrites the v1 genesis file. This script only ever writes
testnet-v2/genesis.json, never testnet/genesis.json.

The v2 genesis: previous_hash "R-" + 128 zeros, data
"R0NI testnet v2 genesis — R- block hashes — circulating supply
100000 to start", and a hash of "R-" + 128 hex chars of EvoHash-11
whose hex part starts with "0000". The "R" is a label, NOT part of
the hash — hex has no R.

Usage:
  /home/hatch/workspace/r0ni-v2-venv/bin/python testnet-v2/mine_v2_genesis.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_testnet import make_wallet, mine_genesis, TEST_FUNDS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def main():
    wallets = [make_wallet(f"v2-genesis-{c}") for c in "ABC"]
    allocations = {w["address"]: TEST_FUNDS for w in wallets}
    genesis = mine_genesis(allocations)
    out = REPO_ROOT / "testnet-v2" / "genesis.json"
    out.write_text(json.dumps(genesis, indent=2))
    print(f"v2 genesis mined -> {out}")
    print(f"  timestamp: {genesis['timestamp']}")
    print(f"  nonce:     {genesis['nonce']}")
    print(f"  hash:      {genesis['hash']}")
    print(f"  data:      {genesis['data']}")
    for w in wallets:
        print(f"  funded:    {w['address']} ({TEST_FUNDS} R0NI, test-only)")


if __name__ == "__main__":
    main()
