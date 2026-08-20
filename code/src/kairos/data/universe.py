"""SPY + QQQ constituent ticker list — the kairos PEAD candidate universe.

Static snapshot (copied from swing-trader, taken 2026-05-29). The backtest
filters this to liquid sub-$100 names at run time (via Polygon last close +
option open-interest/spread checks); this list is just the starting pool of
optionable large-caps. The same tuple applies across the ~2yr Polygon options
window. Not survivorship-bias-corrected (current membership, not point-in-time);
acceptable for a first-pass edge test, revisit if results prove sensitive.

Source: composite of S&P 500 (SPY) + Nasdaq 100 (QQQ) memberships, deduplicated.
"""

from __future__ import annotations


_RAW: tuple[str, ...] = (
    # Mega-cap tech (SPY + QQQ overlap)
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "ORCL", "ADBE", "CRM", "CSCO", "ACN", "AMD", "INTC", "QCOM", "TXN", "INTU",
    "IBM", "NOW", "PANW", "AMAT", "MU", "LRCX", "KLAC", "ADI", "MRVL", "SNPS",
    "CDNS", "FTNT", "ANET", "WDAY", "ROP", "PAYX", "FISV", "CTSH", "MCHP",
    "ON", "NXPI", "MPWR", "ASML", "TEAM", "DDOG", "ZS", "CRWD", "PLTR",
    "SNOW", "MDB", "OKTA", "NET", "ZM", "DOCU", "TWLO", "ANSS", "VRSN",
    # Communication services
    "NFLX", "CMCSA", "DIS", "VZ", "T", "TMUS", "CHTR", "EA", "TTWO",
    "WBD", "PARA", "FOXA", "FOX", "OMC", "IPG", "LYV", "NWS", "NWSA",
    "MTCH", "PINS", "SNAP", "RBLX", "TTD", "ROKU", "SPOT", "BIDU", "PDD",
    "JD", "BABA", "MELI",
    # Consumer discretionary
    "HD", "MCD", "NKE", "LOW", "TJX", "SBUX", "BKNG", "ABNB", "MAR", "HLT",
    "LULU", "ROST", "ORLY", "AZO", "GM", "F", "RIVN", "LCID", "LI", "NIO",
    "XPEV", "YUM", "CMG", "DRI", "DPZ", "MNST", "KDP", "BUD", "STZ", "DEO",
    "EBAY", "ETSY", "W", "RH", "ULTA", "BBY", "DG", "DLTR", "TGT", "DKS",
    "GPC", "POOL", "VFC", "TPR", "RL", "TPX", "WHR", "LEN", "DHI", "PHM",
    "NVR", "TOL", "MHK", "GRMN", "HAS", "MAT",
    # Consumer staples
    "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "CL", "EL",
    "GIS", "K", "HSY", "SYY", "ADM", "TSN", "HRL", "MKC", "CHD", "CLX",
    "KMB", "KR", "WBA", "CAG", "CPB", "LW", "TAP", "BG", "SJM", "DLTR",
    # Healthcare
    "UNH", "JNJ", "LLY", "MRK", "ABBV", "PFE", "TMO", "ABT", "DHR", "AMGN",
    "BMY", "GILD", "MDT", "ISRG", "VRTX", "REGN", "CI", "ELV", "HUM", "CVS",
    "CNC", "BSX", "SYK", "ZTS", "BDX", "EW", "DXCM", "RMD", "IDXX", "IQV",
    "HCA", "MCK", "COR", "CAH", "A", "WAT", "PKI", "MTD", "WST", "BAX",
    "BIO", "HOLX", "ALGN", "DGX", "LH", "STE", "CTLT", "ZBH", "BIIB", "ILMN",
    "MRNA", "BMRN", "INCY", "JAZZ", "EXAS", "TECH", "CRL", "PODD", "INSP",
    "VEEV", "VTRS", "OGN", "MOH", "HSIC", "PRGO",
    # Financials
    "BRK.B", "JPM", "V", "MA", "BAC", "WFC", "MS", "GS", "C", "AXP",
    "BLK", "SCHW", "PGR", "AON", "MMC", "PYPL", "FIS", "USB", "PNC", "TFC",
    "BX", "KKR", "APO", "AIG", "MET", "PRU", "TRV", "ALL", "AFL", "HIG",
    "CB", "CINF", "WRB", "L", "RJF", "AMP", "BEN", "IVZ", "NTRS", "STT",
    "BK", "FITB", "HBAN", "RF", "MTB", "KEY", "CMA", "ZION", "WAL", "WTFC",
    "CFG", "CFR", "FRC", "SIVB", "PBCT", "DFS", "COF", "SYF", "ALLY", "WU",
    "GL", "LNC", "PFG", "UNM", "TROW", "STT", "MKTX", "CBOE", "CME", "ICE",
    "NDAQ", "MCO", "MSCI", "SPGI", "FICO",
    # Industrials
    "RTX", "HON", "UNP", "BA", "CAT", "DE", "LMT", "GE", "MMM", "UPS",
    "FDX", "EMR", "ETN", "ITW", "GD", "NOC", "TDG", "PH", "CMI", "ROK",
    "PCAR", "WAB", "PWR", "FAST", "PAYC", "VRSK", "BR", "BAH", "LDOS", "CTAS",
    "RSG", "WM", "GWW", "URI", "AME", "DOV", "XYL", "FBHS", "PNR", "SWK",
    "IR", "TT", "JCI", "OTIS", "CARR", "TXT", "HII", "LHX", "MAS", "ALLE",
    "ROL", "GNRC", "AOS", "HEI", "TDY", "FLS", "GGG", "RHI", "ALSN", "EXPD",
    "JBHT", "CHRW", "ODFL", "XPO", "KNX", "LSTR", "MATX", "NSC", "CSX", "UHAL",
    "DAL", "UAL", "AAL", "LUV", "SAVE", "JBLU", "ALK", "HA", "ULCC", "MESA",
    # Energy
    "XOM", "CVX", "COP", "EOG", "SLB", "PSX", "PXD", "MPC", "VLO", "OXY",
    "HES", "DVN", "FANG", "WMB", "OKE", "KMI", "TRGP", "BKR", "HAL", "FTI",
    "NOV", "RIG", "VAL", "EQT", "AR", "CTRA", "CHK", "MRO", "APA", "OVV",
    # Materials
    "LIN", "APD", "SHW", "ECL", "FCX", "NEM", "DD", "DOW", "PPG", "VMC",
    "MLM", "NUE", "STLD", "CLF", "X", "ATI", "RS", "WRK", "PKG", "IP",
    "AVY", "SEE", "BLL", "AMCR", "WLK", "CE", "EMN", "LYB", "CF", "MOS",
    "FMC", "ALB", "RPM", "FUL", "AXTA", "OLN", "CC", "HUN",
    # Real estate
    "PLD", "AMT", "EQIX", "CCI", "PSA", "O", "WELL", "DLR", "SPG", "SBAC",
    "AVB", "EQR", "VICI", "ARE", "EXR", "MAA", "ESS", "UDR", "VTR", "INVH",
    "CPT", "AIV", "BXP", "VNO", "KIM", "REG", "FRT", "ELS", "SUI", "PEAK",
    "HST", "DRH", "RHP", "APLE", "PK", "DOC", "OHI", "HR", "MPW", "IRM",
    # Utilities
    "NEE", "SO", "DUK", "AEP", "SRE", "D", "EXC", "PCG", "ED", "XEL",
    "PEG", "WEC", "ETR", "ES", "AWK", "DTE", "FE", "AEE", "PPL", "CMS",
    "CNP", "EIX", "AES", "NRG", "LNT", "EVRG", "PNW", "ATO", "NI", "ALE",
    "IDA", "OGE", "BKH", "AVA", "HE", "PNM", "POR", "NWE", "MGEE", "MDU",
    # Nasdaq-100-only specific (not in SPY): ADP, AEP, ADSK, ATVI, BIIB,
    # CDW, CHKP, COST, CSGP, CSX, CTAS, CTSH, DLTR, EBAY, EXC, FANG, FAST,
    # FISV, FTNT, GFS, GILD, HON, IDXX, ILMN, INTU, ISRG, JKHY, KDP, KLAC,
    # LCID, LIN, LRCX, LULU, MAR, MCHP, MELI, MDLZ, MNST, MRNA, MRVL, MU,
    # NXPI, ODFL, OKTA, ORLY, PAYX, PCAR, PDD, PEP, PYPL, REGN, ROST, SBUX,
    # SGEN, SIRI, SNPS, SPLK, TEAM, TMUS, TTD, TTWO, TXN, VRSK, VRSN, VRTX,
    # WBA, WBD, WDAY, XEL, ZM, ZS. (Most already listed above via SPY
    # membership.)
    "ADP", "ADSK", "CDW", "CHKP", "CSGP", "JKHY", "GFS", "SGEN", "SIRI", "SPLK",
)


# Dedup at import (sector cross-mentions like DLTR + STT appear twice in
# the raw list above). Sorted for stable ordering across imports.
SPY_QQQ_CONSTITUENTS: tuple[str, ...] = tuple(sorted(set(_RAW)))


if __name__ == "__main__":
    print(f"raw={len(_RAW)} dedup={len(SPY_QQQ_CONSTITUENTS)}")
