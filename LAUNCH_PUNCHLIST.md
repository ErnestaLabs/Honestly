# Launch punch list

## Done
- Telegram landing flow and start payload handoff
- Free / paid valuation flow
- Blog SEO/AEO structure
- PDF and blog deliverables
- Optional PDF dependency crash fixed
- `.env` loader file-handle warnings fixed
- Live QA pass completed on the local bot app, landing page, blog index, district page, robots.txt, and sitemap.xml
- Rebuilt blog network to restore missing `/blog/` and refresh the feed/sitemap
- Fresh Hit MCP launch scan saved to `research/hit_monopoly_launch_raw.json`
- Launch-tonight PRD saved to `research/HONESTLY_monopoly_launch_PRD.md`
- Main app and landing copy aligned to: one address, defended price, sold evidence shown
- Pack labels changed to Evidence Pack / Decision Pack
- Compile, bot tests, and SEO/public-copy audit passed after launch-copy changes

## Still open
### P0 - ship blockers
- Confirm PDF generation on a machine with `fpdf2` installed
- Verify hosted `/blog/` and sitemap/feed on the deployment target
- Verify production bot shows Evidence Pack / Decision Pack invoices
- Point `usehonestly.co.uk` DNS/hosting at the Honestly web server or publish `site/` to the current host
- Verify production landing page hero says "One address. A defended price. Sold evidence shown."

### P0 - current production finding
- Bot VPS is active at `187.77.100.209` after deploy and missing `brand.py` fix.
- `usehonestly.co.uk` currently resolves to `76.223.105.230` / `13.248.243.5`, not the bot VPS.
- Public root returns a parked/default page titled `usehonestly.co.uk`.
- Public `/blog/` returns 404 until DNS/hosting is corrected or the generated `site/` tree is uploaded to that host.

### P1 - product polish
- Broaden blog coverage with more city hubs and internal links
- Add more mid-funnel content for buyer/vendor objections
- Tighten plain-English copy variants by audience
- Make weak-evidence fallback stay fully invisible in customer surfaces

### P2 - growth
- More lead magnets and follow-up paths
- Email nurture / referral tuning
- Ongoing SEO content expansion
