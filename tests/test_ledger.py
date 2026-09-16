import pytest
from conftest import (deploy_ledger, set_sender, hx, op_dict, ag_dict, ledger_gate_hook,
                      OWNER, PARTY_A, PARTY_B, BYSTANDER, GATE_ADDR, SOURCE, RECIP)

VAULT = "__vault__"

def _funded_ledger(vm, amount=100):
    c = deploy_ledger(vm, hx(GATE_ADDR))
    c.mint(VAULT, amount)
    return c

def test_confirmed_duplicate_pays_nothing_no_double_execution(vm):
    # THE replay / double-spend proof: an op that discharges an already-satisfied
    # entitlement settles to satisfied_by_prior and moves ZERO value.
    c = _funded_ledger(vm)
    op = op_dict(oid="2", state="CONFIRMED_DUPLICATE", linked_prior="1")
    vm._gl_call_hook = ledger_gate_hook(op=op)
    with vm.activate():
        before = int(c.balance_of(VAULT))
        result = c.settle_operation("2")
        after = int(c.balance_of(VAULT))
    assert result == "satisfied_by_prior"
    assert before == after == 100            # vault untouched
    assert int(c.balance_of(RECIP)) == 0     # recipient paid nothing

def test_clear_new_executes_with_exact_conservation(vm):
    c = _funded_ledger(vm)
    op = op_dict(oid="1", state="CLEAR_NEW", amount="5")
    vm._gl_call_hook = ledger_gate_hook(op=op)
    with vm.activate():
        result = c.settle_operation("1")
        vault = int(c.balance_of(VAULT))
        recip = int(c.balance_of(RECIP))
    assert result == "executed"
    assert vault == 95      # down by exactly 5
    assert recip == 5       # up by exactly 5

def test_confirmed_new_executes(vm):
    c = _funded_ledger(vm)
    op = op_dict(oid="4", state="CONFIRMED_NEW", amount="5")
    vm._gl_call_hook = ledger_gate_hook(op=op)
    with vm.activate():
        result = c.settle_operation("4")
    assert result == "executed"
    assert int(c.balance_of(RECIP)) == 5

def test_permissionless_bystander_settle(vm):
    # a wallet that is neither owner nor a party settles an executable op; the
    # value math is exact. Answers the centralization critique in code.
    c = _funded_ledger(vm)
    op = op_dict(oid="1", state="CLEAR_NEW", amount="5")
    vm._gl_call_hook = ledger_gate_hook(op=op)
    with vm.activate():
        set_sender(vm, BYSTANDER)
        result = c.settle_operation("1")
        vault = int(c.balance_of(VAULT))
        recip = int(c.balance_of(RECIP))
    assert result == "executed"
    assert vault == 95 and recip == 5

def test_double_settle_reverts(vm):
    # settling the same op twice must revert on the second attempt.
    c = _funded_ledger(vm)
    op = op_dict(oid="1", state="CLEAR_NEW", amount="5")
    vm._gl_call_hook = ledger_gate_hook(op=op)
    with vm.activate():
        c.settle_operation("1")
        with pytest.raises(AssertionError):
            c.settle_operation("1")

def test_possible_duplicate_holds_funds_untouched(vm):
    c = _funded_ledger(vm)
    op = op_dict(oid="3", state="POSSIBLE_DUPLICATE", linked_prior="2")
    vm._gl_call_hook = ledger_gate_hook(op=op)
    with vm.activate():
        result = c.settle_operation("3")
        vault = int(c.balance_of(VAULT))
    assert result == "held"
    assert vault == 100      # nothing moved
    assert c.get_settlement("3")["status"] == "held"

def test_two_party_both_execute_pays_once(vm):
    # HELD_FINAL op resolved by the two named parties both approving execute.
    c = _funded_ledger(vm)
    op = op_dict(oid="5", state="HELD_FINAL", amount="5", linked_prior="2")
    ag = ag_dict(aid="1", party_a=hx(PARTY_A), party_b=hx(PARTY_B))
    vm._gl_call_hook = ledger_gate_hook(op=op, ag=ag)
    with vm.activate():
        c.settle_operation("5")   # -> held_final
        assert c.get_settlement("5")["status"] == "held_final"
        set_sender(vm, PARTY_A)
        r1 = c.party_approve("5", "execute")
        assert r1 == "awaiting_second_party"
        set_sender(vm, PARTY_B)
        r2 = c.party_approve("5", "execute")
        vault = int(c.balance_of(VAULT))
    assert r2 == "resolved_executed"
    assert vault == 95   # paid exactly once

def test_two_party_disagree_stays_frozen(vm):
    c = _funded_ledger(vm)
    op = op_dict(oid="5", state="HELD_FINAL", amount="5", linked_prior="2")
    ag = ag_dict(aid="1", party_a=hx(PARTY_A), party_b=hx(PARTY_B))
    vm._gl_call_hook = ledger_gate_hook(op=op, ag=ag)
    with vm.activate():
        c.settle_operation("5")
        set_sender(vm, PARTY_A)
        c.party_approve("5", "execute")
        set_sender(vm, PARTY_B)
        r = c.party_approve("5", "reject")
        vault = int(c.balance_of(VAULT))
    assert r == "parties_disagree"
    assert vault == 100   # frozen, nothing moved

def test_two_party_nonparty_rejected(vm):
    c = _funded_ledger(vm)
    op = op_dict(oid="5", state="HELD_FINAL", amount="5", linked_prior="2")
    ag = ag_dict(aid="1", party_a=hx(PARTY_A), party_b=hx(PARTY_B))
    vm._gl_call_hook = ledger_gate_hook(op=op, ag=ag)
    with vm.activate():
        c.settle_operation("5")
        set_sender(vm, BYSTANDER)
        with pytest.raises(AssertionError):
            c.party_approve("5", "execute")
