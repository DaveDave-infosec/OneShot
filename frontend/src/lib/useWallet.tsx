import { createContext, useContext, useState, useEffect, useCallback } from "react";
import type { ReactNode } from "react";
import {
  setWalletProvider,
  activateMetaMask,
  activateDemo,
  resetBurner,
  normAddr,
} from "./genlayer";

interface WalletCtx {
  address: string | null;
  mode: "metamask" | "demo" | null;
  connectMetaMask: () => Promise<string>;
  useDemo: () => string;
  newDemoWallet: () => string;
  disconnect: () => void;
}

const Ctx = createContext<WalletCtx | null>(null);

export function WalletProvider({ children }: { children: ReactNode }) {
  const [address, setAddress] = useState<string | null>(null);
  const [mode, setMode] = useState<"metamask" | "demo" | null>(null);
  const [providers, setProviders] = useState<any[]>([]);

  useEffect(() => {
    function onAnnounce(event: any) {
      const p = event.detail;
      setProviders((prev) => {
        if (prev.find((x) => x.info.uuid === p.info.uuid)) return prev;
        return [...prev, p];
      });
    }
    window.addEventListener("eip6963:announceProvider", onAnnounce as any);
    window.dispatchEvent(new Event("eip6963:requestProvider"));
    return () =>
      window.removeEventListener("eip6963:announceProvider", onAnnounce as any);
  }, []);

  const connectMetaMask = useCallback(async () => {
    let provider: any = null;
    const mm = providers.find((p) =>
      p.info.name.toLowerCase().includes("metamask")
    );
    provider = mm ? mm.provider : (window as any).ethereum;
    if (!provider) {
      throw new Error(
        "No wallet found. Install MetaMask, or use demo mode to explore."
      );
    }
    setWalletProvider(provider);
    const accounts = await provider.request({ method: "eth_requestAccounts" });
    const addr = normAddr(accounts[0]);
    activateMetaMask(addr);
    setAddress(addr);
    setMode("metamask");
    return addr;
  }, [providers]);

  const useDemo = useCallback(() => {
    const addr = activateDemo();
    setAddress(normAddr(addr));
    setMode("demo");
    return addr;
  }, []);

  const newDemoWallet = useCallback(() => {
    resetBurner();
    const addr = activateDemo();
    setAddress(normAddr(addr));
    setMode("demo");
    return addr;
  }, []);

  const disconnect = useCallback(() => {
    setAddress(null);
    setMode(null);
  }, []);

  return (
    <Ctx.Provider value={{ address, mode, connectMetaMask, useDemo, newDemoWallet, disconnect }}>
      {children}
    </Ctx.Provider>
  );
}

export function useWallet(): WalletCtx {
  const c = useContext(Ctx);
  if (!c) {
    throw new Error("useWallet must be used within WalletProvider");
  }
  return c;
}
