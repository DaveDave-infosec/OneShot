import pytest
from conftest import (deploy_ledger, set_sender, hx, op_dict, ag_dict, ledger_gate_hook,
                      OWNER, PARTY_A, PARTY_B, BYSTANDER, GATE_ADDR, RECIP)


def fresh(vm):
    c = deploy_ledger(vm, hx(GATE_ADDR))   # deployed by OWNER, who becomes the issuer
    set_sender(vm, OWNER)
    return c


def issued(c):
    return int(c.get_supply()["total_issued"])


def active_ag(aid="1"):
    return ag_dict(aid=aid, party_a=hx(PARTY_A), party_b=hx(PARTY_B))


# 1. the issuer mints into its own treasury, within the cap
def test_issuer_mints_into_own_treasury(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(400)
    assert int(c.balance_of(hx(OWNER))) == 400
    assert issued(c) == 400
    assert c.get_supply()["issuer"] == hx(OWNER).lower()


# 2. UNAUTHORIZED MINTING FAILS: a bystander cannot mint
def test_bystander_cannot_mint(vm):
    c = fresh(vm)
    with vm.activate():
        set_sender(vm, BYSTANDER)
        with pytest.raises(AssertionError):
            c.mint(5)
    assert issued(c) == 0
    assert int(c.balance_of(hx(BYSTANDER))) == 0


# 3. UNAUTHORIZED MINTING FAILS: a party or recipient cannot mint itself a balance
def test_party_cannot_mint_itself_a_balance(vm):
    c = fresh(vm)
    with vm.activate():
        set_sender(vm, PARTY_B)
        with pytest.raises(AssertionError):
            c.mint(5)
    assert issued(c) == 0
    assert int(c.balance_of(hx(PARTY_B))) == 0


# 4. scarcity: the issuer cannot mint past max_supply
def test_issuer_cannot_exceed_max_supply(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(1000)
        with pytest.raises(AssertionError):
            c.mint(1)
    assert issued(c) == 1000


# 5. there is no way to mint into a vault, an escrow, or a recipient
def test_mint_has_no_recipient_path(vm):
    c = fresh(vm)
    with vm.activate():
        with pytest.raises(Exception):
            c.mint("__vault__", 100)
        with pytest.raises(Exception):
            c.mint(RECIP, 100)
    assert issued(c) == 0
    assert int(c.balance_of("__vault__")) == 0
    assert int(c.balance_of(RECIP)) == 0


# 6. transfer is caller-bound: a holder can only move its own balance
def test_transfer_moves_only_own_balance(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(100)
        c.transfer(hx(PARTY_A), 30)
        set_sender(vm, BYSTANDER)
        with pytest.raises(AssertionError):
            c.transfer(hx(BYSTANDER), 1)
    assert int(c.balance_of(hx(OWNER))) == 70
    assert int(c.balance_of(hx(PARTY_A))) == 30
    assert issued(c) == 100


# 7. a pending agreement cannot be funded
def test_fund_escrow_on_pending_agreement_reverts(vm):
    c = fresh(vm)
    pending = active_ag()
    pending["active"] = False
    with vm.activate():
        c.mint(100)
        vm._gl_call_hook = ledger_gate_hook(ag=pending)
        with pytest.raises(AssertionError):
            c.fund_escrow("1", 60)
    assert int(c.get_escrow("1")) == 0
    assert int(c.balance_of(hx(OWNER))) == 100


# 8. funding moves the caller's own balance into the agreement's escrow
def test_fund_escrow_moves_caller_balance(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(100)
        vm._gl_call_hook = ledger_gate_hook(ag=active_ag())
        c.fund_escrow("1", 60)
    assert int(c.get_escrow("1")) == 60
    assert int(c.balance_of(hx(OWNER))) == 40


# 9. escrows are isolated: agreement 1 cannot be paid from agreement 2's escrow
def test_escrow_isolation_between_agreements(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(100)
        vm._gl_call_hook = ledger_gate_hook(ag=active_ag("2"))
        c.fund_escrow("2", 100)
        vm._gl_call_hook = ledger_gate_hook(op=op_dict(oid="1", agreement_id="1", state="CLEAR_NEW", amount="5"))
        with pytest.raises(AssertionError):
            c.settle_operation("1")
    assert int(c.get_escrow("2")) == 100
    assert int(c.get_escrow("1")) == 0
    assert int(c.balance_of(RECIP)) == 0


# 10. an underfunded escrow refuses the payout and moves nothing
def test_underfunded_escrow_refuses_payout(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(100)
        vm._gl_call_hook = ledger_gate_hook(ag=active_ag())
        c.fund_escrow("1", 3)
        vm._gl_call_hook = ledger_gate_hook(op=op_dict(oid="1", state="CLEAR_NEW", amount="5"))
        with pytest.raises(AssertionError):
            c.settle_operation("1")
    assert int(c.get_escrow("1")) == 3
    assert int(c.balance_of(RECIP)) == 0


# 11. supply invariant: every unit ever issued is accounted for, across a full flow
def test_supply_invariant_across_full_flow(vm):
    c = fresh(vm)
    with vm.activate():
        c.mint(200)
        c.transfer(hx(PARTY_A), 50)
        vm._gl_call_hook = ledger_gate_hook(ag=active_ag())
        c.fund_escrow("1", 100)
        vm._gl_call_hook = ledger_gate_hook(op=op_dict(oid="1", state="CLEAR_NEW", amount="5"))
        c.settle_operation("1")
    held = (int(c.balance_of(hx(OWNER))) + int(c.balance_of(hx(PARTY_A)))
            + int(c.balance_of(RECIP)) + int(c.get_escrow("1")))
    assert int(c.balance_of(RECIP)) == 5
    assert int(c.get_escrow("1")) == 95
    assert held == issued(c) == 200
