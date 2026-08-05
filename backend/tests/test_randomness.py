import numpy as np
import pytest

from platon.randomness import (
    GENESIS_HASH,
    Beacon,
    draw_randomness,
    beacon_round_canonical,
    randomness_canonical,
    verify_beacon_chain,
    verify_checkpoint,
    verify_randomness,
)
from platon.signing import Signer


def _other_first_byte(hex_str: str) -> str:
    """Return `hex_str` with its first byte changed to one it definitely was not.

    The tamper tests below used to write a literal `"00" + rest` (or `"ff" + rest`).
    One run in 256 the draw already began with that byte, so the "tampered" value was
    byte-identical to the original, verification correctly returned True, and the suite
    reported a failure — on the one assertion that must never cry wolf. Harmless when
    draws were deterministic; a fresh coin flip every run since they take OS entropy.
    """
    return ("01" if hex_str[:2] == "00" else "00") + hex_str[2:]


# One displaced line caused both halves of this. The @pytest.fixture decorator had slipped up
# onto `_other_first_byte`, a plain string helper — so `signer` was an undecorated function that
# pytest could not inject, and 25 tests errored at SETUP rather than failing, while every direct
# call to the helper raised "Fixture called directly".
#
# The 25 are not incidental: beacon genesis binding, rejection of a forged genesis prev_hash,
# rejection of a front-truncated chain, and the two tamper-detection assertions. A suite
# reporting "47 passed" while a quarter of it never ran is worse than a red one — and this is
# the tree published to PyPI as aimarket-platon. The sibling copy under oracles/ never had the
# slip, which is why it reported 71 passed against this one's 47.
@pytest.fixture
def signer(tmp_path):
    return Signer(tmp_path / "key")


class TestChaosVRF:
    def test_draw_is_signed_and_verifies(self, signer):
        v = np.random.default_rng(1).normal(size=64)
        r = draw_randomness(v, tick=10, timestamp="2026-06-13T10:00:00Z", signer=signer)
        assert len(bytes.fromhex(r["random_hex"])) == 32
        assert verify_randomness(r, signer.public_key_b64) is True

    def test_num_bytes_clamped_and_honored(self, signer):
        v = np.zeros(64)
        r = draw_randomness(v, 1, "2026-06-13T10:00:00Z", signer, num_bytes=8)
        assert r["num_bytes"] == 8
        assert len(bytes.fromhex(r["random_hex"])) == 8
        big = draw_randomness(v, 1, "2026-06-13T10:00:00Z", signer, num_bytes=999)
        assert big["num_bytes"] == 64

    def test_different_state_gives_different_output(self, signer):
        v1 = np.random.default_rng(1).normal(size=64)
        v2 = np.random.default_rng(2).normal(size=64)
        ts = "2026-06-13T10:00:00Z"
        r1 = draw_randomness(v1, 5, ts, signer, client_seed="x")
        r2 = draw_randomness(v2, 5, ts, signer, client_seed="x")
        assert r1["random_hex"] != r2["random_hex"]

    def test_client_seed_changes_output(self, signer):
        v = np.random.default_rng(3).normal(size=64)
        ts = "2026-06-13T10:00:00Z"
        a = draw_randomness(v, 5, ts, signer, client_seed="alice")
        b = draw_randomness(v, 5, ts, signer, client_seed="bob")
        assert a["random_hex"] != b["random_hex"]

    def test_tampered_draw_is_rejected(self, signer):
        v = np.random.default_rng(4).normal(size=64)
        r = draw_randomness(v, 7, "2026-06-13T10:00:00Z", signer)
        tampered = dict(r)
        tampered["random_hex"] = _other_first_byte(r["random_hex"])
        assert verify_randomness(tampered, signer.public_key_b64) is False

    def test_canonical_is_stable(self, signer):
        v = np.zeros(64)
        r = draw_randomness(v, 1, "2026-06-13T10:00:00Z", signer)
        c = randomness_canonical(r["random_hex"], r["proof"])
        assert c.startswith("scheme:platon-chaos-vrf/v1|random_hex:")

    def test_unpredictable_with_os_entropy(self, signer):
        # Identical public inputs MUST now yield different output (true OS entropy),
        # and each draw commits to its entropy and stays signature-verifiable.
        v = np.zeros(64)
        a = draw_randomness(v, 7, "2026-06-13T10:00:00Z", signer, client_seed="same")
        b = draw_randomness(v, 7, "2026-06-13T10:00:00Z", signer, client_seed="same")
        assert a["random_hex"] != b["random_hex"]
        assert len(a["proof"]["entropy_commitment"]) == 64
        assert verify_randomness(a, signer.public_key_b64) is True


