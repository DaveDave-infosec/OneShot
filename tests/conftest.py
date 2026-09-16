import os as _os
_orig_unlink = _os.unlink
def _safe_unlink(path, *a, **k):
    try:
        return _orig_unlink(path, *a, **k)
    except PermissionError:
        return None
_os.unlink = _safe_unlink

import sys
from pathlib import Path
import pytest
from gltest.direct import deploy_contract, VMContext, create_address

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
GATE = CONTRACTS / "oneshot_gate.py"
LEDGER = CONTRACTS / "oneshot_ledger.py"
SDK = "v0.2.16"

def hx(b):
    return "0x" + b.hex()

OWNER = create_address("owner")
PARTY_A = create_address("party_a")
PARTY_B = create_address("party_b")
BYSTANDER = create_address("bystander")
GATE_ADDR = create_address("gate")

SOURCE = "0x7bbcac9c77aabc2aca19cd34f944fbc015f06a54"
RECIP = "0x000000000000000000000000000000000000aaaa"
RECIP2 = "0x000000000000000000000000000000000000cccc"

def set_sender(vm, addr):
    vm._sender = addr
    vm._refresh_gl_message()

@pytest.fixture(autouse=True)
def _reset_registry():
    m = sys.modules.get('genlayer.gl.genvm_contracts')
    if m is not None:
        m.__known_contract__ = None
    yield

@pytest.fixture
def vm():
    v = VMContext()
    set_sender(v, OWNER)
    return v

def deploy_gate(vm):
    return deploy_contract(GATE, vm, sdk_version=SDK)

def deploy_ledger(vm, gate_hex):
    return deploy_contract(LEDGER, vm, gate_hex, sdk_version=SDK)

# ---- gate consensus stub: the gate calls gl.eq_principle.prompt_non_comparative
# internally. We answer the ExecPromptTemplate request with a JSON string so the
# gate's REAL pairing + state-determination logic runs on our controlled verdict.
def gate_llm_hook(relationship, new_ent="entitlement B", prior_ent="entitlement A",
                  confidence="high", reasoning="grounded in the agreement wording",
                  minority=""):
    import json
    def hook(vm, request):
        if isinstance(request, dict) and "ExecPromptTemplate" in request:
            payload = json.dumps({
                "relationship": relationship,
                "new_entitlement": new_ent,
                "prior_entitlement": prior_ent,
                "confidence": confidence,
                "reasoning": reasoning,
                "minority_note": minority,
            })
            return {"ok": payload}
        return None
    return hook

# ---- ledger cross-contract stub: the ledger calls gl.get_contract_at(gate)
# .view().get_operation(oid) and .get_agreement(aid). We answer those two
# methods so the ledger's REAL settle / hold / party_approve logic runs.
def op_dict(oid="1", agreement_id="1", recipient=RECIP, amount="5", asset="GEN",
            state="CLEAR_NEW", entitlement="M2 completion payment", linked_prior="",
            action_family="completion_payment", obligation_ref="m2", incident_id="",
            economic_purpose="Completion payment for M2", entitlement_hint="M2 completion payment",
            collision_key="m2", prior_entitlement="", relationship="none",
            confidence="high", reasoning="cleared", minority_note="", escalated=False):
    return {"id": oid, "agreement_id": agreement_id, "source": SOURCE,
            "recipient": recipient, "asset": asset, "amount": amount,
            "action_family": action_family, "obligation_ref": obligation_ref,
            "incident_id": incident_id, "economic_purpose": economic_purpose,
            "entitlement_hint": entitlement_hint, "collision_key": collision_key,
            "state": state, "entitlement": entitlement,
            "prior_entitlement": prior_entitlement, "linked_prior": linked_prior,
            "relationship": relationship, "confidence": confidence,
            "reasoning": reasoning, "minority_note": minority_note, "escalated": escalated}

def ag_dict(aid="1", title="Smoke Test Agreement", text="Provider completes M2.",
            authorized_sources=SOURCE, party_a=None, party_b=None):
    pa = party_a if party_a is not None else SOURCE
    pb = party_b if party_b is not None else RECIP2
    return {"id": aid, "title": title, "agreement_text": text,
            "authorized_sources": authorized_sources,
            "party_a": pa.lower(), "party_b": pb.lower()}

def ledger_gate_hook(op=None, ag=None):
    from genlayer.py import calldata
    def hook(vm, request):
        if isinstance(request, dict) and "CallContract" in request:
            m = request["CallContract"]["calldata"]["method"]
            if m == "get_operation" and op is not None:
                return bytes([0]) + calldata.encode(op)
            if m == "get_agreement" and ag is not None:
                return bytes([0]) + calldata.encode(ag)
        return None
    return hook
