# jfinance

jfinance is a Python library for retrieving corporate disclosure data filed with EDINET free
of charge: financial statements, officers and their compensation, major shareholders, large
shareholding reports and investment trusts. It covers annual, semi-annual and quarterly
securities reports and large shareholding reports **from fiscal 2016 onwards**.
The API is yfinance-compatible.

[日本語 README](README.ja.md)

## Installation

```bash
pip install jfinance
```

Try it without installing anything: [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sgawa/jfinance/blob/main/examples/quickstart.ipynb)

Python 3.9 or later is required. `pandas`, `numpy`, `requests` and `pytz` are installed as
dependencies. (Where `curl_cffi` is available, it is used instead.)

Company names and industries are returned in English by default. Setting
`jf.config.locale.lang = "ja-JP"` returns them in Japanese. Values with no English source
(business descriptions, names of officers and shareholders) are returned in Japanese under
either setting.

## Documentation

See <https://jfnc.org/docs/>.

- [Installation](https://jfnc.org/docs/install/)
- [Ticker symbols](https://jfnc.org/docs/symbols/)
- [Ticker](https://jfnc.org/docs/reference/ticker/)
- [Coverage](https://jfnc.org/docs/data/coverage/)
- [Data notes](https://jfnc.org/docs/data/notes/)
- [Terms of use](https://jfnc.org/docs/terms/)
- [HTTP API](https://jfnc.org/docs/http-api/)

## Where the data comes from

Data is retrieved from a server operated by the author (`https://query1.jfnc.org`).
No registration or API key is required, and there is no SLA. A per-IP rate limit applies.

**Amendments to filings past their EDINET public inspection period cannot be retrieved and
may therefore not be reflected.** Older fiscal years are more likely to retain pre-amendment
values. The same notice is available as `jf.NOTICE_CORRECTIONS` and in the `X-JF-Notice`
header of every HTTP response.

## Examples

```python
import jfinance as jf

t = jf.Ticker("7203.T")           # Toyota. "E02144" (EDINET code) and "JP3633400001" (ISIN) also work
t.info                            # name, industry, employees, business description, officers and their pay
t.financials                      # income statement (annual). balance_sheet, cashflow, quarterly_* likewise
t.major_holders                   # shareholder breakdown (from the annual report)
t.sec_filings                     # filings on EDINET
jf.Ticker("8035.T").institutional_holders   # institutions (special reports under the 5% rule)

# jfinance only
t.major_shareholders              # top 10 shareholders from the annual report
t.large_holders                   # holders in large shareholding reports
t.large_holder_transactions       # their trades (large_holder_activity is a 6-month summary)
t.officer_compensation            # individual officer pay (100M yen and above), all years, amendments applied
t.emissions                       # greenhouse gas emissions (tCO2e, as disclosed in annual reports)
t.report_filing_dates             # filing dates of annual, semi-annual and quarterly reports
t.get_jp_financials()             # ordinary income, book value per share, employees, bank/insurer line items
t.get_statements()                # every line of the financial statements, in the order and hierarchy as filed
t.segments, t.employees           # segment information, workforce (average age, tenure, pay)
t.get_officers(year=2020)         # officers for any year. t.officer_remuneration, t.audit_fees
t.dividend_resolutions            # dividend resolutions (date, per share, total)
t.get_filings(types=["120"])      # all filings (filtering and paging)
jf.set_financials_basis(consolidation="standalone", version="as_filed")   # standalone / as-filed statements
jf.JpSector("automobiles-transportation-equipment").top_companies   # TSE industry classification
jf.edinet_screen(jf.EdinetQuery("gt", ["roe", 0.2]), sortField="revenue")   # screener over EDINET fields
jf.FilingCalendar("2026-06-25").get_filings(types=["120"])          # filings on a given day

f = jf.Ticker("1306.T")           # ETF. "G02925" (EDINET fund code) also works
f.get_fund_financials()           # net assets, principal, trust fees, distributions — 25 items per period
```

## Licensing and attribution

**The source code and the data are licensed differently.**

| | License |
|---|---|
| Source code | **Apache License 2.0** ([LICENSE](LICENSE), [NOTICE](NOTICE)) |
| Data returned by the API | **Governed by EDINET's terms** (below). jfinance does not license it to you |

### Software included

- **yfinance** — Copyright 2017-2019 Ran Aroussi, Apache License 2.0.
  Part of `src/jfinance/` is copied from yfinance 1.5.2. The copying procedure and every
  change made are recorded in [`tools/vendor_yfinance.py`](tools/vendor_yfinance.py).

### Data attribution (the same notice is required when you redistribute or republish it)

    出典：EDINET閲覧（提出）サイト（https://disclosure2.edinet-fsa.go.jp/）、
          PDL1.0（https://www.digital.go.jp/resources/open_data/public_data_license_v1.0）
    EDINET閲覧（提出）サイト（https://disclosure2.edinet-fsa.go.jp/）をもとに jfinance 作成

EDINET content is used under the Public Data License 1.0. jfinance selects values, applies
amendment filings and reshapes the data into yfinance's format, which constitutes **editing
and processing** under those terms.
**It must not be published or used as the government's unprocessed information.**

### EDINET Taxonomy

Element labels, statement names and segment names are quoted from the EDINET Taxonomy.
PDL1.0 does not apply to the EDINET Taxonomy; the EDINET Taxonomy Legal Statement applies
instead.

    EDINETタクソノミ © Copyright 2014 Financial Services Agency, The Japanese Government

jfinance does not alter, modify or translate these labels, as that requires prior consent
from the Financial Services Agency. The full text of that Statement is included as
[`licenses/EDINET_Taxonomy_Legal_Statement.txt`](licenses/EDINET_Taxonomy_Legal_Statement.txt).
Copyright in some of the content of the EDINET Taxonomy belongs to XBRL International, Inc.
(XII), and the Statement requires use in accordance with XII's Intellectual Property Policy.
