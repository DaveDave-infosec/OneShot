import pytest
from conftest import (deploy_ledger, set_sender, hx, op_dict, ag_dict,
                      GATE_ADDR, OWNER, PARTY_A, PARTY_B, BYSTANDER, RECIP)

VAULT = "__vault__"

ENT_M2 = {"agreement_id": "1", "id": "M2", "label": "M2 milestone fee", "cap": "10",
          "committed": "10", "remaining": "0", "recipient": RECIP}

AG = ag_dict(party_a=hx(PARTY_A), party_b=hx(PARTY_B))


def mop(oid="1", amount="5", state="CONFIRMED_NEW", payable="5", residual="0",
        eid="M2", linked_prior="", mode="incremental"):
    d = op_dict(oid=oid, amount=amount, state=state, linked_prior=linked_prior)
    d.update({
        "metered": True,
        "entitlement_id": eid,
        "amount_mode": mode,
        "requested": payable,
        "payable": payable,
        "residual": residual,
        "committed_before": "0",
    })
    return d


def gate_hook(op=None, ag=None, ent=None):
    from genlayer.py import calldata
    def hook(vm, request):
        if isinstance(request, dict) and "CallContract" in request:
            m = request["CallContract"]["calldata"]["method"]
            if m == "get_operation" and op is not None:
                return bytes([0]) + calldata.encode(op)
            if m == "get_agreement" and ag is not None:
                return bytes([0]) + calldata.encode(ag)
            if m == "get_entitlement" and ent is not None:
                return bytes([0]) + calldata.encode(ent)
        return None
    return hook


def bal(c, who):
    return int(c.balance_of(who))


def fresh(vm):
    c = deploy_ledger(vm, hx(GATE_ADDR))
    set_sender(vm, OWNER)
    return c


