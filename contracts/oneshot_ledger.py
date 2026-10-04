# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

class OneShotLedger(gl.Contract):
    gate_address: str

    # ---- scarce, authorized asset model ----
    issuer: str
    max_supply: u256
    total_issued: u256
    escrow: TreeMap[str, u256]

    # internal token ledger (the ledger IS the token � Holdline pattern)
    balances: TreeMap[str, u256]

    # per-operation settlement record (flat parallel TreeMaps, keyed by op id)
    s_status: TreeMap[str, str]
    s_recipient: TreeMap[str, str]
    s_asset: TreeMap[str, str]
    s_amount: TreeMap[str, str]
    s_state: TreeMap[str, str]
    s_entitlement: TreeMap[str, str]
    s_linked_prior: TreeMap[str, str]
    s_agreement: TreeMap[str, str]
    s_note: TreeMap[str, str]

    # two-party joint release votes (keyed by op id)
    s_vote_a: TreeMap[str, str]
    s_vote_b: TreeMap[str, str]

    # ---- V2: metered settlement ----
    s_metered: TreeMap[str, bool]
    s_ent_id: TreeMap[str, str]
    s_payable: TreeMap[str, str]
    s_residual: TreeMap[str, str]
    s_residual_status: TreeMap[str, str]
    ent_paid: TreeMap[str, u256]

    settled_count: u256

    def __init__(self, gate_address: str, max_supply: u256):
        self.gate_address = gate_address.strip().lower()
        self.settled_count = u256(0)
        # The deployer is the only issuer. Total issuance can never exceed max_supply.
        assert int(max_supply) > 0, "max_supply must be greater than zero"
        self.issuer = gl.message.sender_address.as_hex.lower()
        self.max_supply = max_supply
        self.total_issued = u256(0)

    # ---- internal token ledger (Holdline pattern) ----
    @gl.public.write
    def mint(self, amount: u256) -> None:
        # Restricted issuance: only the issuer, only into the issuer's own
        # treasury balance, never beyond max_supply. There is no recipient
        # argument, so nothing can be minted into an escrow or a recipient.
        caller = gl.message.sender_address.as_hex.lower()
        assert caller == self.issuer, "only the issuer can mint"
        amt = int(amount)
        assert amt > 0, "mint amount must be greater than zero"
        issued = int(self.total_issued)
        assert issued + amt <= int(self.max_supply), "mint would exceed max_supply"
        self.total_issued = u256(issued + amt)
        cur = int(self.balances[caller]) if caller in self.balances else 0
        self.balances[caller] = u256(cur + amt)

    @gl.public.write
    def transfer(self, to_address: str, amount: u256) -> None:
        # A holder can only ever move their own balance.
        caller = gl.message.sender_address.as_hex.lower()
        to_addr = to_address.strip().lower()
        assert to_addr.startswith("0x") and len(to_addr) == 42, "recipient must be an address"
        amt = int(amount)
        assert amt > 0, "transfer amount must be greater than zero"
        cbal = int(self.balances[caller]) if caller in self.balances else 0
        assert cbal >= amt, "insufficient balance"
        self.balances[caller] = u256(cbal - amt)
        tbal = int(self.balances[to_addr]) if to_addr in self.balances else 0
        self.balances[to_addr] = u256(tbal + amt)

    @gl.public.write
    def fund_escrow(self, agreement_id: str, amount: u256) -> None:
        # Back an ACTIVE agreement with real balance. The caller moves their own
        # balance into that agreement's escrow; settlement for the agreement
        # draws only from here.
        aid = agreement_id.strip()
        caller = gl.message.sender_address.as_hex.lower()
        amt = int(amount)
        assert amt > 0, "escrow amount must be greater than zero"
        proxy = gl.get_contract_at(Address(self.gate_address))
        ag = proxy.view().get_agreement(aid)
        assert ag.get("active", False) is True, "agreement is pending: both named parties must accept it before it can be funded"
        cbal = int(self.balances[caller]) if caller in self.balances else 0
        assert cbal >= amt, "insufficient balance"
        self.balances[caller] = u256(cbal - amt)
        ebal = int(self.escrow[aid]) if aid in self.escrow else 0
        self.escrow[aid] = u256(ebal + amt)

    @gl.public.view
    def balance_of(self, account: str) -> u256:
        acct = account.strip().lower()
        return self.balances[acct] if acct in self.balances else u256(0)

    def _pay(self, oid: str, recipient: str, amount: int) -> None:
        # Settlement draws ONLY from the escrow of the operation's own agreement.
        # An agreement can never pay out more than was escrowed for it.
        aid = self.s_agreement[oid]
        ebal = int(self.escrow[aid]) if aid in self.escrow else 0
        assert ebal >= amount, "agreement escrow below payout amount"
        self.escrow[aid] = u256(ebal - amount)
        rbal = int(self.balances[recipient]) if recipient in self.balances else 0
        self.balances[recipient] = u256(rbal + amount)

    def _record_from_op(self, oid: str, op: dict) -> None:
        self.s_recipient[oid] = str(op["recipient"]).strip().lower()
        self.s_asset[oid] = str(op["asset"])
        self.s_amount[oid] = str(op["amount"])
        self.s_state[oid] = str(op["state"])
        self.s_entitlement[oid] = str(op["entitlement"])
        self.s_linked_prior[oid] = str(op["linked_prior"])
        self.s_agreement[oid] = str(op["agreement_id"])
        self.s_metered[oid] = op.get("metered", False) is True
        self.s_ent_id[oid] = str(op.get("entitlement_id", ""))
        self.s_payable[oid] = str(op.get("payable", ""))
        self.s_residual[oid] = str(op.get("residual", ""))

    def _apply_state(self, oid: str, state: str, linked_prior: str) -> str:
        # V2: metered ops settle on the gate's PAYABLE figure through the cap
        # guard. Non-metered ops continue on the unchanged V1 path below.
        if self.s_metered.get(oid, False):
            return self._apply_metered(oid, state, linked_prior)

        if state == "CLEAR_NEW" or state == "CONFIRMED_NEW":
            recipient = self.s_recipient[oid]
            amount = int(self.s_amount[oid])
            self._pay(oid, recipient, amount)
            self.s_status[oid] = "executed"
            self.s_note[oid] = "Executed. Discharges a distinct entitlement; payout released."
            self.settled_count = u256(int(self.settled_count) + 1)
            return "executed"

        if state == "CONFIRMED_DUPLICATE":
            self.s_status[oid] = "satisfied_by_prior"
            self.s_note[oid] = "Not executed. Discharges an entitlement already satisfied by prior operation " + linked_prior + "."
            self.settled_count = u256(int(self.settled_count) + 1)
            return "satisfied_by_prior"

        if state == "POSSIBLE_DUPLICATE" or state == "AMBIGUOUS":
            self.s_status[oid] = "held"
            self.s_note[oid] = "Held visibly. Suspected collision with prior operation " + linked_prior + ". Funds not moved; recoverable. Anyone may escalate to a forcing consensus pass."
            return "held"

        if state == "HELD_FINAL":
            self.s_status[oid] = "held_final"
            self.s_note[oid] = "Final hold. Consensus could not resolve even under a forced binary. Resolvable only by joint release of the two named agreement parties."
            return "held_final"

        if state == "REPLACEMENT":
            prior_ledger_status = self.s_status.get(linked_prior, "unsettled")
            if prior_ledger_status == "executed":
                self.s_status[oid] = "held"
                self.s_note[oid] = "Held. Marked as replacement of prior operation " + linked_prior + ", but that prior was already executed."
                return "held"
            if linked_prior != "":
                self.s_status[linked_prior] = "superseded"
                self.s_note[linked_prior] = "Superseded by replacement operation " + oid + "."
            recipient = self.s_recipient[oid]
            amount = int(self.s_amount[oid])
            self._pay(oid, recipient, amount)
            self.s_status[oid] = "executed"
            self.s_note[oid] = "Executed as replacement. Superseded pending prior operation " + linked_prior + "."
            self.settled_count = u256(int(self.settled_count) + 1)
            return "executed"

        self.s_status[oid] = "held"
        self.s_note[oid] = "Held. Unrecognized state from gate: " + state + "."
        return "held"

    # -----------------------------------------------------------------
    # V2 cap guard. Before ANY metered payout the ledger reads the
    # entitlement cap from the gate and asserts that what it has already
    # paid on that entitlement plus this payout stays within the cap. The
    # gate reserves at verdict time; the ledger enforces at payout time.
    # Invariant: ledger paid <= gate committed <= cap. Even a wrong gate
    # verdict cannot make the ledger overpay an entitlement.
    # -----------------------------------------------------------------
    def _pay_metered(self, oid: str, payable: int) -> None:
        aid = self.s_agreement[oid]
        eid = self.s_ent_id.get(oid, "")
        assert eid != "", "metered payout has no entitlement"
        assert payable > 0, "metered payout must be greater than zero"
        proxy = gl.get_contract_at(Address(self.gate_address))
        ent = proxy.view().get_entitlement(aid, eid)
        cap = int(str(ent["cap"]))
        k = aid + "|" + eid
        paid = int(self.ent_paid[k]) if k in self.ent_paid else 0
        assert paid + payable <= cap, "ledger cap guard: payout would exceed the entitlement cap"
        self._pay(oid, self.s_recipient[oid], payable)
        self.ent_paid[k] = u256(paid + payable)

    def _apply_metered(self, oid: str, state: str, linked_prior: str) -> str:
        eid = self.s_ent_id.get(oid, "")

        if state == "CONFIRMED_NEW":
            payable = int(self.s_payable[oid])
            self._pay_metered(oid, payable)
            self.s_status[oid] = "executed"
            self.s_note[oid] = "Executed. Paid " + str(payable) + " against entitlement " + eid + ", within its cap."
            self.settled_count = u256(int(self.settled_count) + 1)
            return "executed"

        if state == "PARTIAL":
            payable = int(self.s_payable[oid])
            residual = self.s_residual.get(oid, "0")
            self._pay_metered(oid, payable)
            self.s_status[oid] = "partial_executed"
            self.s_residual_status[oid] = "held"
            self.s_note[oid] = (
                "Partially executed. Paid " + str(payable) + ", the amount still owed on entitlement " + eid
                + ". Residual " + residual + " exceeds what the agreement grants and is held visibly, not erased."
                + " Recoverable only by joint release of the two named agreement parties."
            )
            self.settled_count = u256(int(self.settled_count) + 1)
            return "partial_executed"

        if state == "CONFIRMED_DUPLICATE":
            self.s_status[oid] = "satisfied_by_prior"
            self.s_note[oid] = "Not executed. Entitlement " + eid + " is already fully discharged up to its cap, first by operation " + linked_prior + "."
            self.settled_count = u256(int(self.settled_count) + 1)
            return "satisfied_by_prior"

        if state == "AMBIGUOUS" or state == "POSSIBLE_DUPLICATE":
            self.s_status[oid] = "held"
            self.s_note[oid] = "Held visibly. Consensus could not meter this operation against one entitlement with confidence. Funds not moved; recoverable. Anyone may escalate to a forcing consensus pass."
            return "held"

        if state == "HELD_FINAL":
            self.s_status[oid] = "held_final"
            self.s_note[oid] = "Final hold. Forced consensus could not meter this operation. Resolvable only by joint release of the two named agreement parties."
            return "held_final"

        self.s_status[oid] = "held"
        self.s_note[oid] = "Held. Unrecognized metered state from gate: " + state + "."
        return "held"

    # ---- V2: two-party vote on a PARTIAL op's held residual. ----
    def _resolve_residual(self, oid: str, vote_a: str, vote_b: str) -> str:
        residual = int(self.s_residual.get(oid, "0"))
        if vote_a == "execute" and vote_b == "execute":
            if residual > 0:
                self._pay(oid, self.s_recipient[oid], residual)
            self.s_residual_status[oid] = "resolved_executed"
            self.s_note[oid] = "Both named parties jointly released the residual of " + str(residual) + " beyond the entitlement cap. Paid once."
            return "residual_executed"
        if vote_a == "reject" and vote_b == "reject":
            self.s_residual_status[oid] = "resolved_rejected"
            self.s_note[oid] = "Both named parties jointly rejected the residual of " + str(residual) + ". Permanently refused; record retained."
            return "residual_rejected"
        self.s_note[oid] = "Parties disagree on the residual (party_a: '" + vote_a + "', party_b: '" + vote_b + "'). Residual stays held until they concur."
        return "parties_disagree"

    # ---- settle one operation: read verdict from gate, act. PERMISSIONLESS. ----
    @gl.public.write
    def settle_operation(self, op_id: str) -> str:
        oid = op_id.strip()
        assert self.s_status.get(oid, "unsettled") == "unsettled", "operation already settled"

        proxy = gl.get_contract_at(Address(self.gate_address))
        op = proxy.view().get_operation(oid)

        self._record_from_op(oid, op)
        state = str(op["state"])
        linked_prior = str(op["linked_prior"])
        return self._apply_state(oid, state, linked_prior)

    # ---- react to a gate state change after an on-gate escalate. PERMISSIONLESS. ----
    # Call this AFTER calling escalate(op_id) directly on the gate. It re-reads
    # the now-updated state via the proven view pattern and acts on it.
    @gl.public.write
    def sync_from_gate(self, op_id: str) -> str:
        oid = op_id.strip()
        cur = self.s_status.get(oid, "unsettled")
        assert cur == "held" or cur == "unsettled", "operation is not in a syncable held state"

        proxy = gl.get_contract_at(Address(self.gate_address))
        op = proxy.view().get_operation(oid)

        self._record_from_op(oid, op)
        state = str(op["state"])
        linked_prior = str(op["linked_prior"])
        return self._apply_state(oid, state, linked_prior)

    # ---- two-party joint release for a HELD_FINAL op. No authority. ----
    # Reads the two named parties from the gate. Caller must be one of them.
    # Acts only when BOTH parties have voted AND their votes match.
    @gl.public.write
    def party_approve(self, op_id: str, decision: str) -> str:
        oid = op_id.strip()
        cur_status = self.s_status.get(oid, "unsettled")
        residual_vote = cur_status == "partial_executed" and self.s_residual_status.get(oid, "") == "held"
        assert cur_status == "held_final" or residual_vote, "operation is not in a final hold or a held residual"

        dec = decision.strip().lower()
        assert dec == "execute" or dec == "reject", "decision must be execute or reject"

        caller = gl.message.sender_address.as_hex.lower()

        aid = self.s_agreement[oid]
        proxy = gl.get_contract_at(Address(self.gate_address))
        ag = proxy.view().get_agreement(aid)
        party_a = str(ag["party_a"]).strip().lower()
        party_b = str(ag["party_b"]).strip().lower()

        assert caller == party_a or caller == party_b, "caller is not a named party to this agreement"

        if caller == party_a:
            self.s_vote_a[oid] = dec
        if caller == party_b:
            self.s_vote_b[oid] = dec

        vote_a = self.s_vote_a.get(oid, "")
        vote_b = self.s_vote_b.get(oid, "")

        if vote_a == "" or vote_b == "":
            self.s_note[oid] = "Awaiting both parties. party_a vote: '" + vote_a + "', party_b vote: '" + vote_b + "'."
            return "awaiting_second_party"

        if residual_vote:
            return self._resolve_residual(oid, vote_a, vote_b)

        if vote_a == "execute" and vote_b == "execute":
            recipient = self.s_recipient[oid]
            amount = int(self.s_amount[oid])
            self._pay(oid, recipient, amount)
            self.s_status[oid] = "resolved_executed"
            self.s_note[oid] = "Both named parties jointly approved execution. Payout released."
            self.settled_count = u256(int(self.settled_count) + 1)
            return "resolved_executed"

        if vote_a == "reject" and vote_b == "reject":
            self.s_status[oid] = "resolved_rejected"
            self.s_note[oid] = "Both named parties jointly rejected. Permanently quarantined; not executed; record retained."
            self.settled_count = u256(int(self.settled_count) + 1)
            return "resolved_rejected"

        self.s_note[oid] = "Parties disagree (party_a: '" + vote_a + "', party_b: '" + vote_b + "'). Operation stays in final hold until they concur."
        return "parties_disagree"

    # ---- views ----
    @gl.public.view
    def get_settlement(self, op_id: str) -> dict:
        oid = op_id.strip()
        return {
            "op_id": oid,
            "status": self.s_status.get(oid, "unsettled"),
            "recipient": self.s_recipient.get(oid, ""),
            "asset": self.s_asset.get(oid, ""),
            "amount": self.s_amount.get(oid, ""),
            "state": self.s_state.get(oid, ""),
            "entitlement": self.s_entitlement.get(oid, ""),
            "linked_prior": self.s_linked_prior.get(oid, ""),
            "agreement_id": self.s_agreement.get(oid, ""),
            "vote_a": self.s_vote_a.get(oid, ""),
            "vote_b": self.s_vote_b.get(oid, ""),
            "note": self.s_note.get(oid, ""),
            "metered": self.s_metered.get(oid, False),
            "entitlement_id": self.s_ent_id.get(oid, ""),
            "payable": self.s_payable.get(oid, ""),
            "residual": self.s_residual.get(oid, ""),
            "residual_status": self.s_residual_status.get(oid, ""),
        }

    @gl.public.view
    def get_gate(self) -> str:
        return self.gate_address

    @gl.public.view
    def get_settled_count(self) -> u256:
        return self.settled_count

    @gl.public.view
    def get_entitlement_paid(self, agreement_id: str, entitlement_id: str) -> str:
        k = agreement_id + "|" + entitlement_id.strip().upper()
        return str(int(self.ent_paid[k])) if k in self.ent_paid else "0"

    @gl.public.view
    def get_escrow(self, agreement_id: str) -> u256:
        aid = agreement_id.strip()
        return self.escrow[aid] if aid in self.escrow else u256(0)

    @gl.public.view
    def get_supply(self) -> dict:
        return {
            "issuer": self.issuer,
            "max_supply": str(int(self.max_supply)),
            "total_issued": str(int(self.total_issued)),
        }

