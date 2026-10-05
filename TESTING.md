# OneShot: Test Suite

Real-contract tests that drive the actual `OneShotGate` and `OneShotLedger`
code paths on the GenLayer `gltest` direct in-process runner. Every state
decision, every metering computation, every settlement, and the cross-contract
reads are the contracts' own code. Only two things are stubbed: the *other*
contract's return value on a cross-contract call, and the LLM consensus verdict.
The surrounding guards, pairing, state determination, arithmetic, reservation
and value movement are real, so each test exercises the true code path, not a
reimplementation.

**83 tests, no skips.** 17 V1 tests (the regression proof), 45 V2 tests, and 21
steward-round tests.

## Run

```
pip install "genlayer-test[sim]" pytest
python -m pytest tests/
```

The first run downloads and caches the pinned SDK (`v0.2.16`); later runs are
offline.

## V1: what each test proves

### tests/test_gate.py: pairing, mapping, escalation, access (8)

- **novel_op_clears_in_code_without_consensus**: a first operation on a fresh
  obligation has no colliding prior, so it resolves `CLEAR_NEW` purely in code.
  No consensus hook is set; if the gate reached for the LLM here the test would
  fail. Proves the deterministic filter that keeps the easy case off the
  validators.
- **first_pass_duplicate_against_clean_prior**: a differently worded operation
  that collides with a clean prior, with the mapping consensus returning
  `duplicate`, resolves `CONFIRMED_DUPLICATE` and links to its prior.
- **first_pass_distinct_is_confirmed_new**: the same collision shape with the
  consensus returning `distinct` resolves `CONFIRMED_NEW`. Proves the engine
  discriminates rather than always quarantining.
- **escalate_resolves_ambiguous_to_duplicate**: an operation held after an
  ambiguous first pass is escalated; the forcing pass commits to `duplicate`
  and resolves it. Proves escalation resolves a hold instead of holding again.
- **unauthorized_caller_rejected**: an operation whose actual transaction
  sender is not an authorized source reverts, even when the caller passes an
  authorized address as the `source` argument.
- **blank_reference_rejected**: an operation with both `obligation_ref` and
  `incident_id` blank reverts. A duplicate cannot dodge comparison by omitting
  its reference.
- **pairs_against_first_prior_not_last**: every later operation in a bucket is
  paired against the first (original) operation, not a later entry.
- **escalate_unresolved_reaches_held_final**: when the forcing pass genuinely
  cannot commit, it returns `unresolved` and the operation moves to
  `HELD_FINAL`, the reachable deadlock that unlocks the two-party release.

### tests/test_ledger.py: settlement, replay, conservation, joint release (9)

- **confirmed_duplicate_pays_nothing_no_double_execution**: an operation that
  discharges an already-satisfied entitlement settles to `satisfied_by_prior`;
  the vault is unchanged and the recipient receives nothing.
- **clear_new_executes_with_exact_conservation**: the vault decreases and the
  recipient increases by exactly the amount.
- **confirmed_new_executes**: a genuinely distinct operation pays the recipient.
- **permissionless_bystander_settle**: a wallet that is neither the owner nor a
  party settles an operation, and the value math is exact.
- **double_settle_reverts**: settling the same operation twice reverts.
- **possible_duplicate_holds_funds_untouched**: a held operation settles to
  `held`, and the vault is untouched.
- **two_party_both_execute_pays_once**: a final hold releases only when both
  named parties approve `execute`, then pays exactly once.
- **two_party_disagree_stays_frozen**: differing votes move nothing.
- **two_party_nonparty_rejected**: a non-party cannot resolve a final hold.

## V2: what each test proves

### tests/test_metered.py: schedule registration and verification (10)

- **metered_faithful_schedule_registers_and_is_stored**: a schedule the
  consensus finds faithful is stored, ids are normalized to upper case, every
  entitlement starts at committed 0 with no locked recipient, and the
  validators' schedule reasoning is kept on-chain.
- **metered_inflated_cap_rejected_by_consensus_and_nothing_stored**: when
  consensus finds a cap unfaithful to the text (15 against a written 10), the
  registration reverts and no agreement is created.
- **metered_schedule_shape_guards_reject_in_code** (6 cases): an empty
  schedule, a non-whole cap, a zero cap, a blank label, the reserved id `NONE`,
  and a duplicate id differing only in case all revert in code, before
  consensus runs, and nothing is stored.