# 1. cumulative "total 8" settles on PAYABLE 3, never on the raw amount 8
def test_metered_settles_on_payable_not_raw_amount(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(VAULT, 100)
        vm._gl_call_hook = gate_hook(op=mop(amount="8", payable="3", mode="cumulative"), ent=ENT_M2)
        r = c.settle_operation("1")
    assert r == "executed"
    assert bal(c, RECIP) == 3
    assert bal(c, VAULT) == 97
    assert c.get_entitlement_paid("1", "M2") == "3"


# 2. PARTIAL pays exactly the payable part, holds the residual, exact conservation
def test_partial_pays_payable_and_holds_residual(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(VAULT, 100)
        vm._gl_call_hook = gate_hook(op=mop(state="PARTIAL", amount="5", payable="3", residual="2"), ent=ENT_M2)
        r = c.settle_operation("1")
    assert r == "partial_executed"
    assert bal(c, RECIP) == 3
    assert bal(c, VAULT) == 97
    assert bal(c, RECIP) + bal(c, VAULT) == 100
    s = c.get_settlement("1")
    assert s["status"] == "partial_executed"
    assert s["residual"] == "2"
    assert s["residual_status"] == "held"
    assert c.get_entitlement_paid("1", "M2") == "3"


# 3. CAP GUARD: a wrong gate verdict cannot make the ledger overpay
def test_cap_guard_refuses_payout_beyond_cap(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(VAULT, 100)
        vm._gl_call_hook = gate_hook(op=mop(oid="1", payable="7"), ent=ENT_M2)
        c.settle_operation("1")
        vm._gl_call_hook = gate_hook(op=mop(oid="2", payable="5"), ent=ENT_M2)
        with pytest.raises(AssertionError):
            c.settle_operation("2")
    assert bal(c, RECIP) == 7
    assert bal(c, VAULT) == 93
    assert c.get_entitlement_paid("1", "M2") == "7"


# 4. metered duplicate moves nothing
def test_metered_duplicate_pays_nothing(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(VAULT, 100)
        vm._gl_call_hook = gate_hook(op=mop(state="CONFIRMED_DUPLICATE", payable="0", linked_prior="1"), ent=ENT_M2)
        r = c.settle_operation("2")
    assert r == "satisfied_by_prior"
    assert bal(c, RECIP) == 0
    assert bal(c, VAULT) == 100


# 5. metered hold moves nothing
def test_metered_ambiguous_holds_funds_untouched(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(VAULT, 100)
        vm._gl_call_hook = gate_hook(op=mop(state="AMBIGUOUS", payable="0"), ent=ENT_M2)
        r = c.settle_operation("1")
    assert r == "held"
    assert bal(c, VAULT) == 100


# 6. after an escalate, sync_from_gate settles the resolved PARTIAL
def test_sync_after_escalate_settles_partial(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(VAULT, 100)
        vm._gl_call_hook = gate_hook(op=mop(state="AMBIGUOUS", payable="0"), ent=ENT_M2)
        c.settle_operation("1")
        vm._gl_call_hook = gate_hook(op=mop(state="PARTIAL", amount="6", payable="3", residual="3"), ent=ENT_M2)
        r = c.sync_from_gate("1")
    assert r == "partial_executed"
    assert bal(c, RECIP) == 3
    assert c.get_settlement("1")["residual_status"] == "held"


def settle_partial(vm, c):
    c.mint(VAULT, 100)
    vm._gl_call_hook = gate_hook(op=mop(state="PARTIAL", amount="5", payable="3", residual="2"), ag=AG, ent=ENT_M2)
    c.settle_operation("1")


# 7. residual: both parties execute -> paid exactly once
def test_residual_both_execute_pays_once(vm):
    c = fresh(vm)
    with vm.activate():
        settle_partial(vm, c)
        set_sender(vm, PARTY_A)
        r1 = c.party_approve("1", "execute")
        set_sender(vm, PARTY_B)
        r2 = c.party_approve("1", "execute")
        with pytest.raises(AssertionError):
            c.party_approve("1", "execute")
    assert r1 == "awaiting_second_party"
    assert r2 == "residual_executed"
    assert bal(c, RECIP) == 5
    assert bal(c, VAULT) == 95
    assert c.get_settlement("1")["residual_status"] == "resolved_executed"


# 8. residual: both parties reject -> permanently refused
def test_residual_both_reject_is_permanent(vm):
    c = fresh(vm)
    with vm.activate():
        settle_partial(vm, c)
        set_sender(vm, PARTY_A)
        c.party_approve("1", "reject")
        set_sender(vm, PARTY_B)
        r = c.party_approve("1", "reject")
    assert r == "residual_rejected"
    assert bal(c, RECIP) == 3
    assert c.get_settlement("1")["residual_status"] == "resolved_rejected"


# 9. residual: parties disagree -> stays held, nothing moves
def test_residual_disagree_stays_held(vm):
    c = fresh(vm)
    with vm.activate():
        settle_partial(vm, c)
        set_sender(vm, PARTY_A)
        c.party_approve("1", "execute")
        set_sender(vm, PARTY_B)
        r = c.party_approve("1", "reject")
    assert r == "parties_disagree"
    assert bal(c, RECIP) == 3
    assert c.get_settlement("1")["residual_status"] == "held"


# 10. a non-party cannot vote on a residual
def test_nonparty_cannot_vote_on_residual(vm):
    c = fresh(vm)
    with vm.activate():
        settle_partial(vm, c)
        set_sender(vm, BYSTANDER)
        with pytest.raises(AssertionError):
            c.party_approve("1", "execute")


# 11. settlement stays permissionless: a bystander settles a PARTIAL exactly
def test_bystander_settles_partial_exactly(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(VAULT, 100)
        set_sender(vm, BYSTANDER)
        vm._gl_call_hook = gate_hook(op=mop(state="PARTIAL", amount="5", payable="3", residual="2"), ent=ENT_M2)
        r = c.settle_operation("1")
    assert r == "partial_executed"
    assert bal(c, RECIP) == 3
    assert bal(c, VAULT) == 97
