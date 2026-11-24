// R0NI amounts — milli-R0NI (v0.5, 2026-11-23).
//
// Canonical stored unit is the integer milli-R0NI:
//   1 R0NI = 1000 milli-units; smallest unit 1 milli = 0.001 R0NI.
// Max supply ceiling CHOSEN by Mac 2026-11-23: 10,000,000,000 R0NI
// (recorded decision only — not on-chain until the "Choose max
// supply" proposal is filed and passes). Block 0 was NOT re-mined;
// genesis circulating supply is unchanged: 100,000 R0NI to start.
//
// This file is the extension's amount boundary, mirroring
// parse_amount() / format_amount() in roni_wallet.py exactly:
//   * Human input is decimal R0NI, parsed once, at the boundary.
//   * All arithmetic is exact integer arithmetic on milli-units —
//     no binary floats anywhere in balances or signed amounts.
//   * A signed transaction's "amount" is integer milli-R0NI and
//     the tx carries "amount_unit": "milli-R0NI". A transaction
//     without that marker is a pre-milli transaction and is
//     REJECTED by testnet/accept_signed_tx.py — never silently
//     converted (a silent conversion would be a 1000x error).
//
// Pure functions only: no DOM, no chrome.* — so this file can be
// driven from Node (extension/test_amounts.js) as well as from
// popup.js. Exposes global R0niAmounts in the browser; in Node it
// also sets module.exports.

