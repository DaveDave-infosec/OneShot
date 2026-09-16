import { Link, useLocation } from "react-router-dom";
import { useWallet } from "../lib/useWallet";

function short(a: string | null): string {
  if (!a) return "";
  return a.slice(0, 6) + "…" + a.slice(-4);
}

export function Nav({ showWallet }: { showWallet: boolean }) {
  const loc = useLocation();
  const { address, connectMetaMask, useDemo, disconnect } = useWallet();
  const onDesk = loc.pathname.startsWith("/desk");

  return (
    <div className="nav">
      <div className="nav-inner">
        <Link to="/" className="nav-brand">
          OneShot<span className="dot">.</span>
        </Link>
        <div className="nav-links">
          <Link to="/#how" className="nav-link">How it works</Link>
          <Link to="/desk" className={"nav-link" + (onDesk ? " active" : "")}>Desk</Link>
          <a href="https://github.com/DaveDave-infosec" target="_blank" rel="noreferrer" className="nav-link">Docs</a>
          {!showWallet && (
            <Link to="/desk" className="nav-cta">Launch Desk →</Link>
          )}
          {showWallet && (
            <div className="nav-wallet">
              <span className="live">● studionet</span>
              {address ? (
                <>
                  <span className="wallet-addr">{short(address)}</span>
                  <button className="btn ghost small" onClick={() => disconnect()}>Disconnect</button>
                </>
              ) : (
                <>
                  <button className="btn ghost small" onClick={() => useDemo()}>Demo</button>
                  <button className="btn small" onClick={() => connectMetaMask().catch((e) => alert(String(e?.message || e)))}>Connect</button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
