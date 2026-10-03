import { useEffect, useRef, useState } from "react";
import "../styles.css";
import { Nav } from "../components/Nav";
import { useWallet } from "../lib/useWallet";
import {
  getAgreementCount, getOperationCount, getAgreement, getOperation, getSettlement,
  getSchedule, getEntitlementPaid,
  submitOperation, settleOperation, escalate, syncFromGate, partyApprove,
} from "../lib/contracts";
import { stateMeta, settlementText } from "../lib/states";

interface Agreement {
  id: string; title: string; agreement_text: string; authorized_sources: string;
  party_a: string; party_b: string; metered: boolean;
}
interface Operation {
  id: string; agreement_id: string; recipient: string; amount: string;
  action_family: string; obligation_ref: string; state: string; entitlement: string;
  linked_prior: string; reasoning: string; minority_note: string;
  settlement_status: string; residual_status: string; settlement_note: string;
  metered: boolean; entitlement_id: string; amount_mode: string;
  requested: string; payable: string; residual: string; committed_before: string;
}
interface Meter { id: string; label: string; cap: number; committed: number; paid: number; recipient: string; }
type Msg = { kind: string; text: string };

function short(a: string): string {
  if (!a || a.length < 12) return a;
  return a.slice(0, 6) + "…" + a.slice(-4);
}

// Contract results can arrive as Maps (nested ones especially). Convert to plain objects.
function plain(x: any): any {
  if (x instanceof Map) {
    const out: any = {};
    x.forEach((v: any, k: any) => { out[String(k)] = plain(v); });
    return out;
  }
  if (Array.isArray(x)) return x.map(plain);
  return x;
}

function toOp(oRaw: any, sRaw: any): Operation {
  const o = plain(oRaw);
  const s = sRaw ? plain(sRaw) : null;
  return {
    id: String(o.id), agreement_id: String(o.agreement_id),
    recipient: String(o.recipient), amount: String(o.amount),
    action_family: String(o.action_family), obligation_ref: String(o.obligation_ref),
    state: String(o.state), entitlement: String(o.entitlement ?? ""),
    linked_prior: String(o.linked_prior ?? ""), reasoning: String(o.reasoning ?? ""),
    minority_note: String(o.minority_note ?? ""),
    settlement_status: s ? String(s.status ?? "unsettled") : "unsettled",
    residual_status: s ? String(s.residual_status ?? "") : "",
    settlement_note: s ? String(s.note ?? "") : "",
    metered: o.metered === true,
    entitlement_id: String(o.entitlement_id ?? ""),
    amount_mode: String(o.amount_mode ?? ""),
    requested: String(o.requested ?? ""),
    payable: String(o.payable ?? ""),
    residual: String(o.residual ?? ""),
    committed_before: String(o.committed_before ?? ""),
  };
}

// Retry a chain read with a short backoff. A transient RPC failure must never
// be shown to the user as a real on-chain state.
async function withRetry<T>(fn: () => Promise<T>, tries = 3): Promise<T> {
  let last: any = null;
  for (let i = 0; i < tries; i++) {
    try {
      return await fn();
    } catch (e) {
      last = e;
      await new Promise((r) => setTimeout(r, 600 * (i + 1)));
    }
  }
  throw last;
}

async function readOp(id: string): Promise<Operation> {
  const o = await withRetry(() => getOperation(id));
  let s: any = null;
  try { s = await withRetry(() => getSettlement(id)); } catch (_) { s = null; }
  const op = toOp(o, s);
  // If the settlement could not be read, say so. Never claim "unsettled".
  if (s === null) op.settlement_status = "unknown";
  return op;
}

interface SubmitFormProps {
  agreementId: string;
  walletAddress: string | null;
  metered: boolean;
  onDone: () => void;
}

