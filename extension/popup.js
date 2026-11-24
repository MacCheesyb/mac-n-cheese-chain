// R0NI Wallet popup — v0.5, own extension first.
// Real WebCrypto work, prototype only — not audited, do not use for real funds.
//
// What v0.5 does (new in v0.5 — milli-R0NI, 2026-11-23):
//  - Amounts are integer milli-R0NI (1 R0NI = 1000 milli; smallest
//    unit 0.001 R0NI), exactly as roni_wallet.py since commit
//    e308fee. Human amounts are parsed once, at the boundary, by
//    R0niAmounts.parseAmount() in amounts.js: decimal R0NI with
//    at most 3 places ("1.500" -> 1500 milli, "0.001" -> 1 milli).
//    Below 0.001 R0NI or more than 3 decimal places is rejected.
//    Balances display with exactly 3 places, e.g. 100000.000 R0NI.
//  - Sign a transfer: recipient + amount (decimal R0NI) + nonce,
//    signed over sender|recipient|<amount in milli>|nonce with
//    Ed25519, producing a signed testnet transaction JSON whose
//    "amount" is integer milli AND which carries
//    "amount_unit": "milli-R0NI". testnet/accept_signed_tx.py
//    accepts that tx; a tx without the marker is a pre-milli tx
//    and is REJECTED (never silently converted — that would be a
//    1000x error). Submit the signed JSON with
//    testnet/accept_signed_tx.py — the extension itself does not
//    talk to a node yet.
//  - Legacy ledgers (whole-R0NI amounts, no amount_unit marker)
//    are migrated x1000 on load, idempotently, mirroring
//    roni_wallet.py load_ledger().
//
// What v0.4 did (kept in v0.5, unchanged):
//  - Create an Ed25519 keypair with WebCrypto
//  - Encrypt the private key at rest with AES-GCM, key from PBKDF2(password)
//    100,000 iterations, SHA-256, random salt + IV per wallet
//  - Store only the encrypted key + public key in chrome.storage.local
//  - Unlock, sign a message, verify the signature, copy the address, lock, delete
//  - Balance display from a local ledger: load genesis_allocation.json
//    (from the repo, or exported from wallet-app.html) with the "Load
//    ledger" file picker. If this wallet's address is the genesis
//    holder recorded in that ledger, the balance shows 100000.000 R0NI;
//    otherwise it shows the balance computed from the ledger's
//    allocations + transfers, or 0 when no ledger is loaded.
//    There is no node yet — the ledger is a local file.
//  - Unified address: "R0NI-" + first 40 hex of EvoHash-11(public
//    key), the SAME canonical address as roni_wallet.py.
//    Implemented with the vendored EvoHash-11 bundle in
//    evo-hash-11.js (@noble/hashes 1.8.0, no CDN, no network).
//    Verified against Python on 6 test vectors, including the
//    0x11*32 key -> R0NI-d867166b51a61bcbd4c498524fb8cd3008514823.
//  - Migration: wallets created by v0.3 with the old interim
//    SHA-512 address are migrated on load — see
//    migrateInterimAddress() below. The same key now gives the
//    canonical address, and ledger entries for the old address are
//    rewritten to the new one, so a genesis allocation keeps working.
//
// What v0.5 does NOT do:
//  - No node connection yet (the signed transfer JSON is handed to
//    accept_signed_tx.py by the user; the popup does not POST it)
//  - Signing happens in the popup only; the background worker holds no keys.
//
// Ticker: R0NI (renamed 2026-11-19 from RONI — 0 in place of O — to
// avoid confusion with an existing RONI token).

const $ = (id) => document.getElementById(id);
const enc = new TextEncoder();
const dec = new TextDecoder();
const GENESIS_SUPPLY_R0NI = 100000;
const GENESIS_SUPPLY_MILLI = 100000000; // 100,000 R0NI x 1000 milli

function bufToHex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
function bufToB64(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}
function b64ToBuf(b64) {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
}
function setStatus(msg) { $('status').textContent = msg; }

// Storage: chrome.storage.local when available, in-memory fallback for testing.
const store = {
  _mem: {},
  async get(keys) {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      return chrome.storage.local.get(keys);
    }
    const out = {};
    for (const k of keys) out[k] = this._mem[k];
    return out;
  },
  async set(obj) {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      return chrome.storage.local.set(obj);
    }
    Object.assign(this._mem, obj);
  },
  async remove(keys) {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      return chrome.storage.local.remove(keys);
    }
    for (const k of keys) delete this._mem[k];
  },
};

