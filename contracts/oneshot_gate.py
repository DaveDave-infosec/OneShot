# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json


class OneShotGate(gl.Contract):
    agreement_count: u256
    ag_exists: TreeMap[str, bool]
    ag_title: TreeMap[str, str]
    ag_text: TreeMap[str, str]
    ag_authorized_sources: TreeMap[str, str]
    ag_party_a: TreeMap[str, str]
    ag_party_b: TreeMap[str, str]

    op_count: u256
    op_exists: TreeMap[str, bool]
    op_agreement: TreeMap[str, str]
    op_source: TreeMap[str, str]
    op_recipient: TreeMap[str, str]
    op_asset: TreeMap[str, str]
    op_amount: TreeMap[str, str]
    op_action_family: TreeMap[str, str]
    op_obligation_ref: TreeMap[str, str]
    op_incident_id: TreeMap[str, str]
    op_economic_purpose: TreeMap[str, str]
    op_entitlement_hint: TreeMap[str, str]
    op_collision_key: TreeMap[str, str]

    op_state: TreeMap[str, str]
    op_entitlement: TreeMap[str, str]
    op_prior_entitlement: TreeMap[str, str]
    op_linked_prior: TreeMap[str, str]
    op_relationship: TreeMap[str, str]
    op_confidence: TreeMap[str, str]
    op_reasoning: TreeMap[str, str]
    op_minority: TreeMap[str, str]
    op_escalated: TreeMap[str, bool]

    bucket_ops: TreeMap[str, str]

    def __init__(self):
        self.agreement_count = u256(0)
        self.op_count = u256(0)

    @gl.public.write
    def register_agreement(
        self,
        title: str,
        agreement_text: str,
        authorized_sources: str,
        party_a: str,
        party_b: str,
    ) -> str:
        idx = u256(int(self.agreement_count) + 1)
        self.agreement_count = idx
        aid = str(idx)

        parts = authorized_sources.split(",")
        norm = []
        for p in parts:
            q = p.strip().lower()
            if q != "":
                norm.append(q)

        self.ag_title[aid] = title
        self.ag_text[aid] = agreement_text
        self.ag_authorized_sources[aid] = ",".join(norm)
        self.ag_party_a[aid] = party_a.strip().lower()
        self.ag_party_b[aid] = party_b.strip().lower()
        self.ag_exists[aid] = True
        return aid

    @gl.public.write
    def submit_operation(
        self,
        agreement_id: str,
        source: str,
        recipient: str,
        asset: str,
        amount: str,
        action_family: str,
        obligation_ref: str,
        incident_id: str,
        economic_purpose: str,
        entitlement_hint: str,
    ) -> str:
        aid = agreement_id
        assert self.ag_exists.get(aid, False), "agreement does not exist"

        # Ask 1 — bind the source to the ACTUAL transaction sender. A caller can
        # only ever submit as itself; the passed `source` arg is ignored for auth
        # so no one can spoof an authorized address they do not control.
        caller = gl.message.sender_address.as_hex.lower()
        src = caller
        allowed = self.ag_authorized_sources.get(aid, "")
        is_auth = False
        for a in allowed.split(","):
            if a == src and a != "":
                is_auth = True
        assert is_auth, "caller is not an authorized source on this agreement"

        idx = u256(int(self.op_count) + 1)
        self.op_count = idx
        oid = str(idx)

        rcpt = recipient.strip().lower()
        obl = obligation_ref.strip().lower()
        inc = incident_id.strip().lower()
        collision_key = obl if obl != "" else inc
        # Ask 2 — every payout MUST carry an obligation or incident reference to
        # pair on. A blank-and-blank reference would skip comparison entirely and
        # let a duplicate slip through as CLEAR_NEW, so it is rejected.
        assert collision_key != "", "operation must carry an obligation_ref or incident_id to be checked for collisions"

        self.op_exists[oid] = True
        self.op_agreement[oid] = aid
        self.op_source[oid] = src
        self.op_recipient[oid] = rcpt
        self.op_asset[oid] = asset
        self.op_amount[oid] = amount
        self.op_action_family[oid] = action_family
        self.op_obligation_ref[oid] = obl
        self.op_incident_id[oid] = inc
        self.op_economic_purpose[oid] = economic_purpose
        self.op_entitlement_hint[oid] = entitlement_hint
        self.op_collision_key[oid] = collision_key
        self.op_escalated[oid] = False

        prior_id = ""
        bkey = aid + "|" + collision_key + "|" + rcpt
        prior_ids_raw = self.bucket_ops.get(bkey, "")
        if prior_ids_raw != "":
            # pair against the FIRST prior in the bucket — the ORIGINAL operation
            # that opened this obligation+recipient. Every later op is a candidate
            # duplicate of that original, so a duplicate cannot be paired against a
            # weaker/older-but-not-original entry to dodge a clean finding.
            for p in prior_ids_raw.split(","):
                if p.strip() != "":
                    prior_id = p.strip()
                    break
        if prior_ids_raw == "":
            self.bucket_ops[bkey] = oid
        else:
            self.bucket_ops[bkey] = prior_ids_raw + "," + oid

        if prior_id == "":
            self.op_state[oid] = "CLEAR_NEW"
            self.op_entitlement[oid] = entitlement_hint
            self.op_prior_entitlement[oid] = ""
            self.op_linked_prior[oid] = ""
            self.op_relationship[oid] = "none"
            self.op_confidence[oid] = "high"
            self.op_reasoning[oid] = "No prior operation shares this obligation reference and recipient. No collision candidate. Cleared in code without consensus."
            self.op_minority[oid] = ""
            return "CLEAR_NEW"

        ag_text = self.ag_text[aid]
        new_family = action_family
        new_amount = amount
        new_purpose = economic_purpose
        new_hint = entitlement_hint
        prior_family = self.op_action_family[prior_id]
        prior_amount = self.op_amount[prior_id]
        prior_purpose = self.op_economic_purpose[prior_id]
        prior_hint = self.op_entitlement_hint[prior_id]

        def build_prompt() -> str:
            return f"""You are an independent settlement auditor for payouts generated from a human-language agreement. Your ONLY job is to decide whether TWO proposed payout operations discharge the SAME economic entitlement (a genuine duplicate) or TWO DISTINCT entitlements (both genuinely owed), based strictly on the governing agreement text. Do not trust either operation's own label over the agreement.

GOVERNING AGREEMENT (locked, authoritative):
{ag_text}

OPERATION A (the earlier, already-recorded operation):
- action family: {prior_family}
- amount: {prior_amount}
- stated economic purpose: {prior_purpose}
- entitlement hint: {prior_hint}

OPERATION B (the new operation being checked):
- action family: {new_family}
- amount: {new_amount}
- stated economic purpose: {new_purpose}
- entitlement hint: {new_hint}

Both operations pay the SAME recipient and reference the SAME obligation or incident. The structured fields alone cannot separate them. The ONLY question is semantic: under the governing agreement, do A and B discharge the same entitlement, or two separate ones?

Decide the relationship:
- "duplicate" means A and B discharge the SAME entitlement. Paying both would pay one economic obligation twice.
- "distinct" means A and B discharge DIFFERENT entitlements the agreement genuinely owes separately. Both should be paid.
- "replacement" means B explicitly corrects or supersedes A (same entitlement, B is meant to replace A, for example a corrected amount), so only B should be paid.
- "ambiguous" means the agreement wording does NOT clearly resolve whether these are the same entitlement or two. Do NOT guess; mark ambiguous.

Rules:
- Base the decision on the AGREEMENT WORDING, not on the operations' own labels.
- Wording like "and" or "in addition to" between two remedies points to distinct. Wording like "or", "in lieu of", or "sole remedy" points to a single entitlement.
- If the agreement does not define a separate entitlement for B, treat B as the SAME entitlement as A, not distinct.
- If you cannot tell with confidence, use "ambiguous". Never force distinct or duplicate.

Return ONLY one JSON object with these keys:
- relationship: one of "duplicate", "distinct", "replacement", "ambiguous"
- new_entitlement: a short label of at most 8 words naming the entitlement operation B discharges
- prior_entitlement: a short label of at most 8 words naming the entitlement operation A discharges
- confidence: "high" or "low"
- reasoning: 1 to 2 sentences grounded in the specific agreement wording
- minority_note: one sentence giving the strongest argument for the OPPOSITE conclusion, or an empty string if none"""

        task = (
            "Decide whether the two operations discharge the same economic "
            "entitlement or two distinct entitlements, based only on the "
            "governing agreement, and output the verdict as one JSON object."
        )
        criteria = (
            "The response is exactly one valid JSON object with keys "
            "relationship, new_entitlement, prior_entitlement, confidence, "
            "reasoning, minority_note. relationship is one of duplicate, "
            "distinct, replacement, ambiguous. confidence is high or low. "
            "reasoning is a non-empty string that refers to the agreement wording."
        )

        raw = gl.eq_principle.prompt_non_comparative(
            build_prompt,
            task=task,
            criteria=criteria,
        )

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            newline_pos = cleaned.find("\n")
            if newline_pos != -1:
                cleaned = cleaned[newline_pos + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        parsed = json.loads(cleaned)

        relationship = str(parsed["relationship"]).lower()
        new_entitlement = str(parsed["new_entitlement"])
        prior_entitlement = str(parsed["prior_entitlement"])
        confidence = str(parsed["confidence"]).lower()
        reasoning = str(parsed["reasoning"])
        minority = str(parsed["minority_note"])

        prior_state = self.op_state.get(prior_id, "").strip()
        if relationship == "distinct":
            state = "CONFIRMED_NEW"
        elif relationship == "replacement":
            state = "REPLACEMENT"
        elif relationship == "ambiguous" or confidence == "low":
            state = "AMBIGUOUS"
        elif relationship == "duplicate":
            if prior_state == "CLEAR_NEW" or prior_state == "CONFIRMED_NEW":
                state = "CONFIRMED_DUPLICATE"
            else:
                state = "POSSIBLE_DUPLICATE"
        else:
            state = "AMBIGUOUS"

        self.op_state[oid] = state
        self.op_entitlement[oid] = new_entitlement
        self.op_prior_entitlement[oid] = prior_entitlement
        self.op_linked_prior[oid] = prior_id
        self.op_relationship[oid] = relationship
        self.op_confidence[oid] = confidence
        self.op_reasoning[oid] = reasoning
        self.op_minority[oid] = minority

        return state

    # -----------------------------------------------------------------
    # Forcing second-consensus pass. Only valid for a held op
    # (POSSIBLE_DUPLICATE or AMBIGUOUS). Validators must COMMIT to
    # duplicate or distinct; ambiguous is not allowed. If consensus
    # cannot converge on the forced binary, the op goes to HELD_FINAL,
    # which unlocks the two-party joint release on the ledger.
    # PERMISSIONLESS: anyone may trigger it.
    # -----------------------------------------------------------------
    @gl.public.write
    def escalate(self, op_id: str) -> str:
        oid = op_id.strip()
        assert self.op_exists.get(oid, False), "operation does not exist"
        cur = self.op_state.get(oid, "")
        assert cur == "POSSIBLE_DUPLICATE" or cur == "AMBIGUOUS", "operation is not in a held state that can be escalated"
        assert not self.op_escalated.get(oid, False), "operation already escalated"

        prior_id = self.op_linked_prior.get(oid, "")
        assert prior_id != "", "no linked prior operation to compare against"

        aid = self.op_agreement[oid]
        ag_text = self.ag_text[aid]
        new_family = self.op_action_family[oid]
        new_amount = self.op_amount[oid]
        new_purpose = self.op_economic_purpose[oid]
        new_hint = self.op_entitlement_hint[oid]
        prior_family = self.op_action_family[prior_id]
        prior_amount = self.op_amount[prior_id]
        prior_purpose = self.op_economic_purpose[prior_id]
        prior_hint = self.op_entitlement_hint[prior_id]

        def build_prompt2() -> str:
            return f"""You are an independent settlement auditor making a FINAL, BINDING decision on two payout operations generated from a human-language agreement. A first careful review already found this pair hard to separate and held it. You must now commit to the most defensible answer the agreement supports. Prefer to resolve it; declare a genuine deadlock only if the agreement truly cannot support either resolution, based strictly on the governing agreement text.

GOVERNING AGREEMENT (locked, authoritative):
{ag_text}

OPERATION A (the earlier, already-recorded operation):
- action family: {prior_family}
- amount: {prior_amount}
- stated economic purpose: {prior_purpose}
- entitlement hint: {prior_hint}

OPERATION B (the new operation being checked):
- action family: {new_family}
- amount: {new_amount}
- stated economic purpose: {new_purpose}
- entitlement hint: {new_hint}

Both pay the SAME recipient and reference the SAME obligation or incident. Decide, and COMMIT to the most defensible answer:
- "duplicate" means A and B discharge the SAME entitlement; paying both double-pays one obligation, so B must NOT be paid.
- "distinct" means A and B discharge DIFFERENT entitlements the agreement genuinely owes separately, so B should be paid.
- "unresolved" means the governing agreement text genuinely does NOT provide enough basis to defend EITHER answer even after this forced review. Use it ONLY as a true last resort when committing to duplicate or distinct would require inventing terms the agreement does not contain. It is not the cautious default; it is the honest deadlock.

Rules:
- Base the decision on the AGREEMENT WORDING, not the operations' own labels.
- Wording like "and" or "in addition to" between remedies favors distinct. Wording like "or", "in lieu of", or "sole remedy" favors duplicate.
- If the agreement does not clearly define a SEPARATE entitlement that B discharges, the more defensible answer is duplicate (do not invent an entitlement the text does not grant).
- Strongly prefer duplicate or distinct. Choose "unresolved" ONLY when the agreement text truly cannot support either.

Return ONLY one JSON object with these keys:
- relationship: exactly "duplicate", "distinct", or "unresolved"
- new_entitlement: a short label of at most 8 words naming the entitlement operation B discharges
- prior_entitlement: a short label of at most 8 words naming the entitlement operation A discharges
- reasoning: 1 to 2 sentences grounded in the specific agreement wording, explaining the final call
- minority_note: one sentence giving the strongest argument for the OPPOSITE conclusion, or an empty string if none"""

        task2 = (
            "Make the final binding call: do the two operations discharge the "
            "same entitlement (duplicate), two distinct entitlements (distinct), "
            "or does the agreement genuinely fail to support either even under "
            "this forced review (unresolved). Strongly prefer duplicate or "
            "distinct. Output one JSON object."
        )
        criteria2 = (
            "The response is exactly one valid JSON object with keys "
            "relationship, new_entitlement, prior_entitlement, reasoning, "
            "minority_note. relationship is exactly duplicate, distinct, or "
            "unresolved and nothing else. reasoning is a non-empty string that "
            "refers to the agreement wording."
        )

        raw = gl.eq_principle.prompt_non_comparative(
            build_prompt2,
            task=task2,
            criteria=criteria2,
        )

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            newline_pos = cleaned.find("\n")
            if newline_pos != -1:
                cleaned = cleaned[newline_pos + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        relationship = str(parsed["relationship"]).lower()
        new_entitlement = str(parsed["new_entitlement"])
        prior_entitlement = str(parsed["prior_entitlement"])
        reasoning = str(parsed["reasoning"])
        minority = str(parsed["minority_note"])

        self.op_escalated[oid] = True

        if relationship == "distinct":
            state = "CONFIRMED_NEW"
        elif relationship == "duplicate":
            # The forcing pass has made a final, binding commit. A duplicate
            # discharges the same entitlement as its prior, so it must not be
            # paid — regardless of whether that prior was an original payment
            # or itself a duplicate. Holding again here would defeat the whole
            # purpose of escalation, which is to RESOLVE a held operation.
            state = "CONFIRMED_DUPLICATE"
        else:
            # relationship == "unresolved" (or any non-committal answer): the
            # agreement genuinely cannot settle this even under forcing. This is
            # the REACHABLE deadlock — the operation moves to HELD_FINAL, which
            # is resolvable only by the two named agreement parties acting
            # jointly. There is no owner or operator override.
            state = "HELD_FINAL"
            if reasoning == "":
                reasoning = "Forced consensus could not defend either duplicate or distinct on the agreement text. Moved to final hold; resolvable only by joint release of the two named agreement parties."

        self.op_state[oid] = state
        self.op_entitlement[oid] = new_entitlement
        self.op_prior_entitlement[oid] = prior_entitlement
        self.op_relationship[oid] = relationship
        self.op_confidence[oid] = "forced"
        self.op_reasoning[oid] = reasoning
        self.op_minority[oid] = minority

        return state

    @gl.public.view
    def get_agreement(self, agreement_id: str) -> dict:
        aid = agreement_id
        assert self.ag_exists.get(aid, False), "agreement does not exist"
        return {
            "id": aid,
            "title": self.ag_title[aid],
            "agreement_text": self.ag_text[aid],
            "authorized_sources": self.ag_authorized_sources[aid],
            "party_a": self.ag_party_a.get(aid, ""),
            "party_b": self.ag_party_b.get(aid, ""),
        }

    @gl.public.view
    def get_operation(self, op_id: str) -> dict:
        oid = op_id
        assert self.op_exists.get(oid, False), "operation does not exist"
        return {
            "id": oid,
            "agreement_id": self.op_agreement[oid],
            "source": self.op_source[oid],
            "recipient": self.op_recipient[oid],
            "asset": self.op_asset[oid],
            "amount": self.op_amount[oid],
            "action_family": self.op_action_family[oid],
            "obligation_ref": self.op_obligation_ref[oid],
            "incident_id": self.op_incident_id[oid],
            "economic_purpose": self.op_economic_purpose[oid],
            "entitlement_hint": self.op_entitlement_hint[oid],
            "collision_key": self.op_collision_key[oid],
            "state": self.op_state.get(oid, ""),
            "entitlement": self.op_entitlement.get(oid, ""),
            "prior_entitlement": self.op_prior_entitlement.get(oid, ""),
            "linked_prior": self.op_linked_prior.get(oid, ""),
            "relationship": self.op_relationship.get(oid, ""),
            "confidence": self.op_confidence.get(oid, ""),
            "reasoning": self.op_reasoning.get(oid, ""),
            "minority_note": self.op_minority.get(oid, ""),
            "escalated": self.op_escalated.get(oid, False),
        }

    @gl.public.view
    def get_operation_count(self) -> u256:
        return self.op_count

    @gl.public.view
    def get_agreement_count(self) -> u256:
        return self.agreement_count
