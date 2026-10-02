import json
import pytest
from conftest import deploy_gate, set_sender, hx, OWNER, PARTY_A, PARTY_B, SOURCE

AG_TEXT = (
    "Provider completes milestone M2. Client pays a milestone M2 fee of 10 GEN. "
    "Client also pays a documentation fee of 4 GEN in addition to the M2 fee."
)

GOOD_SCHEDULE = json.dumps([
    {"id": "m2", "label": "M2 milestone fee", "cap": 10},
    {"id": "DOC", "label": "Documentation fee", "cap": 4},
])


def verify_hook(faithful, problems="", reasoning="grounded in the agreement wording", fenced=False):
    def hook(vm, request):
        if isinstance(request, dict) and "ExecPromptTemplate" in request:
            payload = json.dumps({
                "faithful": faithful,
                "problems": problems,
                "reasoning": reasoning,
            })
            if fenced:
                payload = "Here is my verdict:\n```json\n" + payload + "\n```\nDone."
            return {"ok": payload}
        return None
    return hook


def register(gate, schedule=GOOD_SCHEDULE):
    return gate.register_metered_agreement(
        "Metered Test", AG_TEXT, SOURCE, hx(PARTY_A), hx(PARTY_B), schedule
    )


def test_metered_faithful_schedule_registers_and_is_stored(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        vm._gl_call_hook = verify_hook("yes")
        aid = register(gate)
    assert aid == "1"

    ag = gate.get_agreement(aid)
    assert ag["metered"] is True

    s = gate.get_schedule(aid)
    assert s["metered"] is True
    assert s["schedule_reasoning"] == "grounded in the agreement wording"
    ents = s["entitlements"]
    assert len(ents) == 2
    assert ents[0]["id"] == "M2"
    assert ents[0]["cap"] == "10"
    assert ents[0]["committed"] == "0"
    assert ents[0]["remaining"] == "10"
    assert ents[0]["recipient"] == ""
    assert ents[1]["id"] == "DOC"
    assert ents[1]["cap"] == "4"

    e = gate.get_entitlement(aid, "doc")
    assert e["label"] == "Documentation fee"
    assert e["remaining"] == "4"


def test_metered_inflated_cap_rejected_by_consensus_and_nothing_stored(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    inflated = json.dumps([{"id": "M2", "label": "M2 milestone fee", "cap": 15}])
    with vm.activate():
        vm._gl_call_hook = verify_hook("no", problems="M2 cap 15 exceeds the written 10 GEN fee")
        with pytest.raises(AssertionError):
            register(gate, inflated)
    assert int(gate.get_agreement_count()) == 0


@pytest.mark.parametrize("bad_schedule", [
    json.dumps([]),
    json.dumps([{"id": "M2", "label": "M2 milestone fee", "cap": "10.5"}]),
    json.dumps([{"id": "M2", "label": "M2 milestone fee", "cap": 0}]),
    json.dumps([{"id": "M2", "label": "", "cap": 10}]),
    json.dumps([{"id": "none", "label": "M2 milestone fee", "cap": 10}]),
    json.dumps([{"id": "M2", "label": "a", "cap": 10}, {"id": "m2", "label": "b", "cap": 4}]),
])
def test_metered_schedule_shape_guards_reject_in_code(vm, bad_schedule):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        vm._gl_call_hook = verify_hook("yes")
        with pytest.raises(AssertionError):
            register(gate, bad_schedule)
    assert int(gate.get_agreement_count()) == 0


def test_metered_fenced_consensus_output_still_parses(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        vm._gl_call_hook = verify_hook("yes", fenced=True)
        aid = register(gate)
    assert gate.get_schedule(aid)["metered"] is True


def test_v1_agreement_reports_unmetered_with_empty_schedule(vm):
    gate = deploy_gate(vm)
    set_sender(vm, OWNER)
    with vm.activate():
        aid = gate.register_agreement("V1 Test", AG_TEXT, SOURCE, hx(PARTY_A), hx(PARTY_B))
    assert gate.get_agreement(aid)["metered"] is False
    s = gate.get_schedule(aid)
    assert s["metered"] is False
    assert s["entitlements"] == []
