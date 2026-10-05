import { readContract, writeContract } from "./genlayer";

export const GATE_ADDRESS = "0xA01F6Da1D0884ECB31674791146a6bCBa7D93D08";
export const LEDGER_ADDRESS = "0x48D7e7cF2F6E5D36A842352Caf08f12A37e93588";

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

// ---- V2 gate reads (metered agreements) ----
export async function getSchedule(agreementId: string) {
  return readContract({
    address: GATE_ADDRESS,
    functionName: "get_schedule",
    args: [agreementId],
  });
}

export async function getEntitlement(agreementId: string, entitlementId: string) {
  return readContract({
    address: GATE_ADDRESS,
    functionName: "get_entitlement",
    args: [agreementId, entitlementId],
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

export async function registerMeteredAgreement(
  title: string,
  agreementText: string,
  authorizedSources: string,
  partyA: string,
  partyB: string,
  scheduleJson: string
) {
  return writeContract({
    address: GATE_ADDRESS,
    functionName: "register_metered_agreement",
    args: [title, agreementText, authorizedSources, partyA, partyB, scheduleJson],
  });
}

export async function acceptAgreement(agreementId: string, textHash: string) {
  return writeContract({
    address: GATE_ADDRESS,
    functionName: "accept_agreement",
    args: [agreementId, textHash],
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

// ---- ledger reads ----
export async function getEntitlementPaid(agreementId: string, entitlementId: string) {
  return readContract({
    address: LEDGER_ADDRESS,
    functionName: "get_entitlement_paid",
    args: [agreementId, entitlementId],
  });
}

export async function getEscrow(agreementId: string) {
  return readContract({
    address: LEDGER_ADDRESS,
    functionName: "get_escrow",
    args: [agreementId],
  });
}

export async function getSupply() {
  return readContract({
    address: LEDGER_ADDRESS,
    functionName: "get_supply",
    args: [],
  });
}

// ---- ledger writes ----
export async function fundEscrow(agreementId: string, amount: string) {
  return writeContract({
    address: LEDGER_ADDRESS,
    functionName: "fund_escrow",
    args: [agreementId, BigInt(amount)],
  });
}

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
