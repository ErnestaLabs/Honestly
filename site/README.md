# usehonestly.co.uk - funnel

A single-purpose funnel that routes visitors into the Telegram bot
[@usehonestly_bot](https://t.me/usehonestly_bot). Brand palette and the
serif "Honestly" wordmark are taken verbatim from the PDF the bot produces
(`report.py`). Design system: `../../../Downloads/DESIGN.md`.

## Files

- **`index.html`** - the deployable funnel. Zero build: Tailwind Play CDN +
  iconify-icon over a CDN, brand tokens inline. Open it, or drop it on the
  host for `usehonestly.co.uk`. This is what ships.
- **`App.jsx`** - the same funnel as a React component (the supplied template,
  rebranded). Use it if the site moves to a React/Vite/Next build. Needs the
  three setup pieces below.

Both point every call-to-action at `https://t.me/usehonestly_bot`. No pricing,
no team grid, no lead form - the bot handles all of that. No em dashes anywhere.

## Wiring App.jsx into a build

`App.jsx` assumes Tailwind, the brand tokens, the **Fraunces** web font, the
custom component CSS, and the iconify web component are present. Three steps
(the Fraunces `<link>` rides along with step 1). Both files share these styles,
so `App.jsx` is a one-for-one match of `index.html`.

### 1. Brand tokens + Fraunces - `tailwind.config.js`

```js
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#f6f3ec", ink: "#1c1a16", muted: "#6b6557",
        green: "#1f6f5c", dark: "#143f33", terra: "#b9623a",
        sand: "#c9c1ad", pale: "#ecf2ef", line: "#e7e1d4",
      },
      fontFamily: {
        display: ["Fraunces", "Georgia", "Times New Roman", "serif"],
        logo: ["Fraunces", "Georgia", "serif"],
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(20,63,51,0.05), 0 10px 28px rgba(20,63,51,0.08), 0 30px 64px rgba(20,63,51,0.10)",
        cta: "0 10px 22px rgba(31,111,92,0.28), 0 2px 6px rgba(20,63,51,0.18)",
      },
    },
  },
};
```

Load Fraunces once in your document `<head>` (the only external font - body
stays on the system sans stack):

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400;1,9..144,500&display=swap" rel="stylesheet" />
```

### 2. Custom CSS (add after `@tailwind` directives in your global stylesheet)

```css
html { scroll-behavior: smooth; }
body {
  background-color: #f6f3ec;
  background-image:
    radial-gradient(1200px 620px at 82% -12%, rgba(31,111,92,0.10), transparent 60%),
    radial-gradient(960px 520px at -12% 8%, rgba(185,98,58,0.08), transparent 55%);
  color: #1c1a16;
  font-feature-settings: "ss01", "cv01";
}
.font-display { font-optical-sizing: auto; }
h1, h2, h3 { letter-spacing: -0.015em; }
::selection { background: #1f6f5c; color: #f6f3ec; }
*:focus-visible { outline: 2px solid #1f6f5c; outline-offset: 3px; border-radius: 4px; }

/* Paper grain - reinforces the appraisal-document feel */
.grain {
  position: fixed; inset: 0; z-index: 9; pointer-events: none; opacity: 0.045;
  mix-blend-mode: multiply;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>");
}

.glass-panel {
  background: rgba(246, 243, 236, 0.7);
  backdrop-filter: blur(14px) saturate(1.1);
  -webkit-backdrop-filter: blur(14px) saturate(1.1);
  border-bottom: 1px solid rgba(201, 193, 173, 0.45);
}
.premium-panel {
  background:
    linear-gradient(180deg, rgba(255,255,255,0.5), rgba(255,255,255,0) 38%),
    #f6f3ec;
  border: 1px solid #c9c1ad;
  box-shadow: 0 1px 2px rgba(20,63,51,0.05), 0 14px 34px rgba(20,63,51,0.10),
              0 40px 80px rgba(20,63,51,0.10), inset 0 1px 0 rgba(255,255,255,0.7);
}
.hairline-card {
  background: rgba(255,255,255,0.55);
  border: 1px solid #e7e1d4;
  transition: transform 0.4s cubic-bezier(0.16,1,0.3,1), box-shadow 0.4s ease, border-color 0.4s ease;
}
.hairline-card:hover { transform: translateY(-4px); box-shadow: 0 20px 44px rgba(20,63,51,0.12); border-color: #c9c1ad; }

.data-bar { background: linear-gradient(180deg, #2a8a72, #143f33); }
.data-bar-muted { background: linear-gradient(180deg, #c9c1ad, #b3a98f); }
.bar { transform-origin: bottom; transform: scaleY(0); }
.terra-rule { background: linear-gradient(90deg, #b9623a, rgba(185,98,58,0)); }

/* Section index numerals (report style) */
.sec-index { font-family: "Fraunces", Georgia, serif; font-variant-numeric: lining-nums; }

.btn-lift { transition: transform 0.25s cubic-bezier(0.16,1,0.3,1), box-shadow 0.25s ease, background-color 0.25s ease; }
.btn-lift:hover { transform: translateY(-2px); }
.btn-lift .arrow { transition: transform 0.25s ease; }
.btn-lift:hover .arrow { transform: translateX(3px); }

/* Orchestrated entrance (hero) + below-fold reveals */
@keyframes rise { from { opacity: 0; transform: translateY(26px); } to { opacity: 1; transform: none; } }
@keyframes grow { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@keyframes floaty { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
.anim { opacity: 0; animation: rise 0.95s cubic-bezier(0.16,1,0.3,1) forwards; }
.d1 { animation-delay: 0.05s; } .d2 { animation-delay: 0.15s; } .d3 { animation-delay: 0.25s; }
.d4 { animation-delay: 0.35s; } .d5 { animation-delay: 0.45s; } .d6 { animation-delay: 0.55s; }
.float-slow { animation: floaty 7s ease-in-out infinite; }

.reveal-on-scroll {
  opacity: 0; transform: translateY(30px);
  transition: opacity 1.1s cubic-bezier(0.16, 1, 0.3, 1), transform 1.1s cubic-bezier(0.16, 1, 0.3, 1);
}
.reveal-on-scroll.animate-in { opacity: 1; transform: translateY(0); }
.rd-1 { transition-delay: 0.08s; } .rd-2 { transition-delay: 0.18s; } .rd-3 { transition-delay: 0.28s; }

/* valuation widget */
@keyframes hermes-pulse {
  0%, 100% { box-shadow: 0 12px 30px rgba(31,111,92,0.40), 0 0 0 0 rgba(31,111,92,0.40); }
  50% { box-shadow: 0 12px 30px rgba(31,111,92,0.40), 0 0 0 12px rgba(31,111,92,0); }
}
.hermes-launcher { animation: hermes-pulse 2.6s ease-out infinite; }
.hermes-panel {
  transform: translateY(16px) scale(0.98); opacity: 0; pointer-events: none;
  transition: opacity 0.28s ease, transform 0.28s cubic-bezier(0.16,1,0.3,1);
}
.hermes-panel.open { transform: translateY(0) scale(1); opacity: 1; pointer-events: auto; }
.hermes-chip[aria-pressed="true"] { background: #1f6f5c; color: #f6f3ec; border-color: #1f6f5c; }

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  .anim, .reveal-on-scroll { opacity: 1 !important; transform: none !important; animation: none !important; transition: none !important; }
  .bar { transform: scaleY(1) !important; animation: none !important; }
  .float-slow, .hermes-launcher { animation: none !important; }
  .hermes-panel { transition: none; }
}
```

The valuation widget (both files) passes a `?start=` payload (`v1|audience|address`,
base64url, capped at Telegram's 64-char limit) into the bot. The bot decodes it in
`/start` (`decode_start_payload` -> `begin_from_landing`), so the bot opens already
knowing the address and audience: it seeds PENDING with both and jumps straight into
the intake wizard, skipping "Who are you?" - it never starts from nothing. An empty
address (the >64-char fallback) or any unrecognised payload falls through to the
normal greeting.

## Free-valuation abuse

There is nothing to farm: the free Lite valuation is unlimited - free forever, by design.
It is the lead magnet and the permanent public asset, not a one-time taste. What is paid is
the PRO upgrade (the decision layer), in Telegram Stars. `entitlements.json` -> `first_done`
only marks a user's first touch, keyed to the Telegram user id (set on a successful delivery),
and varies first-touch copy / testimonial timing - it is NOT a paywall after one use. A deep
link still forces a real Telegram identity, useful for the Pro funnel and abuse-resistance
generally; tightening that further is a bot-side product decision, not a funnel change.

### 3. iconify web component (once, e.g. in `index.html`)

```html
<script src="https://code.iconify.design/iconify-icon/2.1.0/iconify-icon.min.js"></script>
```

## Deploy

The simplest path is `index.html` on whatever serves `usehonestly.co.uk`. It is
self-contained and dependency-free at runtime (CDNs only). `App.jsx` is there
for when the site graduates to a React build.
