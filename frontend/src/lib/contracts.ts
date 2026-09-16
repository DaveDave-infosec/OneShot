import { readContract, writeContract } from "./genlayer";

export const GATE_ADDRESS = "0x48206589c69d61220A73D20374B1A10e0c92aD9d";
export const LEDGER_ADDRESS = "0xdc350cdE0F632Df308B5dbA21833C7B76F3FA3C5";

// ---- gate reads ----
export async function getAgreement(agreementId: string) {
  return readContract({
    address: GATE_ADDRESS,
    functionName: "get_agreement",
    args: [agreementId],
  });
}

export async function getOperation(opId: string) {
  return readContract({
    address: GATE_ADDRESS,
    functionName: "get_operation",
    args: [opId],
  });
}

export async function getAgreementCount() {
  return readContract({
    address: GATE_ADDRESS,
    functionName: "get_agreement_count",
    args: [],
  });
}

export async function getOperationCount() {
  return readContract({
    address: GATE_ADDRESS,
    functionName: "get_operation_count",
    args: [],
  });
}

// ---- gate writes ----
export async function registerAgreement(
  title: string,
  agreementText: string,
  authorizedSources: string,
  partyA: string,
  partyB: string
) {
  return writeContract({
    address: GATE_ADDRESS,
    functionName: "register_agreement",
    args: [title, agreementText, authorizedSources, partyA, partyB],
  });
}

export async function submitOperation(
  agreementId: string,
  source: string,
  recipient: string,
  asset: string,
  amount: string,
  actionFamily: string,
  obligationRef: string,
  incidentId: string,
  economicPurpose: string,
  entitlementHint: string
) {
  return writeContract({
    address: GATE_ADDRESS,
    functionName: "submit_operation",
    args: [
      agreementId,
      source,
      recipient,
      asset,
      amount,
      actionFamily,
      obligationRef,
      incidentId,
      economicPurpose,
      entitlementHint,
    ],
  });
}

export async function escalate(opId: string) {
  return writeContract({
    address: GATE_ADDRESS,
    functionName: "escalate",
    args: [opId],
  });
}

// ---- ledger reads ----
export async function getSettlement(opId: string) {
  return readContract({
    address: LEDGER_ADDRESS,
    functionName: "get_settlement",
    args: [opId],
  });
}

export async function balanceOf(account: string) {
  return readContract({
    address: LEDGER_ADDRESS,
    functionName: "balance_of",
    args: [account],
  });
}

// ---- ledger writes ----
export async function settleOperation(opId: string) {
  return writeContract({
    address: LEDGER_ADDRESS,
    functionName: "settle_operation",
    args: [opId],
  });
}

export async function syncFromGate(opId: string) {
  return writeContract({
    address: LEDGER_ADDRESS,
    functionName: "sync_from_gate",
    args: [opId],
  });
}

export async function partyApprove(opId: string, decision: string) {
  return writeContract({
    address: LEDGER_ADDRESS,
    functionName: "party_approve",
    args: [opId, decision],
  });
}
