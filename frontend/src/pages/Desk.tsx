import { useEffect, useState } from "react";
import "../styles.css";
import { Nav } from "../components/Nav";
import { useWallet } from "../lib/useWallet";
import {
  getAgreementCount, getOperationCount, getAgreement, getOperation, getSettlement,
  submitOperation, settleOperation, escalate, syncFromGate,
} from "../lib/contracts";
import { stateMeta, settlementLabel } from "../lib/states";

interface Agreement { id: string; title: string; agreement_text: string; authorized_sources: string; party_a: string; party_b: string; }
interface Operation { id: string; agreement_id: string; recipient: string; amount: string; action_family: string; obligation_ref: string; state: string; entitlement: string; linked_prior: string; reasoning: string; minority_note: string; settlement_status: string; }

function short(a: string): string {
  if (!a || a.length < 12) return a;
  return a.slice(0, 6) + "…" + a.slice(-4);
}

interface SubmitFormProps {
  agreementId: string;
  walletAddress: string | null;
  onDone: () => void;
}

function SubmitForm({ agreementId, walletAddress, onDone }: SubmitFormProps) {
  const [recipient, setRecipient] = useState("");
  const [amount, setAmount] = useState("");
  const [actionFamily, setActionFamily] = useState("");
  const [obligationRef, setObligationRef] = useState("");
  const [incidentId, setIncidentId] = useState("");
  const [economicPurpose, setEconomicPurpose] = useState("");
  const [entitlementHint, setEntitlementHint] = useState("");
  const [status, setStatus] = useState<"idle" | "busy" | "ok" | "bad">("idle");
  const [msg, setMsg] = useState("");

  const source = walletAddress || "";

  async function doSubmit() {
    if (!walletAddress) { setStatus("bad"); setMsg("Connect a wallet or use demo first."); return; }
    if (!recipient || !amount || !actionFamily) { setStatus("bad"); setMsg("Recipient, amount and action family are required."); return; }
    setStatus("busy"); setMsg("Submitting to the gate… consensus may take a moment.");
    try {
      await submitOperation(
        agreementId, source, recipient, "GEN", amount,
        actionFamily, obligationRef, incidentId, economicPurpose, entitlementHint
      );
      setStatus("ok"); setMsg("Submitted. Refreshing operations…");
      onDone();
    } catch (e: any) {
      const raw = String(e?.message || e);
      if (e?.pending) {
        setStatus("busy");
        setMsg("Submitted on-chain and still finalizing through consensus. Reload in a few seconds to see the resolved state.");
        return;
      }
      setStatus("bad");
      if (raw.toLowerCase().includes("not authorized")) {
        setMsg("Rejected: this wallet is not an authorized source on this agreement. Register your own agreement to submit freely (coming in the actions panel).");
      } else {
        setMsg("Failed: " + raw);
      }
    }
  }

  return (
    <div className="sform">
      <div className="sform-grid">
        <div className="field">
          <label>Source (you)</label>
          <input value={short(source)} disabled readOnly />
        </div>
        <div className="field">
          <label>Recipient address</label>
          <input value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="0x…" />
        </div>
        <div className="field">
          <label>Amount (GEN)</label>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="5" />
        </div>
        <div className="field">
          <label>Action family</label>
          <input value={actionFamily} onChange={(e) => setActionFamily(e.target.value)} placeholder="completion_payment" />
        </div>
        <div className="field">
          <label>Obligation ref</label>
          <input value={obligationRef} onChange={(e) => setObligationRef(e.target.value)} placeholder="M2" />
        </div>
        <div className="field">
          <label>Incident id (optional)</label>
          <input value={incidentId} onChange={(e) => setIncidentId(e.target.value)} placeholder="" />
        </div>
        <div className="field full">
          <label>Economic purpose</label>
          <input value={economicPurpose} onChange={(e) => setEconomicPurpose(e.target.value)} placeholder="Completion payment for milestone M2" />
        </div>
        <div className="field full">
          <label>Entitlement hint</label>
          <input value={entitlementHint} onChange={(e) => setEntitlementHint(e.target.value)} placeholder="M2 completion payment" />
        </div>
      </div>
      <div className="sform-foot">
        <button className="act-btn solid" onClick={doSubmit} disabled={status === "busy"}>
          {status === "busy" ? "Submitting…" : "Submit operation"}
        </button>
        {msg && <span className={"sform-msg " + (status === "ok" ? "ok" : status === "bad" ? "bad" : "busy")}>{msg}</span>}
      </div>
      <div className="gate-note">The gate runs deterministic pairing in code; a colliding pair triggers consensus, which can take a moment to finalize.</div>
    </div>
  );
}