- **metered_fenced_consensus_output_still_parses**: a verdict wrapped in prose
  and a fenced code block still parses, proving the robust first-brace to
  last-brace extraction.
- **v1_agreement_reports_unmetered_with_empty_schedule**: a V1 agreement
  reports `metered: false` and an empty schedule.

### tests/test_metered_submit.py: the metered verdict and the reservation (15)

- **incremental_within_cap_is_confirmed_new_and_reserves**: 7 against a cap of
  10 resolves `CONFIRMED_NEW`, payable 7, and the entitlement reserves 7 and
  locks its recipient.
- **partial_pays_remaining_and_holds_excess**: the headline V2 case. After 7,
  a differently worded 5 resolves `PARTIAL`: requested 5, payable 3, residual 2,
  linked to the first op, with the code's metering line in the reasoning.
- **exhausted_entitlement_is_confirmed_duplicate**: once the cap is fully
  committed, a further op resolves `CONFIRMED_DUPLICATE` with payable 0.
- **cumulative_mode_pays_only_the_difference**: after 5, a cumulative "total 8"
  pays only 3, and a cumulative "total 4" pays nothing.
- **cumulative_over_cap_is_partial**: after 5, a cumulative "total 12" requests
  7, pays the 5 left, and holds 2.
- **reservation_race_sum_of_payable_never_exceeds_cap**: three ops of 7,
  verdicted back to back before any settlement, resolve NEW, PARTIAL and
  DUPLICATE, and their payables sum to exactly the cap of 10.
- **entitlements_meter_independently**: exhausting M2 does not touch DOC.
- **recipient_redirect_is_held**: a later op on a locked entitlement that pays
  a different recipient is held `AMBIGUOUS` and reserves nothing.
- **none_mapping_is_held**: a `NONE` mapping is held and reserves nothing on
  any entitlement.
- **low_confidence_is_held**: a low-confidence mapping is held and reserves
  nothing.
- **invented_entitlement_id_is_held**: an id outside the schedule is held.
- **bad_metered_amount_reverts** (3 cases): amounts of 0, 2.5 and -3 revert in
  code.
- **fenced_mapping_output_parses**: a fenced mapping verdict still parses.

### tests/test_metered_escalate.py: the metered forcing pass (9)

- **escalate_commits_held_op_to_confirmed_new**: a low-confidence hold
  reserves nothing until escalation commits it, and only then reserves.
- **late_escalate_meters_against_current_remaining**: an op held at submit,
  resolved after another op took 7 of the 10, is metered against the 3 that are
  actually left: `PARTIAL`, payable 3. Late resolution cannot claim stale
  headroom.
- **escalate_after_exhaustion_is_confirmed_duplicate**: a held op resolved after
  the cap is exhausted pays nothing.
- **escalate_unresolved_reaches_held_final**: `UNRESOLVED` is the honest
  deadlock and moves the op to `HELD_FINAL`, reserving nothing.
- **forced_mapping_cannot_redirect_locked_recipient**: even a forced mapping
  cannot pay a recipient other than the one locked on the entitlement; the op
  moves to `HELD_FINAL`.
- **forced_invented_id_reaches_held_final**: a forced id outside the schedule
  moves the op to `HELD_FINAL`.
- **forced_cumulative_pays_only_the_difference**: a forced cumulative reading
  pays only the difference.
- **metered_op_cannot_be_escalated_twice**: a second escalation reverts.
- **unheld_metered_op_cannot_be_escalated**: an op that was never held cannot
  be escalated.

### tests/test_metered_ledger.py: metered settlement and the cap guard (11)

- **metered_settles_on_payable_not_raw_amount**: a cumulative "total 8" with
  payable 3 moves exactly 3, never 8.
- **partial_pays_payable_and_holds_residual**: a PARTIAL moves exactly the
  payable part, holds the residual, and conserves value to the unit.
- **cap_guard_refuses_payout_beyond_cap**: with 7 of 10 already paid, a
  deliberately wrong gate verdict asking to pay 5 more is refused by the ledger,
  and not one unit moves.
- **metered_duplicate_pays_nothing**: a metered duplicate moves nothing.
- **metered_ambiguous_holds_funds_untouched**: a metered hold moves nothing.
- **sync_after_escalate_settles_partial**: after an escalation resolves a held
  op to PARTIAL, `sync_from_gate` settles it exactly.