async function deriveKey(password, salt) {
  const base = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' },
    base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
}

// Canonical address: "R0NI-" + first 40 hex of EvoHash-11(public key),
// exactly as roni_wallet.py. Synchronous — the vendored bundle in
// evo-hash-11.js (loaded before this file in popup.html) exposes
// global EvoHash11.r0niAddress(). Throws if the bundle did not load.
function canonicalAddress(publicKeyRaw) {
  if (typeof EvoHash11 === 'undefined' || !EvoHash11.r0niAddress) {
    throw new Error('EvoHash-11 bundle (evo-hash-11.js) did not load.');
  }
  return EvoHash11.r0niAddress(publicKeyRaw);
}
function hexToBytes(hex) {
  return Uint8Array.from(hex.match(/../g), (h) => parseInt(h, 16));
}

// Migration for wallets created by v0.3 (or earlier) with the interim
// SHA-512 address ("R0NI-" + first 40 hex of SHA-512(public key)).
// The same key now produces the canonical EvoHash-11 address, so:
//   1. recompute the address from the stored public key,
//   2. update the stored wallet address,
//   3. rewrite any local ledger allocation / transfer entries that
//      name the old interim address to the new canonical address
//      (same key, same wallet — the genesis 100,000 R0NI allocation
//      recorded against the old address moves with it, so the balance
//      stays 100,000).
// Returns { migrated: bool, oldAddress, newAddress }. No-op when the
// stored address is already canonical, or when there is no wallet.
async function migrateInterimAddress() {
  const { roniWallet, r0niLedger } = await store.get(['roniWallet', 'r0niLedger']);
  if (!roniWallet || !roniWallet.publicKeyHex) return { migrated: false };
  let newAddress;
  try {
    newAddress = canonicalAddress(hexToBytes(roniWallet.publicKeyHex));
  } catch (e) {
    return { migrated: false };
  }
  const oldAddress = roniWallet.address;
  if (oldAddress === newAddress) return { migrated: false, oldAddress, newAddress };
  roniWallet.address = newAddress;
  const updates = { roniWallet };
  if (r0niLedger) {
    for (const a of r0niLedger.allocations || []) {
      if (a.address === oldAddress) a.address = newAddress;
    }
    for (const tx of r0niLedger.transfers || []) {
      if (tx.from === oldAddress) tx.from = newAddress;
      if (tx.to === oldAddress) tx.to = newAddress;
    }
    updates.r0niLedger = r0niLedger;
  }
  await store.set(updates);
  return { migrated: true, oldAddress, newAddress };
}

// Amounts live in integer milli-R0NI (amounts.js, mirroring
// roni_wallet.py). A stored ledger may still be legacy
// (whole-R0NI amounts, no amount_unit marker) — migrate it x1000
// once and persist the migrated copy, so a second load does not
// multiply again. Returns the milli ledger (or null).
async function ensureMilliLedger() {
  const { r0niLedger } = await store.get(['r0niLedger']);
  if (!r0niLedger) return null;
  const { ledger, changed } = R0niAmounts.migrateLedgerAmounts(r0niLedger);
  if (changed) await store.set({ r0niLedger: ledger });
  return ledger;
}

async function refreshBalance() {
  const { roniWallet } = await store.get(['roniWallet']);
  if (!roniWallet) { $('balance').textContent = '— (no wallet yet)'; return; }
  const ledger = await ensureMilliLedger();
  if (!ledger) {
    $('balance').textContent = '0.000 R0NI — no ledger loaded (load genesis_allocation.json below)';
    return;
  }
  const balance = R0niAmounts.ledgerBalanceMilli(ledger, roniWallet.address);
  const isGenesis = (ledger.allocations || []).some(
    (a) => a.address === roniWallet.address && a.source === 'genesis');
  $('balance').textContent = R0niAmounts.formatAmount(balance) + ' R0NI'
    + (isGenesis ? ' — genesis holder' : ' (from local ledger)');
}

let unlockedPrivateKey = null;
let currentPublicKeyHex = null;

