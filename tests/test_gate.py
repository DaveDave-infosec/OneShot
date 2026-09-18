import pytest
from conftest import (deploy_gate, set_sender, gate_llm_hook, hx,
                      OWNER, BYSTANDER, RECIP)

TEXT = "Provider completes milestone M2 for a fixed fee. On acceptance, the completion payment for M2 becomes due to the provider."

# The gate now binds the operation source to the ACTUAL caller (gl.message
# .sender_address). The default vm sender is OWNER, so OWNER is registered as the
# authorized source. A caller can only ever submit as itself.
def _reg(c):
    return c.register_agreement("Smoke", TEXT, hx(OWNER), hx(OWNER),
                                "0x000000000000000000000000000000000000bbbb")

def _submit(c, obligation="M2", family="completion_payment", purpose="pay", hint="hint", incident=""):
    # the passed source arg is ignored by the gate for auth; caller identity wins.
    return c.submit_operation("1", hx(OWNER), RECIP, "GEN", "5", family, obligation, incident, purpose, hint)

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

def test_escalate_resolves_ambiguous_to_duplicate(vm):
    # With first-prior pairing, a duplicate-of-a-duplicate resolves directly to
    # CONFIRMED_DUPLICATE in the first pass (the first prior is the original).
    # Escalation is now needed only for AMBIGUOUS ops. Prove escalation still
    # resolves: an ambiguous first-pass verdict becomes CONFIRMED_DUPLICATE.
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        _submit(c)  # op1 CLEAR_NEW
        vm._gl_call_hook = gate_llm_hook("ambiguous")
        s2 = _submit(c, family="retention_release", purpose="r1", hint="h1")
        assert s2 == "AMBIGUOUS"
        vm._gl_call_hook = gate_llm_hook("duplicate")
        escalated = c.escalate("2")
    assert escalated == "CONFIRMED_DUPLICATE"
    assert c.get_operation("2")["state"] == "CONFIRMED_DUPLICATE"
    assert c.get_operation("2")["confidence"] == "forced"

# ---- Ask 1: an unauthorized CALLER cannot submit (source is caller-bound) ----
def test_unauthorized_caller_rejected(vm):
    # BYSTANDER is not an authorized source; even passing OWNER's address as the
    # source argument must not help, because the gate checks the real caller.
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        set_sender(vm, BYSTANDER)
        with pytest.raises(AssertionError):
            c.submit_operation("1", hx(OWNER), RECIP, "GEN", "5",
                               "completion_payment", "M2", "", "p", "h")

# ---- Ask 2: a duplicate cannot dodge comparison with a blank reference ----
def test_blank_reference_rejected(vm):
    # both obligation_ref and incident_id empty -> no collision key -> would skip
    # comparison entirely. The gate now rejects it so a duplicate cannot slip
    # through as CLEAR_NEW by omitting its reference.
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        with pytest.raises(AssertionError):
            c.submit_operation("1", hx(OWNER), RECIP, "GEN", "5",
                               "completion_payment", "", "", "p", "h")

# ---- Ask 2: a later duplicate pairs against the FIRST (original) prior ----
def test_pairs_against_first_prior_not_last(vm):
    # op1 opens the M2 bucket. op2 and op3 also target M2+recipient. op3 must be
    # paired against op1 (the original), not op2 (a later entry), so a duplicate
    # cannot be matched against a weaker/older-but-not-original entry.
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        _submit(c)  # op1 CLEAR_NEW (the original)
        vm._gl_call_hook = gate_llm_hook("duplicate")
        _submit(c, family="retention_release", purpose="r1", hint="h1")  # op2
        _submit(c, family="retention_release", purpose="r2", hint="h2")  # op3
    assert c.get_operation("2")["linked_prior"] == "1"
    assert c.get_operation("3")["linked_prior"] == "1"

# ---- Ask 4: the forcing pass CAN land on HELD_FINAL (reachable deadlock) ----
def test_escalate_unresolved_reaches_held_final(vm):
    # When the forcing pass genuinely cannot commit, it returns "unresolved" and
    # the operation moves to HELD_FINAL — the reachable path that unlocks the
    # two-party joint release. Proves the recovery path is real, not a claim.
    c = deploy_gate(vm)
    _reg(c)
    with vm.activate():
        _submit(c)  # op1 CLEAR_NEW
        vm._gl_call_hook = gate_llm_hook("ambiguous")
        s2 = _submit(c, family="retention_release", purpose="r1", hint="h1")
        assert s2 == "AMBIGUOUS"
        vm._gl_call_hook = gate_llm_hook("unresolved")
        result = c.escalate("2")
    assert result == "HELD_FINAL"
    assert c.get_operation("2")["state"] == "HELD_FINAL"
