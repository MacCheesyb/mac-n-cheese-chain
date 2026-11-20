#!/usr/bin/env python3
"""
Test the R0NI governance / voting system (v0.4).

Token-weighted voting ("capital democracy", Mac's design):
1 R0NI held = 1 vote, power taken from the voter's balance at the
proposal's snapshot block, one signed vote per address, quorum
(default 10% of genesis supply = 10,000 R0NI) + strict majority
to pass — and a majority for the rejection option "no" means the
proposal FAILS.

Runs offline in-process (single Node) plus a live 3-node roundtrip
over HTTP: file a proposal, vote on it, close it, and read the
tally back from the /proposal endpoint, with all nodes agreeing.

Writes testnet-v2/governance_test_results.json. Exits non-zero on any
failure. Prototype only — not audited, no real value.

Usage: /tmp/r0ni-gov-venv/bin/python testnet/test_governance.py
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
    create_wallet, make_gov_propose_tx, make_gov_vote_tx,
    make_proposal, make_testnet_tx, gov_vote_message,
    gov_propose_message, tally_proposal, proposal_status,
    new_gov_registry, registry_apply_propose, registry_apply_vote,
    registry_tally, verify_signature, _load_private,
)
from node import Node  # noqa: E402
from run_testnet import (  # noqa: E402
    http, wait_up, wait_mempool_empty, mine_genesis, VENV_PY,
)

RESULTS = {"tests": [], "passed": 0, "failed": 0}


def check(name, ok, detail=""):
    RESULTS["tests"].append({"name": name, "passed": bool(ok), "detail": str(detail)})
    if ok:
        RESULTS["passed"] += 1
        print(f"PASS  {name}  {detail}")
    else:
        RESULTS["failed"] += 1
        print(f"FAIL  {name}  {detail}")


def mine_all(node):
    """Mine every mempool tx into blocks, one block at a time."""
    mined = 0
    while node.mempool:
        block = node.mine_one()
        if block is None:
            break
        ok, reason = node.add_block(block)
        assert ok, f"mined block rejected: {reason}"
        mined += 1
    return mined


def main():
    pw = "test-password"
    with tempfile.TemporaryDirectory() as d:
        whale_path = f"{d}/whale.json"
        whale = create_wallet(pw, whale_path)
        small_paths, smalls = [], []
        for i in range(10):
            sp = f"{d}/small-{i}.json"
            small_paths.append(sp)
            smalls.append(create_wallet(pw, sp))
        broke_path = f"{d}/broke.json"
        broke = create_wallet(pw, broke_path)

        # --- offline: proposal creation + deterministic ID --------
        prop1 = make_proposal("Set max supply to 10B", "Should the max supply be 10B R0NI?",
                              ["yes", "no"], whale["address"], whale["public_key_hex"],
                              created_at=1795132723, voting_start_block=1, voting_end_block=10)
        prop1_dup = make_proposal("Set max supply to 10B", "Should the max supply be 10B R0NI?",
                                  ["yes", "no"], whale["address"], whale["public_key_hex"],
                                  created_at=1795132723, voting_start_block=1, voting_end_block=10)
        check("proposal creation + deterministic ID",
              prop1["proposal_id"] == prop1_dup["proposal_id"]
              and prop1["proposal_id"].startswith("PROP-")
              and prop1["quorum"] == 10000, prop1["proposal_id"])

        # --- offline: single node ----------------------------------
        allocations = {whale["address"]: 10000}
        allocations.update({s["address"]: 100 for s in smalls})
        genesis = mine_genesis(allocations)
        node = Node(f"{d}/node1", [], None, mine=False)
        node.chain = [genesis]
        node.save()
        check("offline node starts at height 1 (genesis only)", node.chain_height() == 1)

        # File proposal 1 (whale nonce 0, window [1, 10)).
        propose1 = make_gov_propose_tx(whale_path, pw, "Set max supply to 10B",
                                       "Should the max supply be 10B R0NI?",
                                       ["yes", "no"], 1, 10, 0,
                                       created_at=1795132723)
        check("node: gov-propose accepted into mempool",
              node.add_tx(propose1)[0], propose1["proposal"]["proposal_id"])
        mine_all(node)
        pid1 = propose1["proposal"]["proposal_id"]
        entry = node.proposal(pid1)
        check("snapshot: whale 10,000 / small 100 / broke 0 at proposal block",
              entry is not None
              and entry["snapshot_balances"].get(whale["address"]) == 10000
              and entry["snapshot_balances"].get(smalls[0]["address"]) == 100
              and entry["snapshot_balances"].get(broke["address"], 0) == 0
              and entry["snapshot_block"] == 1, f"snapshot_block={entry['snapshot_block']}")

        # Whale sends 5,000 to broke AFTER the proposal — snapshot must not move.
        xfer = make_testnet_tx(whale_path, pw, broke["address"], 5000, 1)
        ok, reason = node.add_tx(xfer)
        check("node: post-proposal transfer accepted", ok, reason)
        mine_all(node)
        entry = node.proposal(pid1)
        check("snapshot power: transfer after proposal does not change snapshot",
              entry["snapshot_balances"].get(whale["address"]) == 10000
              and entry["snapshot_balances"].get(broke["address"], 0) == 0
              and node.balance(broke["address"]) == 5000,
              f"current broke balance now {node.balance(broke['address'])}, snapshot still 0")

        # Whale votes yes (nonce 2), smalls vote no (nonce 0 each).
        whale_vote = make_gov_vote_tx(whale_path, pw, pid1, "yes", 2)
        ok, reason = node.add_tx(whale_vote)
        check("node: whale vote accepted", ok, reason)
        # Duplicate vote while the first is still in the mempool.
        dup_vote = make_gov_vote_tx(whale_path, pw, pid1, "no", 3)
        ok, reason = node.add_tx(dup_vote)
        check("reject: one vote per address (duplicate in mempool)",
              not ok and "duplicate vote" in reason, reason)
        small_votes = []
        for i, sp in enumerate(small_paths):
            v = make_gov_vote_tx(sp, pw, pid1, "no", 0)
            ok, reason = node.add_tx(v)
            assert ok, f"small vote {i} rejected: {reason}"
            small_votes.append(v)
        # Zero-balance-at-snapshot voter: broke has 5,000 NOW but 0 at snapshot.
        broke_vote = make_gov_vote_tx(broke_path, pw, pid1, "yes", 0)
        ok, reason = node.add_tx(broke_vote)
        check("reject: zero-balance-at-snapshot voter (broke holds 5,000 now, 0 at snapshot)",
              not ok and "0 R0NI at the snapshot" in reason, reason)
        # Forged vote: signed by small-0's key, claiming to be the whale.
        _, small0_priv = _load_private(pw, small_paths[0])
        forged_msg = gov_vote_message(whale["address"], pid1, "yes")
        forged_vote = {
            "type": "gov-vote", "sender": whale["address"], "recipient": pid1,
            "amount": 0, "nonce": 4, "proposal_id": pid1, "option": "yes",
            "signature": small0_priv.sign(forged_msg.encode("utf-8")).hex(),
            "sender_pubkey_hex": whale["public_key_hex"],
            "txid": "00" * 64,
        }
        from roni_wallet import gov_vote_tx_id
        forged_vote["txid"] = gov_vote_tx_id(whale["address"], pid1, "yes")
        ok, reason = node.add_tx(forged_vote)
        check("reject: forged vote signature", not ok, reason)
        # Vote for an unknown proposal.
        unknown_vote = make_gov_vote_tx(small_paths[0], pw, "PROP-" + "0" * 40, "yes", 1)
        ok, reason = node.add_tx(unknown_vote)
        check("reject: vote for unknown proposal", not ok and "unknown proposal" in reason, reason)
        # Vote for an option that is not on the ballot.
        bad_option = make_gov_vote_tx(small_paths[0], pw, pid1, "maybe", 1)
        ok, reason = node.add_tx(bad_option)
        check("reject: vote for option not on the ballot",
              not ok and "not on proposal" in reason, reason)
        mine_all(node)

        # Weighted tally: whale 10,000 yes beats ten 100s no.
        tally1 = node.proposal_tally(pid1)
        check("weighted tally: whale 10,000 yes beats ten 100s no",
              tally1["per_option"] == {"yes": 10000, "no": 1000}
              and tally1["total_voting_power"] == 11000
              and tally1["quorum_met"] and tally1["winner"] == "yes",
              f"yes={tally1['per_option']['yes']} no={tally1['per_option']['no']} "
              f"total={tally1['total_voting_power']}")
        check("proposal still open before end block",
              tally1["status"] == "open", f"height={node.chain_height()} end=10")
        RESULTS["offline_tally_proposal_1"] = {k: v for k, v in tally1.items() if k != "votes"}

        # Duplicate proposal (same ID, new nonce) is rejected.
        dup_propose = make_gov_propose_tx(whale_path, pw, "Set max supply to 10B",
                                          "Should the max supply be 10B R0NI?",
                                          ["yes", "no"], 1, 10, 3,
                                          created_at=1795132723)
        ok, reason = node.add_tx(dup_propose)
        check("reject: duplicate proposal (same proposal ID)",
              not ok and "duplicate proposal" in reason, reason)
        # Proposal whose voting window starts in the future: filing is
        # fine, but voting on it now is outside the window.
        propose_future = make_gov_propose_tx(whale_path, pw, "Future vote",
                                             "Starts at block 99", ["yes", "no"],
                                             99, 100, 3, created_at=1795132800)
        ok, reason = node.add_tx(propose_future)
        check("node: future-window proposal accepted for filing", ok, reason)
        mine_all(node)
        pid_future = propose_future["proposal"]["proposal_id"]
        early_vote = make_gov_vote_tx(whale_path, pw, pid_future, "yes", 4)
        ok, reason = node.add_tx(early_vote)
        check("reject: vote outside window (before voting_start_block)",
              not ok and "outside voting window" in reason, reason)

        # Proposal 3: only the small holders vote -> quorum not met.
        propose3 = make_gov_propose_tx(whale_path, pw, "Set max supply to 1B",
                                       "Should it be 1B?", ["yes", "no"],
                                       6, 9, 4, created_at=1795132900)
        ok, reason = node.add_tx(propose3)
        check("node: proposal 3 filed (window [6, 9))", ok, reason)
        mine_all(node)
        pid3 = propose3["proposal"]["proposal_id"]
        for i, sp in enumerate(small_paths):
            v = make_gov_vote_tx(sp, pw, pid3, "yes", 1)
            ok, reason = node.add_tx(v)
            assert ok, f"proposal-3 small vote {i} rejected: {reason}"
        mine_all(node)
        # Advance the chain to the end block with a filler transfer.
        filler = make_testnet_tx(whale_path, pw, smalls[0]["address"], 1, 5)
        assert node.add_tx(filler)[0]
        mine_all(node)
        tally3 = node.proposal_tally(pid3)
        check("quorum not met -> failed (1,000 < 10,000)",
              tally3["total_voting_power"] == 1000 and not tally3["quorum_met"]
              and tally3["status"] == "failed",
              f"total={tally3['total_voting_power']} status={tally3['status']}")
        RESULTS["offline_tally_proposal_3_quorum_fail"] = {
            k: v for k, v in tally3.items() if k != "votes"}

        # Proposal 4: whale votes no, smalls vote yes -> majority no -> failed.
        propose4 = make_gov_propose_tx(whale_path, pw, "Set max supply to 100B",
                                       "Should it be 100B?", ["yes", "no"],
                                       9, 12, 6, created_at=1795133000)
        ok, reason = node.add_tx(propose4)
        check("node: proposal 4 filed (window [9, 12))", ok, reason)
        mine_all(node)
        pid4 = propose4["proposal"]["proposal_id"]
        whale_no = make_gov_vote_tx(whale_path, pw, pid4, "no", 7)
        ok, reason = node.add_tx(whale_no)
        assert ok, f"whale no-vote rejected: {reason}"
        for i, sp in enumerate(small_paths):
            v = make_gov_vote_tx(sp, pw, pid4, "yes", 2)
            ok, reason = node.add_tx(v)
            assert ok, f"proposal-4 small vote {i} rejected: {reason}"
        mine_all(node)
        filler2 = make_testnet_tx(whale_path, pw, smalls[0]["address"], 1, 8)
        assert node.add_tx(filler2)[0]
        mine_all(node)
        tally4 = node.proposal_tally(pid4)
        # Snapshot for proposal 4 (taken at its filing block): the
        # whale had already sent 5,000 to broke and 1 to small-0,
        # so the whale votes with 4,999 and small-0 with 101 — the
        # snapshot is the point, not the genesis balances.
        snap4 = node.proposal(pid4)["snapshot_balances"]
        exp_no = snap4[whale["address"]]
        exp_yes = sum(snap4[s["address"]] for s in smalls)
        check("majority no -> failed (whale's snapshot power beats the smalls)",
              tally4["per_option"] == {"yes": exp_yes, "no": exp_no}
              and tally4["winner"] == "no" and tally4["status"] == "failed",
              f"yes={tally4['per_option']['yes']} (snapshot {exp_yes}) "
              f"no={tally4['per_option']['no']} (snapshot {exp_no})")
        RESULTS["offline_tally_proposal_4_majority_no"] = {
            k: v for k, v in tally4.items() if k != "votes"}
        # Proposal 1 is now past its end block (height 12 >= 10): passed.
        tally1_closed = node.proposal_tally(pid1)
        check("majority yes -> passed (proposal 1 closes passed at height 12)",
              tally1_closed["status"] == "passed" and tally1_closed["passed"],
              f"status={tally1_closed['status']} height={node.chain_height()}")
        RESULTS["offline_tally_proposal_1_closed"] = {
            k: v for k, v in tally1_closed.items() if k != "votes"}

        # --- live 3-node roundtrip over HTTP --------------------------
        run_dir = Path("/tmp/r0ni-gov-testnet-v2-run")
        import shutil
        for sub in ("node1", "node2", "node3"):
            shutil.rmtree(run_dir / sub, ignore_errors=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        live_allocations = {whale["address"]: 10000}
        live_allocations.update({s["address"]: 100 for s in smalls})
        live_genesis = mine_genesis(live_allocations)
        (REPO_ROOT / "testnet-v2" / "genesis.json").write_text(json.dumps(live_genesis, indent=2))
        ports = [8031, 8032, 8033]
        procs = []
        try:
            for i, port in enumerate(ports):
                peers = ",".join(f"http://127.0.0.1:{p}" for p in ports if p != port)
                cmd = [VENV_PY, str(REPO_ROOT / "testnet-v2" / "node.py"),
                       "--port", str(port), "--data-dir", str(run_dir / f"node{i+1}"),
                       "--peers", peers, "--genesis", str(REPO_ROOT / "testnet-v2" / "genesis.json")]
                if i == 0:
                    cmd.append("--mine")
                procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                              stderr=subprocess.STDOUT, text=True))
            for p in ports:
                assert wait_up(p), f"live node {p} did not come up"
            check("live: 3 nodes up (ports 8031-8033)", True)
            time.sleep(1)

            # Live proposal: window [1, 6). Nonces are fresh on this chain.
            live_propose = make_gov_propose_tx(whale_path, pw, "Set max supply to 10B",
                                               "Should the max supply be 10B R0NI?",
                                               ["yes", "no"], 1, 6, 0,
                                               created_at=1795132723)
            live_pid = live_propose["proposal"]["proposal_id"]
            s, r = http("POST", 8031, "/tx", live_propose)
            check("live: gov-propose accepted via HTTP", s == 200 and r.get("accepted"), str(r))
            assert wait_mempool_empty(8031, timeout=60), "live proposal mempool did not drain"
            s, props = http("GET", 8031, "/proposals")
            check("live: /proposals lists the filed proposal",
                  s == 200 and any(p["proposal_id"] == live_pid for p in props),
                  f"{len(props)} proposal(s) listed")
            # Whale votes yes (nonce 1), smalls vote no (nonce 0 each).
            live_whale_vote = make_gov_vote_tx(whale_path, pw, live_pid, "yes", 1)
            s, r = http("POST", 8031, "/tx", live_whale_vote)
            check("live: whale vote accepted via HTTP", s == 200 and r.get("accepted"), str(r))
            # Duplicate vote over HTTP is rejected.
            dup = make_gov_vote_tx(whale_path, pw, live_pid, "no", 2)
            s, r = http("POST", 8031, "/tx", dup)
            check("live: duplicate vote rejected via HTTP",
                  s == 400 and "duplicate vote" in str(r.get("reason", "")), str(r))
            for i, sp in enumerate(small_paths):
                v = make_gov_vote_tx(sp, pw, live_pid, "no", 0)
                s, r = http("POST", 8031, "/tx", v)
                assert s == 200 and r.get("accepted"), f"live small vote {i} rejected: {r}"
            # Zero-balance voter over HTTP is rejected.
            broke_live = make_gov_vote_tx(broke_path, pw, live_pid, "yes", 0)
            s, r = http("POST", 8031, "/tx", broke_live)
            check("live: zero-balance vote rejected via HTTP",
                  s == 400 and "0 R0NI at the snapshot" in str(r.get("reason", "")), str(r))
            assert wait_mempool_empty(8031, timeout=90), "live votes mempool did not drain"
            # Close the proposal: advance the chain to height 6 with
            # filler transfers (one per block, drained in between).
            nonces = {whale["address"]: 2, smalls[0]["address"]: 1}
            while True:
                s, st = http("GET", 8031, "/status")
                if st.get("height", 0) >= 6:
                    break
                tx = make_testnet_tx(whale_path, pw, smalls[0]["address"], 1,
                                     nonces[whale["address"]])
                nonces[whale["address"]] += 1
                s, r = http("POST", 8031, "/tx", tx)
                assert s == 200 and r.get("accepted"), f"live filler rejected: {r}"
                assert wait_mempool_empty(8031, timeout=60), "live filler mempool did not drain"
            s, prop = http("GET", 8031, f"/proposal?proposal_id={live_pid}")
            tally_live = prop.get("tally", {}) if s == 200 else {}
            check("live: /proposal tally — whale 10,000 yes beats ten 100s no, passed",
                  s == 200 and tally_live.get("per_option") == {"yes": 10000, "no": 1000}
                  and tally_live.get("total_voting_power") == 11000
                  and tally_live.get("quorum_met") and prop.get("status") == "passed",
                  f"tally={tally_live} status={prop.get('status')}")
            RESULTS["live_tally"] = {k: v for k, v in tally_live.items() if k != "votes"}
            RESULTS["live_proposal_id"] = live_pid
            # A vote after the window closed is rejected.
            late_vote = make_gov_vote_tx(small_paths[0], pw, live_pid, "yes", 1)
            s, r = http("POST", 8031, "/tx", late_vote)
            check("live: vote after window closed rejected via HTTP",
                  s == 400 and "outside voting window" in str(r.get("reason", "")), str(r))
            # All three nodes agree on the chain.
            c1 = http("GET", 8031, "/chain")[1]
            c2 = http("GET", 8032, "/chain")[1]
            c3 = http("GET", 8033, "/chain")[1]
            check("live: all 3 nodes agree on the chain", c1 == c2 == c3,
                  f"heights {len(c1)}/{len(c2)}/{len(c3)}")
            s, tally_ep = http("GET", 8031, f"/tally?proposal_id={live_pid}")
            check("live: /tally endpoint matches /proposal tally",
                  s == 200 and tally_ep.get("total_voting_power") == 11000
                  and tally_ep.get("result") == "passed", str(tally_ep)[:200])
        finally:
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass
            for p in procs:
                try:
                    p.wait(timeout=5)
                except Exception:
                    p.kill()

    out = REPO_ROOT / "testnet-v2" / "governance_test_results.json"
    out.write_text(json.dumps(RESULTS, indent=2) + "\n")
    print(f"\n{RESULTS['passed']} passed, {RESULTS['failed']} failed — wrote {out}")
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
