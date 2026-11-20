# R0NI Governance — Token-Weighted Voting (v0.4)

Prototype only — not audited, no live network, no real value.
Governance decides the direction of the Mac 'N Cheese Chain by
**capital democracy**: voting power is relative to the coins held
in each account, so majority holders have more leverage — 1 R0NI
held = 1 vote.

## The rules

### Proposals
- A proposal is filed by a signed `gov-propose` transaction
  (amount 0 R0NI — filing moves no money). Fields: `title`,
  `description`, `options` (default `["yes", "no"]`, up to 8
  custom options — e.g. `["1B", "10B", "100B"]` to choose a max
  supply), `creator`, `voting_start_block`, `voting_end_block`,
  `quorum`, `snapshot_block`.
- Proposal ID is deterministic: `PROP-` + first 40 hex of
  EvoHash-11(`title + "|" + creator + "|" + created_at`). The
  same title + creator + timestamp always gives the same ID, so
  a duplicate filing is detectable and rejected.
- The creator signs the WHOLE proposal (canonical JSON), so the
  title, options, voting window or quorum cannot be swapped
  without breaking the signature and the transaction ID.
- The voting window is `[voting_start_block, voting_end_block)`.
  Height is the number of blocks in the chain (genesis = 1).
  A proposal cannot start voting in the past.

### Voting power — the snapshot
- Power is the voter's balance **at the snapshot**: the balances
  as of the block the proposal was filed in (`snapshot_block`).
  Buying R0NI after a proposal starts does **not** inflate your
  power on that proposal, and selling after it starts does not
  reduce it either — the snapshot is frozen at filing.
- An address that held **0 R0NI at the snapshot cannot vote**,
  even if it holds R0NI now.

### Votes
- A vote is a signed `gov-vote` transaction (amount 0 R0NI)
  carrying `proposal_id` + `option`, signed by the voter's
  Ed25519 key. The transaction's recipient is the proposal ID
  itself (no R0NI moves — a vote is a record, not a payment).
- **One vote per address per proposal.** A second vote from the
  same address is rejected by the node, and in v1 a vote cannot
  be changed after it is cast.
- The node rejects a vote when: the proposal does not exist
  (or is still only in the mempool), the vote is outside the
  voting window, the option is not on the ballot, the address
  already voted, the address held 0 R0NI at the snapshot, or
  the signature does not verify. The address must also derive
  from the sender's public key via EvoHash-11, as for every
  transaction.

### Passing — quorum + strict majority
A proposal passes only if, at the end of its voting window
(height >= `voting_end_block`), BOTH hold:

1. **Quorum:** total voting power cast >= `quorum`. Default
   quorum is **10% of the genesis circulating supply**
   (100,000 R0NI to start) = **10,000 R0NI** of voting power.
   A custom quorum can be set when the proposal is filed.
2. **Strict majority:** the winning option holds more than half
   of the votes cast (it must beat ALL other options combined —
   a tie for first place is not a majority).

And one more rule: the literal option `"no"` is the rejection
option. If `"no"` wins the majority, the proposal **fails** —
the thing proposed was voted down. For custom options with no
`"no"` on the ballot (e.g. choosing a max supply), a majority
winner adopts the decision and the proposal passes.

While height < `voting_end_block` the proposal's status is
`open`; at height >= `voting_end_block` it closes as `passed`
or `failed` and the result is final.

### Worked example (from the tests)
Proposal "Set max supply to 10B", options yes/no, quorum 10,000:
- One holder with **10,000 R0NI** votes **yes**.
- Ten holders with **100 R0NI** each vote **no**.
- Tally: yes **10,000**, no **1,000** (10 × 100), total **11,000**
  >= quorum 10,000, yes has a strict majority — **passed**.
  The whale outweighs the ten small holders, exactly as designed.
- If only the ten small holders had voted: total 1,000 < 10,000
  quorum — **failed**, even though they all agreed.
