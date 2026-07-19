"""Chaos VRF — verifiable randomness drawn from the 32D chaotic shadow.

The 32 coupled Stuart-Landau / Kuramoto oscillators have a positive Lyapunov
exponent in the chaotic regime, so the evolving state is a deterministic but
practically unpredictable entropy source. Each draw:

1. hashes the full live state vector -> ``state_hash`` (the beacon round's entropy),
2. mixes in an optional ``client_seed`` (commit-reveal: the client contributes
   entropy the server cannot control) plus the tick and timestamp,
3. expands that to ``num_bytes`` of output in SHA-256 counter mode,
4. signs a canonical binding of (output, proof) with the service's Ed25519 key.

Consumers verify the signature against Platon's published ``signer_public_key``
(from ``/.well-known/ai-market.json``); the value is unpredictable before issuance
and non-repudiable after — a drand-style beacon backed by a chaotic oracle.
"""

from __future__ import annotations

import hashlib
import secrets
from collections import deque
from typing import Any

import numpy as np

SCHEME = "platon-chaos-vrf/v1"
BEACON_SCHEME = "platon-chaos-beacon/v1"


def _expand(seed: bytes, num_bytes: int) -> bytes:
    """SHA-256 counter-mode expansion to an arbitrary length."""
    out = bytearray()
    counter = 0
    while len(out) < num_bytes:
        out += hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(out[:num_bytes])


def randomness_canonical(random_hex: str, proof: dict[str, Any]) -> str:
    """The exact string signed for a randomness draw (UTF-8 bytes, Ed25519)."""
    return (
        f"scheme:{proof['scheme']}"
        f"|random_hex:{random_hex}"
        f"|state_hash:{proof['state_hash']}"
        f"|client_seed:{proof['client_seed']}"
        f"|tick:{proof['tick']}"
        f"|timestamp:{proof['timestamp']}"
        f"|entropy_commitment:{proof.get('entropy_commitment', '')}"
    )


def draw_randomness(
    state_vector: np.ndarray,
    tick: int,
    timestamp: str,
    signer: Any,
    num_bytes: int = 32,
    client_seed: str = "",
) -> dict[str, Any]:
    """Produce a signed verifiable-randomness draw from the current chaotic state."""
    num_bytes = max(1, min(int(num_bytes), 64))

    state_bytes = np.ascontiguousarray(state_vector, dtype=np.float64).tobytes()
    state_hash = hashlib.sha256(state_bytes).hexdigest()

    # Fresh OS-CSPRNG entropy makes the draw a true (unpredictable) entropy source — not
    # merely a deterministic function of the public inputs. We publish a commitment to it
    # (signed) AND reveal the preimage (`entropy`) so a consumer can OPEN the commitment
    # and re-derive `random_hex` — a signature alone does not prove the output came from
    # the committed entropy (see verify_randomness / _entropy_binding_ok).
    os_entropy = secrets.token_bytes(32)
    entropy_commitment = hashlib.sha256(os_entropy).hexdigest()

    seed = (
        bytes.fromhex(state_hash)
        + os_entropy
        + client_seed.encode()
        + str(tick).encode()
        + timestamp.encode()
    )
    random_hex = _expand(seed, num_bytes).hex()

    proof = {
        "scheme": SCHEME,
        "state_hash": state_hash,
        "client_seed": client_seed,
        "tick": tick,
        "timestamp": timestamp,
        "entropy_commitment": entropy_commitment,
        "entropy": os_entropy.hex(),  # revealed preimage — opens the commitment
    }
    signature = signer.sign_payload(randomness_canonical(random_hex, proof))

    return {
        "random_hex": random_hex,
        "num_bytes": num_bytes,
        "proof": proof,
        "signature": signature,
    }