async function createWallet() {
  const password = $('password').value;
  if (!password || password.length < 8) {
    setStatus('Choose a password of at least 8 characters first.');
    return;
  }
  const keyPair = await crypto.subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
  const pubRaw = await crypto.subtle.exportKey('raw', keyPair.publicKey);
  const privRaw = await crypto.subtle.exportKey('pkcs8', keyPair.privateKey);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const aesKey = await deriveKey(password, salt);
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, aesKey, privRaw);
  const address = canonicalAddress(pubRaw);
  await store.set({
    roniWallet: {
      address,
      publicKeyHex: bufToHex(pubRaw),
      saltB64: bufToB64(salt),
      ivB64: bufToB64(iv),
      encryptedPrivateKeyB64: bufToB64(encrypted),
    },
  });
  currentPublicKeyHex = bufToHex(pubRaw);
  $('address').textContent = address;
  $('lock').disabled = false;
  await refreshBalance();
  setStatus('Wallet created and encrypted in this browser. Address is the canonical EvoHash-11 address — the same as roni_wallet.py gives for this key.');
}

async function unlockWallet() {
  const password = $('password').value;
  const { roniWallet } = await store.get(['roniWallet']);
  if (!roniWallet) { setStatus('No wallet in this browser yet — create one first.'); return; }
  try {
    const aesKey = await deriveKey(password, b64ToBuf(roniWallet.saltB64));
    const privRaw = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: new Uint8Array(b64ToBuf(roniWallet.ivB64)) },
      aesKey, b64ToBuf(roniWallet.encryptedPrivateKeyB64));
    unlockedPrivateKey = await crypto.subtle.importKey(
      'pkcs8', privRaw, { name: 'Ed25519' }, false, ['sign']);
    currentPublicKeyHex = roniWallet.publicKeyHex;
    $('address').textContent = roniWallet.address;
    $('lock').disabled = false;
    await refreshBalance();
    setStatus('Unlocked. You can sign now. Lock when done.');
  } catch (e) {
    setStatus('Unlock failed — wrong password, or the stored wallet is corrupt.');
  }
}

function lockWallet() {
  unlockedPrivateKey = null;
  $('lock').disabled = true;
  setStatus('Locked. Private key is not in memory.');
}

async function signMessage() {
  if (!unlockedPrivateKey) { setStatus('Unlock the wallet first.'); return; }
  const message = $('message').value;
  const sig = await crypto.subtle.sign({ name: 'Ed25519' }, unlockedPrivateKey, enc.encode(message));
  const sigHex = bufToHex(sig);
  $('signature').textContent = sigHex;
  // Verify with the stored public key, in this popup.
  const pubRaw = Uint8Array.from(currentPublicKeyHex.match(/../g), (h) => parseInt(h, 16));
  const pubKey = await crypto.subtle.importKey('raw', pubRaw, { name: 'Ed25519' }, false, ['verify']);
  const ok = await crypto.subtle.verify({ name: 'Ed25519' }, pubKey, sig, enc.encode(message));
  $('verifyResult').textContent = ok ? 'Valid signature' : 'INVALID signature';
  setStatus(ok ? 'Signed and verified.' : 'Signature did not verify — do not trust it.');
}

async function loadLedgerFile(file) {
  try {
    const raw = JSON.parse(await file.text());
    if (raw.ticker !== 'R0NI' && raw.ticker !== 'RONI') {
      setStatus('That file is not an R0NI ledger (ticker is not R0NI).');
      return;
    }
    // Legacy ledgers (whole-R0NI amounts, no amount_unit marker)
    // migrate x1000 on load, idempotently — same as roni_wallet.py.
    const { ledger, changed } = R0niAmounts.migrateLedgerAmounts(raw);
    await store.set({ r0niLedger: ledger });
    await refreshBalance();
    setStatus('Ledger loaded: ' + (ledger.allocations || []).length
      + ' allocation(s), ' + (ledger.transfers || []).length + ' transfer(s).'
      + (changed ? ' Legacy whole-R0NI amounts migrated x1000 to milli-R0NI.' : ''));
  } catch (e) {
    setStatus('Could not read that ledger file — it must be a genesis_allocation.json file.');
  }
}

