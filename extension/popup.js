// R0NI Wallet popup — v0.3, own extension first.
// Real WebCrypto work, prototype only — not audited, do not use for real funds.
//
// What v0.3 does:
//  - Create an Ed25519 keypair with WebCrypto
//  - Encrypt the private key at rest with AES-GCM, key from PBKDF2(password)
//    100,000 iterations, SHA-256, random salt + IV per wallet
//  - Store only the encrypted key + public key in chrome.storage.local
//  - Unlock, sign a message, verify the signature, copy the address, lock, delete
//  - Balance display from a local ledger: load genesis_allocation.json
//    (from the repo, or exported from wallet-app.html) with the "Load
//    ledger" file picker. If this wallet's address is the genesis
//    holder recorded in that ledger, the balance shows 100,000 R0NI;
//    otherwise it shows the balance computed from the ledger's
//    allocations + transfers, or 0 when no ledger is loaded.
//    There is no node yet — the ledger is a local file.
//
// What v0.3 does NOT do:
//  - No node / transaction sending yet (sending lives in wallet-app.html)
//  - Address is interim: "R0NI-" + first 40 hex of SHA-512(public key).
//    The canonical address in roni_wallet.py is EvoHash-11(public key).
//    WebCrypto has no SHA3 / BLAKE2, so full EvoHash-11 in the browser
//    is still v0.3 work — it was not finished in this version, and
//    unifying the two addresses remains open. Do not mix extension
//    addresses with Python wallet addresses — they differ for the same key.
//  - Signing happens in the popup only; the background worker holds no keys.
//
// Ticker: R0NI (renamed 2026-11-19 from RONI — 0 in place of O — to
// avoid confusion with an existing RONI token).

const $ = (id) => document.getElementById(id);
const enc = new TextEncoder();
const dec = new TextDecoder();
const GENESIS_SUPPLY = 100000;

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

async function interimAddress(publicKeyRaw) {
  const digest = await crypto.subtle.digest('SHA-512', publicKeyRaw);
  return 'R0NI-' + bufToHex(digest).slice(0, 40);
}

function ledgerBalance(ledger, address) {
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

async function refreshBalance() {
  const { roniWallet, r0niLedger } = await store.get(['roniWallet', 'r0niLedger']);
  if (!roniWallet) { $('balance').textContent = '— (no wallet yet)'; return; }
  const balance = ledgerBalance(r0niLedger, roniWallet.address);
  if (balance === null) {
    $('balance').textContent = '0 R0NI — no ledger loaded (load genesis_allocation.json below)';
    return;
  }
  const isGenesis = (r0niLedger.allocations || []).some(
    (a) => a.address === roniWallet.address && a.source === 'genesis');
  $('balance').textContent = balance.toLocaleString('en-US') + ' R0NI'
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
  const address = await interimAddress(pubRaw);
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
  setStatus('Wallet created and encrypted in this browser. Address is interim SHA-512 — see note below.');
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
    const ledger = JSON.parse(await file.text());
    if (ledger.ticker !== 'R0NI' && ledger.ticker !== 'RONI') {
      setStatus('That file is not an R0NI ledger (ticker is not R0NI).');
      return;
    }
    await store.set({ r0niLedger: ledger });
    await refreshBalance();
    setStatus('Ledger loaded: ' + (ledger.allocations || []).length
      + ' allocation(s), ' + (ledger.transfers || []).length + ' transfer(s).');
  } catch (e) {
    setStatus('Could not read that ledger file — it must be a genesis_allocation.json file.');
  }
}

async function init() {
  const { roniWallet } = await store.get(['roniWallet']);
  if (roniWallet) {
    $('address').textContent = roniWallet.address + ' (locked)';
    setStatus('Wallet found in this browser. Enter your password and Unlock.');
  }
  await refreshBalance();
  $('create').addEventListener('click', createWallet);
  $('unlock').addEventListener('click', unlockWallet);
  $('lock').addEventListener('click', lockWallet);
  $('sign').addEventListener('click', signMessage);
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
