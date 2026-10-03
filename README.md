# OneShot

**Semantic collision detection and recoverable quarantine for payouts generated
from human-language agreements, on GenLayer.**

A nonce stops the same message twice. It cannot stop two *differently worded*
messages that pay the same money. OneShot sits between the contracts that
propose payouts and the ledger that executes them, and before a payout settles
it asks a question a nonce cannot: **has this economic entitlement already been
discharged under a different description?**

Every economic intent executes once, or stays visibly unresolved. Never
duplicated, never silently erased.

**Live:** https://oneshot-genlayer.vercel.app (landing) and
https://oneshot-genlayer.vercel.app/desk (the Reconciliation Desk).

---

## V2: partial and cumulative entitlements

V1 asks a binary question: do two operations discharge the **same**
entitlement, or two **distinct** ones? Real payouts are messier. An entitlement
is often paid in pieces (progress payments, retentions, installments), and a
later message can discharge **part** of what an earlier one left open.

Take a milestone fee of 10 GEN. A progress payment of 7 GEN goes through. Then a
differently worded message arrives: "release the retained amount for milestone
2", for 5 GEN. Only 3 GEN is still owed.

- A nonce sees new bytes and pays all 5. **Overpaid by 2.**
- A binary duplicate check has no right answer. Calling it a duplicate pays 0
  and **eats 3 GEN that is genuinely owed**. Calling it distinct pays 5 and
  **overpays by 2**.
- OneShot V2 pays exactly **3**, and holds the other **2** visibly, recoverable
  only by the two named parties acting jointly.

V2 also catches a second collision a nonce cannot see: **amount semantics**.
"Bring the documentation fee paid to date up to 3 GEN in total" states a running
total, not a new payment. With 2 GEN already paid, a naive system pays 3. OneShot
reads the wording as cumulative and pays **1**.

### Consensus decides meaning. Code does money.

The LLM never computes what gets paid. For each operation on a metered
agreement, one consensus pass answers only the two semantic questions:

1. **Which scheduled entitlement does this operation discharge?** Judged by the
   agreement wording and the operation's economic purpose, not by its labels.
   Differently worded operations can map to the same entitlement.
2. **How is its amount meant?** `incremental` (a new payment on top of earlier
   ones) or `cumulative` (the total that should have been paid to date).

Deterministic code then does all the arithmetic on whole numbers:

```
requested = amount                    (incremental)
requested = amount - committed        (cumulative)
remaining = cap - committed

requested <= 0 or remaining <= 0  ->  CONFIRMED_DUPLICATE   payable 0
requested <= remaining            ->  CONFIRMED_NEW         payable = requested
requested >  remaining > 0        ->  PARTIAL               payable = remaining, residual = the rest
```

Semantic judgment stays where GenLayer consensus is needed. Money stays where
it can be tested to the unit.

### The schedule is verified, not trusted

A metered agreement is registered with an entitlement schedule: an id, a label
and a cap for each entitlement. The registrant supplies it; **consensus verifies
it against the locked agreement text** before anything is stored. Every
entitlement must be granted by the text, and every cap must equal an amount
written explicitly in the text. A cap derived by arithmetic, inflated, or
double-counted is rejected, and the registration reverts with the validators'
stated problem. Nobody can meter a cap the agreement does not grant.

Verification, rather than free extraction, is deliberate: a faithful-or-not
judgment converges across validators far better than open-ended extraction.

### The reservation closes the race

If remaining balance were tracked only at payout time, two operations verdicted
before either settled would both see the full balance, and both would be
approved. OneShot closes that:

- The **gate reserves** the payable amount at verdict time (`committed`), so a
  second operation already sees the first one's claim.
- The **ledger enforces** at payout time. Before any metered payout it reads the
  cap from the gate and asserts that what it has already paid plus this payout
  stays within the cap (`ent_paid`).
- **Invariant: ledger paid ≤ gate committed ≤ cap.** Even a wrong gate verdict
  cannot make the ledger overpay an entitlement.

### The residual is held, not erased

A PARTIAL pays what is owed and holds the excess visibly on the ledger. The
residual is recoverable only by the two named agreement parties: both vote
`execute` and it pays (an explicit joint decision to go beyond the cap), both
vote `reject` and it is permanently refused, disagree and it stays frozen.
There is no owner override.

### Redirects are questions, not payments

The first payout on an entitlement locks its recipient. A later operation that
maps to the same entitlement but pays someone else is held, never paid, even
after a forcing escalation. A redirect goes to the two named parties.

### Late resolution sees what is left

A held operation escalates to a forcing consensus pass that must commit to one
entitlement and an amount mode, or declare `UNRESOLVED` as an honest deadlock.
A commit is metered **at escalate time**, against what is actually left then,
never against the headroom that existed when it was first held.