// Sign a transfer (new in v0.5). The user enters the amount in
// decimal R0NI ("1.500"); it is parsed once, at this boundary,
// into integer milli-R0NI (1500) and the transaction is signed
// over sender|recipient|<milli>|nonce — exactly the message
// roni_wallet.py testnet_tx_message() signs. The signed JSON
// carries "amount_unit": "milli-R0NI" so testnet/accept_signed_tx.py
// knows it was signed in milli units. A transfer is NOT sent by
// the extension: copy the signed JSON and submit it with
// testnet/accept_signed_tx.py signed-tx.json (the node re-verifies
// it before accepting). Amounts below 0.001 R0NI or with more than
// 3 decimal places are rejected before anything is signed.
async function signTransfer() {
  if (!unlockedPrivateKey) { setStatus('Unlock the wallet first.'); return; }
  const { roniWallet } = await store.get(['roniWallet']);
  const recipient = $('txRecipient').value.trim();
  if (!recipient.startsWith('R0NI-') || recipient.length !== 45) {
    setStatus('Recipient must be an R0NI- address (R0NI- + 40 hex characters).');
    return;
  }
  let amountMilli;
  try {
    amountMilli = R0niAmounts.parseAmount($('txAmount').value);
  } catch (e) {
    setStatus('Amount rejected: ' + e.message);
    return;
  }
  const nonce = Number($('txNonce').value);
  if (!Number.isSafeInteger(nonce) || nonce < 0) {
    setStatus('Nonce must be a non-negative whole number (0 for the first transfer from this wallet).');
    return;
  }
  const ledger = await ensureMilliLedger();
  if (ledger) {
    const balance = R0niAmounts.ledgerBalanceMilli(ledger, roniWallet.address);
    if (balance < amountMilli) {
      setStatus('Insufficient balance: ' + R0niAmounts.formatAmount(balance)
        + ' R0NI in the loaded ledger, ' + R0niAmounts.formatAmount(amountMilli)
        + ' R0NI requested.');
      return;
    }
  }
  const sender = roniWallet.address;
  const message = R0niAmounts.txMessage(sender, recipient, amountMilli, nonce);
  const sig = await crypto.subtle.sign({ name: 'Ed25519' }, unlockedPrivateKey, enc.encode(message));
  const sigHex = bufToHex(sig);
  // Verify with the stored public key, in this popup, before showing it.
  const pubRaw = Uint8Array.from(currentPublicKeyHex.match(/../g), (h) => parseInt(h, 16));
  const pubKey = await crypto.subtle.importKey('raw', pubRaw, { name: 'Ed25519' }, false, ['verify']);
  const ok = await crypto.subtle.verify({ name: 'Ed25519' }, pubKey, sig, enc.encode(message));
  if (!ok) { setStatus('Signature did not verify — do not use this transaction.'); return; }
  const tx = R0niAmounts.buildTransferTx({
    sender,
    recipient,
    amountMilli,
    nonce,
    signatureHex: sigHex,
    senderPubkeyHex: currentPublicKeyHex,
    txidHex: R0niAmounts.txId(sender, recipient, amountMilli, nonce),
  });
  $('signedTx').value = JSON.stringify(tx, null, 2);
  setStatus('Signed ' + R0niAmounts.formatAmount(amountMilli) + ' R0NI (' + amountMilli
    + ' milli) to ' + recipient.slice(0, 12) + '… — signature verified. Copy the JSON below '
    + 'and submit it with testnet/accept_signed_tx.py signed-tx.json.');
}

async function init() {
  // Migrate a v0.3 interim-address wallet to the canonical address
  // before anything reads the stored address or balance.
  const migration = await migrateInterimAddress();
  const { roniWallet } = await store.get(['roniWallet']);
  if (roniWallet) {
    $('address').textContent = roniWallet.address + ' (locked)';
    if (migration.migrated) {
      setStatus('Migrated this wallet from its old interim address ('
        + migration.oldAddress + ') to the canonical EvoHash-11 address ('
        + migration.newAddress + '). Ledger entries were rewritten, so the balance is unchanged. Enter your password and Unlock.');
    } else {
      setStatus('Wallet found in this browser. Enter your password and Unlock.');
    }
  }
  await refreshBalance();
  $('create').addEventListener('click', createWallet);
  $('unlock').addEventListener('click', unlockWallet);
  $('lock').addEventListener('click', lockWallet);
  $('sign').addEventListener('click', signMessage);
  $('signTx').addEventListener('click', signTransfer);
  $('copySignedTx').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('signedTx').value); setStatus('Signed transaction copied.'); }
    catch { setStatus('Copy failed — select the signed transaction text manually.'); }
  });
  $('ledgerFile').addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) loadLedgerFile(e.target.files[0]);
  });
  $('copyAddress').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('address').textContent); setStatus('Address copied.'); }
    catch { setStatus('Copy failed — select the address text manually.'); }
  });
  $('deleteWallet').addEventListener('click', async () => {
    await store.remove(['roniWallet']);
    unlockedPrivateKey = null;
    $('address').textContent = 'No wallet loaded yet';
    $('signature').textContent = '—';
    $('verifyResult').textContent = '—';
    await refreshBalance();
    setStatus('Wallet deleted from this browser.');
  });
}

init();
