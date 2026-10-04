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


def verify_hook():
    def hook(vm, request):
        if isinstance(request, dict) and "ExecPromptTemplate" in request:
            return {"ok": json.dumps({"faithful": "yes", "problems": "", "reasoning": "schedule matches the text"})}
        return None
    return hook


def map_hook(eid, mode="incremental", confidence="high", reasoning="grounded in the agreement wording", minority="", fenced=False):
    def hook(vm, request):
        if isinstance(request, dict) and "ExecPromptTemplate" in request:
            payload = json.dumps({
                "entitlement_id": eid,
                "amount_mode": mode,
                "confidence": confidence,
                "reasoning": reasoning,
                "minority_note": minority,
            })
            if fenced:
                payload = "Verdict follows.\n```json\n" + payload + "\n```"
            return {"ok": payload}
        return None
    return hook


def reg(vm, gate):
    vm._gl_call_hook = verify_hook()
    aid = gate.register_metered_agreement(
        "Metered", AG_TEXT, hx(OWNER), hx(PARTY_A), hx(PARTY_B), SCHEDULE
    )
    activate(vm, gate, aid, PARTY_A, PARTY_B)
    return aid


def sub(vm, gate, aid, amount, eid="M2", mode="incremental", confidence="high",
        recipient=RECIP, purpose="pay the M2 fee", fenced=False):
    vm._gl_call_hook = map_hook(eid, mode=mode, confidence=confidence, fenced=fenced)
    return gate.submit_operation(aid, hx(OWNER), recipient, "GEN", str(amount),
                                 "completion_payment", "M2", "", purpose, "hint")


def ent(gate, aid, eid):
    return gate.get_entitlement(aid, eid)


