# このファイルは yfinance 1.5.2 の `scrapers/quote.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: info と提出書類
# 変えた点（Apache License 2.0 第 4 条 b）:
#   - 削った: FastInfo, Quote.sustainability, Quote.recommendations, Quote.upgrades_downgrades, Quote.calendar, Quote.valuation_measures, Quote.get_valuation_measures, Quote._fetch_valuation_measures, Quote._fetch_complementary, Quote._fetch_calendar（株価・評価指標・ESG スコア・アナリスト・決算予定）
#   - 名前 yfinance → jfinance（import・ロガー名・repr）
#   - 差し替えた: trailingPegRatio（株価に依存）を取りに行かない

from jfinance._http import HTTPError
import datetime
import json
import numbers
import numpy as _np
import pandas as pd

from jfinance import utils
from jfinance.config import YfConfig
from jfinance.const import quote_summary_valid_modules, _BASE_URL_, _QUERY1_URL_
from jfinance.data import YfData
from jfinance.exceptions import YFDataException, YFException

info_retired_keys_price = {"currentPrice", "dayHigh", "dayLow", "open", "previousClose", "volume", "volume24Hr"}
info_retired_keys_price.update({"regularMarket"+s for s in ["DayHigh", "DayLow", "Open", "PreviousClose", "Price", "Volume"]})
info_retired_keys_price.update({"fiftyTwoWeekLow", "fiftyTwoWeekHigh", "fiftyTwoWeekChange", "52WeekChange", "fiftyDayAverage", "twoHundredDayAverage"})
info_retired_keys_price.update({"averageDailyVolume10Day", "averageVolume10days", "averageVolume"})
info_retired_keys_exchange = {"currency", "exchange", "exchangeTimezoneName", "exchangeTimezoneShortName", "quoteType"}
info_retired_keys_marketCap = {"marketCap"}
info_retired_keys_symbol = {"symbol"}

# Valuation-measure timeseries keys (fundamentals-timeseries API) -> display labels,
# matching the rows historically shown on the Yahoo key-statistics page.
_VALUATION_MEASURE_LABELS = {
    "MarketCap": "Market Cap",
    "EnterpriseValue": "Enterprise Value",
    "PeRatio": "Trailing P/E",
    "ForwardPeRatio": "Forward P/E",
    "PegRatio": "PEG Ratio (5yr expected)",
    "PsRatio": "Price/Sales",
    "PbRatio": "Price/Book",
    "EnterprisesValueRevenueRatio": "Enterprise Value/Revenue",
    "EnterprisesValueEBITDARatio": "Enterprise Value/EBITDA",
}
# Public freq -> fundamentals-timeseries type prefix for the period columns.
_VALUATION_FREQ_PREFIX = {"quarterly": "quarterly", "monthly": "monthly",
                          "yearly": "annual", "trailing": "trailing"}


info_retired_keys = info_retired_keys_price | info_retired_keys_exchange | info_retired_keys_marketCap | info_retired_keys_symbol


_QUOTE_SUMMARY_URL_ = f"{_BASE_URL_}/v10/finance/quoteSummary"


