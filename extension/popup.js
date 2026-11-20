// RONI Wallet popup — v0.2, own extension first.
// Real WebCrypto work, prototype only — not audited, do not use for real funds.
//
// What v0.2 does:
//  - Create an Ed25519 keypair with WebCrypto
//  - Encrypt the private key at rest with AES-GCM, key from PBKDF2(password)
//    100,000 iterations, SHA-256, random salt + IV per wallet
//  - Store only the encrypted key + public key in chrome.storage.local
//  - Unlock, sign a message, verify the signature, copy the address, lock, delete
//
// What v0.2 does NOT do:
//  - No node / balance / transaction sending yet
//  - Address is interim: "RONI-" + first 40 hex of SHA-512(public key).
//    The canonical address in roni_wallet.py is EvoHash-11(public key).
//    WebCrypto has no SHA3 / BLAKE2, so full EvoHash-11 in the browser
//    is v0.3 work. Do not mix v0.2 extension addresses with Python
//    wallet addresses — they will differ for the same key.
//  - Signing happens in the popup only; the background worker holds no keys.

const $ = (id) => document.getElementById(id);
const enc = new TextEncoder();
const dec = new TextDecoder();

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
  return 'RONI-' + bufToHex(digest).slice(0, 40);
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

async function init() {
  const { roniWallet } = await store.get(['roniWallet']);
  if (roniWallet) {
    $('address').textContent = roniWallet.address + ' (locked)';
    setStatus('Wallet found in this browser. Enter your password and Unlock.');
  }
  $('create').addEventListener('click', createWallet);
  $('unlock').addEventListener('click', unlockWallet);
  $('lock').addEventListener('click', lockWallet);
  $('sign').addEventListener('click', signMessage);
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
    setStatus('Wallet deleted from this browser.');
  });
}

init();