### V2 live proofs (GenLayer Studio, real validators)

Agreement 1 is a live metered agreement: an M2 milestone fee capped at 10 GEN
(progress payments and any retained amount count toward the same 10) and a
separate documentation fee capped at 4 GEN. The validators verified both caps
against the locked text. Every row below is readable by anyone through
`get_operation(op_id)` on the gate and `get_settlement(op_id)` on the ledger.

| Op | Wording | Stated | Mode | Verdict | Payable | Held |
|---|---|---|---|---|---|---|
| 1 | Progress payment of 7 GEN toward the M2 milestone fee | 7 | incremental | `CONFIRMED_NEW` | 7 | 0 |
| 2 | Release the retained amount for milestone 2 on acceptance | 5 | incremental | `PARTIAL` | 3 | 2 |
| 3 | Pay the M2 completion fee on acceptance of the payment module | 4 | incremental | `CONFIRMED_DUPLICATE` | 0 | 0 |
| 4 | Installment of 2 GEN toward the documentation fee | 2 | incremental | `CONFIRMED_NEW` | 2 | 0 |
| 5 | Bring the documentation fee paid to date up to 3 GEN in total | 3 | cumulative | `CONFIRMED_NEW` | 1 | 0 |

Ops 1 and 2 are settled on the live ledger: the recipient holds exactly 10 GEN,
the vault exactly 90, and the ledger's M2 paid counter reads 10, exactly the
cap. Op 2's residual of 2 is held, with the ledger note explaining why.

Each verdict carries the validators' reasoning and a minority note. On op 2 the
validators recorded the opposite reading (could the 5 be cumulative?) and
rejected it for lack of running-total wording. On op 5 they recorded the
incremental reading and rejected it on the explicit "paid to date ... in total"
phrasing.

---

## The two keystones

**1. Why GenLayer is load-bearing.** The colliding messages come from
independent agents that never coordinated on a canonical id, because that is
exactly the condition an appeal or re-emission model creates. The original
execution path emits "release M2 payment"; an appeal path re-emits "release the
retained amount for milestone 2." Neither chose to skip canonicalization; they
are independent interpretations of the same natural-language agreement. A
canonical id cannot exist across independent interpreters of a human agreement,
so a deterministic nonce is structurally unable to catch the collision. Deciding
whether two differently worded operations discharge the *same* human-language
entitlement, and in V2 how much of it, is a judgment call. That is what
GenLayer's consensus is for. Remove the consensus and the product collapses into
string comparison, which by construction misses the case.

**2. Recoverable, visible quarantine, never silent suppression.** A naive
version of this has no safe default: wrongly suppressing a payout silently eats a
real payment, wrongly passing one double-pays. OneShot does not decide and
discard; it detects and holds visibly. A suspected collision becomes a
recoverable, attributable, on-chain hold, never a black-box outcome where a
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

- Fully canonicalized agreements: a string compare suffices, OneShot is not
  needed.
- Arbitrary natural-language financial instructions: too loose to be safe.
- Any comparison where structured envelope fields already separate the
  operations deterministically: those never reach consensus on a V1 agreement.

**The deterministic-vs-consensus split.** On a V1 agreement, structured
envelope fields create candidate pairs and separate the easy cases *in code*,
with no LLM cost. Consensus is invoked only for the residual question: do these
two operations discharge the same human-language entitlement, or two distinct
ones? On a V2 metered agreement, consensus answers only the mapping and the
amount mode; every number is computed in code.

---

## The quarantine states

| State | Meaning | Settlement |
|---|---|---|
| `CLEAR_NEW` | No colliding prior. Cleared in code, no consensus. (V1) | Executes |
| `CONFIRMED_NEW` | Discharges a genuinely distinct entitlement, or on a metered agreement, fits within what the entitlement still owes. | Executes (metered: pays `payable`) |
| `PARTIAL` | **V2.** Discharges part of an entitlement that only has part of the request left. | Pays the remaining amount, holds the residual for joint release |
| `CONFIRMED_DUPLICATE` | Discharges an entitlement already satisfied, or already fully committed up to its cap. | Not executed, marked satisfied |
| `POSSIBLE_DUPLICATE` | Credible collision; relationship not yet safe to confirm. (V1) | Held, recoverable |
| `AMBIGUOUS` | Wording does not resolve the case safely, or a redirect, or low confidence. | Held, recoverable, reserves nothing |
| `REPLACEMENT` | Supersedes a still-pending prior. (V1 path) | Replaces, does not double |

A held operation can be escalated to a **forcing** second consensus pass that
must commit. If even that cannot converge, the operation reaches `HELD_FINAL`,
resolvable only by the **two named agreement parties acting jointly**. There is
no owner or privileged operator anywhere in the lifecycle.