- **residual_both_execute_pays_once**: both parties releasing the residual pays
  it exactly once; a further vote reverts.
- **residual_both_reject_is_permanent**: both parties refusing the residual
  refuses it permanently.
- **residual_disagree_stays_held**: differing votes leave the residual held.
- **nonparty_cannot_vote_on_residual**: a non-party vote reverts.
- **bystander_settles_partial_exactly**: settlement of a PARTIAL stays
  permissionless and exact.

## Steward round: what each test proves

### tests/test_acceptance.py: two-party acceptance of the locked text (10)

- **new_agreement_starts_pending_with_text_hash**: a new agreement is pending,
  with neither party accepted, and stores the SHA-256 hash of its exact text.
- **submit_on_pending_agreement_reverts**: a pending agreement cannot govern a
  payout, and no operation is recorded.
- **one_party_alone_cannot_activate**: unilateral activation fails. Party A
  accepting alone leaves the agreement pending, and a submit still reverts.
- **both_parties_activate_and_submit_works**: once both parties accept, the
  agreement is active and governs payouts.
- **party_b_first_then_a_activates**: acceptance order does not matter.
- **non_party_cannot_accept**: a non-party acceptance reverts.
- **wrong_text_hash_reverts**: accepting with any hash other than that of the
  locked text reverts. A party must accept the exact text.
- **double_acceptance_reverts**: a party cannot accept twice.
- **same_address_as_both_parties_rejected**: one wallet cannot be named as both
  parties, so activation can never be unilateral. Registration reverts before
  anything is written.
- **metered_agreement_pending_until_both_accept**: metered agreements follow the
  same rule.

### tests/test_asset_model.py: scarce issuance and escrow backing (11)

- **issuer_mints_into_own_treasury**: the issuer mints within the cap, into its
  own balance only.
- **bystander_cannot_mint**: unauthorized minting fails. A bystander mint
  reverts and nothing is issued.
- **party_cannot_mint_itself_a_balance**: unauthorized minting fails. A named
  party or recipient cannot mint itself a balance.
- **issuer_cannot_exceed_max_supply**: issuance past `max_supply` reverts.
- **mint_has_no_recipient_path**: there is no way to mint into a vault, an
  escrow, or a recipient.
- **transfer_moves_only_own_balance**: transfer is caller-bound; an
  insufficient balance reverts.
- **fund_escrow_on_pending_agreement_reverts**: a pending agreement cannot be
  funded.
- **fund_escrow_moves_caller_balance**: funding moves the caller's own balance
  into the agreement's escrow.
- **escrow_isolation_between_agreements**: agreement 1 cannot be paid from
  agreement 2's escrow.
- **underfunded_escrow_refuses_payout**: an escrow below the payout refuses it,
  and nothing moves.
- **supply_invariant_across_full_flow**: across mint, transfer, funding and
  settlement, every unit issued is accounted for.

## Harness notes

- Runner: `gltest` direct in-process runner (`from gltest.direct import ...`).
- Cross-contract calls (the ledger reading the gate's `get_operation`,
  `get_agreement` and `get_entitlement`) are answered by a `_gl_call_hook`, so
  the ledger's real settlement and cap-guard logic runs against a controlled
  gate verdict.
- The gate's consensus steps (`gl.eq_principle.prompt_non_comparative`) are
  answered by the same hook mechanism with a stubbed verdict (schedule
  verification, metered mapping, or the forcing pass); the gate's real
  validation, state determination and arithmetic run on top of it.
- Every contract call that reaches consensus, the balance ledger, or another
  contract runs inside `with vm.activate():`, which installs the GenVM mock that
  routes those calls to the hook. Contract `assert` failures surface as
  `AssertionError` and are asserted with `pytest.raises(AssertionError)`.
- The SDK is pinned to `v0.2.16` in `tests/conftest.py`.

- Agreements are activated in tests through a shared `activate` helper in
  `tests/conftest.py` (both parties accept the stored text hash). Ledger tests
  fund escrow through `fund`, which the issuer runs as the first step inside the
  test's own activation block.
- Two behaviors of the direct runner shape the suite. It cannot make
  cross-contract calls in a second `vm.activate()` block once one has closed,
  so each test uses exactly one. And it does not roll back state when a call
  reverts, so the contracts validate everything before writing anything, and the
  tests assert that nothing was recorded after a revert.