(function (root) {
  'use strict';

  const MILLI_PER_R0NI = 1000;
  const MAX_SUPPLY_R0NI = 10000000000; // 10B, chosen 2026-11-23
  const MAX_SUPPLY_MILLI = MAX_SUPPLY_R0NI * MILLI_PER_R0NI; // 10,000,000,000,000
  const GENESIS_SUPPLY_R0NI = 100000;
  const GENESIS_SUPPLY_MILLI = GENESIS_SUPPLY_R0NI * MILLI_PER_R0NI; // 100,000,000
  const AMOUNT_UNIT = 'milli-R0NI';
  // Decimal R0NI with at most 3 places after the point. No sign,
  // no exponent, no thousands separators — the same shapes
  // roni_wallet.py parse_amount() accepts as a string.
  const DECIMAL_RE = /^\d+(\.\d{1,3})?$/;

  function fail(msg) { throw new Error(msg); }

  // Parse a human amount (decimal R0NI) into integer milli-R0NI.
  // Accepts a string ("1.500", "0.001", "100000") or a number
  // (1.5, 0.001). A bare integer means that many whole R0NI —
  // "1" is 1 R0NI = 1000 milli, exactly as Python's decimal path.
  // Rejects: zero or negative amounts, more than 3 decimal places
  // (e.g. "0.0005", "1.0005"), anything below 0.001 R0NI, bools,
  // non-numeric strings, NaN / infinities, and anything above the
  // 10B ceiling. Numbers go through String(value) so 0.001 is
  // exact, not the binary-float approximation of 0.001.
  function parseAmount(value) {
    if (typeof value === 'boolean' || value === null || value === undefined) {
      fail('amount must be a number of R0NI (e.g. "1.500")');
    }
    let text;
    if (typeof value === 'number') {
      if (!Number.isFinite(value)) fail('amount must be a finite number of R0NI');
      text = String(value);
    } else if (typeof value === 'string') {
      text = value.trim();
    } else {
      fail('amount must be a number of R0NI (e.g. "1.500")');
    }
    if (!DECIMAL_RE.test(text)) {
      fail('amount ' + JSON.stringify(value) + ' is not decimal R0NI with at most '
        + '3 decimal places — the smallest unit is 0.001 R0NI (1 milli-R0NI)');
    }
    const dot = text.indexOf('.');
    const whole = dot === -1 ? text : text.slice(0, dot);
    const frac = dot === -1 ? '' : text.slice(dot + 1);
    // Integer arithmetic on the string parts — no floats.
    const milli = Number(whole) * MILLI_PER_R0NI + Number((frac + '000').slice(0, 3));
    if (!Number.isSafeInteger(milli)) fail('amount ' + JSON.stringify(value) + ' is too large');
    if (milli <= 0) {
      fail('amount must be positive — the smallest unit is 0.001 R0NI (1 milli-R0NI)');
    }
    if (milli > MAX_SUPPLY_MILLI) {
      fail('amount ' + JSON.stringify(value) + ' exceeds the chosen max supply ceiling of '
        + '10,000,000,000 R0NI');
    }
    return milli;
  }

  // Format an integer milli-R0NI amount as decimal R0NI with
  // exactly 3 places: 1 -> "0.001", 1500 -> "1.500",
  // 100000000 -> "100000.000". Mirrors format_amount().
  function formatAmount(amountMilli) {
    if (!Number.isSafeInteger(amountMilli)) {
      fail('formatAmount takes an integer milli-R0NI amount');
    }
    const sign = amountMilli < 0 ? '-' : '';
    const whole = Math.floor(Math.abs(amountMilli) / MILLI_PER_R0NI);
    const frac = Math.abs(amountMilli) % MILLI_PER_R0NI;
    return sign + String(whole) + '.' + String(frac).padStart(3, '0');
  }

  // Migrate a ledger (genesis_allocation.json) from legacy
  // whole-R0NI amounts to milli-R0NI, mirroring roni_wallet.py
  // load_ledger(). A ledger already marked
  // "amount_unit": "milli-R0NI" is returned unchanged; a legacy
  // ledger (no marker) has every allocation / transfer amount
  // multiplied by 1000 and is marked, so a second migration does
  // not multiply again. Returns { ledger, changed } and never
  // mutates its input.
  function migrateLedgerAmounts(ledger) {
    if (!ledger || typeof ledger !== 'object') return { ledger, changed: false };
    if (ledger.amount_unit === AMOUNT_UNIT) return { ledger, changed: false };
    const out = JSON.parse(JSON.stringify(ledger));
    for (const a of out.allocations || []) {
      a.amount = (Number(a.amount) || 0) * MILLI_PER_R0NI;
    }
    for (const tx of out.transfers || []) {
      tx.amount = (Number(tx.amount) || 0) * MILLI_PER_R0NI;
    }
    out.amount_unit = AMOUNT_UNIT;
    return { ledger: out, changed: true };
  }

  // Balance of one address in a ledger, in integer milli-R0NI.
  // The caller must have run migrateLedgerAmounts() first (or pass
  // a milli-marked ledger); legacy amounts would otherwise be
  // summed as if they were milli.
  function ledgerBalanceMilli(ledger, address) {
    if (!ledger || !address) return null;
    let balance = 0;
    for (const a of ledger.allocations || []) {
      if (a.address === address) balance += Number(a.amount) || 0;
    }
    for (const tx of ledger.transfers || []) {
      if (tx.to === address) balance += Number(tx.amount) || 0;
      if (tx.from === address) balance -= Number(tx.amount) || 0;
    }
    return balance;
  }

  // The message a testnet transaction is signed over (v1, no
  // payload): sender|recipient|amount|nonce — with amount in
  // integer milli-R0NI, exactly as roni_wallet.py
  // testnet_tx_message(). A 1.500 R0NI transfer signs over 1500.
  function txMessage(sender, recipient, amountMilli, nonce) {
    return sender + '|' + recipient + '|' + amountMilli + '|' + nonce;
  }

  function _bytesToHex(bytes) {
    return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  // txid = EvoHash-11 of the signed message, hex — exactly as
  // roni_wallet.py testnet_tx_id(). Needs the vendored EvoHash-11
  // bundle (evo-hash-11.js, global EvoHash11) loaded first.
  function txId(sender, recipient, amountMilli, nonce) {
    if (typeof EvoHash11 === 'undefined' || !EvoHash11.evoHash11) {
      throw new Error('EvoHash-11 bundle (evo-hash-11.js) did not load.');
    }
    const msg = new TextEncoder().encode(txMessage(sender, recipient, amountMilli, nonce));
    return _bytesToHex(EvoHash11.evoHash11(msg));
  }

  // Assemble a signed transfer transaction in the shape
  // testnet/accept_signed_tx.py accepts: amount in integer milli
  // AND the "amount_unit": "milli-R0NI" marker. The marker is
  // what tells the node-side acceptor this tx was signed in
  // milli units; a tx without it is rejected as pre-milli.
  function buildTransferTx(opts) {
    return {
      sender: opts.sender,
      recipient: opts.recipient,
      amount: opts.amountMilli,
      amount_unit: AMOUNT_UNIT,
      nonce: opts.nonce,
      signature: opts.signatureHex,
      sender_pubkey_hex: opts.senderPubkeyHex,
      txid: opts.txidHex,
    };
  }

  const api = {
    MILLI_PER_R0NI,
    MAX_SUPPLY_R0NI,
    MAX_SUPPLY_MILLI,
    GENESIS_SUPPLY_R0NI,
    GENESIS_SUPPLY_MILLI,
    AMOUNT_UNIT,
    parseAmount,
    formatAmount,
    migrateLedgerAmounts,
    ledgerBalanceMilli,
    txMessage,
    txId,
    buildTransferTx,
  };

  root.R0niAmounts = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
