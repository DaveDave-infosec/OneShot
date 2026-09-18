# OneShot — Test Suite


Real-contract tests that drive the actual `OneShotGate` and `OneShotLedger`
code paths on the GenLayer `gltest` direct in-process runner. Every state
decision, every settlement, and the cross-contract read are the contracts' own
code. Only two things are stubbed: the *other* contract's return value on a
cross-contract call, and the LLM consensus verdict. The surrounding guard,
pairing, state-determination and value-movement logic is real, so each test
exercises the true code path, not a reimplementation.


**17 tests, no skips.**


## Run


pip install "genlayer-test[sim]" pytest
python -m pytest tests/




The first run downloads and caches the pinned SDK (`v0.2.16`); later runs are
offline.


## What each test proves


### tests/test_gate.py — pairing, mapping, escalation, access


- **novel_op_clears_in_code_without_consensus** — a first operation on a fresh
  obligation has no colliding prior, so it resolves `CLEAR_NEW` purely in code.
  No consensus hook is set; if the gate reached for the LLM here the test would
  fail. Proves the deterministic filter that keeps the ~95% easy case off the
  validators.
- **first_pass_duplicate_against_clean_prior** — a differently-worded operation
  that collides with a clean prior, with the entitlement-mapping consensus
  returning `duplicate`, resolves `CONFIRMED_DUPLICATE` and links to its prior.
- **first_pass_distinct_is_confirmed_new** — the same collision shape but with
  the consensus returning `distinct` resolves `CONFIRMED_NEW`. Proves the engine
  discriminates rather than always-quarantining.
- **escalate_resolves_ambiguous_to_duplicate** — an operation held
  `POSSIBLE_DUPLICATE` after an ambiguous first pass is escalated; the forcing
  pass commits to `duplicate` and resolves it to `CONFIRMED_DUPLICATE`. Proves
  escalation always resolves a hold instead of re-verdicting and holding again.
- **unauthorized_caller_rejected** — an operation whose actual transaction
  sender is not an authorized source reverts, even when the caller passes an
  authorized address as the `source` argument. The source is bound to the real
  caller, so an authorized address cannot be spoofed.
- **blank_reference_rejected** — an operation with both `obligation_ref` and
  `incident_id` blank reverts. A duplicate cannot dodge comparison by omitting
  its reference to slip through as `CLEAR_NEW`.
- **pairs_against_first_prior_not_last** — when several operations target the
  same obligation and recipient, every later one is paired against the *first*
  (original) operation in the bucket, not a later entry. A duplicate cannot be
  matched against a weaker or older-but-not-original entry to dodge a clean
  finding.
- **escalate_unresolved_reaches_held_final** — when the forcing pass genuinely
  cannot commit, it returns `unresolved` and the operation moves to
  `HELD_FINAL` — the reachable deadlock that unlocks the two-party joint
  release. Proves the failed-consensus recovery path is real, not a claim.


### tests/test_ledger.py — settlement, replay, conservation, joint release


- **confirmed_duplicate_pays_nothing_no_double_execution** — the core
  replay / double-spend property: an operation that discharges an
  already-satisfied entitlement settles to `satisfied_by_prior`, the vault
  balance is unchanged, and the recipient receives nothing. One economic intent,
  paid once.
- **clear_new_executes_with_exact_conservation** — a `CLEAR_NEW` operation pays:
  the vault decreases by exactly the amount and the recipient increases by
  exactly the amount. Value is conserved to the unit.
- **confirmed_new_executes** — a `CONFIRMED_NEW` (genuinely distinct)
  operation pays the recipient.
- **permissionless_bystander_settle** — a wallet that is neither the owner nor a
  named party settles an executable operation, and the value math is exact.
  There is no privileged settler; the outcome is fixed by the gate verdict, not
  the caller. This answers the centralization critique in code.
- **double_settle_reverts** — settling the same operation twice reverts on the
  second attempt. An operation cannot be replayed through the settlement path.
- **possible_duplicate_holds_funds_untouched** — a held operation settles to
  `held`, and the vault is untouched. A suspected collision is never silently
  suppressed and never blindly paid; it waits, recoverably.
- **two_party_both_execute_pays_once** — an operation in final hold is released
  only when both named agreement parties independently approve `execute`; it
  then pays exactly once.
- **two_party_disagree_stays_frozen** — if the two parties vote differently
  (one `execute`, one `reject`), nothing moves; the operation stays in final
  hold until they concur.
- **two_party_nonparty_rejected** — a caller who is not one of the two named
  parties cannot resolve a final hold; the call reverts. No authority, no
  backdoor.


## Harness notes


- Runner: `gltest` direct in-process runner (`from gltest.direct import ...`).
- Cross-contract calls (the ledger reading the gate's `get_operation` /
  `get_agreement`) are answered by a `_gl_call_hook` in `tests/conftest.py`, so
  the ledger's real settlement logic runs against a controlled gate verdict.
- The gate's consensus step (`gl.eq_principle.prompt_non_comparative`) is
  answered by the same hook with a stubbed entitlement-mapping verdict; the
  gate's real pairing and state-determination logic runs on top of it.
- `vm.activate()` wraps any call that reads the internal balance ledger or
  crosses contracts. Contract `assert` failures surface as `AssertionError`
  under the direct runner and are asserted with `pytest.raises(AssertionError)`.
- The SDK is pinned to `v0.2.16` in `tests/conftest.py`.