---

## Architecture

Two Intelligent Contracts (Python, GenLayer Studio), split so the brain never
holds the money:

- **`contracts/oneshot_gate.py`**: the decision engine. Registers agreements
  with their governing text locked on-chain. V1 agreements use deterministic
  candidate-pairing in code and run the entitlement-mapping consensus only on a
  real candidate pair. V2 metered agreements (`register_metered_agreement`)
  carry a consensus-verified entitlement schedule; each operation runs one
  mapping consensus, then `_apply_meter` does the arithmetic and the
  reservation. Produces the state, the mapping, the metering figures, the
  reasoning and a minority note. Never moves funds.
- **`contracts/oneshot_ledger.py`**: settlement. Holds test GEN in an internal
  balance ledger, reads the gate's verdict cross-contract, and acts on it:
  executes, holds visibly, marks satisfied without paying, supersedes, pays a
  PARTIAL's payable part through the cap guard, or awaits the two parties'
  joint release of a final hold or a held residual. Settlement is
  permissionless; the outcome is fixed by the gate verdict, not by the caller.

V1 agreements run the unchanged V1 path, and all 17 V1 tests still pass as the
regression proof.

### Deployed contracts (GenLayer Studio, chainId 61999)

| Contract | Address |
|---|---|
| Gate (V2) | `0xC769DcDAbb228e3568452B2F09a7cE9bD7075cA5` |
| Ledger (V2) | `0x14419dAd62612038A005F70636351035f5E2Dcdf` |

The ledger is constructed with the gate address baked in, so the linkage is
fixed on-chain and a bystander can verify any decision against the gate
directly.

Superseded V1 pair: gate `0xd3eC9487aEa79655d7F7e62A2D4DE673f21a7b49`, ledger
`0x633EAC3F74cD645c8ECBe2F6284fFBf62FA1DC7f`.

---

## Trust model

- **Source bound to the caller.** An operation's source is bound to the actual
  transaction sender, so a caller can only ever submit as itself.
- **No duplicate can dodge comparison.** Every operation must carry an
  obligation or incident reference. On V1 agreements a collision is paired
  against the first (original) operation in the bucket.
- **Caps come from the text, verified by consensus.** No registrant can meter
  an entitlement the agreement does not grant, or a cap larger than it states.
- **No overpayment, even on a wrong verdict.** The gate reserves at verdict
  time; the ledger independently enforces the cap at payout time.
- **No privileged settler.** `settle_operation` is permissionless. State,
  recipient and payable amount all come from the gate cross-contract, never from
  the caller.
- **No authority in the lifecycle.** A held operation escalates to a forcing
  consensus pass. Only a genuine deadlock, a redirect, or a residual beyond the
  cap falls to the two named parties, who must both concur. There is no admin
  key and no external override.
- **Locked governing text.** The agreement text is stored on-chain at
  registration and is the authority every verdict is judged against.
- **Full audit trail.** Every operation is recorded with its state, its
  metering figures, the validators' reasoning and a minority note on-chain.

---

## Honest limitations

- OneShot is narrow-domain, not universal idempotency. See the domain boundary
  above.
- The promise is "no silent semantic replay, every collision recoverable and
  attributable," not "perfect exactly-once."
- **Metered caps must be written explicitly in the agreement text.** A cap that
  needs arithmetic (a percentage, a split) is rejected by design, so
  verification stays convergent.
- **Amounts on metered agreements are whole numbers.** Fractional amounts revert.
- **REPLACEMENT is not emitted on metered agreements.** Superseding a pending
  operation would move reservations mid-flight; it stays on the V1 path.
- **A joint release beyond the cap is an explicit override.** When both parties
  release a residual, or execute a metered final hold, the ledger pays it as
  agreed by both, outside the meter. That is the parties' decision, recorded
  on-chain, never an automatic one.
- The forcing pass prefers to commit; the two-party release is the honest
  backstop for the rare true deadlock, and a disagreement stays frozen until the
  parties concur.

---

## Tests

**62 real-contract tests, no skips.** They drive the actual gate and ledger
code paths on the `gltest` direct runner: the 17 V1 tests (unchanged, as the
regression proof) plus 45 V2 tests covering schedule verification, the PARTIAL
split, cumulative mode, the reservation race, redirects, metered escalation, the
ledger cap guard, exact conservation, and the residual's two-party release. See
**[TESTING.md](./TESTING.md)**.

---

*OneShot is the one build about execution identity rather than value
settlement. It does not ask "is it allowed" or "was it delivered." It asks
whether this economic intent has already happened under a different
description, and in V2, how much of it is still owed. It never fails
destructively, only into visible, recoverable quarantine.*
