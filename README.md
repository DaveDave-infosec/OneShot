# OneShot

**Semantic collision detection and recoverable quarantine for payouts generated
from human-language agreements, on GenLayer.**

A nonce stops the same message twice. It cannot stop two *differently worded*
messages that pay the same money. OneShot sits between the contracts that
propose payouts and the ledger that executes them, and before a payout settles
it asks a question a nonce cannot: **has this economic entitlement already been
discharged under a different description?**

Every economic intent executes once — or stays visibly unresolved. Never
duplicated, never silently erased.

---

## The two keystones

**1. Why GenLayer is load-bearing.** The colliding messages come from
independent agents that never coordinated on a canonical id — because that is
exactly the condition an appeal / re-emission model creates. The original
execution path emits "release M2 payment"; an appeal path re-emits "release the
retained amount for milestone 2." Neither *chose* to skip canonicalization; they
are independent interpretations of the same natural-language agreement. A
canonical id cannot exist across independent interpreters of a human agreement,
so a deterministic nonce is structurally unable to catch the collision. Deciding
whether two differently-worded operations discharge the *same* human-language
entitlement is a judgment call — which is what GenLayer's consensus is for.
Remove the consensus and the product collapses into string comparison, which by
construction misses the case.

**2. Recoverable, visible quarantine — never silent suppression.** A naive
version of this has no safe default: wrongly suppressing a payout silently eats a
real payment, wrongly passing one double-pays. OneShot does not decide-and-
discard; it detects-and-holds-visibly. A suspected collision becomes a
recoverable, attributable, on-chain hold — never a black-box outcome where a
party just notices the money never arrived. Quarantine *is* the safe default.

The honest promise, stated plainly: OneShot prevents suspected semantic replays
from executing silently and makes every collision recoverable, attributable and
reviewable. It does **not** claim perfect, universal exactly-once.

---

## The domain boundary (what keeps OneShot honest)

OneShot is **not** universal idempotency middleware. Its domain is narrow and
stated on purpose: recoverable semantic-collision quarantine for payouts
generated from human-language agreements, specifically where the agreement is
partly natural language, one umbrella obligation can generate several distinct
remedies, different agents produce execution messages independently, and the
exact sub-entitlement cannot be reliably canonicalized beforehand.

Explicitly out of scope, and said so rather than hidden:

- Fully-canonicalized agreements — a string compare suffices, OneShot is not
  needed.
- Arbitrary natural-language financial instructions — too loose to be safe.
- Any comparison where structured envelope fields already separate the
  operations deterministically — those never reach consensus.

**The deterministic-vs-consensus split.** Structured envelope fields create
candidate pairs and separate the easy cases *in code*, with no LLM cost.
Consensus is invoked only for the residual question: do these two operations
discharge the same human-language entitlement, or two cumulative ones? Different
obligation refs are separated in code and never reach the validators. Same
obligation ref, same amount, same recipient, but "refund" vs "service credit"
under an SLA whose wording turns on "and" vs "or" — that is the load-bearing
slice consensus decides.

---

## The six quarantine states

| State | Meaning | Settlement |
|---|---|---|
| `CLEAR_NEW` | No colliding prior. Cleared in code, no consensus. | Executes |
| `CONFIRMED_NEW` | Discharges a genuinely distinct entitlement. | Executes |
| `CONFIRMED_DUPLICATE` | Discharges an entitlement a prior already satisfied. | Not executed, marked satisfied |
| `POSSIBLE_DUPLICATE` | Credible collision; relationship not yet safe to confirm. | Held, recoverable |
| `AMBIGUOUS` | Wording does not resolve the relationship safely. | Held, recoverable |
| `REPLACEMENT` | Supersedes a still-pending prior. | Replaces, does not double |

A held operation can be escalated to a **forcing** second consensus pass that
must commit to duplicate or distinct. If even that cannot converge, the
operation reaches `HELD_FINAL`, resolvable only by the **two named agreement
parties acting jointly** — there is no owner or privileged operator anywhere in
the lifecycle.

---

## Architecture

Two Intelligent Contracts (Python, GenLayer Studio), split so the brain never
holds the money:

- **`contracts/oneshot_gate.py`** — the decision engine. Registers agreements
  with their governing text locked on-chain (the immutable pin), does
  deterministic candidate-pairing in code, and runs the entitlement-mapping
  consensus only on a real candidate pair. Produces the state, the mapping, the
  reasoning and a minority note. Never moves funds.
- **`contracts/oneshot_ledger.py`** — settlement. Holds test GEN in an internal
  balance ledger, reads the gate's verdict cross-contract, and acts on it:
  executes, holds visibly, marks satisfied without paying, supersedes, or (in
  final hold) awaits the two parties' joint release. Settlement is permissionless
  — the outcome is fixed by the gate verdict, not by the caller.

### Deployed contracts (GenLayer Studio, chainId 61999)

| Contract | Address |
|---|---|
| Gate | `0xd3eC9487aEa79655d7F7e62A2D4DE673f21a7b49` |
| Ledger | `0x633EAC3F74cD645c8ECBe2F6284fFBf62FA1DC7f` |

The ledger is constructed with the gate address baked in, so the linkage is
fixed on-chain and a bystander can verify any decision against the gate directly.

---

## Trust model

- **Source bound to the caller.** An operation's source is bound to the actual
  transaction sender, so a caller can only ever submit as itself. Passing an
  authorized address you do not control does not help; the real caller is what
  the authorization check reads.
- **No duplicate can dodge comparison.** Every operation must carry an
  obligation or incident reference, and a collision is paired against the first
  (original) operation that opened the bucket. A duplicate cannot slip through
  by blanking or changing its reference, or by being matched against a weaker,
  later entry.
- **No privileged settler.** `settle_operation` is permissionless. The state,
  recipient and amount all come from the gate cross-contract, never from the
  caller, so no one can fake a payout and the owner cannot override a hold.
- **No authority in the lifecycle.** A held operation escalates to a forcing
  consensus pass. If that pass can commit, it resolves the operation. Only when
  the forcing pass itself returns `unresolved` — a genuine deadlock the
  agreement cannot settle — does the operation reach `HELD_FINAL`, resolvable
  only by the two named parties acting jointly. There is no admin key and no
  external override; the deadlock path is reachable only through consensus.
- **Locked governing text.** The agreement text is stored on-chain at
  registration and is the authority every verdict is judged against; it cannot
  be rewritten after operations start.
- **Full audit trail.** Every operation is recorded, attributable, and
  recoverable, with its state, reasoning and minority note on-chain.

---

## Honest limitations

- OneShot is narrow-domain, not universal idempotency. See the domain boundary
  above.
- The promise is "no silent semantic replay, every collision recoverable and
  attributable," not "perfect exactly-once."
- Fully-canonicalized agreements do not need OneShot; string comparison already
  separates them.
- The escalation forcing pass commits to duplicate-or-distinct; the two-party
  joint release is the honest backstop for the rare true deadlock, and if the
  parties disagree the operation stays frozen until they concur.

---

## Tests

A real-contract test suite drives the actual gate and ledger code paths on the
`gltest` direct runner — including the no-double-execution proof, permissionless
bystander settlement, exact value conservation, and the two-party joint release.
See **[TESTING.md](./TESTING.md)**.

---

*OneShot is the one build about execution identity rather than value settlement.
It does not ask "how much," "is it allowed," or "was it delivered" — it asks
whether this economic intent has already happened under a different description,
and it never fails destructively, only into visible, recoverable quarantine.*
