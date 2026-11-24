// Node harness for extension/amounts.js (milli-R0NI, v0.5).
//
// Loads the vendored EvoHash-11 bundle + amounts.js in a vm global
// context (no DOM, no chrome.* — amounts.js is pure), then checks:
//   * parseAmount / formatAmount mirror roni_wallet.py exactly,
//     including every rejection (below 0.001, >3 dp, zero/negative,
//     non-numeric, above the 10B ceiling),
//   * migrateLedgerAmounts migrates a legacy whole-R0NI ledger
//     x1000, idempotently,
//   * txMessage / txId match Python-computed vectors (fixed test
//     keys 0x11*32 -> R0NI-d867..., 0x22*32 -> R0NI-d2bd...; txids
//     computed with roni_wallet.py testnet_tx_id),
//   * a real extension-style signed transfer: a fresh Ed25519
//     keypair via WebCrypto signs sender|recipient|1500|0, and the
//     resulting tx JSON (amount 1500 milli + "amount_unit":
//     "milli-R0NI") is written to the path in argv[2] (default
//     /tmp/extension-signed-tx.json) for testnet/test_extension_milli.py
//     to verify against Python and submit to a live node.
//
// Usage: node extension/test_amounts.js [out-tx.json]
// Exits non-zero on any failure. No network, no keys on disk.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');

const DIR = __dirname;
const context = vm.createContext({
  console, TextEncoder, TextDecoder, JSON, Math, Number, Error,
});
context.globalThis = context;
for (const file of ['evo-hash-11.js', 'amounts.js']) {
  vm.runInContext(fs.readFileSync(path.join(DIR, file), 'utf-8'), context, { filename: file });
}
const A = context.R0niAmounts;

let passed = 0, failed = 0;
function check(name, ok, detail = '') {
  if (ok) { passed++; console.log('PASS  ' + name + '  ' + detail); }
  else { failed++; console.log('FAIL  ' + name + '  ' + detail); }
}
function expectReject(name, fn) {
  try { fn(); } catch (e) { check(name, true, String(e.message).slice(0, 100)); return; }
  check(name, false, 'was accepted, should have been rejected');
}

const SENDER = 'R0NI-d867166b51a61bcbd4c498524fb8cd3008514823'; // 0x11*32 pubkey
const RECIPIENT = 'R0NI-d2bd52a4486edaafd7eac67b5b4b21641fb492d7'; // 0x22*32 pubkey

