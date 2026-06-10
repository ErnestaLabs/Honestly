import React, { useEffect, useState, useRef } from "react";

// ---------------------------------------------------------------------------
// Honestly - usehonestly.co.uk funnel (React)
// Single-purpose: route the visitor into @usehonestly_bot. Brand palette and
// wordmark are lifted verbatim from the PDF the bot produces (report.py).
// Adapted from the supplied Sequra template: recoloured to the Honestly
// palette, sections trimmed to a funnel (no pricing, team, or lead form).
// "Honest premium" editorial-luxury treatment: Fraunces display serif, warm
// paper grain, layered shadows, orchestrated load motion, report-style section
// numbering, italic serif accents. Mirrors site/index.html one-for-one.
// Tailwind + iconify-icon expected on the page; brand tokens, fonts, and the
// custom CSS (grain, premium-panel, anim/d*, bar/grow, sec-index, btn-lift,
// reveal-on-scroll, hermes-*) are registered globally (see README).
// No em dashes anywhere - hyphens only.
// ---------------------------------------------------------------------------

const BOT_URL = "https://t.me/usehonestly_bot";

// Scroll-reveal hook (kept from the template). Adds .animate-in when an element
// with .reveal-on-scroll enters the viewport. Respects prefers-reduced-motion.
function useScrollReveal() {
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const els = document.querySelectorAll(".reveal-on-scroll");
    if (reduce) {
      els.forEach((el) => el.classList.add("animate-in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("animate-in");
            obs.unobserve(e.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -50px 0px" }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
}

// Small wrapper so JSX stays readable for the iconify web component.
function Icon({ icon, className = "" }) {
  return <iconify-icon icon={icon} class={className}></iconify-icon>;
}

function Nav() {
  return (
    <header className="w-full fixed top-0 z-50 glass-panel">
      <nav className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-6 py-4 sm:px-8 lg:px-12">
        <a href="#" className="font-logo shrink-0 text-2xl font-medium tracking-tight text-dark">
          Honestly
        </a>
        <div className="hidden items-center gap-8 sm:flex">
          <a href="#problem" className="text-sm font-medium text-muted transition hover:text-dark">
            The problem
          </a>
          <a href="#how" className="text-sm font-medium text-muted transition hover:text-dark">
            How it works
          </a>
        </div>
        <a
          href={BOT_URL}
          className="btn-lift inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-dark px-5 text-sm font-semibold text-cream shadow-cta hover:bg-green"
        >
          <Icon icon="ic:baseline-telegram" className="text-lg" />
          Open in Telegram
        </a>
      </nav>
    </header>
  );
}

// The centrepiece: a mock of the bot's own output. Sample data only - we never
// imply a real valuation. The glass-box chain is reproduced exactly as the bot
// shows it: sold median -> condition-adjusted -> live market % = central.
// Comparable bars grow in on load via the shared `grow` keyframe (staggered).
function ValuationCard() {
  const bars = [
    { h: "42%", muted: true, delay: "0.5s", peak: false },
    { h: "55%", muted: true, delay: "0.6s", peak: false },
    { h: "72%", muted: false, delay: "0.7s", peak: true },
    { h: "48%", muted: true, delay: "0.8s", peak: false },
    { h: "80%", muted: false, delay: "0.9s", peak: true },
  ];
  return (
    <div className="anim d4 relative flex items-center justify-center lg:justify-end">
      <div className="float-slow absolute -right-8 -top-10 h-44 w-44 rounded-full bg-terra/12 blur-3xl"></div>
      <div className="float-slow absolute -bottom-10 -left-6 h-52 w-52 rounded-full bg-green/15 blur-3xl"></div>
      <div className="premium-panel group relative w-full max-w-md overflow-hidden rounded-3xl p-6">
        <div className="absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r from-green via-green to-terra"></div>

        <div className="mb-6 flex items-center justify-between border-b border-line pb-4 pt-1.5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-green text-cream shadow-inner">
              <Icon icon="solar:home-smile-bold" className="text-xl" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight text-dark">24 Wolves Lane, London N22</div>
              <div className="text-xs font-medium text-muted">Sample appraisal - vendor view</div>
            </div>
          </div>
          <span className="rounded-full bg-terra/15 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-terra">
            Sample
          </span>
        </div>

        <div className="mb-6">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-green">Central value</div>
          <div className="font-display text-[3.25rem] leading-none tracking-tight text-dark" style={{ fontVariantNumeric: "tabular-nums" }}>
            £640,000
          </div>
          <div className="mt-2.5 text-sm font-medium text-muted" style={{ fontVariantNumeric: "tabular-nums" }}>
            Assessed range £615,000 to £660,000
          </div>
        </div>

        {/* Glass-box chain */}
        <div className="mb-6 rounded-2xl border border-green/20 bg-pale p-4">
          <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-green">
            <Icon icon="solar:magnifer-zoom-in-bold" /> How we got here
          </div>
          <div className="text-sm font-medium leading-relaxed text-ink" style={{ fontVariantNumeric: "tabular-nums" }}>
            sold median £625,000 <span className="text-terra">-&gt;</span> condition-adjusted £631,000{" "}
            <span className="text-terra">-&gt;</span> live market <span className="font-semibold text-green">+1.4%</span>{" "}
            <span className="text-terra">=</span> <span className="font-semibold text-dark">£640,000</span>
          </div>
        </div>

        {/* Mini comparables chart: green = subject/central, sand = muted comps */}
        <div className="relative flex h-32 w-full items-end justify-between gap-2 border-b border-l border-line pb-2 pl-2">
          <div className="absolute left-2 right-0 top-0 h-px bg-line"></div>
          <div className="absolute left-2 right-0 top-1/2 h-px -translate-y-1/2 bg-line"></div>
          {bars.map((b, i) => (
            <div
              key={i}
              className={`bar ${b.muted ? "data-bar-muted" : "data-bar"} relative w-1/6 rounded-t-md`}
              style={{ height: b.h, animation: `grow 0.9s cubic-bezier(0.16,1,0.3,1) ${b.delay} forwards` }}
            >
              {b.peak && <div className="absolute -top-3 left-1/2 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-terra"></div>}
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between text-[11px] font-medium text-muted">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-green"></span> comparable
          </span>
          <span>5 sold comparables - each links to its record</span>
        </div>
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="pb-16 pt-10 lg:pb-28 lg:pt-16">
      <div className="mx-auto max-w-7xl px-6 sm:px-8 lg:px-12">
        <div className="grid items-center gap-14 lg:grid-cols-[1.05fr_0.95fr] xl:gap-20">
          {/* Copy */}
          <div className="flex flex-col justify-center">
            <div className="anim d1 mb-7 inline-flex w-fit items-center gap-2 rounded-full border border-green/25 bg-pale px-3.5 py-1.5">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green/60"></span>
                <span className="relative inline-flex h-2 w-2 rounded-full bg-green"></span>
              </span>
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-green">
                UK property valuation, on Telegram
              </span>
            </div>

            <h1 className="anim d2 font-display text-[3.25rem] font-normal leading-[0.96] tracking-tight text-dark sm:text-6xl lg:text-[4.75rem]">
              Know what it is really worth. <span className="italic text-green">And why.</span>
            </h1>

            <div className="anim d3 mt-8 h-1 w-20 rounded-full terra-rule"></div>

            <p className="anim d3 mt-7 max-w-xl text-lg font-medium leading-relaxed text-ink/90">
              Built from real HM Land Registry sold prices, adjusted for condition and steered by today's market - with
              every figure and the exact sums shown. Free on Telegram, whether you are buying, selling, or an agent.
            </p>

            <div className="anim d4 mt-9 flex flex-col gap-4 sm:flex-row sm:items-center">
              <a
                href={BOT_URL}
                className="btn-lift group inline-flex h-14 items-center justify-center gap-3 rounded-2xl bg-green px-8 text-base font-semibold text-cream shadow-cta hover:bg-dark"
              >
                <Icon icon="ic:baseline-telegram" className="text-2xl" />
                Get your free valuation
                <Icon icon="solar:arrow-right-linear" className="arrow text-xl" />
              </a>
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-terra">
                <Icon icon="solar:gift-linear" className="text-base" />
                First one free. No account, no card.
              </span>
            </div>

            {/* Trust row */}
            <div className="anim d5 mt-12 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="flex items-center gap-2.5 rounded-xl border border-line bg-white/55 px-3.5 py-3 shadow-sm">
                <Icon icon="solar:document-text-bold" className="text-xl text-green" />
                <span className="text-sm font-medium text-ink">Land Registry evidence</span>
              </div>
              <div className="flex items-center gap-2.5 rounded-xl border border-line bg-white/55 px-3.5 py-3 shadow-sm">
                <Icon icon="solar:eye-scan-bold" className="text-xl text-green" />
                <span className="text-sm font-medium text-ink">The glass-box method</span>
              </div>
              <div className="flex items-center gap-2.5 rounded-xl border border-line bg-white/55 px-3.5 py-3 shadow-sm">
                <Icon icon="solar:soundwave-bold" className="text-xl text-green" />
                <span className="text-sm font-medium text-ink">PDF + audio walkthrough</span>
              </div>
            </div>
          </div>

          {/* The product, shown */}
          <ValuationCard />
        </div>
      </div>
    </section>
  );
}

function Pain() {
  const pains = [
    {
      icon: "solar:tag-price-bold",
      tag: "If you are selling",
      title: "The highest number wins the instruction",
      body: "Agents pitch a price to land your listing. That is sales talk, not a value you can defend to a buyer or a lender.",
      reveal: "rd-1",
    },
    {
      icon: "solar:home-search-bold",
      tag: "If you are buying",
      title: "The asking price is just a hope",
      body: "It is what the seller wishes for. Nothing shows you what the house next door actually sold for, so it is easy to overpay.",
      reveal: "rd-2",
    },
    {
      icon: "solar:lock-keyhole-bold",
      tag: "If you are an agent",
      title: "The evidence tools are locked away",
      body: "Hometrack, Sprift, Acaboom - the data that wins and defends instructions, gated behind a pro account and hundreds of pounds a month.",
      reveal: "rd-3",
    },
  ];
  return (
    <section id="problem" className="border-y border-line bg-dark py-18 lg:py-28">
      <div className="mx-auto max-w-7xl px-6 sm:px-8 lg:px-12">
        <div className="mx-auto max-w-2xl text-center reveal-on-scroll">
          <div className="mb-3 flex items-center justify-center gap-3">
            <span className="sec-index text-base text-terra">01</span>
            <span className="h-px w-8 bg-terra/40"></span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-terra">The problem</span>
          </div>
          <h2 className="font-display text-4xl font-normal leading-tight tracking-tight text-cream sm:text-5xl">
            Everyone gives you a price. <span className="italic text-terra">Nobody proves it.</span>
          </h2>
        </div>
        <div className="mt-14 grid gap-6 md:grid-cols-3">
          {pains.map((p) => (
            <div
              key={p.title}
              className={`reveal-on-scroll ${p.reveal} rounded-3xl border border-white/10 bg-white/[0.04] p-7 transition hover:bg-white/[0.07]`}
            >
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-terra/15">
                <Icon icon={p.icon} className="text-2xl text-terra" />
              </div>
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-terra">{p.tag}</div>
              <h3 className="font-display text-xl font-medium tracking-tight text-cream">{p.title}</h3>
              <p className="mt-2.5 text-sm font-medium leading-relaxed text-cream/60">{p.body}</p>
            </div>
          ))}
        </div>
        <p className="mx-auto mt-12 max-w-xl text-center font-display text-2xl font-normal italic leading-snug text-cream reveal-on-scroll">
          Whichever side of the deal you are on, you are left guessing.{" "}
          <span className="text-terra">Honestly fixes that.</span>
        </p>
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    {
      n: "1",
      icon: "solar:map-point-bold",
      title: "Send an address",
      body: "Any UK address or postcode in the chat.",
      reveal: "rd-1",
    },
    {
      n: "2",
      icon: "solar:users-group-rounded-bold",
      title: "Pick who you are",
      body: "Vendor, buyer, or agent - the number is the same, the framing fits you.",
      reveal: "rd-2",
    },
    {
      n: "3",
      icon: "solar:document-add-bold",
      title: "Get the valuation",
      body: "Range, central value, the evidence, and a full PDF report.",
      reveal: "rd-3",
    },
  ];
  return (
    <section id="how" className="bg-pale/50 py-18 lg:py-28">
      <div className="mx-auto max-w-7xl px-6 sm:px-8 lg:px-12">
        <div className="mx-auto max-w-2xl text-center reveal-on-scroll">
          <div className="mb-3 flex items-center justify-center gap-3">
            <span className="sec-index text-base text-green">02</span>
            <span className="h-px w-8 bg-green/40"></span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-green">How it works</span>
          </div>
          <h2 className="font-display text-4xl font-normal leading-tight tracking-tight text-dark sm:text-5xl">
            Three taps to an honest number.
          </h2>
        </div>
        <div className="relative mt-16 grid gap-10 md:grid-cols-3">
          <div className="absolute left-[16%] right-[16%] top-10 hidden h-0.5 bg-gradient-to-r from-green via-terra to-green md:block"></div>
          {steps.map((s) => (
            <div key={s.title} className={`relative flex flex-col items-center text-center reveal-on-scroll ${s.reveal}`}>
              <div className="relative z-10 mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-green text-cream shadow-[0_16px_34px_rgba(31,111,92,0.35)]">
                <span className="sec-index absolute -right-1 -top-1 flex h-7 w-7 items-center justify-center rounded-full border border-line bg-cream text-sm text-green shadow-sm">
                  {s.n}
                </span>
                <Icon icon={s.icon} className="text-3xl" />
              </div>
              <h3 className="font-display text-xl font-medium tracking-tight text-dark">{s.title}</h3>
              <p className="mt-2 max-w-xs text-sm font-medium text-muted">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCTA() {
  return (
    <section className="px-6 py-16 sm:px-8 lg:px-12 lg:py-28">
      <div className="relative mx-auto max-w-5xl overflow-hidden rounded-[2rem] bg-dark px-6 py-18 text-center shadow-[0_40px_90px_rgba(20,63,51,0.40)] lg:px-16 lg:py-20 reveal-on-scroll">
        <div className="pointer-events-none absolute -right-12 -top-12 h-56 w-56 rounded-full bg-green/30 blur-3xl"></div>
        <div className="pointer-events-none absolute -bottom-16 -left-10 h-64 w-64 rounded-full bg-terra/20 blur-3xl"></div>
        <div className="relative">
          <Icon icon="solar:shield-check-bold" className="mb-5 text-4xl text-green" />
          <h2 className="mx-auto max-w-2xl font-display text-4xl font-normal leading-[1.05] tracking-tight text-cream sm:text-5xl">
            Stop guessing. <span className="italic text-green">See the evidence.</span>
          </h2>
          <p className="mx-auto mt-5 max-w-lg text-base font-medium text-cream/70">
            One address in, one defensible value out: sold evidence, steered by the live market. No black box, no
            flattery. Your first valuation is free.
          </p>
          <a
            href={BOT_URL}
            className="btn-lift group mt-9 inline-flex h-14 items-center justify-center gap-3 rounded-2xl bg-cream px-8 text-base font-semibold text-dark shadow-lg hover:bg-white"
          >
            <Icon icon="ic:baseline-telegram" className="text-2xl text-green" />
            Start free on Telegram
            <Icon icon="solar:arrow-right-linear" className="arrow text-xl" />
          </a>
        </div>
      </div>
    </section>
  );
}

// base64url so the bot can decode a single ?start= payload: v1|audience|address
function b64url(s) {
  const b = btoa(unescape(encodeURIComponent(s)));
  return b.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// Front of house only. The widget never computes a value (the engine owns the
// number); it captures intent and hands off to the bot via a ?start= payload.
function ValuationWidget() {
  const [open, setOpen] = useState(false);
  const [audience, setAudience] = useState("vendor");
  const [address, setAddress] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    if (open && inputRef.current) {
      const t = setTimeout(() => inputRef.current.focus(), 120);
      return () => clearTimeout(t);
    }
  }, [open]);

  function buildLink() {
    let payload = b64url(`v1|${audience}|${address.trim()}`);
    // Telegram caps the start param at 64 chars; fall back to audience-only.
    if (payload.length > 64) payload = b64url(`v1|${audience}|`);
    return `${BOT_URL}?start=${payload}`;
  }

  const audiences = ["vendor", "buyer", "agent"];

  return (
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col items-end gap-3 sm:bottom-6 sm:right-6">
      {/* Panel */}
      <div
        className={`hermes-panel w-[calc(100vw-2.5rem)] max-w-sm overflow-hidden rounded-3xl border border-line bg-cream shadow-[0_30px_70px_rgba(20,63,51,0.30)] ${open ? "open" : ""}`}
      >
        <div className="flex items-center gap-3 bg-dark px-5 py-4">
          <div className="relative flex h-10 w-10 items-center justify-center rounded-2xl bg-green text-cream">
            <Icon icon="solar:chat-round-line-bold" className="text-xl" />
            <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-dark bg-terra"></span>
          </div>
          <div className="flex-1">
            <div className="font-logo text-base font-medium tracking-wide text-cream">Honestly</div>
            <div className="text-[11px] font-medium text-cream/60">Evidence-led property valuations</div>
          </div>
          <button aria-label="Close" onClick={() => setOpen(false)} className="text-cream/60 transition hover:text-cream">
            <Icon icon="solar:close-circle-linear" className="text-2xl" />
          </button>
        </div>

        <div className="px-5 py-5">
          <div className="mb-4 rounded-2xl rounded-tl-sm border border-line bg-white px-4 py-3 text-sm font-medium leading-relaxed text-ink">
            Give me an address and tell me who you are. I'll run it through the sold evidence and show you
            exactly how I got there - your first valuation is free.
          </div>

          <label htmlFor="hermes-address" className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.16em] text-green">
            Property address
          </label>
          <input
            id="hermes-address"
            ref={inputRef}
            type="text"
            autoComplete="off"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") window.open(buildLink(), "_blank", "noopener");
            }}
            placeholder="e.g. 24 Wolves Lane, London N22"
            className="mb-4 w-full rounded-xl border border-line bg-white px-4 py-3 text-sm font-medium text-ink outline-none transition placeholder:text-muted/70 focus:border-green focus:ring-2 focus:ring-green/20"
          />

          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-green">I am a</div>
          <div className="mb-5 grid grid-cols-3 gap-2">
            {audiences.map((a) => (
              <button
                key={a}
                type="button"
                aria-pressed={audience === a}
                onClick={() => setAudience(a)}
                className="hermes-chip rounded-lg border border-line bg-white px-2 py-2 text-sm font-semibold capitalize text-ink transition"
              >
                {a}
              </button>
            ))}
          </div>

          <a
            href={buildLink()}
            target="_blank"
            rel="noopener"
            className="btn-lift flex h-12 w-full items-center justify-center gap-2.5 rounded-xl bg-green text-sm font-semibold text-cream shadow-cta hover:bg-dark"
          >
            <Icon icon="ic:baseline-telegram" className="text-xl" />
            Start my free valuation
          </a>
          <p className="mt-3 flex items-center justify-center gap-1.5 text-[11px] font-medium text-muted">
            <Icon icon="solar:lock-keyhole-minimalistic-linear" />
            Runs in Telegram. No account, no card.
          </p>
        </div>
      </div>

      {/* Launcher */}
      {!open && (
        <button
          aria-label="Get a free valuation"
          onClick={() => setOpen(true)}
          className="hermes-launcher group inline-flex h-14 items-center gap-2.5 rounded-full bg-green pl-4 pr-5 text-cream transition hover:bg-dark"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-cream/15">
            <Icon icon="solar:chat-round-line-bold" className="text-xl" />
          </span>
          <span className="text-sm font-semibold">Free valuation</span>
        </button>
      )}
    </div>
  );
}

function Footer() {
  return (
    <footer className="relative z-10 border-t border-line bg-cream pb-8 pt-14">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-6 sm:flex-row sm:px-8 lg:px-12">
        <div className="text-center sm:text-left">
          <a href="#" className="font-logo text-xl font-medium tracking-tight text-dark">
            Honestly
          </a>
          <p className="mt-1 text-xs font-medium text-muted">Anchored in HM Land Registry sold evidence.</p>
        </div>
        <div className="flex items-center gap-6 text-xs font-medium text-muted">
          <a href={BOT_URL} className="transition hover:text-green">
            Telegram
          </a>
          <span>&copy; 2026 Honestly</span>
        </div>
      </div>
    </footer>
  );
}

export default function App() {
  useScrollReveal();
  return (
    <div className="min-h-screen font-sans antialiased text-ink">
      {/* Paper grain - reinforces the appraisal-document feel */}
      <div className="grain" aria-hidden="true"></div>
      <Nav />
      <main className="relative z-10 pt-24">
        <Hero />
        <Pain />
        <HowItWorks />
        <FinalCTA />
      </main>
      <Footer />
      <ValuationWidget />
    </div>
  );
}