export function Desk() {
  const { address } = useWallet();
  const [agreements, setAgreements] = useState<Agreement[]>([]);
  const [ops, setOps] = useState<Operation[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [agLoading, setAgLoading] = useState(true);
  const [opsLoading, setOpsLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [settling, setSettling] = useState<string>("");
  const [settleMsg, setSettleMsg] = useState<Record<string, { kind: string; text: string }>>({});
  const [escalating, setEscalating] = useState<string>("");
  const [escMsg, setEscMsg] = useState<Record<string, { kind: string; text: string }>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  async function loadOps() {
    setOpsLoading(true);
    try {
      const opCount = Number(await getOperationCount());
      const opIds = Array.from({ length: opCount }, (_, i) => String(i + 1));
      const opResults = await Promise.all(
        opIds.map(async (id) => {
          const o = await getOperation(id);
          let settlement = "unsettled";
          try { const s = await getSettlement(id); settlement = String(s.status); } catch (_) { settlement = "unsettled"; }
          return { o, settlement };
        })
      );
      const operations: Operation[] = opResults.map(({ o, settlement }) => ({
        id: String(o.id), agreement_id: String(o.agreement_id),
        recipient: String(o.recipient), amount: String(o.amount),
        action_family: String(o.action_family), obligation_ref: String(o.obligation_ref),
        state: String(o.state), entitlement: String(o.entitlement),
        linked_prior: String(o.linked_prior), reasoning: String(o.reasoning),
        minority_note: String(o.minority_note), settlement_status: settlement,
      }));
      setOps(operations);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setOpsLoading(false);
    }
  }

  async function refreshOneOp(opId: string): Promise<string> {
    try {
      const o = await getOperation(opId);
      let settlement = "unsettled";
      try { const s = await getSettlement(opId); settlement = String(s.status); } catch (_) { settlement = "unsettled"; }
      const updated: Operation = {
        id: String(o.id), agreement_id: String(o.agreement_id),
        recipient: String(o.recipient), amount: String(o.amount),
        action_family: String(o.action_family), obligation_ref: String(o.obligation_ref),
        state: String(o.state), entitlement: String(o.entitlement),
        linked_prior: String(o.linked_prior), reasoning: String(o.reasoning),
        minority_note: String(o.minority_note), settlement_status: settlement,
      };
      setOps((prev) => prev.map((x) => (x.id === opId ? updated : x)));
      return settlement;
    } catch (_) {
      return "unsettled";
    }
  }

  function pollOp(opId: string, onResolved: () => void) {
    // poll every 5s for up to ~90s; stop as soon as the settlement leaves "unsettled".
    let tries = 0;
    const maxTries = 18;
    const timer = setInterval(async () => {
      tries += 1;
      const status = await refreshOneOp(opId);
      if (status !== "unsettled") {
        clearInterval(timer);
        onResolved();
      } else if (tries >= maxTries) {
        clearInterval(timer);
      }
    }, 5000);
  }

  async function loadAll() {
    setError("");
    try {
      const [agCountRaw] = await Promise.all([getAgreementCount()]);
      const agCount = Number(agCountRaw);
      const agIds = Array.from({ length: agCount }, (_, i) => String(i + 1));
      const agResults = await Promise.all(agIds.map((id) => getAgreement(id)));
      const ags: Agreement[] = agResults.map((a) => ({
        id: String(a.id), title: String(a.title),
        agreement_text: String(a.agreement_text),
        authorized_sources: String(a.authorized_sources),
        party_a: String(a.party_a), party_b: String(a.party_b),
      }));
      setAgreements(ags);
      setSelected((cur) => cur || (ags.length > 0 ? ags[0].id : ""));
      setAgLoading(false);
      await loadOps();
    } catch (e: any) {
      setError(String(e?.message || e));
      setAgLoading(false);
      setOpsLoading(false);
    }
  }

  useEffect(() => { loadAll(); }, []);

  const current = agreements.find((a) => a.id === selected) || null;
  const currentOps = ops.filter((o) => o.agreement_id === selected);

  function collisionTone(o: Operation): string {
    // amber = the prior in a collision pair; cyan = the new colliding op.
    if (!o.linked_prior) return "";
    return "tone-cyan";
  }
  function priorTone(o: Operation): string {
    // the linked-prior operation, when shown in this list, reads amber.
    const priorIds = ops.filter((x) => x.linked_prior && x.linked_prior !== "").map((x) => x.linked_prior);
    return priorIds.includes(o.id) ? "tone-amber" : "";
  }
  function paidClass(status: string): string {
    if (status === "executed" || status === "resolved_executed") return "foot-v paid";
    if (status === "satisfied_by_prior" || status === "resolved_rejected") return "foot-v notpaid";
    return "foot-v";
  }

  async function doSettle(opId: string) {
    if (!address) { setSettleMsg((m) => ({ ...m, [opId]: { kind: "bad", text: "Connect a wallet or use demo first." } })); return; }
    setSettling(opId);
    setSettleMsg((m) => ({ ...m, [opId]: { kind: "busy", text: "Settling on the ledger…" } }));
    try {
      await settleOperation(opId);
      setSettleMsg((m) => ({ ...m, [opId]: { kind: "ok", text: "Settled. Refreshing…" } }));
      const status = await refreshOneOp(opId);
      if (status === "unsettled") pollOp(opId, () => {});
    } catch (e: any) {
      if (e?.pending) {
        setSettleMsg((m) => ({ ...m, [opId]: { kind: "busy", text: "Submitted on-chain, finalizing… this updates automatically." } }));
        pollOp(opId, () => {
          setSettleMsg((m) => ({ ...m, [opId]: { kind: "ok", text: "Settled." } }));
        });
      } else {
        setSettleMsg((m) => ({ ...m, [opId]: { kind: "bad", text: "Failed: " + String(e?.message || e) } }));
      }
    } finally {
      setSettling("");
    }
  }

  async function doEscalate(opId: string) {
    if (!address) { setEscMsg((m) => ({ ...m, [opId]: { kind: "bad", text: "Connect a wallet or use demo first." } })); return; }
    setEscalating(opId);
    try {
      setEscMsg((m) => ({ ...m, [opId]: { kind: "busy", text: "Step 1 of 2 — forcing a second consensus pass on the gate. Sign in your wallet…" } }));
      await escalate(opId);
      setEscMsg((m) => ({ ...m, [opId]: { kind: "busy", text: "Step 2 of 2 — syncing the new verdict to the ledger. Sign again…" } }));
      await syncFromGate(opId);
      setEscMsg((m) => ({ ...m, [opId]: { kind: "ok", text: "Escalation complete. Refreshing…" } }));
      await loadOps();
    } catch (e: any) {
      if (e?.pending) {
        setEscMsg((m) => ({ ...m, [opId]: { kind: "busy", text: "Submitted on-chain, finalizing… this updates automatically." } }));
        pollOp(opId, () => {
          setEscMsg((m) => ({ ...m, [opId]: { kind: "ok", text: "Resolved." } }));
        });
      } else {
        setEscMsg((m) => ({ ...m, [opId]: { kind: "bad", text: "Failed: " + String(e?.message || e) } }));
      }
    } finally {
      setEscalating("");
    }
  }

  return (
    <div className="page desk-page">
      <Nav showWallet={true} />
      <div className="content desk-content">
        {error && <div className="err">Error: {error}</div>}
        {agLoading && !error && <div className="loading-line">Reading agreements from chain…</div>}

        {!agLoading && !error && (
          <div className="grid">
            <div className="panel">
              <div className="list-head">Agreements</div>
              {agreements.map((a) => (
                <div key={a.id} className={"ag-item" + (a.id === selected ? " active" : "")} onClick={() => { setSelected(a.id); setShowForm(false); }}>
                  <div className="ag-id">AGREEMENT {a.id}</div>
                  <div className="ag-title">{a.title}</div>
                  <div className="ag-snip">{a.agreement_text}</div>
                </div>
              ))}
            </div>

            <div>
              {!current ? (
                <div className="detail"><div className="empty">Select an agreement to see its operations and their reconciliation.</div></div>
              ) : (
                <div className="detail">
                  <div className="detail-top">
                    <h2 className="detail-title">{current.title}</h2>
                    <span className="detail-sub">AGREEMENT {current.id} · TEXT LOCKED ON-CHAIN</span>
                  </div>
                  <div className="ag-text">{current.agreement_text}</div>
                  <div className="meta-row">
                    <div><div className="meta-k">Party A</div><div className="meta-v">{short(current.party_a)}</div></div>
                    <div><div className="meta-k">Party B</div><div className="meta-v">{short(current.party_b)}</div></div>
                    <div><div className="meta-k">Authorized source</div><div className="meta-v">{short(current.authorized_sources)}</div></div>
                  </div>

                  <div className="ops-bar">
                    <div className="ops-head">Operations under this agreement</div>
                    <button className="act-btn" onClick={() => setShowForm((s) => !s)}>
                      {showForm ? "Close" : "+ Submit operation"}
                    </button>
                  </div>

                  {showForm && (
                    <SubmitForm
                      agreementId={current.id}
                      walletAddress={address}
                      onDone={() => { loadOps(); }}
                    />
                  )}

                  {opsLoading && <div className="loading-line">Reading operations from chain…</div>}
                  {!opsLoading && currentOps.length === 0 && <div className="loading-line">No operations submitted under this agreement yet.</div>}

                  {currentOps.map((o) => {
                    const meta = stateMeta(o.state);
                    const sm = settleMsg[o.id];
                    const em = escMsg[o.id];
                    const canSettle = o.settlement_status === "unsettled";
                    const isHeld = o.settlement_status === "held";
                    const canEscalate = isHeld && (o.state === "POSSIBLE_DUPLICATE" || o.state === "AMBIGUOUS");
                    const isOpen = !!expanded[o.id];
                    const tone = collisionTone(o) || priorTone(o);
                    const hasWhy = !!(o.reasoning || o.minority_note);
                    return (
                      <div key={o.id} className={"op v2 " + tone} style={{ ["--st" as any]: meta.color, ["--st-dim" as any]: meta.dim }}>
                        <div className="op-verdict">
                          <div className="op-verdict-left">
                            <span className="op-verdict-label">{meta.label}</span>
                            {tone === "tone-cyan" && <span className="tone-tag cyan">message B</span>}
                            {tone === "tone-amber" && <span className="tone-tag amber">message A</span>}
                          </div>
                          <span className="op-idtag">OP {o.id}</span>
                        </div>
                        <div className="op-in">
                          <div className="op-fam-line">{o.action_family} · {o.obligation_ref}</div>
                          {o.entitlement && <div className="op-ent">{o.entitlement}</div>}

                          <div className="op-foot">
                            <div><div className="foot-k">Amount</div><div className="foot-v">{o.amount} GEN</div></div>
                            <div><div className="foot-k">Recipient</div><div className="foot-v">{short(o.recipient)}</div></div>
                            {o.linked_prior && <div><div className="foot-k">Linked prior</div><div className="foot-v">Operation {o.linked_prior}</div></div>}
                            <div><div className="foot-k">Settlement</div><div className={paidClass(o.settlement_status)}>{settlementLabel(o.settlement_status)}</div></div>
                          </div>

                          {hasWhy && (
                            <button className="why-toggle" onClick={() => setExpanded((m) => ({ ...m, [o.id]: !m[o.id] }))}>
                              {isOpen ? "Hide reasoning ▲" : "Why this verdict ▼"}
                            </button>
                          )}
                          {hasWhy && isOpen && (
                            <div className="op-why">
                              {o.reasoning && <div className="op-reason">{o.reasoning}</div>}
                              {o.minority_note && <div className="op-minority"><b>Minority view</b> — {o.minority_note}</div>}
                            </div>
                          )}

                          {(canSettle || sm || canEscalate || em) && (
                            <div className="op-settle-row">
                              {canSettle && (
                                <button className="settle-btn" onClick={() => doSettle(o.id)} disabled={settling === o.id}>
                                  {settling === o.id ? "Settling…" : "Settle on ledger"}
                                </button>
                              )}
                              {canEscalate && (
                                <button className="settle-btn" onClick={() => doEscalate(o.id)} disabled={escalating === o.id}>
                                  {escalating === o.id ? "Escalating…" : "Escalate to forcing consensus"}
                                </button>
                              )}
                              {sm && <span className={"settle-msg " + sm.kind}>{sm.text}</span>}
                              {em && <span className={"settle-msg " + em.kind}>{em.text}</span>}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
