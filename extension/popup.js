// RONI Wallet popup — scaffold v0.1, no real keys, no network yet.
// Next step: wire this to a Mac 'N Cheese node (JSON-RPC, TBD)
// and to encrypted key storage, mirroring roni_wallet.py.
document.getElementById('create').addEventListener('click', () => {
  document.getElementById('address').textContent =
    'RONI-… (test wallet — keys are in-memory only in this scaffold)';
});
document.getElementById('connect').addEventListener('click', () => {
  document.getElementById('balance').textContent =
    'No node yet — node / RPC is the next build after the wallet CLI.';
});