class Quote:
    def __init__(self, data: YfData, symbol: str):
        self._data = data
        self._symbol = symbol

        self._info = None
        self._retired_info = None
        self._sustainability = None
        self._recommendations = None
        self._upgrades_downgrades = None
        self._calendar = None
        self._sec_filings = None
        self._valuation_measures = {}  # keyed by freq

        self._already_scraped = False
        self._already_fetched = False
        self._already_fetched_complementary = False

    @property
    def info(self) -> dict:
        if self._info is None:
            self._fetch_info()

        return self._info

    @property
    def sec_filings(self) -> dict:
        if self._sec_filings is None:
            f = self._fetch_sec_filings()
            self._sec_filings = {} if f is None else f
        return self._sec_filings

    @staticmethod
    def valid_modules():
        return quote_summary_valid_modules

    def _fetch(self, modules: list):
        if not isinstance(modules, list):
            raise YFException("Should provide a list of modules, see available modules using `valid_modules`")

        modules = ','.join([m for m in modules if m in quote_summary_valid_modules])
        if len(modules) == 0:
            raise YFException("No valid modules provided, see available modules using `valid_modules`")
        params_dict = {"modules": modules, "corsDomain": "finance.yahoo.com", "formatted": "false", "symbol": self._symbol, "lang": YfConfig.locale.lang, "region": YfConfig.locale.region}
        try:
            result = self._data.get_raw_json(_QUOTE_SUMMARY_URL_ + f"/{self._symbol}", params=params_dict)
        except HTTPError as e:
            if not YfConfig.debug.hide_exceptions:
                raise
            utils.get_yf_logger().error(str(e) + e.response.text)
            return None
        return result

    def _fetch_additional_info(self):
        params_dict = {"symbols": self._symbol, "formatted": "false", "lang": YfConfig.locale.lang, "region": YfConfig.locale.region}
        try:
            result = self._data.get_raw_json(f"{_QUERY1_URL_}/v7/finance/quote?", params=params_dict)
        except HTTPError as e:
            if not YfConfig.debug.hide_exceptions:
                raise
            utils.get_yf_logger().error(str(e) + e.response.text)
            return None
        return result

    def _fetch_info(self):
        if self._already_fetched:
            return
        self._already_fetched = True
        modules = ['financialData', 'quoteType', 'defaultKeyStatistics', 'assetProfile', 'summaryDetail']
        result = self._fetch(modules=modules)
        additional_info = self._fetch_additional_info()

        if result is None:
            result = {}

        if additional_info is not None:
            result.update(additional_info)

        query1_info = {}
        for quote in ["quoteSummary", "quoteResponse"]:
            quote_result = result.get(quote, {}).get("result", [])

            if len(quote_result) > 0:
                quote_result[0]["symbol"] = self._symbol
                query_info = next(
                    (info for info in quote_result if info.get("symbol") == self._symbol),
                    None,
                )
                if query_info:
                    query1_info.update(query_info)

        # Normalize and flatten nested dictionaries while converting maxAge from days (1) to seconds (86400).
        # This handles Yahoo Finance API inconsistency where maxAge is sometimes expressed in days instead of seconds.
        processed_info = {}
        for k, v in query1_info.items():

            # Handle nested dictionary
            if isinstance(v, dict):
                for k1, v1 in v.items():
                    if v1 is not None:
                        processed_info[k1] = 86400 if k1 == "maxAge" and v1 == 1 else v1

            elif v is not None:
                processed_info[k] = v

        query1_info = processed_info

        # recursively format but only because of 'companyOfficers'

        def _format(k, v):
            if isinstance(v, dict) and "raw" in v and "fmt" in v:
                v2 = v["fmt"] if k in {"regularMarketTime", "postMarketTime"} else v["raw"]
            elif isinstance(v, list):
                v2 = [_format(None, x) for x in v]
            elif isinstance(v, dict):
                v2 = {k: _format(k, x) for k, x in v.items()}
            elif isinstance(v, str):
                v2 = v.replace("\xa0", " ")
            else:
                v2 = v
            return v2

        self._info = {k: _format(k, v) for k, v in query1_info.items()}

    def _fetch_sec_filings(self):
        result = self._fetch(modules=['secFilings'])
        if result is None:
            return None

        filings = result["quoteSummary"]["result"][0]["secFilings"]["filings"]

        # Improve structure
        for f in filings:
            if 'exhibits' in f:
                f['exhibits'] = {e['type']:e['url'] for e in f['exhibits']}
            f['date'] = datetime.datetime.strptime(f['date'], '%Y-%m-%d').date()

        # Experimental: convert to pandas
        # for i in range(len(filings)):
        #     f = filings[i]
        #     if 'exhibits' in f:
        #         for e in f['exhibits']:
        #             f[e['type']] = e['url']
        #         del f['exhibits']
        #     filings[i] = f
        # filings = pd.DataFrame(filings)
        # for c in filings.columns:
        #     if c.startswith('EX-'):
        #         filings[c] = filings[c].astype(str)
        #         filings.loc[filings[c]=='nan', c] = ''
        # filings = filings.drop('epochDate', axis=1)
        # filings = filings.set_index('date')

        return filings
