---
name: local-news-translation
description: Locale-aware multilingual equity-research news ingestion. Use when surfacing news for any non-US-listed name or any name with material non-English business geography. Covers locale inference, source-tier rules, query construction per language, translation tone, copyright caps, and when trade-press scoops should beat Tier-1 wires.
---

# Local News Translation — Operating Manual

## Why this skill exists

The single biggest failure mode of US-built research stacks: every Asian and European name gets reported through Bloomberg / Reuters / FT / WSJ filtered through Simply Wall St rehosts. The on-the-ground signal — Yokkaichi capex commentary in *Nikkei*, a Bain Capital placement filing in *Toyo Keizai*, SMIC's 7nm allocation decisions in *36Kr* — never reaches the report. **This skill exists to fix that for every Asian and European name in the universe.**

The Kioxia v1 report exposed the failure: §N news block surfaced two Simply Wall St aggregator items. Zero Nikkei, Toyo Keizai, Diamond, Nikkei xTECH, NHK. For a JPX-listed memory name with a Yokkaichi JV and Bain Capital secondary overhang, that is the primary quality gap. NewsCore + this skill close it.

## Step 1 — Locale inference

For every name, resolve the locale list before constructing queries:

1. **Listing exchange suffix → primary locale.** `.T` → ja. `.HK` → zh-HK. `.SS / .SZ` → zh-CN. `.KS / .KQ` → ko. `.PA` → fr. `.DE / .F` → de. `.TW / .TWO` → zh-TW. US tickers (no suffix) → en.
2. **Business geography → secondary locales.** Use the universe's `business_geography` tag set. Examples:
   - `global_memory` → adds ja + ko (NAND/DRAM peer ecosystem)
   - `global_semis` → adds zh-TW + ko + ja (foundry + memory + equipment)
   - `china_evs` → adds zh-CN + ja + ko (battery / supplier read-through)
   - `luxury_eu` → adds fr + zh-CN (Chinese consumer is the demand market)
3. **EN always appended.** Even for the most JP-domestic name, English wires occasionally carry the early translation of a domestic scoop.

Worked locale resolutions:

- 285A.T (Kioxia) + `["JP","global_memory"]` → **ja, ko, en**
- 0700.HK (Tencent) + `["china_internet"]` → **zh-HK, zh-CN, en**
- 9660.HK (Horizon Robotics) + `["china_ai"]` → **zh-HK, zh-CN, en**
- 005930.KS (Samsung) + `["global_memory"]` → **ko, ja, en**
- 7203.T (Toyota) + `["japan_autos"]` → **ja, de, ko, zh-CN, en**
- MC.PA (LVMH) + `["luxury_eu"]` → **fr, zh-CN, en**
- META + `["us_megacap"]` → **en**

## Step 2 — Conventional name construction

Local search engines (Naver, Yahoo Japan, Baidu) rank against the *conventional* name. For Kioxia, "Kioxia" alone misses items; **キオクシア** is what *Nikkei* uses. Always include:

- The katakana/Hangul/Hanzi conventional name
- The romanised English name
- The bare ticker code (without exchange suffix) — local press cites e.g. `(285A)`, not `(285A.T)`

| Ticker | Locale | Variants |
|---|---|---|
| 285A.T | ja | キオクシア, キオクシアホールディングス, Kioxia, 285A |
| 0700.HK | zh-CN | 腾讯, 腾讯控股, Tencent |
| 0700.HK | zh-HK | 騰訊, 騰訊控股, Tencent |
| 9660.HK | zh-CN | 地平线, 地平线机器人, Horizon Robotics |
| 005930.KS | ko | 삼성전자, Samsung Electronics |
| 000660.KS | ko | SK하이닉스, 하이닉스, SK Hynix |
| 7203.T | ja | トヨタ, トヨタ自動車, Toyota |
| MC.PA | fr | LVMH, Louis Vuitton Moët Hennessy |

Query format: `"variant1" OR "variant2" OR "variant3"` — works on Tavily, Google, Bing, Naver, Yahoo Japan, Baidu, DuckDuckGo identically.

## Step 3 — Source tiering

Tiers are **priors**, not a hard whitelist. Unregistered domains still surface, just with lower authority weight.