- If the whale had voted **no** and the smalls **yes**: no wins
  10,000 vs 1,000 — **failed** (the proposal was voted down).

## What v1 does NOT do (limitations)

- **No vote changing.** One vote per address, final. Changing a
  vote would need a "supersede" rule and a decision about which
  vote counts — not designed yet.
- **No delegation.** You cannot lend your voting power to
  another address. Your power only counts when you vote yourself.
- **No on-chain execution.** A passed proposal is a recorded
  decision, not an automatic change: nothing in the chain
  changes the max supply, the difficulty, or any other parameter
  by itself. Execution is a human step for now — someone (Mac,
  in practice) reads the result and applies it, e.g. by a code
  change and a new release. An execution mechanism (parameter
  proposals that the node applies at a set block) is future work.
- **No vote privacy.** Votes are public signed transactions:
  anyone can see who voted for what, and with how much power.
- **No protection against vote buying or coercion.** A holder
  can be paid or pressured to vote a certain way — the chain
  cannot tell why a vote was cast.
- **Quorum is absolute, not relative.** The default quorum is
  10,000 R0NI of voting power (10% of the 100,000 genesis
  supply). If the circulating supply grows well past 100,000,
  10,000 becomes a small fraction of it — the quorum default
  will need revisiting (itself a governance decision) once
  supply changes.
- **Snapshot = filing block.** The snapshot is taken when the
  proposal is filed, not when voting opens. If
  `voting_start_block` is well after filing, balances can move
  in between without affecting power — that is by design (the
  power is fixed when the question is asked), but it is a
  choice, not an accident.

## Using it

### CLI (roni_wallet.py)
```
# File a proposal (creator signs the whole proposal).
python3 roni_wallet.py gov-propose <wallet.json> <password> \
  "Set max supply to 10B" "Should the max supply be 10B R0NI?" \
  1 10 0 --options yes,no --ledger ledger.json --registry gov.json
# Custom options + quorum:
python3 roni_wallet.py gov-propose <wallet.json> <password> \
  "Choose max supply" "Pick the max supply" 1 10 0 \
  --options 1B,10B,100B --quorum 5000 --registry gov.json

# Vote (voter signs proposal_id + option).
python3 roni_wallet.py gov-vote <wallet.json> <password> \
  PROP-<40 hex> yes 1 --registry gov.json

# Tally + status (pass --height N to see the status at a height).
python3 roni_wallet.py gov-tally PROP-<40 hex> --registry gov.json --height 10
python3 roni_wallet.py gov-list --registry gov.json --height 3
```
`--ledger ledger.json` on `gov-propose` snapshots balances from
a local ledger file. Options accept both `--key value` and
`--key=value` forms.

### Node (testnet/node.py)
Proposals and votes are ordinary transactions (`gov-propose` /
`gov-vote`, amount 0) submitted to `POST /tx` and mined like any
other transaction. Endpoints:
- `GET /proposals` — every proposal with its tally and status.
- `GET /proposal?proposal_id=PROP-...` — one proposal, its
  snapshot balances, its votes, its tally and status.
- `GET /tally?proposal_id=PROP-...` — just the tally.

## Tests
`testnet/test_governance.py` — **32 checks, all passing**:
offline (single Node) + live 3-node roundtrip over HTTP. Covers
proposal creation + deterministic ID, snapshot power (a transfer
after filing does not move the snapshot — a voter with 5,000
R0NI now but 0 at the snapshot still cannot vote), one-vote-
per-address rejection, zero-balance rejection, forged signature
rejection, vote outside window rejection (before start and after
close), vote for an unknown proposal, vote for an option not on
the ballot, duplicate proposal rejection, quorum not met ->
failed, majority yes -> passed, majority no -> failed, the whale
tally (10,000 yes beats ten 100s no), and the live end-to-end
tally read back from `/proposal` with all 3 nodes agreeing.
Results: `testnet/governance_test_results.json`.
`roni_wallet.py` self-test also covers governance (checks 30–39).