class TestBeacon:
    def test_chain_links_and_verifies(self, signer):
        beacon = Beacon(signer)
        v = np.random.default_rng(1).normal(size=64)
        for i in range(5):
            beacon.emit(v, tick=i, timestamp="2026-06-13T10:00:00Z", client_seed=str(i))
        rounds = list(beacon.rounds)
        assert [r["round"] for r in rounds] == [0, 1, 2, 3, 4]
        assert rounds[0]["prev_hash"] == GENESIS_HASH
        assert rounds[1]["prev_hash"] == rounds[0]["round_hash"]
        assert verify_beacon_chain(rounds, signer.public_key_b64) is True

    def test_tampering_breaks_chain(self, signer):
        beacon = Beacon(signer)
        v = np.zeros(64)
        for i in range(3):
            beacon.emit(v, tick=i, timestamp="2026-06-13T10:00:00Z")
        rounds = list(beacon.rounds)
        rounds[1]["random_hex"] = _other_first_byte(rounds[1]["random_hex"])
        assert verify_beacon_chain(rounds, signer.public_key_b64) is False

    def test_broken_link_rejected(self, signer):
        beacon = Beacon(signer)
        v = np.zeros(64)
        for i in range(3):
            beacon.emit(v, tick=i, timestamp="2026-06-13T10:00:00Z")
        rounds = list(beacon.rounds)
        rounds[2]["prev_hash"] = "0" * 64  # wrong link
        assert verify_beacon_chain(rounds, signer.public_key_b64) is False

    def test_signed_checkpoint_verifies(self, signer):
        beacon = Beacon(signer)
        beacon.emit(np.zeros(64), tick=0, timestamp="2026-06-13T10:00:00Z")
        cp = beacon.checkpoint("2026-06-13T10:00:10Z")
        assert cp["latest_round"] == 0 and cp["chain_length"] == 1
        assert verify_checkpoint(cp, signer.public_key_b64) is True
        cp["round_hash"] = "0" * 64  # tamper
        assert verify_checkpoint(cp, signer.public_key_b64) is False


class TestCommitReveal:
    def _beacon(self, signer):
        from platon.commit_reveal import CommitRevealBeacon

        return CommitRevealBeacon(signer)

    def test_commit_reveal_verifies(self, signer):
        from platon.commit_reveal import verify_reveal

        b = self._beacon(signer)
        v = np.zeros(64)
        c = b.commit(v, tick=1, committed_at="2026-06-13T10:00:00Z")
        assert "signature" in c and "preimage" not in c  # preimage stays secret at commit
        r = b.reveal(c["round"], client_seed="agent-42", revealed_at="2026-06-13T10:00:05Z")
        assert verify_reveal(r, signer.public_key_b64) is True

    def test_commitment_binds_preimage(self, signer):
        from platon.commit_reveal import verify_reveal

        b = self._beacon(signer)
        c = b.commit(np.zeros(64), 1, "2026-06-13T10:00:00Z")
        r = b.reveal(c["round"], "x", "2026-06-13T10:00:05Z")
        bad = dict(r)
        bad["preimage"] = r["preimage"] + "Z"  # guaranteed different
        assert verify_reveal(bad, signer.public_key_b64) is False
        bad2 = dict(r)
        bad2["random_hex"] = r["random_hex"] + "00"  # guaranteed different
        assert verify_reveal(bad2, signer.public_key_b64) is False

    def test_double_and_unknown_reveal_raise(self, signer):
        b = self._beacon(signer)
        c = b.commit(np.zeros(64), 1, "2026-06-13T10:00:00Z")
        b.reveal(c["round"], "x", "2026-06-13T10:00:05Z")
        with pytest.raises(ValueError):
            b.reveal(c["round"], "x", "2026-06-13T10:00:06Z")  # double
        with pytest.raises(ValueError):
            b.reveal(99999, "x", "2026-06-13T10:00:07Z")  # unknown


