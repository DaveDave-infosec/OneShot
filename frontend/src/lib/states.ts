export interface StateMeta {
  color: string;
  dim: string;
  label: string;
  blurb: string;
}

const META: Record<string, StateMeta> = {
  CLEAR_NEW: {
    color: "#6FBF8E",
    dim: "#16281E",
    label: "Clear / New",
    blurb: "No prior shares this obligation and recipient. Cleared in code, no consensus.",
  },
  POSSIBLE_DUPLICATE: {
    color: "#E0B24A",
    dim: "#2A2210",
    label: "Possible duplicate",
    blurb: "A credible collision with a prior operation. Held visibly, recoverable.",
  },
  AMBIGUOUS: {
    color: "#C79A5E",
    dim: "#271F12",
    label: "Ambiguous",
    blurb: "The agreement wording does not resolve this safely. Held, not guessed.",
  },
  CONFIRMED_DUPLICATE: {
    color: "#E58C6E",
    dim: "#2A1712",
    label: "Confirmed duplicate",
    blurb: "Discharges an entitlement a prior operation already satisfied. Not executed.",
  },
  CONFIRMED_NEW: {
    color: "#6FC7B0",
    dim: "#132622",
    label: "Confirmed new",
    blurb: "Discharges a genuinely distinct entitlement. Released for settlement.",
  },
  REPLACEMENT: {
    color: "#A99AC7",
    dim: "#201C2A",
    label: "Replacement",
    blurb: "Supersedes a still-pending prior operation. Replaces, does not double.",
  },
  HELD_FINAL: {
    color: "#C79A5E",
    dim: "#271F12",
    label: "Final hold",
    blurb: "Consensus could not resolve even when forced. Resolvable only by the two named parties.",
  },
};

export function stateMeta(state: string): StateMeta {
  return (
    META[state] || {
      color: "#8A8474",
      dim: "#1E1D18",
      label: state || "unsettled",
      blurb: "",
    }
  );
}

export function settlementLabel(status: string): string {
  const m: Record<string, string> = {
    executed: "Executed · paid",
    satisfied_by_prior: "Satisfied by prior · not paid",
    held: "Held · awaiting escalation",
    held_final: "Final hold · awaiting the two parties",
    superseded: "Superseded by a replacement",
    resolved_executed: "Resolved · paid by joint release",
    resolved_rejected: "Resolved · rejected by joint release",
    unsettled: "Not yet settled",
  };
  return m[status] || status || "Not yet settled";
}