function SubmitForm({ agreementId, walletAddress, metered, onDone }: SubmitFormProps) {
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
    if (metered && !/^[0-9]+$/.test(amount.trim())) { setStatus("bad"); setMsg("Metered agreements take whole GEN amounts only."); return; }
    setStatus("busy"); setMsg("Submitting to the gate… consensus may take a moment.");
    try {
      await submitOperation(
        agreementId, source, recipient, "GEN", amount.trim(),
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
        setMsg("Rejected: this wallet is not an authorized source on this agreement.");
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
          <label>{metered ? "Amount (whole GEN)" : "Amount (GEN)"}</label>
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
          <input value={economicPurpose} onChange={(e) => setEconomicPurpose(e.target.value)} placeholder={metered ? "Bring the M2 fee paid to date up to 8 GEN in total" : "Completion payment for milestone M2"} />
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
      <div className="gate-note">
        {metered
          ? "Metered agreement: consensus maps every operation to one scheduled entitlement and reads whether its amount is a new payment or a running total. Code then pays only what that entitlement still owes."
          : "The gate runs deterministic pairing in code; a colliding pair triggers consensus, which can take a moment to finalize."}
      </div>
    </div>
  );
}

function SkeletonOps({ count }: { count: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skel-card" aria-hidden="true">
          <div className="skel-head"><div className="skel skel-line w30" /></div>
          <div className="skel-body">
            <div className="skel skel-line w50" />
            <div className="skel skel-bar" />
            <div className="skel skel-line w70" />
          </div>
        </div>
      ))}
    </>
  );
}

