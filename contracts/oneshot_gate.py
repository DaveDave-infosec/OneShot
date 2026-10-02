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

    # ---- V2: metered agreements (entitlement schedule + reservation) ----
    ag_metered: TreeMap[str, bool]
    ag_ent_ids: TreeMap[str, str]
    ag_schedule_reasoning: TreeMap[str, str]
    ent_label: TreeMap[str, str]
    ent_cap: TreeMap[str, u256]
    ent_committed: TreeMap[str, u256]
    ent_recipient: TreeMap[str, str]
    ent_first_op: TreeMap[str, str]
    op_ent: TreeMap[str, str]
    op_mode: TreeMap[str, str]
    op_requested: TreeMap[str, str]
    op_payable: TreeMap[str, str]
    op_residual: TreeMap[str, str]
    op_committed_before: TreeMap[str, str]

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

        # V2: a METERED agreement routes to the amount-aware path. Non-metered
        # agreements continue on the unchanged V1 pairing path below.
        if self.ag_metered.get(aid, False):
            return self._submit_metered(oid, aid)

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

        # V2: a held op on a METERED agreement escalates through the
        # amount-aware forcing pass. Non-metered ops continue on the
        # unchanged V1 forcing path below.
        if self.ag_metered.get(self.op_agreement[oid], False):
            return self._escalate_metered(oid)

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

    # -----------------------------------------------------------------
    # V2 helper: robust JSON extraction from consensus output. Takes the
    # text from the first { to the last }, so ```json fences or stray
    # prose around the object cannot break parsing.
    # -----------------------------------------------------------------
    def _parse_json(self, raw: str) -> dict:
        text = str(raw)
        start = text.find("{")
        end = text.rfind("}")
        assert start != -1 and end != -1 and end > start, "consensus output did not contain a JSON object"
        return json.loads(text[start:end + 1])

    # -----------------------------------------------------------------
    # V2: register a METERED agreement. The registrant supplies an
    # entitlement schedule (id, label, cap). Code validates its shape.
    # Consensus then VERIFIES the schedule against the locked agreement
    # text: every entitlement must be granted by the text and every cap
    # must equal an amount written explicitly in the text. Nobody can
    # meter a cap the agreement does not grant. Nothing is stored unless
    # consensus finds the schedule faithful.
    # -----------------------------------------------------------------
    @gl.public.write
    def register_metered_agreement(
        self,
        title: str,
        agreement_text: str,
        authorized_sources: str,
        party_a: str,
        party_b: str,
        schedule_json: str,
    ) -> str:
        entries = json.loads(schedule_json)
        assert isinstance(entries, list), "schedule must be a JSON list"
        assert len(entries) >= 1, "schedule must have at least one entitlement"
        assert len(entries) <= 12, "schedule may have at most 12 entitlements"

        ids = []
        labels = []
        caps = []
        for e in entries:
            assert isinstance(e, dict), "each schedule entry must be an object"
            eid = str(e.get("id", "")).strip().upper()
            label = str(e.get("label", "")).strip()
            cap_raw = str(e.get("cap", "")).strip()
            assert eid != "", "entitlement id must not be blank"
            assert "," not in eid and "|" not in eid, "entitlement id must not contain a comma or a pipe"
            assert eid != "NONE", "entitlement id NONE is reserved"
            assert eid not in ids, "duplicate entitlement id in schedule"
            assert label != "", "entitlement label must not be blank"
            assert cap_raw.isdigit(), "entitlement cap must be a whole number"
            cap = int(cap_raw)
            assert cap > 0, "entitlement cap must be greater than zero"
            ids.append(eid)
            labels.append(label)
            caps.append(cap)

        schedule_lines = ""
        for i in range(len(ids)):
            schedule_lines += "- " + ids[i] + ": " + labels[i] + " | cap " + str(caps[i]) + "\n"
        ag_text = agreement_text

        def build_verify_prompt() -> str:
            return f"""You are an independent auditor. A registrant has proposed an ENTITLEMENT SCHEDULE for a human-language agreement. Each entry names one entitlement the agreement grants and a cap: the maximum total amount that entitlement can ever pay. Payouts will be metered against these caps, so an inflated, invented, or double-counted entry would let money be paid that the agreement does not owe. Your ONLY job is to decide whether the schedule is FAITHFUL to the governing agreement text.

GOVERNING AGREEMENT (locked, authoritative):
{ag_text}

PROPOSED SCHEDULE (id: label | cap):
{schedule_lines}
The schedule is FAITHFUL only if ALL of these hold:
1. Every entry names an entitlement the agreement text explicitly grants.
2. Every cap equals an amount written explicitly in the agreement text for that entitlement. A cap derived by arithmetic (a percentage, a sum, or a split) is NOT faithful. A cap larger than the written amount is NOT faithful.
3. No two entries describe the same entitlement (no double-counting).
An entitlement the agreement grants but the schedule omits does NOT make the schedule unfaithful. Omitted entitlements are simply not metered.

Return ONLY one JSON object with these keys:
- faithful: "yes" or "no"
- problems: one sentence naming each failing entry id and why, or an empty string if faithful is "yes"
- reasoning: 1 to 2 sentences grounded in the specific agreement wording"""

        task_v = (
            "Decide whether the proposed entitlement schedule is faithful to "
            "the governing agreement text, and output the verdict as one JSON "
            "object."
        )
        criteria_v = (
            "The response is exactly one valid JSON object with keys faithful, "
            "problems, reasoning. faithful is yes or no. faithful is yes only if "
            "every schedule entry is explicitly granted by the agreement text "
            "with exactly that written amount and no two entries double-count "
            "one entitlement; otherwise faithful is no and problems names the "
            "failing entry. reasoning is a non-empty string that refers to the "
            "agreement wording."
        )

        raw = gl.eq_principle.prompt_non_comparative(
            build_verify_prompt,
            task=task_v,
            criteria=criteria_v,
        )
        parsed = self._parse_json(raw)
        faithful = str(parsed.get("faithful", "")).strip().lower()
        assert faithful == "yes", "schedule rejected by consensus: " + str(parsed.get("problems", ""))

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

        self.ag_metered[aid] = True
        self.ag_ent_ids[aid] = ",".join(ids)
        self.ag_schedule_reasoning[aid] = str(parsed.get("reasoning", ""))
        for i in range(len(ids)):
            k = aid + "|" + ids[i]
            self.ent_label[k] = labels[i]
            self.ent_cap[k] = u256(caps[i])
            self.ent_committed[k] = u256(0)
            self.ent_recipient[k] = ""
        return aid

    # -----------------------------------------------------------------
    # V2: metered submit. Consensus decides MEANING: which scheduled
    # entitlement this op discharges, and whether its amount is stated as
    # an increment or as a running total. Deterministic code decides
    # MONEY: requested, remaining, payable, residual, on whole numbers.
    # The payable part is RESERVED (committed) at verdict time, so a second
    # op verdicted before the first settles already sees the first op's
    # claim. The sum of payable on one entitlement can never exceed its cap.
    # -----------------------------------------------------------------
    def _submit_metered(self, oid: str, aid: str) -> str:
        amount_raw = str(self.op_amount[oid]).strip()
        assert amount_raw.isdigit(), "metered operation amount must be a whole number"
        amt = int(amount_raw)
        assert amt > 0, "metered operation amount must be greater than zero"

        rcpt = self.op_recipient[oid]
        ids = []
        for e in self.ag_ent_ids.get(aid, "").split(","):
            if e != "":
                ids.append(e)

        schedule_lines = ""
        for e in ids:
            ke = aid + "|" + e
            cap_i = int(self.ent_cap[ke])
            com_i = int(self.ent_committed[ke]) if ke in self.ent_committed else 0
            locked_i = self.ent_recipient.get(ke, "")
            if locked_i == "":
                locked_i = "not yet set"
            schedule_lines += (
                "- " + e + ": " + self.ent_label.get(ke, "")
                + " | cap " + str(cap_i)
                + " | already committed " + str(com_i)
                + " | remaining " + str(cap_i - com_i)
                + " | recipient " + locked_i + "\n"
            )

        ag_text = self.ag_text[aid]
        op_family = self.op_action_family[oid]
        op_purpose = self.op_economic_purpose[oid]
        op_hint = self.op_entitlement_hint[oid]
        op_ref = self.op_collision_key[oid]
        valid_list = ", ".join(ids) + ", NONE"

        def build_map_prompt() -> str:
            return f"""You are an independent settlement auditor for a METERED agreement. Every entitlement the agreement grants is listed in a locked schedule with a cap: the maximum total that entitlement can ever pay. Deterministic code tracks how much of each cap is already committed. Your ONLY job is to read ONE new payout operation and decide two things: (1) which single schedule entitlement it discharges, and (2) how its stated amount is meant. You do NOT compute what gets paid. Code computes that from your answer.

GOVERNING AGREEMENT (locked, authoritative):
{ag_text}

ENTITLEMENT SCHEDULE (locked; the committed and remaining figures are facts computed by code):
{schedule_lines}
NEW OPERATION:
- action family: {op_family}
- amount: {amount_raw}
- stated economic purpose: {op_purpose}
- entitlement hint: {op_hint}
- obligation or incident reference: {op_ref}
- recipient: {rcpt}

Decide:
- entitlement_id: the id of the ONE schedule entitlement this operation discharges, judged by the AGREEMENT WORDING and the operation's economic purpose, not by its own labels. Differently worded operations can discharge the same entitlement. Use "NONE" if it discharges no listed entitlement, or if it could discharge more than one and the agreement wording does not settle which.
- amount_mode:
  "incremental" means the amount is a NEW payment on top of whatever was already paid on that entitlement (for example "pay 5 toward M2" or "progress payment of 5").
  "cumulative" means the amount states the TOTAL that should have been paid on that entitlement to date, including earlier payments (for example "M2 paid to date should total 8" or "bring M2 up to 8 in total").
  A plain payment instruction with no running-total wording is incremental.
- confidence: "high" or "low". Use "low" if the mapping or the amount mode could genuinely be read more than one way. Do not guess.

Return ONLY one JSON object with these keys:
- entitlement_id: exactly one of {valid_list}
- amount_mode: "incremental" or "cumulative"
- confidence: "high" or "low"
- reasoning: 1 to 2 sentences grounded in the specific agreement wording and the operation's wording
- minority_note: one sentence giving the strongest argument for a different entitlement or a different amount mode, or an empty string if none"""

        task_m = (
            "Map the new payout operation to the one scheduled entitlement it "
            "discharges under the governing agreement, decide whether its amount "
            "is incremental or cumulative, and output the verdict as one JSON object."
        )
        criteria_m = (
            "The response is exactly one valid JSON object with keys "
            "entitlement_id, amount_mode, confidence, reasoning, minority_note. "
            "entitlement_id is exactly one of: " + valid_list + ". amount_mode is "
            "incremental or cumulative. confidence is high or low. entitlement_id "
            "is the entitlement the agreement wording ties the operation to, and "
            "amount_mode matches the operation's own wording. reasoning is a "
            "non-empty string that refers to the agreement wording."
        )

        raw = gl.eq_principle.prompt_non_comparative(
            build_map_prompt,
            task=task_m,
            criteria=criteria_m,
        )
        parsed = self._parse_json(raw)
        eid = str(parsed.get("entitlement_id", "")).strip().upper()
        mode = str(parsed.get("amount_mode", "")).strip().lower()
        confidence = str(parsed.get("confidence", "")).strip().lower()
        reasoning = str(parsed.get("reasoning", ""))
        minority = str(parsed.get("minority_note", ""))

        self.op_mode[oid] = mode
        self.op_relationship[oid] = mode
        self.op_confidence[oid] = confidence
        self.op_minority[oid] = minority
        self.op_prior_entitlement[oid] = ""

        hold_reason = ""
        if eid not in ids:
            hold_reason = "Consensus could not map this operation to exactly one scheduled entitlement."
        elif mode != "incremental" and mode != "cumulative":
            hold_reason = "Consensus did not commit to how the amount is stated."
        elif confidence != "high":
            hold_reason = "Consensus confidence was low on the entitlement mapping or the amount mode."
        else:
            locked = self.ent_recipient.get(aid + "|" + eid, "")
            if locked != "" and locked != rcpt:
                hold_reason = "Recipient differs from the recipient locked on entitlement " + eid + " by its first payout. A redirect is a question, not a payment."

        if hold_reason != "":
            mapped = eid in ids
            kh = aid + "|" + eid
            self.op_state[oid] = "AMBIGUOUS"
            self.op_ent[oid] = eid if mapped else ""
            self.op_entitlement[oid] = self.ent_label.get(kh, "") if mapped else ""
            self.op_linked_prior[oid] = self.ent_first_op.get(kh, "") if mapped else ""
            self.op_requested[oid] = ""
            self.op_payable[oid] = "0"
            self.op_residual[oid] = "0"
            self.op_committed_before[oid] = ""
            self.op_reasoning[oid] = reasoning + " HELD: " + hold_reason
            return "AMBIGUOUS"

        return self._apply_meter(oid, aid, eid, mode, amt, rcpt, reasoning)

    # -----------------------------------------------------------------
    # V2: the money logic, shared by metered submit and metered escalate.
    # Whole-number arithmetic only. Reads the entitlement's committed
    # figure AT CALL TIME, so an op resolved late by escalation is metered
    # against what is actually left, never against stale headroom.
    # -----------------------------------------------------------------
    def _apply_meter(self, oid: str, aid: str, eid: str, mode: str, amt: int, rcpt: str, reasoning: str) -> str:
        k = aid + "|" + eid
        cap = int(self.ent_cap[k])
        committed = int(self.ent_committed[k]) if k in self.ent_committed else 0
        remaining = cap - committed
        if mode == "cumulative":
            requested = amt - committed
        else:
            requested = amt

        if requested <= 0 or remaining <= 0:
            state = "CONFIRMED_DUPLICATE"
            payable = 0
            residual = 0
        elif requested <= remaining:
            state = "CONFIRMED_NEW"
            payable = requested
            residual = 0
        else:
            state = "PARTIAL"
            payable = remaining
            residual = requested - remaining

        first = self.ent_first_op.get(k, "")
        if payable > 0:
            self.ent_committed[k] = u256(committed + payable)
            if self.ent_recipient.get(k, "") == "":
                self.ent_recipient[k] = rcpt
            if first == "":
                self.ent_first_op[k] = oid

        requested_shown = requested if requested > 0 else 0
        self.op_state[oid] = state
        self.op_ent[oid] = eid
        self.op_entitlement[oid] = self.ent_label.get(k, "")
        self.op_linked_prior[oid] = first
        self.op_requested[oid] = str(requested_shown)
        self.op_payable[oid] = str(payable)
        self.op_residual[oid] = str(residual)
        self.op_committed_before[oid] = str(committed)
        self.op_reasoning[oid] = (
            reasoning
            + " METERING (code): cap " + str(cap)
            + ", committed before " + str(committed)
            + ", requested " + str(requested_shown)
            + ", payable " + str(payable)
            + ", residual " + str(residual) + "."
        )
        return state

    # -----------------------------------------------------------------
    # V2: metered forcing pass. Validators must COMMIT to one scheduled
    # entitlement and an amount mode, or declare UNRESOLVED as an honest
    # deadlock. A commit is metered by code at escalate time. UNRESOLVED,
    # or a commit whose recipient differs from the recipient locked on that
    # entitlement, goes to HELD_FINAL: resolvable only by joint release of
    # the two named agreement parties. There is no owner override.
    # -----------------------------------------------------------------
    def _escalate_metered(self, oid: str) -> str:
        aid = self.op_agreement[oid]
        amount_raw = str(self.op_amount[oid]).strip()
        amt = int(amount_raw)
        rcpt = self.op_recipient[oid]
        ids = []
        for e in self.ag_ent_ids.get(aid, "").split(","):
            if e != "":
                ids.append(e)

        schedule_lines = ""
        for e in ids:
            ke = aid + "|" + e
            cap_i = int(self.ent_cap[ke])
            com_i = int(self.ent_committed[ke]) if ke in self.ent_committed else 0
            locked_i = self.ent_recipient.get(ke, "")
            if locked_i == "":
                locked_i = "not yet set"
            schedule_lines += (
                "- " + e + ": " + self.ent_label.get(ke, "")
                + " | cap " + str(cap_i)
                + " | already committed " + str(com_i)
                + " | remaining " + str(cap_i - com_i)
                + " | recipient " + locked_i + "\n"
            )

        ag_text = self.ag_text[aid]
        op_family = self.op_action_family[oid]
        op_purpose = self.op_economic_purpose[oid]
        op_hint = self.op_entitlement_hint[oid]
        op_ref = self.op_collision_key[oid]
        first_note = self.op_reasoning.get(oid, "")
        valid_list = ", ".join(ids) + ", UNRESOLVED"

        def build_force_prompt() -> str:
            return f"""You are an independent settlement auditor making a FINAL, BINDING decision on one payout operation under a METERED agreement. A first review held this operation because it could not map it to exactly one scheduled entitlement with confidence. You must now commit to the most defensible answer the agreement supports. You do NOT compute what gets paid. Code computes that from your answer, against the caps and committed figures below.

GOVERNING AGREEMENT (locked, authoritative):
{ag_text}

ENTITLEMENT SCHEDULE (locked; the committed and remaining figures are facts computed by code):
{schedule_lines}
OPERATION:
- action family: {op_family}
- amount: {amount_raw}
- stated economic purpose: {op_purpose}
- entitlement hint: {op_hint}
- obligation or incident reference: {op_ref}
- recipient: {rcpt}

FIRST REVIEW NOTE (why it was held):
{first_note}

Decide and COMMIT:
- entitlement_id: the id of the ONE schedule entitlement the agreement wording most defensibly ties this operation to, judged by the agreement wording and the operation's economic purpose, not by its own labels. Use "UNRESOLVED" ONLY as a true last resort, when committing to any listed entitlement would require inventing terms the agreement does not contain. It is not the cautious default; it is the honest deadlock.
- amount_mode: "incremental" means a NEW payment on top of earlier payments on that entitlement. "cumulative" means the TOTAL that should have been paid on that entitlement to date. A plain payment instruction with no running-total wording is incremental.

Return ONLY one JSON object with these keys:
- entitlement_id: exactly one of {valid_list}
- amount_mode: "incremental" or "cumulative"
- reasoning: 1 to 2 sentences grounded in the specific agreement wording, explaining the final call
- minority_note: one sentence giving the strongest argument for a different answer, or an empty string if none"""

        task_f = (
            "Make the final binding call: map the held operation to the one "
            "scheduled entitlement the agreement most defensibly ties it to and "
            "state its amount mode, or declare UNRESOLVED only if the agreement "
            "genuinely cannot support any listed entitlement. Output one JSON object."
        )
        criteria_f = (
            "The response is exactly one valid JSON object with keys "
            "entitlement_id, amount_mode, reasoning, minority_note. "
            "entitlement_id is exactly one of: " + valid_list + ". amount_mode is "
            "incremental or cumulative. reasoning is a non-empty string that "
            "refers to the agreement wording."
        )

        raw = gl.eq_principle.prompt_non_comparative(
            build_force_prompt,
            task=task_f,
            criteria=criteria_f,
        )
        parsed = self._parse_json(raw)
        eid = str(parsed.get("entitlement_id", "")).strip().upper()
        mode = str(parsed.get("amount_mode", "")).strip().lower()
        reasoning = str(parsed.get("reasoning", ""))
        minority = str(parsed.get("minority_note", ""))

        self.op_escalated[oid] = True
        self.op_confidence[oid] = "forced"
        self.op_mode[oid] = mode
        self.op_relationship[oid] = mode
        self.op_minority[oid] = minority

        final_reason = ""
        if eid not in ids:
            final_reason = "Forced consensus could not tie this operation to any single scheduled entitlement."
        elif mode != "incremental" and mode != "cumulative":
            final_reason = "Forced consensus did not commit to how the amount is stated."
        else:
            locked = self.ent_recipient.get(aid + "|" + eid, "")
            if locked != "" and locked != rcpt:
                final_reason = "Forced consensus mapped this operation to entitlement " + eid + ", but its recipient differs from the recipient locked on that entitlement. A redirect is not a consensus question."

        if final_reason != "":
            mapped = eid in ids
            kf = aid + "|" + eid
            self.op_state[oid] = "HELD_FINAL"
            self.op_ent[oid] = eid if mapped else ""
            self.op_entitlement[oid] = self.ent_label.get(kf, "") if mapped else ""
            self.op_linked_prior[oid] = self.ent_first_op.get(kf, "") if mapped else ""
            self.op_requested[oid] = ""
            self.op_payable[oid] = "0"
            self.op_residual[oid] = "0"
            self.op_committed_before[oid] = ""
            self.op_reasoning[oid] = (
                reasoning + " FINAL HOLD: " + final_reason
                + " Resolvable only by joint release of the two named agreement parties."
            )
            return "HELD_FINAL"

        return self._apply_meter(oid, aid, eid, mode, amt, rcpt, reasoning)

    def _ent_dict(self, aid: str, eid: str) -> dict:
        k = aid + "|" + eid
        assert k in self.ent_cap, "entitlement does not exist"
        cap = int(self.ent_cap[k])
        committed = int(self.ent_committed[k]) if k in self.ent_committed else 0
        return {
            "agreement_id": aid,
            "id": eid,
            "label": self.ent_label.get(k, ""),
            "cap": str(cap),
            "committed": str(committed),
            "remaining": str(cap - committed),
            "recipient": self.ent_recipient.get(k, ""),
        }

    @gl.public.view
    def get_entitlement(self, agreement_id: str, entitlement_id: str) -> dict:
        return self._ent_dict(agreement_id, entitlement_id.strip().upper())

    @gl.public.view
    def get_schedule(self, agreement_id: str) -> dict:
        aid = agreement_id
        assert self.ag_exists.get(aid, False), "agreement does not exist"
        out = []
        metered = self.ag_metered.get(aid, False)
        if metered:
            for eid in self.ag_ent_ids.get(aid, "").split(","):
                if eid != "":
                    out.append(self._ent_dict(aid, eid))
        return {
            "agreement_id": aid,
            "metered": metered,
            "schedule_reasoning": self.ag_schedule_reasoning.get(aid, ""),
            "entitlements": out,
        }

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
            "metered": self.ag_metered.get(aid, False),
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
            "metered": self.ag_metered.get(self.op_agreement[oid], False),
            "entitlement_id": self.op_ent.get(oid, ""),
            "amount_mode": self.op_mode.get(oid, ""),
            "requested": self.op_requested.get(oid, ""),
            "payable": self.op_payable.get(oid, ""),
            "residual": self.op_residual.get(oid, ""),
            "committed_before": self.op_committed_before.get(oid, ""),
        }

    @gl.public.view
    def get_operation_count(self) -> u256:
        return self.op_count

    @gl.public.view
    def get_agreement_count(self) -> u256:
        return self.agreement_count
