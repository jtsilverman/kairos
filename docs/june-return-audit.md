# June return audit

Read-only audit of the 39 shortlisted names for 2026-06-01. Entry close 2026-06-02; exit close 2026-08-31. No outcome labels, cache rows or prompts changed.

Fresh Polygon grouped daily requests, adjusted=True, compared against every shortlisted name's stored outcome:

- SPY: +0.9847676975%.
- Basket equal-weight return: -8.9067184170%.
- Basket alpha: -9.8914861145 percentage points, not the stored -12.5955810511.
- Median alpha: -10.8870325222 percentage points.
- Beat count: 12 of 39, not 10 of 39.
- Exactly two names changed versus stored returns: MNST and APH.
- MNST fresh entry/exit closes: 44.12 / 45.92, +4.08%; cached entry was 88.24 and produced -47.96%.
- APH fresh entry/exit closes: 74.2 / 79.275, +6.84%; cached entry was 148.4 and produced -46.58%.

The cached endpoints mixed historical split-adjustment vintages despite both keys carrying adjusted=true. Fresh adjusted requests correct the two false losses. APH's split occurred after the measurement window, but later adjustment of an exit row without re-adjustment of an older entry row still corrupted the ratio.

Primary split evidence: https://investors.amphenol.com/news-and-events/news-details/2026/Amphenol-Announces-Two-for-One-Stock-Split-and-Third-Quarter-2026-Dividend/default.aspx (two-for-one distributed September 2). MNST split corroboration: https://www.marketbeat.com/stocks/NASDAQ/MNST/ (two-for-one August 11).

Real losses remain: APP -48.47%, STRL -46.31%, MOD -41.86%, POWL -39.90%, CLS -36.62%, MYRG -35.28%, TTMI -33.79%. Search evidence describes a July AI infrastructure and semiconductor correction, plus APP revenue/guidance disappointment and STRL margin/bookings concerns. These support a mix of thematic repricing and company-specific events, not a general market decline: SPY gained over the measured window. They do not prove that technical execution would have avoided the losses.

Sources for the causal interpretation:
https://fortune.com/2026/08/02/wall-street-ai-trade-chip-stocks-volatility-sox-selloff/
https://portusadvisors.com/insights/august-2026-economic-and-investment-update/
https://investorshub.advfn.com/market-news/article/33574/applovin-shares-tumble-as-revenue-miss-and-cautious-outlook-outweigh-earnings-beat
https://weissratings.com/en/instant-news-alerts/sterling-infrastructure-inc-strl-down-9-4-is-this-the-moment-to-unload

Open systemic issue: audit other dates and downstream tier/outcome analyses for mixed adjustment vintages before relying on their reported returns. Frozen label sets require an explicit correction procedure rather than silent overwrites.
