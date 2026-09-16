import pytest
from conftest import (deploy_gate, set_sender, gate_llm_hook,
                      OWNER, SOURCE, RECIP)

TEXT = "Provider completes milestone M2 for a fixed fee. On acceptance, the completion payment for M2 becomes due to the provider."

def _reg(c):
    return c.register_agreement("Smoke", TEXT, SOURCE, SOURCE, "0x000000000000000000000000000000000000bbbb")

def _submit(c, obligation="M2", family="completion_payment", purpose="pay", hint="hint"):
    return c.submit_operation("1", SOURCE, RECIP, "GEN", "5", family, obligation, "", purpose, hint)

def test_novel_op_clears_in_code_without_consensus(vm):
    # a first op on a fresh obligation has no prior -> CLEAR_NEW purely in code.
    # No consensus hook is set; if the gate tried to call the LLM this would fail.
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        state = _submit(c)
    assert state == "CLEAR_NEW"
    assert c.get_operation("1")["state"] == "CLEAR_NEW"
    assert c.get_operation("1")["linked_prior"] == ""

def test_first_pass_duplicate_against_clean_prior(vm):
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        _submit(c)  # op1 CLEAR_NEW
        vm._gl_call_hook = gate_llm_hook("duplicate")
        state = _submit(c, family="retention_release", purpose="release", hint="retained")
    assert state == "CONFIRMED_DUPLICATE"
    assert c.get_operation("2")["linked_prior"] == "1"

def test_first_pass_distinct_is_confirmed_new(vm):
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        _submit(c)  # op1 CLEAR_NEW
        vm._gl_call_hook = gate_llm_hook("distinct")
        state = _submit(c, family="retention_release", purpose="release", hint="retained")
    assert state == "CONFIRMED_NEW"

def test_escalate_resolves_duplicate_of_a_duplicate(vm):
    # the fix: op3 is a duplicate whose prior (op2) is itself a duplicate, so the
    # first pass holds it POSSIBLE_DUPLICATE. Escalation forces a binding
    # duplicate verdict which MUST resolve to CONFIRMED_DUPLICATE, not hold again.
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        _submit(c)  # op1 CLEAR_NEW
        vm._gl_call_hook = gate_llm_hook("duplicate")
        _submit(c, family="retention_release", purpose="r1", hint="h1")  # op2 CONFIRMED_DUPLICATE
        s3 = _submit(c, family="retention_release", purpose="r2", hint="h2")  # op3
        assert s3 == "POSSIBLE_DUPLICATE"
        vm._gl_call_hook = gate_llm_hook("duplicate")
        escalated = c.escalate("3")
    assert escalated == "CONFIRMED_DUPLICATE"
    assert c.get_operation("3")["state"] == "CONFIRMED_DUPLICATE"
    assert c.get_operation("3")["confidence"] == "forced"

def test_unauthorized_source_rejected(vm):
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        with pytest.raises(AssertionError):
            c.submit_operation("1", "0x000000000000000000000000000000000000dead",
                               RECIP, "GEN", "5", "completion_payment", "M2", "", "p", "h")
