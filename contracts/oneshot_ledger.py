# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

# fixed internal-ledger key for funds held by the ledger itself.
VAULT_KEY = "__vault__"


class OneShotLedger(gl.Contract):
    gate_address: str

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

    settled_count: u256

    def __init__(self, gate_address: str):
        self.gate_address = gate_address.strip().lower()
        self.settled_count = u256(0)

    # ---- internal token ledger (Holdline pattern) ----
    @gl.public.write
    def mint(self, to_address: str, amount: u256) -> None:
        to_addr = to_address.strip().lower()
        cur = int(self.balances[to_addr]) if to_addr in self.balances else 0
        self.balances[to_addr] = u256(cur + int(amount))

    @gl.public.view
    def balance_of(self, account: str) -> u256:
        acct = account.strip().lower()
        return self.balances[acct] if acct in self.balances else u256(0)

    def _pay(self, recipient: str, amount: int) -> None:
        vbal = int(self.balances[VAULT_KEY]) if VAULT_KEY in self.balances else 0
        assert vbal >= amount, "ledger vault balance below payout amount"
        self.balances[VAULT_KEY] = u256(vbal - amount)
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

    def _apply_state(self, oid: str, state: str, linked_prior: str) -> str:
        if state == "CLEAR_NEW" or state == "CONFIRMED_NEW":
            recipient = self.s_recipient[oid]
            amount = int(self.s_amount[oid])
            self._pay(recipient, amount)
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
            self._pay(recipient, amount)
            self.s_status[oid] = "executed"
            self.s_note[oid] = "Executed as replacement. Superseded pending prior operation " + linked_prior + "."
            self.settled_count = u256(int(self.settled_count) + 1)
            return "executed"

        self.s_status[oid] = "held"
        self.s_note[oid] = "Held. Unrecognized state from gate: " + state + "."
        return "held"

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
        assert self.s_status.get(oid, "unsettled") == "held_final", "operation is not in a final hold"

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

        if vote_a == "execute" and vote_b == "execute":
            recipient = self.s_recipient[oid]
            amount = int(self.s_amount[oid])
            self._pay(recipient, amount)
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
        }

    @gl.public.view
    def get_gate(self) -> str:
        return self.gate_address

    @gl.public.view
    def get_settled_count(self) -> u256:
        return self.settled_count