def _entropy_binding_ok(
    random_hex: str,
    proof: dict[str, Any],
    *,
    prev_hash: str | None = None,
    counter: Any = None,
) -> bool:
    """Open the entropy commitment and rebind ``random_hex`` to the revealed entropy.

    A valid Ed25519 signature only proves the operator signed *these bytes* — it does NOT
    prove ``random_hex`` was actually derived from the committed entropy. So we (1) open the
    commitment: ``sha256(entropy) == entropy_commitment``, and (2) re-derive ``random_hex``
    from the revealed entropy plus the *signed* public inputs and require an exact match.
    The output length comes from ``len(random_hex)`` (inside the signed canonical), never
    from an unsigned ``num_bytes`` field.
    """
    entropy_hex = proof.get("entropy")
    commitment = proof.get("entropy_commitment", "")
    if not entropy_hex or not commitment:
        return False
    try:
        os_entropy = bytes.fromhex(entropy_hex)
        n = len(bytes.fromhex(random_hex))
        state_bytes = bytes.fromhex(proof["state_hash"])
        prev_bytes = bytes.fromhex(prev_hash) if prev_hash is not None else b""
    except (ValueError, KeyError, TypeError):
        return False
    if hashlib.sha256(os_entropy).hexdigest() != commitment:
        return False
    seed = (
        state_bytes
        + prev_bytes
        + os_entropy
        + str(proof.get("client_seed", "")).encode()
        + str(counter).encode()
        + str(proof.get("timestamp", "")).encode()
    )
    return _expand(seed, n).hex() == random_hex


def verify_randomness(result: dict[str, Any], public_key_b64: str | None = None) -> bool:
    """Verify a randomness draw end-to-end: signature, commitment opening, and rebinding.

    A signature-only check would accept a signed-but-fabricated output (the operator could
    grind ``random_hex`` and re-sign). We additionally open the entropy commitment and
    re-derive ``random_hex`` from the revealed entropy, so a valid signature over a
    fabricated output (or an unopened commitment) is rejected."""
    from platon.signing import Signer

    sig = result.get("signature") or {}
    key = public_key_b64 or sig.get("public_key")
    if not key:
        return False
    proof = result.get("proof") or {}
    random_hex = result.get("random_hex", "")
    canonical = randomness_canonical(random_hex, proof)
    if not Signer.verify(canonical, sig.get("value", ""), key):
        return False
    return _entropy_binding_ok(random_hex, proof, counter=proof.get("tick"))


GENESIS_HASH = "0" * 64


def beacon_round_canonical(rnd: dict[str, Any]) -> str:
    """The exact string signed (and hashed into round_hash) for a beacon round."""
    p = rnd["proof"]
    return (
        f"round:{rnd['round']}"
        f"|prev_hash:{rnd['prev_hash']}"
        f"|random_hex:{rnd['random_hex']}"
        f"|state_hash:{p['state_hash']}"
        f"|client_seed:{p['client_seed']}"
        f"|tick:{p['tick']}"
        f"|timestamp:{p['timestamp']}"
        f"|entropy_commitment:{p.get('entropy_commitment', '')}"
    )


