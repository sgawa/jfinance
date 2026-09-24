# Changelog

Notable changes. This project uses [Semantic Versioning](https://semver.org/lang/ja/).

## [Unreleased]

## [0.3.2]

### Changed
- Financial statement rows with no value at all are no longer returned. Yahoo's own
  constructs (`Normalized EBITDA`, `Tax Effect Of Unusual Items` and the like) have no
  source in a Japanese filing; returning them as empty rows left `financials` 80% `NaN`
  for every company. `financials`, `balance_sheet`, `cashflow` and `get_jp_financials()`
  now return only the line items the company actually discloses, in yfinance's order —
  the same behaviour as yfinance against Yahoo.

### Fixed
- `examples/quickstart.ipynb` leads with `get_statements()`, which shows the filed
  statements with their own hierarchy, and a Japanese notebook was added
  (`examples/quickstart.ja.ipynb`)

## [0.3.1]

Metadata only. No change to the code.

### Changed
- Author is `Sugawara`
- Summary is "Japanese EDINET disclosure data API"

## [0.3.0]

First public release.

### Added
- `Ticker` with the yfinance API: `info`, `financials`, `balance_sheet`, `cashflow`,
  `quarterly_*`, `major_holders`, `institutional_holders`, `sec_filings`
- jfinance-only data: `major_shareholders`, `large_holders`, `large_holder_transactions`,
  `large_holder_activity`, `officer_compensation`, `emissions`, `report_filing_dates`,
  `get_jp_financials()`, `get_statements()`, `segments`, `employees`, `get_officers()`,
  `officer_remuneration`, `audit_fees`, `dividend_resolutions`, `get_filings()`
- Investment trusts: `get_fund_financials()` (25 items)
- `JpSector`, `JpIndustry`, `edinet_screen`, `EdinetQuery`, `FilingCalendar`
- `set_financials_basis()` — standalone / as-filed statements
- Japanese output via `jf.config.locale.lang = "ja-JP"`
- Attribution for EDINET content and the EDINET Taxonomy (`NOTICE`, `licenses/`)

### Notes
- Prices, analyst estimates, news, ESG scores and earnings calendars are **not** provided —
  EDINET has no equivalent. See the compatibility table
- Amendments to filings past their EDINET public inspection period cannot be retrieved
