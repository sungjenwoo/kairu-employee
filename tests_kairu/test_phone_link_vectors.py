"""The phone app's Link tests (phone/app/src/test, LinkCryptoTest) use vectors made with the PC's own code. These tests check
that the PC still agrees with those vectors, so a change on the PC that would break the phone fails here first."""

import base64
import json

from nacl.public import Box, PrivateKey
from nacl.signing import SigningKey

from kairu.config import ROOT
from kairu.link import keys, pairing
from kairu.link.message import open_envelope
from kairu.link.store import Device

V = json.loads((ROOT / "phone" / "app" / "src" / "test" / "resources" / "link-vectors.json").read_text(encoding="utf-8"))
b = lambda name: base64.b64decode(V[name])


def test_keys_ids_signature_and_box_still_match():
    phone_sign, phone_box = SigningKey(b("phone_sign_seed")), PrivateKey(b("phone_box_private"))
    assert bytes(phone_sign.verify_key) == b("phone_sign_public") and bytes(phone_box.public_key) == b("phone_box_public")
    assert keys.device_id(b("phone_sign_public"), "dev") == V["phone_id"] and keys.device_id(b("pc_sign_public"), "pc") == V["pc_id"]
    assert phone_sign.sign(b("message")).signature == b("phone_signature")
    assert bytes(Box(phone_box, PrivateKey(b("pc_box_private")).public_key).encrypt(b("message"), b("nonce"))) == b("box_phone_to_pc")


def test_the_pairing_proof_and_offer_still_match():
    assert pairing.proof(V["proof_code"], V["pc_id"], V["phone_id"], V["phone_sign_public"], V["phone_box_public"],
                         V["proof_nonce"]) == V["proof"]
    pc = keys.Identity(V["pc_id"], SigningKey(b("pc_sign_seed")), PrivateKey(b("pc_box_private")))
    assert pairing.offer_text(pc, "c" * 32, "https://ntfy.sh", 1762850600) == V["offer"]


def test_the_pcs_envelope_in_the_vectors_opens_for_the_phone():
    """The same check the phone does, run with the PC's code from the phone's side."""
    phone = keys.Identity(V["phone_id"], SigningKey(b("phone_sign_seed")), PrivateKey(b("phone_box_private")))
    pc_device = Device(V["pc_id"], "PC", b("pc_sign_public"), b("pc_box_public"), "c" * 32, 0)
    message = open_envelope(V["pc_envelope"], phone, lambda device: pc_device if device == V["pc_id"] else None,
                            lambda *args: True, now=V["pc_envelope_now_ms"] / 1000)
    assert (message.type, message.body) == ("report", "Hi from your PC")


def test_the_fingerprint_statement_in_the_vectors_is_still_the_pcs():
    from kairu.link import approver
    assert approver.statement(V["phone_id"], 7, "f" * 64, 1762850600).decode() == V["approve_statement"]