### Tier S — regulatory / company primary (always include)
TDnet, EDINET (JPX); HKEXnews (HKEX); DART, KIND (KRX); SSE/SZSE/CSRC (China); SEC EDGAR (US); Bundesanzeiger (DE); AMF (FR); company IR.

### Tier 1 — top-tier financial press
- **Global EN:** Bloomberg, Reuters, FT, WSJ, Nikkei Asia
- **JP:** Nikkei, Toyo Keizai, Diamond, Asahi, Yomiuri, NHK, Mainichi
- **CN/HK:** Caixin, Yicai, 21st Century Business Herald, Securities Times, China Securities Journal, SCMP, Ming Pao, HKET
- **KR:** Chosun BIZ, Maeil Business, Hankyung, Yonhap Infomax, Yonhap, The Bell
- **DE:** Handelsblatt, FAZ, Manager Magazin, Börsen-Zeitung
- **FR:** Les Echos, Le Figaro, L'Agefi, La Tribune

### Tier 2 — industry trade & sell-side excerpts
- **Semis/hardware:** DigiTimes, TrendForce, EE Times, EE Times China, Tom's Hardware, AnandTech, The Register, Nikkei xTECH, ITmedia/MONOist, EDN Japan, Korea IT News, ETNews, The Elec, 36Kr, LatePost, Jiemian, ChinaStarMarket
- **Auto:** Automotive News, Automotive News China, Response.jp
- **Regulatory/policy:** MLex, Global Competition Review
- **Sell-side:** Jefferies, Bernstein excerpts where surfaced

### Tier 3 — aggregators / corp channels
Xueqiu, Eastmoney, Sina Finance, Naver Finance, Kabutan, Traders Web, Seeking Alpha. Useful for sentiment and for surfacing material-but-locally-known scoops; never the primary citation.

### Tier X — deprioritise
Simply Wall St, Yahoo News rehosts, MSN Money, Investing.com, Benzinga, The Motley Fool, ZeroHedge, GuruFocus, Insider Monkey. These rehosts and content-farm aggregators rarely carry independent reporting.

## Step 4 — Trade-press scoop rule (the alpha)

**Surface S-tier disclosures and high-conviction Tier-2 trade-press scoops prominently even when they are not yet on Tier-1 wires.** That is the point of this package. Worked example:

> **Biren / SMIC 7nm capacity allocation** — Tom's Hardware (Tier 2 EN) and 36Kr / DigiTimes (Tier 2 zh-CN) reported SMIC was prioritising Biren's 7nm tape-out over Kunlunxin's. Bloomberg / Reuters did not pick this up for ~10 days. The window is the alpha. By the time Tier-1 wires confirm, the position is in.
>
> Ranking: surface the Tom's Hardware + 36Kr cluster at the top of the report.
> Gloss: **"Read-through: SMIC prioritising Biren over Kunlunxin reinforces Biren's scaling certainty vs CN GPU peers — supports a re-rate toward Cambricon multiples."**

Rule of thumb: a Tier-2 scoop with a primary-source citation (filings, named executives quoted, on-the-record manufacturing data) **outranks a Tier-1 wire that is summarising public announcements.** Authority weight in the registry doesn't capture this — it requires editorial judgement at the gloss step.

## Step 5 — Translation tone

Verbatim translation of headline + 2–4 most material sentences from the body. Hard cap at **4 sentences** for copyright defensibility.

- **Preserve numbers verbatim.** Do not round, restate, or convert units.
- **Preserve proper nouns verbatim.** No transliteration of executive names, product codenames, fab IDs.
- **No editorialising in the translation itself.** That belongs in the gloss line, separately labelled.
- **Always preserve the original-language title and source URL** in the citation, even if the English translation is what's displayed.

## Step 6 — Analyst gloss

One sentence. Format: `Read-through: …` or `Implication: …`.

The gloss is where the analytical work shows up. It must:

- State what changes for the named ticker, mechanically. Why does this move estimates / position sizing / risk?
- Be evidence-anchored. No invented numbers, no invented competitive dynamics. If the source doesn't support the read-through, write a shorter gloss.
- Be terse. No hedging filler ("could potentially", "may be considered as"). One declarative sentence.
- Default to silent. If the item has no material read-through for the named ticker, output an empty string. Don't pad.

