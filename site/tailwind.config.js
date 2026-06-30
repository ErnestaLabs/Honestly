module.exports = {
  content: ["./site/index.html"],
  theme: {
    extend: {
      colors: {
        cream: "#f6f3ec", paper: "#fbf9f4", ink: "#1c1a16", muted: "#6b6557",
        green: "#15807f", dark: "#0e2747", terra: "#2aa39a", gold: "#d89a32",
        tg: "#229ED9", tgdark: "#1b88bd",
        sand: "#c9c1ad", pale: "#e7eef0", line: "#e7e1d4",
      },
      fontFamily: {
        display: ["Fraunces", "Georgia", "Times New Roman", "serif"],
        logo: ["Fraunces", "Georgia", "serif"],
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      letterSpacing: { mega: "0.32em" },
      boxShadow: {
        doc: "0 1px 2px rgba(14,39,71,0.05), 0 18px 40px rgba(14,39,71,0.12), 0 48px 90px rgba(14,39,71,0.14)",
        cta: "0 10px 22px rgba(216,154,50,0.32), 0 2px 6px rgba(14,39,71,0.22)",
        tg: "0 10px 22px rgba(34,158,217,0.34), 0 2px 6px rgba(14,39,71,0.22)",
      },
    },
  },
};