class TestSigning:
    def test_manifest_4field_self_verifies(self, signer):
        manifest = {
            "capabilities_count": 7,
            "generated_at": "2026-06-13T10:00:00Z",
            "protocol_version": "v2",
            "tools": [{"capability_id": "platon.random@v1"}],
        }
        manifest["signature"] = signer.sign_manifest(manifest)
        # canonical must include tools_hash (the live-hub 4-field form)
        assert "tools_hash:" in signer.manifest_canonical(manifest)
        assert signer.verify_manifest_signature(manifest) is True

    def test_manifest_tamper_rejected(self, signer):
        manifest = {
            "capabilities_count": 1,
            "generated_at": "2026-06-13T10:00:00Z",
            "protocol_version": "v2",
            "tools": [{"a": 1}],
        }
        manifest["signature"] = signer.sign_manifest(manifest)
        manifest["tools"] = [{"a": 2}]  # changes tools_hash
        assert signer.verify_manifest_signature(manifest) is False

    def test_receipt_7field_verifies(self, signer):
        receipt = signer.sign_receipt(
            {
                "nonce": "n1",
                "product_id": "prod-platon",
                "capability_id": "platon.random@v1",
                "price_usd": 0.004,
                "timestamp": "2026-06-13T10:00:00Z",
                "success": True,
                "latency_ms": 9,
            }
        )
        assert receipt["signature"]["algorithm"] == "ed25519"
        assert "public_key" not in receipt["signature"]  # hub receipt form
        assert signer.verify_receipt(receipt) is True


class TestEntropyBinding:
    """The proof must OPEN the entropy commitment and BIND random_hex to it — a valid
    signature alone must not be enough (a signed-but-fabricated output is rejected)."""

    def test_proof_reveals_and_opens_entropy(self, signer):
        import hashlib
        v = np.random.default_rng(9).normal(size=64)
        r = draw_randomness(v, 3, "2026-06-13T10:00:00Z", signer)
        ent = r["proof"]["entropy"]
        assert hashlib.sha256(bytes.fromhex(ent)).hexdigest() == r["proof"]["entropy_commitment"]
        assert verify_randomness(r, signer.public_key_b64) is True

    def test_fabricated_random_hex_rejected_even_with_valid_signature(self, signer):
        # Operator grinds an arbitrary random_hex and RE-SIGNS the canonical over it.
        v = np.random.default_rng(10).normal(size=64)
        r = draw_randomness(v, 4, "2026-06-13T10:00:00Z", signer)
        forged = dict(r)
        forged["random_hex"] = "de" * 32  # not derived from the committed entropy
        canonical = randomness_canonical(forged["random_hex"], forged["proof"])
        forged["signature"] = signer.sign_payload(canonical)  # signature is now VALID
        assert verify_randomness(forged, signer.public_key_b64) is False

    def test_tampered_entropy_no_longer_opens_commitment(self, signer):
        v = np.random.default_rng(11).normal(size=64)
        r = draw_randomness(v, 5, "2026-06-13T10:00:00Z", signer)
        bad = dict(r)
        bad["proof"] = dict(r["proof"])
        e = bytes.fromhex(r["proof"]["entropy"])
        bad["proof"]["entropy"] = (bytes([e[0] ^ 1]) + e[1:]).hex()  # commitment won't open
        assert verify_randomness(bad, signer.public_key_b64) is False

    def test_missing_entropy_rejected(self, signer):
        v = np.zeros(64)
        r = draw_randomness(v, 6, "2026-06-13T10:00:00Z", signer)
        bad = dict(r); bad["proof"] = {k: x for k, x in r["proof"].items() if k != "entropy"}
        assert verify_randomness(bad, signer.public_key_b64) is False


class TestBeaconGenesisAndBinding:
    def _chain(self, signer, n):
        b = Beacon(signer)
        v = np.random.default_rng(1).normal(size=64)
        return [b.emit(v, tick=i, timestamp="2026-06-13T10:00:00Z") for i in range(n)]

    def test_full_chain_verifies_with_genesis(self, signer):
        rounds = self._chain(signer, 4)
        assert verify_beacon_chain(rounds, signer.public_key_b64) is True

    def test_front_truncated_chain_rejected(self, signer):
        rounds = self._chain(signer, 4)
        assert verify_beacon_chain(rounds[1:], signer.public_key_b64) is False  # genesis gone
        # but the rolling-window mode accepts a linked suffix
        assert verify_beacon_chain(rounds[1:], signer.public_key_b64, require_genesis=False) is True

    def test_forged_genesis_prev_hash_rejected(self, signer):
        rounds = self._chain(signer, 2)
        rounds[0] = dict(rounds[0]); rounds[0]["prev_hash"] = "ab" * 32
        assert verify_beacon_chain(rounds, signer.public_key_b64) is False

    def test_beacon_round_entropy_is_opened(self, signer):
        rounds = self._chain(signer, 2)
        r0 = dict(rounds[0]); r0["random_hex"] = "de" * 32
        canonical = beacon_round_canonical(r0)  # keep signature valid over forged output
        import hashlib
        r0["signature"] = signer.sign_payload(canonical)
        r0["round_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        assert verify_beacon_chain([r0], signer.public_key_b64, require_genesis=False) is False
