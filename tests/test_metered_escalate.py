import json
import pytest
from conftest import deploy_gate, set_sender, hx, OWNER, PARTY_A, PARTY_B, RECIP, RECIP2, activate

AG_TEXT = (
    "Provider completes milestone M2. Client pays a milestone M2 fee of 10 GEN. "
    "Client also pays a documentation fee of 4 GEN in addition to the M2 fee."
)

SCHEDULE = json.dumps([
    {"id": "M2", "label": "M2 milestone fee", "cap": 10},
    {"id": "DOC", "label": "Documentation fee", "cap": 4},
])


def json_hook(obj):
    def hook(vm, request):
        if isinstance(request, dict) and "ExecPromptTemplate" in request:
            return {"ok": json.dumps(obj)}
        return None
    return hook


def reg(vm, gate):
    vm._gl_call_hook = json_hook({"faithful": "yes", "problems": "", "reasoning": "schedule matches the text"})
    aid = gate.register_metered_agreement(
        "Metered", AG_TEXT, hx(OWNER), hx(PARTY_A), hx(PARTY_B), SCHEDULE
    )
    activate(vm, gate, aid, PARTY_A, PARTY_B)
    return aid


def sub(vm, gate, aid, amount, eid="M2", mode="incremental", confidence="high", recipient=RECIP):
    vm._gl_call_hook = json_hook({
        "entitlement_id": eid, "amount_mode": mode, "confidence": confidence,
        "reasoning": "first review", "minority_note": "",
    })
    return gate.submit_operation(aid, hx(OWNER), recipient, "GEN", str(amount),
                                 "completion_payment", "M2", "", "pay the M2 fee", "hint")


def esc(vm, gate, oid, eid="M2", mode="incremental"):
    vm._gl_call_hook = json_hook({
        "entitlement_id": eid, "amount_mode": mode,
        "reasoning": "forced review grounded in the agreement wording", "minority_note": "",
    })
    return gate.escalate(oid)


def committed(gate, aid, eid="M2"):
    return gate.get_entitlement(aid, eid)["committed"]


# 1. a low-confidence hold resolves on escalate and reserves only then
def test_escalate_commits_held_op_to_confirmed_new(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s1 = sub(vm, gate, aid, 5, confidence="low")
        assert s1 == "AMBIGUOUS"
        assert committed(gate, aid) == "0"
        s2 = esc(vm, gate, "1")
    assert s2 == "CONFIRMED_NEW"
    op = gate.get_operation("1")
    assert op["payable"] == "5"
    assert op["confidence"] == "forced"
    assert op["escalated"] is True
    assert committed(gate, aid) == "5"


# 2. a late resolve is metered against what is left NOW, not at submit time
def test_late_escalate_meters_against_current_remaining(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s1 = sub(vm, gate, aid, 6, confidence="low")
        s2 = sub(vm, gate, aid, 7)
        s3 = esc(vm, gate, "1")
    assert s1 == "AMBIGUOUS"
    assert s2 == "CONFIRMED_NEW"
    assert s3 == "PARTIAL"
    op = gate.get_operation("1")
    assert op["committed_before"] == "7"
    assert op["payable"] == "3"
    assert op["residual"] == "3"
    assert committed(gate, aid) == "10"


# 3. a held op resolved after the entitlement is exhausted pays nothing
def test_escalate_after_exhaustion_is_confirmed_duplicate(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 4, confidence="low")
        sub(vm, gate, aid, 10)
        s = esc(vm, gate, "1")
    assert s == "CONFIRMED_DUPLICATE"
    assert gate.get_operation("1")["payable"] == "0"
    assert committed(gate, aid) == "10"


# 4. UNRESOLVED is the honest deadlock -> HELD_FINAL, nothing reserved
def test_escalate_unresolved_reaches_held_final(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 5, eid="NONE")
        s = esc(vm, gate, "1", eid="UNRESOLVED")
    assert s == "HELD_FINAL"
    op = gate.get_operation("1")
    assert op["payable"] == "0"
    assert op["entitlement_id"] == ""
    assert "FINAL HOLD:" in op["reasoning"]
    assert committed(gate, aid) == "0"
    assert committed(gate, aid, "DOC") == "0"


# 5. a forced mapping cannot redirect a locked entitlement -> HELD_FINAL
def test_forced_mapping_cannot_redirect_locked_recipient(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 5)
        s2 = sub(vm, gate, aid, 3, recipient=RECIP2)
        assert s2 == "AMBIGUOUS"
        s3 = esc(vm, gate, "2")
    assert s3 == "HELD_FINAL"
    op = gate.get_operation("2")
    assert op["entitlement_id"] == "M2"
    assert op["payable"] == "0"
    assert committed(gate, aid) == "5"


# 6. a forced id outside the schedule -> HELD_FINAL
def test_forced_invented_id_reaches_held_final(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 5, confidence="low")
        s = esc(vm, gate, "1", eid="M9")
    assert s == "HELD_FINAL"
    assert committed(gate, aid) == "0"


# 7. a forced cumulative reading pays only the difference
def test_forced_cumulative_pays_only_the_difference(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 5)
        sub(vm, gate, aid, 8, confidence="low")
        s = esc(vm, gate, "2", mode="cumulative")
    assert s == "CONFIRMED_NEW"
    op = gate.get_operation("2")
    assert op["amount_mode"] == "cumulative"
    assert op["requested"] == "3"
    assert op["payable"] == "3"
    assert committed(gate, aid) == "8"


# 8. an op cannot be escalated twice
def test_metered_op_cannot_be_escalated_twice(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 5, eid="NONE")
        esc(vm, gate, "1", eid="UNRESOLVED")
        with pytest.raises(AssertionError):
            esc(vm, gate, "1")


# 9. an op that was never held cannot be escalated
def test_unheld_metered_op_cannot_be_escalated(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 5)
        with pytest.raises(AssertionError):
            esc(vm, gate, "1")