Bad gloss: *"This article discusses recent developments at the company that could potentially impact future operations."*

Good gloss: *"Read-through: WDC JV split impacts Kioxia capex independence; binds capacity decisions to Sandisk post-spin."*

### Gloss style by consumer

The two consumers (Deep Dive reports + PM Pulse digests) have different length budgets. Tune the gloss accordingly:

- **Deep Dive** (one-shot reports, ~3–8k words): the gloss above is the spec. One full declarative sentence, mechanically anchored. Allowed to invoke a peer name or a multiple if the read-through requires it. Example: *"Read-through: Tom's Hardware capacity-allocation scoop reinforces Biren's scaling certainty vs CN GPU peers — supports re-rate toward Cambricon multiples."*

- **PM Pulse** (4-times-daily digest, ~1500-word target): glosses must compress further to fit the roster format. Aim for **≤14 words per gloss**; drop the peer-comparison clause; keep just the mechanical change for the named ticker. Example for the same item: *"Read-through: SMIC prioritising Biren tape-out reinforces near-term scaling — bullish for the long."* The full peer-multiple analysis stays in Deep Dive; PM Pulse just flags the directional read.

PM Pulse glosses are emitted from `summary_translated` + `title_translated` exactly like Deep Dive, but the rendering layer (PM Pulse synthesis) caps line length and demands a single-clause sentence. When the source supports a longer read, write the longer Deep-Dive gloss into the item — the PM Pulse renderer will truncate to its budget. **Do not write two glosses.** One gloss per item; consumers compress as needed.

## Step 7 — Cross-language dedup

Cluster on `(entity, topic, 24h_window)`. Within a cluster, **keep all S-tier items unconditionally** (primary disclosures are non-negotiable), then keep the highest-tier non-S item. Drop the rest as duplicates.

The 24h window is deliberate: a Caixin scoop at 18:00 Beijing time and a Reuters wire at 06:00 London the next morning are the same story; a Nikkei follow-up two days later with new exec quotes is a separate story.

When the same story exists across languages, the dedup output should always include the **earliest** local-language source AND the highest-tier translated source. Never collapse to just the English wire — the local citation is what defends the read-through.

## Worked example — Kioxia (canary case)

Inputs:
- ticker: `285A.T`
- company_name: `Kioxia Holdings`
- business_geography: `["JP","global_memory"]`
- lookback: 72h

Locales resolved: **ja, ko, en**

Per-locale queries:
- **ja:** `"キオクシア" OR "キオクシアホールディングス" OR "Kioxia" OR "285A"`
- **ko:** `"키오시아" OR "Kioxia"`
- **en:** `"Kioxia" OR "Kioxia Holdings" OR "285A"`

Expected coverage in any 7-day window: ≥3 distinct JP-Tier-1 sources surfaced (Nikkei + Toyo Keizai + Nikkei xTECH or Diamond), at least one Tier-S item (TDnet disclosure or EDINET filing) when present, and English wires deduped to a single rep per cluster.

The two recurring Kioxia items the v1 report missed:

1. **Yokkaichi capex commentary in *Nikkei*** — Tier-1 JP scoop on the WDC JV split mechanics post Sandisk spin. The English wires carried only the high-level press release.
   Gloss: *"Read-through: WDC JV split impacts Kioxia capex independence; binds capacity decisions to Sandisk post-spin."*

2. **Bain Capital secondary chatter in *Nikkei* / *Toyo Keizai*** — pre-event placement filings. The v1 report's §14 risk section flags this as a HIGH-probability downside risk **with no source**. NewsCore should surface it from the placement-filing side (TDnet + Tier-1 local commentary) before the Tier-1 EN wires confirm.
   Gloss: *"Implication: stake-overhang risk highlighted in §14 now has a quantified pre-event signal — size accordingly."*

## When to invoke this skill

- You are surfacing news for any non-US-listed ticker.
- You are surfacing news for a US-listed ticker with material non-English business geography (e.g. NVDA's CN GPU competitive landscape, MC's Chinese-consumer demand).
- You are auditing a previously generated report's citation list and want to verify local-language coverage was attempted.

When NOT to invoke: pure US-only names with US-only end markets (most regional-bank, most domestic-utility, most US-only software names).