# 1. incremental within cap -> CONFIRMED_NEW, payable reserved
def test_incremental_within_cap_is_confirmed_new_and_reserves(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s = sub(vm, gate, aid, 7)
    assert s == "CONFIRMED_NEW"
    op = gate.get_operation("1")
    assert op["metered"] is True
    assert op["entitlement_id"] == "M2"
    assert op["amount_mode"] == "incremental"
    assert op["requested"] == "7"
    assert op["payable"] == "7"
    assert op["residual"] == "0"
    assert op["committed_before"] == "0"
    assert op["linked_prior"] == ""
    e = ent(gate, aid, "M2")
    assert e["committed"] == "7"
    assert e["remaining"] == "3"
    assert e["recipient"] == RECIP


# 2. THE V2 case: differently worded op over the remaining balance -> PARTIAL 3 / 2
def test_partial_pays_remaining_and_holds_excess(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 7)
        s = sub(vm, gate, aid, 5, purpose="release the retained amount for milestone 2")
    assert s == "PARTIAL"
    op = gate.get_operation("2")
    assert op["requested"] == "5"
    assert op["payable"] == "3"
    assert op["residual"] == "2"
    assert op["committed_before"] == "7"
    assert op["linked_prior"] == "1"
    assert "METERING (code)" in op["reasoning"]
    assert ent(gate, aid, "M2")["remaining"] == "0"


# 3. exhausted entitlement -> CONFIRMED_DUPLICATE, nothing reserved
def test_exhausted_entitlement_is_confirmed_duplicate(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 10)
        s = sub(vm, gate, aid, 4, purpose="pay M2 completion")
    assert s == "CONFIRMED_DUPLICATE"
    op = gate.get_operation("2")
    assert op["payable"] == "0"
    assert op["linked_prior"] == "1"
    assert ent(gate, aid, "M2")["committed"] == "10"


# 4. cumulative wording: "total 8" after 5 pays only 3; "total 4" pays nothing
def test_cumulative_mode_pays_only_the_difference(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s1 = sub(vm, gate, aid, 5)
        s2 = sub(vm, gate, aid, 8, mode="cumulative", purpose="M2 paid to date should total 8")
        s3 = sub(vm, gate, aid, 4, mode="cumulative", purpose="M2 total should be 4")
    assert s1 == "CONFIRMED_NEW"
    assert s2 == "CONFIRMED_NEW"
    op2 = gate.get_operation("2")
    assert op2["amount_mode"] == "cumulative"
    assert op2["requested"] == "3"
    assert op2["payable"] == "3"
    assert s3 == "CONFIRMED_DUPLICATE"
    assert gate.get_operation("3")["requested"] == "0"
    assert ent(gate, aid, "M2")["committed"] == "8"


# 5. cumulative over the cap -> PARTIAL
def test_cumulative_over_cap_is_partial(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 5)
        s = sub(vm, gate, aid, 12, mode="cumulative", purpose="bring M2 up to 12 in total")
    assert s == "PARTIAL"
    op = gate.get_operation("2")
    assert op["requested"] == "7"
    assert op["payable"] == "5"
    assert op["residual"] == "2"


# 6. reservation race: three ops verdicted before any settle can never exceed the cap
def test_reservation_race_sum_of_payable_never_exceeds_cap(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s1 = sub(vm, gate, aid, 7)
        s2 = sub(vm, gate, aid, 7, purpose="milestone 2 retention")
        s3 = sub(vm, gate, aid, 7, purpose="M2 final payment")
    assert [s1, s2, s3] == ["CONFIRMED_NEW", "PARTIAL", "CONFIRMED_DUPLICATE"]
    total = sum(int(gate.get_operation(str(i))["payable"]) for i in (1, 2, 3))
    assert total == 10
    assert ent(gate, aid, "M2")["committed"] == "10"


# 7. entitlements meter independently
def test_entitlements_meter_independently(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s1 = sub(vm, gate, aid, 10)
        s2 = sub(vm, gate, aid, 4, eid="DOC", purpose="documentation fee")
    assert s1 == "CONFIRMED_NEW"
    assert s2 == "CONFIRMED_NEW"
    assert ent(gate, aid, "DOC")["committed"] == "4"
    assert gate.get_operation("2")["linked_prior"] == ""


# 8. recipient redirect on a locked entitlement -> AMBIGUOUS, nothing reserved
def test_recipient_redirect_is_held(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        sub(vm, gate, aid, 5)
        s = sub(vm, gate, aid, 3, recipient=RECIP2)
    assert s == "AMBIGUOUS"
    op = gate.get_operation("2")
    assert op["payable"] == "0"
    assert "HELD:" in op["reasoning"]
    assert op["linked_prior"] == "1"
    assert ent(gate, aid, "M2")["committed"] == "5"


# 9. NONE mapping -> AMBIGUOUS, no reservation anywhere
def test_none_mapping_is_held(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s = sub(vm, gate, aid, 5, eid="NONE")
    assert s == "AMBIGUOUS"
    assert gate.get_operation("1")["entitlement_id"] == ""
    assert ent(gate, aid, "M2")["committed"] == "0"
    assert ent(gate, aid, "DOC")["committed"] == "0"


# 10. low confidence -> AMBIGUOUS, no reservation
def test_low_confidence_is_held(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s = sub(vm, gate, aid, 5, confidence="low")
    assert s == "AMBIGUOUS"
    assert gate.get_operation("1")["entitlement_id"] == "M2"
    assert ent(gate, aid, "M2")["committed"] == "0"


# 11. an id not in the schedule -> AMBIGUOUS
def test_invented_entitlement_id_is_held(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s = sub(vm, gate, aid, 5, eid="M9")
    assert s == "AMBIGUOUS"
    assert gate.get_operation("1")["entitlement_id"] == ""


# 12. non-whole or non-positive amounts revert in code
@pytest.mark.parametrize("bad_amount", ["0", "2.5", "-3"])
def test_bad_metered_amount_reverts(vm, bad_amount):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        with pytest.raises(AssertionError):
            sub(vm, gate, aid, bad_amount)


# 13. fenced mapping output still parses
def test_fenced_mapping_output_parses(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = reg(vm, gate)
        s = sub(vm, gate, aid, 7, fenced=True)
    assert s == "CONFIRMED_NEW"