// The stamp that lands on a card when its on-chain settlement changes.
function stampFor(o: Operation): { text: string; tone: string } {
  const st = o.settlement_status;
  if (st === "partial_executed") {
    if (o.residual_status === "resolved_executed") return { text: "Residual released", tone: "ok" };
    if (o.residual_status === "resolved_rejected") return { text: "Residual refused", tone: "bad" };
    return { text: "Partial · paid", tone: "partial" };
  }
  if (st === "executed" || st === "resolved_executed") return { text: "Paid", tone: "ok" };
  if (st === "satisfied_by_prior") return { text: "Not paid", tone: "bad" };
  if (st === "resolved_rejected") return { text: "Rejected", tone: "bad" };
  if (st === "held_final") return { text: "Final hold", tone: "hold" };
  if (st === "held") return { text: "Held", tone: "hold" };
  return { text: "Updated", tone: "hold" };
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
  const [settleMsg, setSettleMsg] = useState<Record<string, Msg>>({});
  const [escalating, setEscalating] = useState<string>("");
  const [escMsg, setEscMsg] = useState<Record<string, Msg>>({});
  const [voting, setVoting] = useState<string>("");
  const [voteMsg, setVoteMsg] = useState<Record<string, Msg>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [meters, setMeters] = useState<Meter[]>([]);
  const [scheduleNote, setScheduleNote] = useState("");
  const [justSettled, setJustSettled] = useState<Record<string, boolean>>({});
  const opsRef = useRef<Operation[]>([]);
  useEffect(() => { opsRef.current = ops; }, [ops]);

  // Flag ops whose settlement changed since the last read, so their card can
  // show the settle moment. Never fires on first load, never on an unreadable state.
  function flagChanges(next: Operation[]) {
    const prev = new Map(opsRef.current.map((o) => [o.id, o.settlement_status + "|" + o.residual_status]));
    const changed = next
      .filter((o) => {
        const p = prev.get(o.id);
        if (p === undefined || p.startsWith("unknown") || o.settlement_status === "unknown") return false;
        return p !== o.settlement_status + "|" + o.residual_status;
      })
      .map((o) => o.id);
    if (changed.length === 0) return;
    setJustSettled((m) => {
      const c = { ...m };
      changed.forEach((id) => { c[id] = true; });
      return c;
    });
    setTimeout(() => {
      setJustSettled((m) => {
        const c = { ...m };
        changed.forEach((id) => { delete c[id]; });
        return c;
      });
    }, 2600);
  }

  async function loadOps() {
    setOpsLoading(true);
    try {
      const opCount = Number(await getOperationCount());
      const opIds = Array.from({ length: opCount }, (_, i) => String(i + 1));
      const operations: Operation[] = [];
      for (const id of opIds) {
        operations.push(await readOp(id));
      }
      flagChanges(operations);
      setOps(operations);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setOpsLoading(false);
    }
  }

  async function refreshOneOp(opId: string): Promise<string> {
    try {
      const updated = await readOp(opId);
      flagChanges([updated]);
      setOps((prev) => prev.map((x) => (x.id === opId ? updated : x)));
      return updated.settlement_status;
    } catch (_) {
      return "unsettled";
    }
  }

  async function loadMeters(aid: string, metered: boolean) {
    if (!metered) { setMeters([]); setScheduleNote(""); return; }
    try {
      const sch = plain(await withRetry(() => getSchedule(aid)));
      const ents: any[] = Array.isArray(sch.entitlements) ? sch.entitlements : [];
      const rows: Meter[] = await Promise.all(ents.map(async (e: any) => {
        let paid = 0;
        try { paid = Number(plain(await withRetry(() => getEntitlementPaid(aid, String(e.id))))); } catch (_) { paid = 0; }
        return {
          id: String(e.id), label: String(e.label ?? ""),
          cap: Number(e.cap), committed: Number(e.committed),
          paid: isNaN(paid) ? 0 : paid, recipient: String(e.recipient ?? ""),
        };
      }));
      setMeters(rows);
      setScheduleNote(String(sch.schedule_reasoning ?? ""));
    } catch (_) {
      setMeters([]);
    }
  }

  function refreshMeters() {
    const ag = agreements.find((a) => a.id === selected);
    if (ag) loadMeters(ag.id, ag.metered);
  }

  function pollOp(opId: string, onResolved: () => void) {
    // poll every 5s for up to ~90s; stop as soon as the settlement leaves "unsettled".
    let tries = 0;
    const maxTries = 18;
    const timer = setInterval(async () => {
      tries += 1;
      const status = await refreshOneOp(opId);
      if (status !== "unsettled" && status !== "unknown") {
        clearInterval(timer);
        refreshMeters();
        onResolved();
      } else if (tries >= maxTries) {
        clearInterval(timer);
      }
    }, 5000);
  }

  async function loadAll() {
    setError("");
    try {
      const agCount = Number(await getAgreementCount());
      const agIds = Array.from({ length: agCount }, (_, i) => String(i + 1));
      const agResults = await Promise.all(agIds.map((id) => getAgreement(id)));
      const ags: Agreement[] = agResults.map((raw) => {
        const a = plain(raw);
        return {
          id: String(a.id), title: String(a.title),
          agreement_text: String(a.agreement_text),
          authorized_sources: String(a.authorized_sources),
          party_a: String(a.party_a), party_b: String(a.party_b),
          metered: a.metered === true,
        };
      });
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

  useEffect(() => {
    const ag = agreements.find((a) => a.id === selected);
    if (ag) loadMeters(ag.id, ag.metered); else { setMeters([]); setScheduleNote(""); }
  }, [selected, agreements]);

  const current = agreements.find((a) => a.id === selected) || null;
  const currentOps = ops.filter((o) => o.agreement_id === selected);
  const me = (address || "").toLowerCase();
  const isParty = !!current && me !== "" && (me === current.party_a.toLowerCase() || me === current.party_b.toLowerCase());

  function collisionTone(o: Operation): string {
    // amber = the prior in a collision pair; cyan = the new colliding op.
    if (!o.linked_prior) return "";
    return "tone-cyan";
  }
  function priorTone(o: Operation): string {
    const priorIds = ops.filter((x) => x.linked_prior && x.linked_prior !== "").map((x) => x.linked_prior);
    return priorIds.includes(o.id) ? "tone-amber" : "";
  }
  function paidClass(status: string): string {
    if (status === "executed" || status === "resolved_executed" || status === "partial_executed") return "foot-v paid";
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
      refreshMeters();
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
      setEscMsg((m) => ({ ...m, [opId]: { kind: "busy", text: "Step 1 of 2: forcing a second consensus pass on the gate. Sign in your wallet…" } }));
      await escalate(opId);
      setEscMsg((m) => ({ ...m, [opId]: { kind: "busy", text: "Step 2 of 2: syncing the new verdict to the ledger. Sign again…" } }));
      await syncFromGate(opId);
      setEscMsg((m) => ({ ...m, [opId]: { kind: "ok", text: "Escalation complete. Refreshing…" } }));
      await loadOps();
      refreshMeters();
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

  async function doVote(opId: string, decision: string) {
    if (!address) { setVoteMsg((m) => ({ ...m, [opId]: { kind: "bad", text: "Connect a wallet first." } })); return; }
    setVoting(opId);
    setVoteMsg((m) => ({ ...m, [opId]: { kind: "busy", text: "Recording your " + decision + " vote on the ledger…" } }));
    try {
      await partyApprove(opId, decision);
      setVoteMsg((m) => ({ ...m, [opId]: { kind: "ok", text: "Vote recorded. Refreshing…" } }));
      await refreshOneOp(opId);
      refreshMeters();
    } catch (e: any) {
      if (e?.pending) {
        setVoteMsg((m) => ({ ...m, [opId]: { kind: "busy", text: "Submitted on-chain, finalizing… this updates automatically." } }));
        setTimeout(() => { refreshOneOp(opId); refreshMeters(); }, 8000);
      } else {
        setVoteMsg((m) => ({ ...m, [opId]: { kind: "bad", text: "Failed: " + String(e?.message || e) } }));
      }
    } finally {
      setVoting("");
    }
  }

  function pct(n: number, cap: number): string {
    if (cap <= 0) return "0%";
    return Math.max(0, Math.min(100, (n / cap) * 100)) + "%";
  }

  return (
    <div className="page desk-page">
      <Nav showWallet={true} />
      <div className="content desk-content">
        {error && <div className="err">Error: {error}</div>}
        {agLoading && !error && (
          <div className="grid">
            <div className="panel">
              <div className="skel-panel">
                <div className="skel skel-line w30" />
                <div className="skel skel-line w90" />
                <div className="skel skel-line w70" />
              </div>
            </div>
            <div className="detail">
              <div className="skel skel-line w50" style={{ height: 20 }} />
              <div className="skel skel-bar" style={{ height: 120, marginTop: 16, marginBottom: 20 }} />
              <SkeletonOps count={2} />
            </div>
          </div>
        )}

        {!agLoading && !error && (
          <div className="grid">
            <div className="panel">
              <div className="list-head">Agreements</div>
              {agreements.map((a) => (
                <div key={a.id} className={"ag-item" + (a.id === selected ? " active" : "")} onClick={() => { setSelected(a.id); setShowForm(false); }}>
                  <div className="ag-id">AGREEMENT {a.id}{a.metered ? " · METERED" : ""}</div>
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
                    <span className="detail-sub">AGREEMENT {current.id} · TEXT LOCKED ON-CHAIN{current.metered ? " · METERED" : ""}</span>
                  </div>
                  <div className="ag-text">{current.agreement_text}</div>
                  <div className="meta-row">
                    <div><div className="meta-k">Party A</div><div className="meta-v">{short(current.party_a)}</div></div>
                    <div><div className="meta-k">Party B</div><div className="meta-v">{short(current.party_b)}</div></div>
                    <div><div className="meta-k">Authorized source</div><div className="meta-v">{short(current.authorized_sources)}</div></div>
                  </div>

                  {current.metered && (
                    <div className="meters">
                      <div className="meters-head">
                        Entitlement meters
                        <span className="meters-sub">Caps verified against the locked text by consensus. Solid is paid, hatched is reserved.</span>
                      </div>
                      {meters.length === 0 && (
                        <div className="skel-panel" style={{ padding: 0 }}>
                          <div className="skel skel-line w50" />
                          <div className="skel skel-line w90" />
                          <div className="skel skel-line w70" />
                        </div>
                      )}
                      {meters.map((m) => (
                        <div key={m.id} className="meter">
                          <div className="meter-top">
                            <span className="meter-id">{m.id}</span>
                            <span className="meter-label">{m.label}</span>
                            <span className="meter-nums">paid {m.paid} · reserved {m.committed} · cap {m.cap} GEN</span>
                          </div>
                          <div className="meter-bar">
                            <div className="meter-committed" style={{ width: pct(m.committed, m.cap) }} />
                            <div className="meter-paid" style={{ width: pct(m.paid, m.cap) }} />
                          </div>
                          <div className="meter-foot">
                            remaining {Math.max(0, m.cap - m.committed)} GEN{m.recipient ? " · locked to " + short(m.recipient) : ""}
                          </div>
                        </div>
                      ))}
                      {scheduleNote && <div className="meters-note"><b>Schedule verdict:</b> {scheduleNote}</div>}
                    </div>
                  )}

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
                      metered={current.metered}
                      onDone={() => { loadOps().then(() => refreshMeters()); }}
                    />
                  )}

                  {opsLoading && currentOps.length === 0 && <SkeletonOps count={3} />}
                  {!opsLoading && currentOps.length === 0 && (
                    <div className="ops-empty">
                      <div className="ops-empty-title">No operations yet</div>
                      <div className="ops-empty-text">
                        Submit a payout under this agreement. The gate maps it to the entitlement it discharges{current.metered ? " and meters the amount against the schedule" : ""} before anything can settle.
                      </div>
                      {!showForm && <button className="act-btn" onClick={() => setShowForm(true)}>+ Submit the first operation</button>}
                    </div>
                  )}

                  {currentOps.map((o) => {
                    const meta = stateMeta(o.state);
                    const sm = settleMsg[o.id];
                    const em = escMsg[o.id];
                    const vm = voteMsg[o.id];
                    const canSettle = o.settlement_status === "unsettled";
                    const isHeld = o.settlement_status === "held";
                    const canEscalate = isHeld && (o.state === "POSSIBLE_DUPLICATE" || o.state === "AMBIGUOUS");
                    const residualHeld = o.settlement_status === "partial_executed" && o.residual_status === "held";
                    const finalHeld = o.settlement_status === "held_final";
                    const needsParties = residualHeld || finalHeld;
                    const isOpen = !!expanded[o.id];
                    const tone = collisionTone(o) || priorTone(o);
                    const hasWhy = !!(o.reasoning || o.minority_note);
                    const payNum = Number(o.payable) || 0;
                    const resNum = Number(o.residual) || 0;
                    const showSplit = o.metered && (payNum > 0 || resNum > 0);
                    return (
                      <div key={o.id} className={"op v2 " + tone + (justSettled[o.id] ? " just-settled" : "")} style={{ ["--st" as any]: meta.color, ["--st-dim" as any]: meta.dim }}>
                        {justSettled[o.id] && <div className={"settle-stamp " + stampFor(o).tone}>{stampFor(o).text}</div>}
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
                          {(o.entitlement || o.entitlement_id) && (
                            <div className="op-ent">
                              {o.entitlement_id && <span className="ent-chip">{o.entitlement_id}</span>}
                              {o.entitlement}
                            </div>
                          )}

                          {showSplit && (
                            <div className="split">
                              <div className="split-bar">
                                {payNum > 0 && <div className="split-pay" style={{ flexGrow: payNum }}>{payNum} paid</div>}
                                {resNum > 0 && <div className="split-res" style={{ flexGrow: resNum }}>{resNum} held</div>}
                              </div>
                              {o.committed_before !== "" && (
                                <div className="split-cap">entitlement already reserved before this op: {o.committed_before} GEN</div>
                              )}
                            </div>
                          )}

                          <div className="op-foot">
                            {o.metered ? (
                              <>
                                <div>
                                  <div className="foot-k">Stated amount</div>
                                  <div className="foot-v">
                                    {o.amount} GEN
                                    {o.amount_mode && <span className="mode-chip">{o.amount_mode}</span>}
                                  </div>
                                </div>
                                {o.amount_mode === "cumulative" && o.requested !== "" && (
                                  <div><div className="foot-k">Counts as new</div><div className="foot-v">{o.requested} GEN</div></div>
                                )}
                                <div><div className="foot-k">Payable</div><div className="foot-v">{o.payable || "0"} GEN</div></div>
                                {resNum > 0 && <div><div className="foot-k">Held residual</div><div className="foot-v">{o.residual} GEN</div></div>}
                              </>
                            ) : (
                              <div><div className="foot-k">Amount</div><div className="foot-v">{o.amount} GEN</div></div>
                            )}
                            <div><div className="foot-k">Recipient</div><div className="foot-v">{short(o.recipient)}</div></div>
                            {o.linked_prior && <div><div className="foot-k">Linked prior</div><div className="foot-v">Operation {o.linked_prior}</div></div>}
                            <div><div className="foot-k">Settlement</div><div className={paidClass(o.settlement_status)}>{settlementText(o.settlement_status, o.residual_status)}</div></div>
                          </div>

                          {hasWhy && (
                            <button className="why-toggle" onClick={() => setExpanded((m) => ({ ...m, [o.id]: !m[o.id] }))}>
                              {isOpen ? "Hide reasoning ▲" : "Why this verdict ▼"}
                            </button>
                          )}
                          {hasWhy && isOpen && (
                            <div className="op-why">
                              {o.reasoning && <div className="op-reason">{o.reasoning}</div>}
                              {o.minority_note && <div className="op-minority"><b>Minority view:</b> {o.minority_note}</div>}
                              {o.settlement_note && o.metered && <div className="op-minority"><b>Ledger:</b> {o.settlement_note}</div>}
                            </div>
                          )}

                          {needsParties && (
                            <div className="vote-row">
                              {isParty ? (
                                <>
                                  <button className="settle-btn" onClick={() => doVote(o.id, "execute")} disabled={voting === o.id}>
                                    {residualHeld ? "Release residual" : "Approve execution"}
                                  </button>
                                  <button className="settle-btn" onClick={() => doVote(o.id, "reject")} disabled={voting === o.id}>
                                    {residualHeld ? "Refuse residual" : "Reject"}
                                  </button>
                                </>
                              ) : (
                                <span className="vote-note">Awaiting joint release by the two named agreement parties. No owner override.</span>
                              )}
                              {vm && <span className={"settle-msg " + vm.kind}>{vm.text}</span>}
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
