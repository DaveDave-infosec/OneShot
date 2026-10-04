import hashlib
import json
import pytest
from conftest import deploy_gate, set_sender, hx, OWNER, PARTY_A, PARTY_B, BYSTANDER, RECIP

TEXT = "Provider completes milestone M2. Client pays a milestone M2 fee of 10 GEN."
TEXT_HASH = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


def reg(gate):
    return gate.register_agreement("Acceptance", TEXT, hx(OWNER), hx(PARTY_A), hx(PARTY_B))


def submit(gate, aid):
    return gate.submit_operation(aid, hx(OWNER), RECIP, "GEN", "5",
                                 "completion_payment", "M2", "", "pay M2", "M2 fee")


def accept(vm, gate, aid, who, h=TEXT_HASH):
    set_sender(vm, who)
    r = gate.accept_agreement(aid, h)
    set_sender(vm, OWNER)
    return r


# 1. a new agreement starts pending, bound to the hash of its exact text
def test_new_agreement_starts_pending_with_text_hash(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(gate)
    ag = gate.get_agreement(aid)
    assert ag["active"] is False
    assert ag["accepted_a"] is False
    assert ag["accepted_b"] is False
    assert ag["text_hash"] == TEXT_HASH


# 2. a pending agreement cannot govern payouts
def test_submit_on_pending_agreement_reverts(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(gate)
        with pytest.raises(AssertionError):
            submit(gate, aid)
    assert int(gate.get_operation_count()) == 0


# 3. UNILATERAL ACTIVATION FAILS: party A alone cannot activate
def test_one_party_alone_cannot_activate(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(gate)
        r = accept(vm, gate, aid, PARTY_A)
        assert r == "pending"
        with pytest.raises(AssertionError):
            submit(gate, aid)
    ag = gate.get_agreement(aid)
    assert ag["accepted_a"] is True
    assert ag["accepted_b"] is False
    assert ag["active"] is False


# 4. both parties accepting activates it, and payouts can then be governed
def test_both_parties_activate_and_submit_works(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(gate)
        r1 = accept(vm, gate, aid, PARTY_A)
        r2 = accept(vm, gate, aid, PARTY_B)
        s = submit(gate, aid)
    assert r1 == "pending"
    assert r2 == "active"
    assert gate.get_agreement(aid)["active"] is True
    assert s == "CLEAR_NEW"


# 5. acceptance order does not matter
def test_party_b_first_then_a_activates(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(gate)
        r1 = accept(vm, gate, aid, PARTY_B)
        r2 = accept(vm, gate, aid, PARTY_A)
    assert r1 == "pending"
    assert r2 == "active"


# 6. a non-party cannot accept, so it cannot help activate
def test_non_party_cannot_accept(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(gate)
        with pytest.raises(AssertionError):
            accept(vm, gate, aid, BYSTANDER)
    assert gate.get_agreement(aid)["active"] is False


# 7. accepting with the wrong text hash reverts: you must accept the exact locked text
def test_wrong_text_hash_reverts(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    wrong = hashlib.sha256(b"Client pays a milestone M2 fee of 50 GEN.").hexdigest()
    with vm.activate():
        aid = reg(gate)
        with pytest.raises(AssertionError):
            accept(vm, gate, aid, PARTY_A, h=wrong)
    assert gate.get_agreement(aid)["accepted_a"] is False


# 8. a party cannot accept twice
def test_double_acceptance_reverts(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(gate)
        accept(vm, gate, aid, PARTY_A)
        with pytest.raises(AssertionError):
            accept(vm, gate, aid, PARTY_A)
    assert gate.get_agreement(aid)["active"] is False


# 9. one wallet cannot be both parties, which would make activation unilateral
def test_same_address_as_both_parties_rejected(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        with pytest.raises(AssertionError):
            gate.register_agreement("Solo", TEXT, hx(OWNER), hx(PARTY_A), hx(PARTY_A))
    assert int(gate.get_agreement_count()) == 0


# 10. a metered agreement is pending too until both parties accept
def test_metered_agreement_pending_until_both_accept(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    schedule = json.dumps([{"id": "M2", "label": "M2 milestone fee", "cap": 10}])

    def verify_hook(vm_, request):
        if isinstance(request, dict) and "ExecPromptTemplate" in request:
            return {"ok": json.dumps({"faithful": "yes", "problems": "", "reasoning": "matches"})}
        return None

    with vm.activate():
        vm._gl_call_hook = verify_hook
        aid = gate.register_metered_agreement("Metered", TEXT, hx(OWNER), hx(PARTY_A), hx(PARTY_B), schedule)
        assert gate.get_agreement(aid)["active"] is False
        with pytest.raises(AssertionError):
            submit(gate, aid)
        accept(vm, gate, aid, PARTY_A)
        accept(vm, gate, aid, PARTY_B)
    assert gate.get_agreement(aid)["active"] is True
