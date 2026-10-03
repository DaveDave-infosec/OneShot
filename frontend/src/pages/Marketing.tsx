import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Nav } from "../components/Nav";
import "../styles.css";
import { GATE_ADDRESS, LEDGER_ADDRESS } from "../lib/contracts";

export function Marketing() {
  const pairRef = useRef<HTMLDivElement | null>(null);
  const [play, setPlay] = useState(false);

  // Play the collision sequence once, when the pair scrolls into view.
  useEffect(() => {
    const el = pairRef.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") { setPlay(true); return; }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { setPlay(true); io.disconnect(); }
      });
    }, { threshold: 0.45 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Reveal sections as they scroll in. Elements are hidden only after this runs,
  // and lose the hidden state the moment they are revealed.
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>(".reveal"));
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          const t = e.target as HTMLElement;
          t.classList.remove("pending");
          t.classList.add("in");
          io.unobserve(t);
        }
      });
    }, { threshold: 0.15 });
    els.forEach((el) => { el.classList.add("pending"); io.observe(el); });
    return () => io.disconnect();
  }, []);

  return (
    <div className="page">
      <div className="hero-band">
        <Nav showWallet={false} />
        <div className="wrap">
          <div className="hero-copy">
            <div className="hero-mask" />
            <div className="hero-inner">
              <div className="hero-eyebrow">Semantic collision detection</div>
              <h1 className="hero-h">Two messages.<br />One payment.<br />Paid <span className="em">once.</span></h1>
              <p className="hero-sub">A nonce sees bytes. OneShot reads the agreement and maps both messages to the entitlement they discharge, before the money leaves twice.</p>
              <div className="hero-cta">
                <Link to="/desk" className="nav-cta big">Launch Desk →</Link>
              </div>
            </div>
          </div>
        </div>
        <a href="#collision" className="scroll-cue">
          <span>See it catch one</span>
          <span className="chev">↓</span>
        </a>
      </div>

      {/* the M2 collision, caught. Static data, animated once on scroll. No wallet, no chain. */}
      <section className="mkt-section" id="collision">
        <div className="mkt-wrap">
          <div className="reveal">
            <div className="mkt-eyebrow">The collision, caught</div>
            <h2 className="mkt-h2">Two differently worded payouts. Same entitlement.</h2>
            <p className="mkt-lead">Both operations pay the same recipient under the same obligation. Their words differ, the money does not. OneShot maps each to the entitlement it discharges, and stops the second before it settles.</p>
          </div>

          <div ref={pairRef} className={"demo-pair anim" + (play ? " play" : "")}>
            <div className="demo-op id-a">
              <div className="demo-head">
                <span className="tone-tag amber">message A</span>
                <span className="demo-stamp ok">Paid</span>
              </div>
              <div className="demo-body">
                <div className="demo-fam">completion_payment · M2</div>
                <div className="demo-ent">Pay the M2 completion fee</div>
                <div className="demo-reason">The first payout against M2. It discharges the entitlement the agreement grants.</div>
                <div className="demo-foot"><span className="demo-amt">5 GEN</span><span className="demo-paid">paid</span></div>
              </div>
            </div>

            <div className="demo-arrow">→</div>

            <div className="demo-op id-b">
              <div className="demo-head">
                <span className="tone-tag cyan">message B</span>
                <span className="demo-stamp bad">Duplicate · not paid</span>
              </div>
              <div className="demo-body">
                <div className="demo-fam">retention_release · M2</div>
                <div className="demo-ent">Release the retained amount for milestone 2</div>
                <div className="demo-reason">Different words, same entitlement. The agreement defines one M2 fee, so B discharges what A already paid.</div>
                <div className="demo-foot"><span className="demo-amt strike">5 GEN</span><span className="demo-notpaid">not paid</span></div>
              </div>
            </div>
          </div>
          <div className="demo-caption">A nonce sees two different byte strings and waves both through. OneShot reads the agreement and sees one entitlement.</div>
        </div>
      </section>

      {/* how it works */}
      <section className="mkt-section alt" id="how">
        <div className="mkt-wrap">
          <div className="reveal">
            <div className="mkt-eyebrow">How it works</div>
            <h2 className="mkt-h2">Three steps, one honest outcome.</h2>
          </div>
          <div className="how-grid reveal reveal-stagger">
            <div className="how-step">
              <div className="how-num">01</div>
              <div className="how-title">Submit</div>
              <div className="how-text">A source contract submits a payout with a structured envelope (recipient, amount, obligation, purpose) against an agreement whose governing text is locked on-chain.</div>
            </div>
            <div className="how-step">
              <div className="how-num">02</div>
              <div className="how-title">Detect</div>
              <div className="how-text">Structured fields pair candidates in code, free. Only a real collision reaches consensus, which maps each operation to the human-language entitlement it discharges.</div>
            </div>
            <div className="how-step">
              <div className="how-num">03</div>
              <div className="how-title">Settle</div>
              <div className="how-text">A distinct entitlement executes. A duplicate is marked satisfied and never paid. Anything unresolved is held visibly and recoverably, never silently erased.</div>
            </div>
          </div>
        </div>
      </section>

      {/* trust */}
      <section className="mkt-section">
        <div className="mkt-wrap">
          <div className="reveal">
            <div className="mkt-eyebrow">Trust model</div>
            <h2 className="mkt-h2">No privileged operator. Anywhere.</h2>
          </div>
          <div className="trust-grid reveal reveal-stagger">
            <div className="trust-card">
              <div className="trust-title">Permissionless settlement</div>
              <div className="trust-text">Anyone can settle an operation. The state, recipient and amount all come from the gate on-chain, never from the caller. No one can fake a payout and no owner can override a hold.</div>
            </div>
            <div className="trust-card">
              <div className="trust-title">No authority in the lifecycle</div>
              <div className="trust-text">A held operation escalates to a forcing consensus pass, not to a human. Only a genuine deadlock falls to the two named agreement parties, who must both concur. There is no admin key.</div>
            </div>
            <div className="trust-card">
              <div className="trust-title">Locked governing text</div>
              <div className="trust-text">Each agreement's text is stored on-chain at registration and is the authority every verdict is judged against. It cannot be rewritten once operations begin.</div>
            </div>
          </div>
        </div>
      </section>

      {/* footer */}
      <footer className="mkt-footer">
        <div className="mkt-wrap">
          <div className="foot-cta-row reveal">
            <div>
              <div className="foot-brand">OneShot<span className="dot">.</span></div>
              <div className="foot-tag">Every economic intent executes once, or stays visibly unresolved.</div>
            </div>
            <Link to="/desk" className="nav-cta big">Open the Reconciliation Desk →</Link>
          </div>
          <div className="foot-addrs">
            <div className="foot-addr-head">Deployed and verifiable on GenLayer Studio · chainId 61999</div>
            <div className="foot-addr-row">
              <span className="foot-addr-k">Gate</span>
              <span className="foot-addr-v">{GATE_ADDRESS}</span>
            </div>
            <div className="foot-addr-row">
              <span className="foot-addr-k">Ledger</span>
              <span className="foot-addr-v">{LEDGER_ADDRESS}</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