async function main() {
  // --- parseAmount / formatAmount (mirror of Python) -------------
  const cases = [['0.001', 1], ['1.5', 1500], ['1.500', 1500],
    ['100000', 100000000], ['0.002', 2], [1, 1000], [1.5, 1500],
    [0.001, 1], ['100000.000', 100000000], ['0', null]];
  let ok = true;
  for (const [v, want] of cases) {
    if (want === null) continue;
    if (A.parseAmount(v) !== want) { ok = false; console.log('  mismatch', v, A.parseAmount(v), 'want', want); }
  }
  check('parseAmount: decimals + ints -> milli', ok,
    '"0.001"->1, "1.5"->1500, "100000"->100000000, 1->1000');
  for (const bad of ['0.0005', '0.0001', '1.0005', '0', '-1', '', 'abc',
    '1e3', '1,500', 0.0005, -0.001, 0, NaN, Infinity, true, null, undefined]) {
    expectReject('parseAmount rejects ' + JSON.stringify(bad), () => A.parseAmount(bad));
  }
  expectReject('parseAmount rejects above the 10B ceiling',
    () => A.parseAmount('10000000001'));
  const fmt = [[1, '0.001'], [1500, '1.500'], [100000000, '100000.000'],
    [0, '0.000'], [2, '0.002'], [10000000, '10000.000']];
  check('formatAmount: milli -> decimal R0NI, exactly 3 places',
    fmt.every(([m, want]) => A.formatAmount(m) === want),
    '1->0.001, 1500->1.500, 100000000->100000.000');
  check('parse/format roundtrip is exact',
    [1, 2, 999, 1000, 1500, 10000000, 100000000]
      .every((m) => A.parseAmount(A.formatAmount(m)) === m),
    '7 milli values survive format -> parse unchanged');
  check('constants: 1000 milli per R0NI, 10B ceiling, 100,000 genesis',
    A.MILLI_PER_R0NI === 1000 && A.MAX_SUPPLY_MILLI === 10000000000000
    && A.GENESIS_SUPPLY_MILLI === 100000000, 'MAX_SUPPLY_MILLI=10,000,000,000,000');

  // --- legacy ledger migration ------------------------------------
  const legacy = {
    chain: "Mac 'N Cheese Chain", ticker: 'R0NI',
    genesis_block_hash: '0000adbc', genesis_supply: 100000,
    allocations: [{ address: SENDER, amount: 100000, source: 'genesis' }],
    transfers: [{ from: SENDER, to: RECIPIENT, amount: 25000 }],
  };
  const m1 = A.migrateLedgerAmounts(legacy);
  check('migrateLedgerAmounts: legacy whole R0NI x1000 on load',
    m1.changed && m1.ledger.amount_unit === 'milli-R0NI'
    && A.ledgerBalanceMilli(m1.ledger, SENDER) === 75000000
    && A.ledgerBalanceMilli(m1.ledger, RECIPIENT) === 25000000,
    '100,000 -> 100,000,000 milli; 25,000 -> 25,000,000 milli');
  const m2 = A.migrateLedgerAmounts(m1.ledger);
  check('migrateLedgerAmounts is idempotent (no double x1000)',
    !m2.changed && A.ledgerBalanceMilli(m2.ledger, SENDER) === 75000000,
    'reload after migration keeps the same balances');
  check('migrateLedgerAmounts does not mutate its input',
    legacy.amount_unit === undefined && legacy.allocations[0].amount === 100000,
    'original ledger object untouched');
  check('ledgerBalanceMilli of a milli ledger: genesis holder 100000.000',
    A.formatAmount(A.ledgerBalanceMilli(m1.ledger, SENDER)) === '75000.000',
    '75,000,000 milli -> "75000.000"');

  // --- tx message / txid match Python vectors ---------------------
  check('txMessage matches roni_wallet.py testnet_tx_message',
    A.txMessage(SENDER, RECIPIENT, 1500, 0)
    === SENDER + '|' + RECIPIENT + '|1500|0', 'sender|recipient|1500|0');
  const vectors = [
    [1500, 0, 'd4d7f1b4b3b04a048ad7b84b5af9c466558ea41c027781a1d2fa394e652abe43b0e2bdfc463ff861dcfa75fe1df322cc9abc0968f87c442679b12a1db1fe536e'],
    [1, 1, '8b944c6d7151ef318ac5138be4fa6096844bf2d96a68de7445e550ce172fd4162aaf5e1e392eec285728958c40593de42c99df3f76e74ca12a4cd6673cd9a57a'],
    [100000000, 2, '0352a1c4a9b5f7fe0d88118fc33aad8d4527f9f82bbb6f7abdc3172b3943e2ce61ec8a108bdb1e6fa8ad918fa7db42594bc3bf9f79f78ca9224d690b74ba752c'],
  ];
  check('txId matches Python testnet_tx_id on 3 vectors',
    vectors.every(([amt, nonce, want]) => A.txId(SENDER, RECIPIENT, amt, nonce) === want),
    '1500/0, 1/1, 100000000/2 — EvoHash-11 of the signed message');
  check('canonical address matches Python for 0x11*32 key',
    context.EvoHash11.r0niAddress(Uint8Array.from({ length: 32 }, () => 0x11)) === SENDER,
    'R0NI-d867166b51a61bcbd4c498524fb8cd3008514823');

  // --- a real extension-style signed transfer (WebCrypto) ---------
  const keyPair = await crypto.webcrypto.subtle.generateKey(
    { name: 'Ed25519' }, true, ['sign', 'verify']);
  const pubRaw = new Uint8Array(await crypto.webcrypto.subtle.exportKey('raw', keyPair.publicKey));
  const pubHex = [...pubRaw].map((b) => b.toString(16).padStart(2, '0')).join('');
  const sender = context.EvoHash11.r0niAddress(pubRaw);
  const amountMilli = A.parseAmount('1.500');
  const nonce = 0;
  const message = A.txMessage(sender, RECIPIENT, amountMilli, nonce);
  const sig = new Uint8Array(await crypto.webcrypto.subtle.sign(
    { name: 'Ed25519' }, keyPair.privateKey, new TextEncoder().encode(message)));
  const sigHex = [...sig].map((b) => b.toString(16).padStart(2, '0')).join('');
  const pubKey = await crypto.webcrypto.subtle.importKey(
    'raw', pubRaw, { name: 'Ed25519' }, false, ['verify']);
  const sigOk = await crypto.webcrypto.subtle.verify(
    { name: 'Ed25519' }, pubKey, sig, new TextEncoder().encode(message));
  check('extension-style WebCrypto Ed25519 signature verifies in-page',
    sigOk, 'fresh keypair, message sender|recipient|1500|0');
  const tx = A.buildTransferTx({
    sender, recipient: RECIPIENT, amountMilli, nonce,
    signatureHex: sigHex, senderPubkeyHex: pubHex,
    txidHex: A.txId(sender, RECIPIENT, amountMilli, nonce),
  });
  check('buildTransferTx: amount 1500 milli + milli marker',
    tx.amount === 1500 && tx.amount_unit === 'milli-R0NI'
    && tx.txid === A.txId(sender, RECIPIENT, 1500, 0),
    'txid ' + tx.txid.slice(0, 16) + '...');
  const outPath = process.argv[2] || '/tmp/extension-signed-tx.json';
  fs.writeFileSync(outPath, JSON.stringify(tx, null, 2) + '\n');
  console.log('wrote extension-style signed tx to ' + outPath);

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((e) => { console.error('HARNESS ERROR', e); process.exit(1); });