class Beacon:
    """Hash-chained verifiable randomness beacon.

    Each round links to the previous one's ``round_hash`` (a SHA-256 of the
    round's canonical) and is Ed25519-signed. Altering any past round breaks both
    its signature and every subsequent ``prev_hash`` — a provable, tamper-evident
    chain (drand-style), with entropy sourced from the chaotic state plus the
    forward-chained ``prev_hash`` and optional client seed.
    """

    def __init__(self, signer: Any, maxlen: int = 512) -> None:
        self._signer = signer
        self.rounds: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def latest(self) -> dict[str, Any] | None:
        return self.rounds[-1] if self.rounds else None

    def checkpoint(self, timestamp: str) -> dict[str, Any]:
        """A signed commitment to the current chain head — meant to be anchored to
        an external transparency log / chain so the operator cannot silently rewrite
        history (docs/SECURITY.md §2.4)."""
        latest = self.latest()
        body = {
            "scheme": "platon-beacon-checkpoint/v1",
            "latest_round": latest["round"] if latest else -1,
            "round_hash": latest["round_hash"] if latest else GENESIS_HASH,
            "chain_length": len(self.rounds),
            "timestamp": timestamp,
        }
        body["signature"] = self._signer.sign_payload(checkpoint_canonical(body))
        return body

    def emit(
        self,
        state_vector: np.ndarray,
        tick: int,
        timestamp: str,
        num_bytes: int = 32,
        client_seed: str = "",
    ) -> dict[str, Any]:
        num_bytes = max(1, min(int(num_bytes), 64))
        prev = self.latest()
        round_no = prev["round"] + 1 if prev else 0
        prev_hash = prev["round_hash"] if prev else GENESIS_HASH

        state_bytes = np.ascontiguousarray(state_vector, dtype=np.float64).tobytes()
        state_hash = hashlib.sha256(state_bytes).hexdigest()
        os_entropy = secrets.token_bytes(32)  # true OS-CSPRNG entropy per round
        entropy_commitment = hashlib.sha256(os_entropy).hexdigest()
        seed = (
            bytes.fromhex(state_hash)
            + bytes.fromhex(prev_hash)
            + os_entropy
            + client_seed.encode()
            + str(round_no).encode()
            + timestamp.encode()
        )
        random_hex = _expand(seed, num_bytes).hex()

        rnd: dict[str, Any] = {
            "round": round_no,
            "prev_hash": prev_hash,
            "random_hex": random_hex,
            "num_bytes": num_bytes,
            "proof": {
                "scheme": BEACON_SCHEME,
                "state_hash": state_hash,
                "client_seed": client_seed,
                "tick": tick,
                "timestamp": timestamp,
                "entropy_commitment": entropy_commitment,
                "entropy": os_entropy.hex(),  # revealed preimage — opens the commitment
            },
        }
        canonical = beacon_round_canonical(rnd)
        rnd["signature"] = self._signer.sign_payload(canonical)
        rnd["round_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        self.rounds.append(rnd)
        return rnd


def checkpoint_canonical(cp: dict[str, Any]) -> str:
    return (
        f"scheme:{cp['scheme']}|latest_round:{cp['latest_round']}"
        f"|round_hash:{cp['round_hash']}|chain_length:{cp['chain_length']}"
        f"|timestamp:{cp['timestamp']}"
    )


def verify_checkpoint(cp: dict[str, Any], public_key_b64: str | None = None) -> bool:
    from platon.signing import Signer

    sig = cp.get("signature") or {}
    key = public_key_b64 or sig.get("public_key")
    return bool(key) and Signer.verify(checkpoint_canonical(cp), sig.get("value", ""), key)


def verify_beacon_chain(
    rounds: list[dict[str, Any]],
    public_key_b64: str | None = None,
    require_genesis: bool = True,
) -> bool:
    """Verify each round's signature, round_hash, prev_hash linkage, and entropy binding.

    With ``require_genesis=True`` (default) the chain must start at round 0 with
    ``prev_hash == GENESIS_HASH`` — otherwise a *front-truncated* suffix of a genuine chain
    would verify as a complete, valid chain. Pass ``require_genesis=False`` only for
    integrity checks over a rolling window that legitimately no longer holds genesis."""
    from platon.signing import Signer

    prev_hash = None
    for rnd in rounds:
        canonical = beacon_round_canonical(rnd)
        sig = rnd.get("signature") or {}
        key = public_key_b64 or sig.get("public_key")
        if not key or not Signer.verify(canonical, sig.get("value", ""), key):
            return False
        if hashlib.sha256(canonical.encode()).hexdigest() != rnd.get("round_hash"):
            return False
        if prev_hash is not None and rnd.get("prev_hash") != prev_hash:
            return False
        # open + rebind this round's entropy (seed chains prev_hash and keys off round_no)
        if not _entropy_binding_ok(
            rnd.get("random_hex", ""), rnd.get("proof") or {},
            prev_hash=rnd.get("prev_hash"), counter=rnd.get("round"),
        ):
            return False
        prev_hash = rnd["round_hash"]

    if require_genesis and rounds:
        first = rounds[0]
        if first.get("round") != 0 or first.get("prev_hash") != GENESIS_HASH:
            return False
    return True
