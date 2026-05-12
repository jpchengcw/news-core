# news-core

Multilingual equity-research news ingestion.

Locale-aware fetch → tier scoring → translation + analyst gloss → cross-language dedup → recency × authority × relevance ranking. Consumed by `pm-pulse` and `deep-dive` as a shared package.

## Why

English wires miss the alpha. The signal lives in Nikkei, Caixin, Chosun BIZ, Handelsblatt, Les Echos, and trade press like DigiTimes / 36Kr / The Elec / Nikkei xTECH. `news-core` exists so every Asia/EU name in the universe gets the same depth as the US names.

## Install (development)

```bash
# from a consumer app, e.g. /Users/jpcheng/deep-dive
pip install -e ../news-core
```

## Quickstart

```python
from news_core import NewsClient

client = NewsClient(cache_dir="state/news_core", consumer="deep_dive")

result = client.fetch(
    ticker="285A.T",
    company_name="Kioxia Holdings",
    business_geography=["JP", "global_memory"],
    lookback_hours=72,
    max_items=20,
    min_tier=2,  # Tier 2 = industry trade press; raise to 1 for top-tier-only
)

for item in result.items:
    print(f"[{item.tier.name}] {item.source_name}  {item.title_original}")
    if item.title_translated:
        print(f"      → {item.title_translated}")
    if item.analyst_gloss:
        print(f"      {item.analyst_gloss}")
```

## Languages

EN, JA, KO, ZH-CN, ZH-HK, ZH-TW, DE, FR.

Locale inference is keyed on listing-exchange suffix + `business_geography` tags. See `news_core/locales.py`.

## Tier model

- **S** — regulatory / company primary (TDnet, EDINET, HKEXnews, DART, SEC EDGAR, Bundesanzeiger, AMF, IR sites)
- **1** — top-tier financial press (Nikkei, Caixin, Chosun BIZ, Handelsblatt, Les Echos, Bloomberg/Reuters/FT/WSJ)
- **2** — industry trade (DigiTimes, TrendForce, 36Kr, The Elec, Nikkei xTECH, EE Times, MLex)
- **3** — aggregators / corporate channels (Xueqiu, Naver Finance, Kabutan)
- **X** — deprioritised SEO (Simply Wall St, Yahoo News rehosts)

Sources are *priors*, not a hard whitelist — unregistered domains still surface, just with lower authority weight. S-tier and high-conviction Tier-2 scoops surface prominently even when not yet on Tier-1 wires; that is the point of this package.

## Skill

The analytical voice and worked examples (Biren / SMIC 7nm allocation, Kioxia / Bain / Yokkaichi) live in `.claude/skills/local-news-translation/SKILL.md`.

## Status

Scaffold complete. Static data tables, scoring, dedup, schema, and skill in place. Live fetch + DeepL/Claude translation wiring is the next iteration.
