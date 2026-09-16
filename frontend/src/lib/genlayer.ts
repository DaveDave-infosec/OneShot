import { createClient, createAccount, generatePrivateKey } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

export const CHAIN_ID = 61999 as const;

export function normAddr(a: string): string {
  return a.toLowerCase();
}

type Mode = "metamask" | "demo";
let mode: Mode = "demo";
let mmAddress: string | null = null;
let mmProvider: any = null;
let burnerAccount: any = null;

export function setWalletProvider(p: any) {
  mmProvider = p;
}

function applyProvider() {
  if (mmProvider && typeof window !== "undefined") {
    (window as any).ethereum = mmProvider;
  }
}

function getBurner() {
  if (!burnerAccount) {
    let pk = localStorage.getItem("oneshot_burner_pk");
    if (!pk) {
      pk = generatePrivateKey();
      localStorage.setItem("oneshot_burner_pk", pk);
    }
    burnerAccount = createAccount(pk as `0x${string}`);
  }
  return burnerAccount;
}

export function resetBurner() {
  localStorage.removeItem("oneshot_burner_pk");
  burnerAccount = null;
}

export function activateDemo(): string {
  mode = "demo";
  const acct = getBurner();
  return acct.address as string;
}

export function activateMetaMask(address: string) {
  mode = "metamask";
  mmAddress = address;
}

export function currentMode(): Mode {
  return mode;
}

export function currentAddress(): string | null {
  if (mode === "demo") {
    return burnerAccount ? (burnerAccount.address as string) : null;
  }
  return mmAddress;
}

function getReadClient() {
  return createClient({ chain: studionet }) as any;
}

async function getWriteClient() {
  if (mode === "demo") {
    return createClient({ chain: studionet, account: getBurner() }) as any;
  }
  applyProvider();
  const client = createClient({
    chain: studionet,
    account: mmAddress as `0x${string}`,
  }) as any;
  await client.connect("studionet");
  return client;
}

function isBusy(e: any): boolean {
  const m = String(e?.message || e || "").toLowerCase();
  return m.includes("busy") || m.includes("429") || m.includes("rate");
}

function isNetwork(e: any): boolean {
  const m = String(e?.message || e || "").toLowerCase();
  return (
    m.includes("network") ||
    m.includes("fetch") ||
    m.includes("timeout") ||
    m.includes("connection")
  );
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function readContract(params: {
  address: string;
  functionName: string;
  args?: any[];
}): Promise<any> {
  const client = getReadClient();
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      const res = await client.readContract({
        address: params.address as `0x${string}`,
        functionName: params.functionName,
        args: params.args || [],
      });
      return res;
    } catch (e) {
      if (isBusy(e) || isNetwork(e)) {
        await sleep(2000);
        continue;
      }
      throw e;
    }
  }
  throw new Error(
    "The network is busy right now. Please try that again in a moment."
  );
}

export async function writeContract(params: {
  address: string;
  functionName: string;
  args?: any[];
}): Promise<any> {
  const client = await getWriteClient();

  let txHash: any = null;
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      txHash = await client.writeContract({
        address: params.address as `0x${string}`,
        functionName: params.functionName,
        args: params.args || [],
        value: 0n,
      });
      break;
    } catch (e) {
      if (isBusy(e) || isNetwork(e)) {
        await sleep(2000);
        continue;
      }
      throw e;
    }
  }
  if (!txHash) {
    throw new Error(
      "Could not submit the transaction. The network may be busy; please try again."
    );
  }

  for (let attempt = 0; attempt < 75; attempt++) {
    try {
      const receipt = await client.waitForTransactionReceipt({
        hash: txHash,
        status: "FINALIZED",
        interval: 4000,
        retries: 3,
      });
      return receipt;
    } catch (e) {
      if (isBusy(e) || isNetwork(e)) {
        await sleep(4000);
        continue;
      }
      // a timeout waiting for FINALIZED is not a failure — the tx is on-chain
      // and still finalizing. Signal it distinctly so the UI can say so.
      const msg = String((e as any)?.message || e).toLowerCase();
      if (msg.includes("finalized") || msg.includes("timed out") || msg.includes("timeout")) {
        const pending: any = new Error("PENDING_FINALIZATION");
        pending.pending = true;
        pending.txHash = txHash;
        throw pending;
      }
      throw e;
    }
  }
  const pending2: any = new Error("PENDING_FINALIZATION");
  pending2.pending = true;
  pending2.txHash = txHash;
  throw pending2;
}
