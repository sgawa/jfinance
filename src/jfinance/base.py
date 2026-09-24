# このファイルは yfinance 1.5.2 の `base.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: Ticker の本体
# 変えた点（Apache License 2.0 第 4 条 b）:
#   - 削った: TickerBase.history, TickerBase._lazy_load_price_history, TickerBase.get_recommendations, TickerBase.get_recommendations_summary, TickerBase.get_upgrades_downgrades, TickerBase.get_calendar, TickerBase.get_fast_info, TickerBase.get_valuation_measures, TickerBase.get_sustainability, TickerBase.get_analyst_price_targets, TickerBase.get_earnings_estimate, TickerBase.get_revenue_estimate, TickerBase.get_earnings_history, TickerBase.get_eps_trend, TickerBase.get_eps_revisions, TickerBase.get_growth_estimates, TickerBase.get_earnings, TickerBase.get_dividends, TickerBase.get_capital_gains, TickerBase.get_splits, TickerBase.get_actions, TickerBase.get_news, TickerBase.get_earnings_dates, TickerBase._get_earnings_dates_using_scrape, TickerBase._get_earnings_dates_using_screener, TickerBase.get_history_metadata, TickerBase.live, TickerBase.get_mutualfund_holders, TickerBase.get_insider_purchases, TickerBase.get_insider_transactions（株価・配当・アナリスト・ニュース・決算日・リアルタイム・ESG スコア。投資信託の保有と役員の売買（EDINET に同じものが無い。大量保有報告書は jp/ticker.py の独自の名前で出す））
#   - 名前 yfinance → jfinance（import・ロガー名・repr）
#   - 差し替えた: タイムゾーン・ISIN のディスクキャッシュを使わない
#   - 差し替えた: 株価の例外を持たない
#   - 差し替えた: リアルタイムを持たない
#   - 差し替えた: アナリストを持たない
#   - 差し替えた: fast_info を持たない
#   - 差し替えた: 株価を持たない
#   - 差し替えた: 決算日のスクレイピングをしない
#   - 差し替えた: アナリストを持たない
#   - 差し替えた: ISIN はサーバの search で引く。ディスクに保存しない
#   - 差し替えた: タイムゾーンのディスクキャッシュを使わない
#   - 差し替えた: 同上
#   - 差し替えた: 既定で全期間を返す
#   - 差し替えた: ISIN を第三者のサイトで引かず、EDINET の値を使う

#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# jfinance - market data downloader
# https://github.com/ranaroussi/jfinance
#
# Copyright 2017-2019 Ran Aroussi
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import print_function

import json as _json
from typing import Optional, Union
from urllib.parse import quote as urlencode

import numpy as np
import pandas as pd
from ._http import requests, new_session


from . import utils
from .const import _MIC_TO_YAHOO_SUFFIX, _SENTINEL_
from .data import YfData
from .config import YfConfig
from .exceptions import YFDataException, YFRateLimitError
from .scrapers.fundamentals import Fundamentals
from .scrapers.holders import Holders
from .scrapers.quote import Quote
from .scrapers.funds import FundsData

from .const import _BASE_URL_, _ROOT_URL_, _QUERY1_URL_

from io import StringIO


_tz_info_fetch_ctr = 0

class TickerBase:
    def __init__(self, ticker, session=None):
        """
        Initialize a Yahoo Finance Ticker object.

        Args:
            ticker (str | tuple[str, str]):
                Yahoo Finance symbol (e.g. "AAPL")
                or a tuple of (symbol, MIC) e.g. ('OR','XPAR')
                (MIC = market identifier code)

            session (requests.Session, optional):
                Custom requests session.
        """        
        if isinstance(ticker, tuple):
            if len(ticker) != 2:
                raise ValueError("Ticker tuple must be (symbol, mic_code)")
            base_symbol, mic_code = ticker
            # ticker = yahoo_ticker(base_symbol, mic_code)
            if mic_code.startswith('.'):
                mic_code = mic_code[1:]
            if mic_code.upper() not in _MIC_TO_YAHOO_SUFFIX:
                raise ValueError(f"Unknown MIC code: '{mic_code}'")
            sfx = _MIC_TO_YAHOO_SUFFIX[mic_code.upper()]
            if sfx != '':
                ticker = f'{base_symbol}.{sfx}'
            else:
                ticker = base_symbol

        self.ticker = ticker.upper()
        self.session = session or new_session()
        self._tz = None

        self._isin = None
        self._news = []
        self._shares = None

        self._earnings_dates = {}

        self._earnings = None
        self._financials = None

        # raise an error if user tries to give empty ticker
        if self.ticker == "":
            raise ValueError("Empty ticker name")

        self._data: YfData = YfData(session=session)

        # accept isin as ticker
        if utils.is_isin(self.ticker):
            isin = self.ticker
            self.ticker = utils.get_ticker_by_isin(isin)
            if self.ticker == "":
                raise ValueError(f"Invalid ISIN number: {isin}")

        # self._price_history = PriceHistory(self._data, self.ticker)
        self._price_history = None  # lazy-load
        self._holders = Holders(self._data, self.ticker)
        self._quote = Quote(self._data, self.ticker)
        self._fundamentals = Fundamentals(self._data, self.ticker)
        self._funds_data = None

        self._fast_info = None

        self._message_handler = None
        self.ws = None

    # ------------------------

    def _get_ticker_tz(self, timeout):
        if self._tz is not None:
            return self._tz
        tz = None  # jfinance: タイムゾーンをディスクに保存しない

        if tz is None:
            tz = self._fetch_ticker_tz(timeout)
            if tz is None:
                # _fetch_ticker_tz works in 99.999% of cases.
                # For rare fail get from info.
                global _tz_info_fetch_ctr
                if _tz_info_fetch_ctr < 2:
                    # ... but limit. If _fetch_ticker_tz() always
                    # failing then bigger problem.
                    _tz_info_fetch_ctr += 1
                    for k in ['exchangeTimezoneName', 'timeZoneFullName']:
                        if k in self.info:
                            tz = self.info[k]
                            break
            if not utils.is_valid_timezone(tz):
                tz = None

        self._tz = tz
        return tz

    @utils.log_indent_decorator
    def _fetch_ticker_tz(self, timeout):
        # Query Yahoo for fast price data just to get returned timezone
        logger = utils.get_yf_logger()

        params = {"range": "1d", "interval": "1d"}

        # Getting data from json
        url = f"{_BASE_URL_}/v8/finance/chart/{self.ticker}"

        try:
            data = self._data.cache_get(url=url, params=params, timeout=timeout)
            data = data.json()
        except YFRateLimitError:
            # Must propagate this
            raise
        except Exception as e:
            if not YfConfig.debug.hide_exceptions:
                raise
            logger.error(f"Failed to get ticker '{self.ticker}' reason: {e}")
            return None
        else:
            error = data.get('chart', {}).get('error', None)
            if error:
                # explicit error from yahoo API
                logger.debug(f"Got error from yahoo api for ticker {self.ticker}, Error: {error}")
            else:
                try:
                    return data["chart"]["result"][0]["meta"]["exchangeTimezoneName"]
                except Exception as err:
                    if not YfConfig.debug.hide_exceptions:
                        raise
                    logger.error(f"Could not get exchangeTimezoneName for ticker '{self.ticker}' reason: {err}")
                    logger.debug("Got response: ")
                    logger.debug("-------------")
                    logger.debug(f" {data}")
                    logger.debug("-------------")
        return None

    def get_sec_filings(self) -> dict:
        return self._quote.sec_filings

    def get_major_holders(self, as_dict=False):
        data = self._holders.major
        if as_dict:
            return data.to_dict()
        return data

    def get_institutional_holders(self, as_dict=False):
        data = self._holders.institutional
        if data is not None:
            if as_dict:
                return data.to_dict()
            return data

    def get_insider_roster_holders(self, as_dict=False):
        data = self._holders.insider_roster
        if data is not None:
            if as_dict:
                return data.to_dict()
            return data

    def get_info(self) -> dict:
        data = self._quote.info
        return data

    def get_income_stmt(self, as_dict=False, pretty=False, freq="yearly"):
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            pretty: bool
                Format row names nicely for readability
                Default is False
            freq: str
                "yearly" or "quarterly" or "trailing"
                Default is "yearly"
        """

        data = self._fundamentals.financials.get_income_time_series(freq=freq)

        if pretty:
            data = data.copy()
            data.index = utils.camel2title(data.index, sep=' ', acronyms=["EBIT", "EBITDA", "EPS", "NI"])
        if as_dict:
            return data.to_dict()
        return data

    def get_incomestmt(self, as_dict=False, pretty=False, freq="yearly"):
        return self.get_income_stmt(as_dict, pretty, freq)

    def get_financials(self, as_dict=False, pretty=False, freq="yearly"):
        return self.get_income_stmt(as_dict, pretty, freq)

    def get_balance_sheet(self, as_dict=False, pretty=False, freq="yearly"):
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            pretty: bool
                Format row names nicely for readability
                Default is False
            freq: str
                "yearly" or "quarterly"
                Default is "yearly"
        """


        data = self._fundamentals.financials.get_balance_sheet_time_series(freq=freq)

        if pretty:
            data = data.copy()
            data.index = utils.camel2title(data.index, sep=' ', acronyms=["PPE"])
        if as_dict:
            return data.to_dict()
        return data

    def get_balancesheet(self, as_dict=False, pretty=False, freq="yearly"):
        return self.get_balance_sheet(as_dict, pretty, freq)

    def get_cash_flow(self, as_dict=False, pretty=False, freq="yearly") -> Union[pd.DataFrame, dict]:
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            pretty: bool
                Format row names nicely for readability
                Default is False
            freq: str
                "yearly" or "quarterly"
                Default is "yearly"
        """


        data = self._fundamentals.financials.get_cash_flow_time_series(freq=freq)

        if pretty:
            data = data.copy()
            data.index = utils.camel2title(data.index, sep=' ', acronyms=["PPE"])
        if as_dict:
            return data.to_dict()
        return data

    def get_cashflow(self, as_dict=False, pretty=False, freq="yearly"):
        return self.get_cash_flow(as_dict, pretty, freq)

    def get_shares(self, as_dict=False) -> Union[pd.DataFrame, dict]:
        data = self._fundamentals.shares
        if as_dict:
            return data.to_dict()
        return data

    @utils.log_indent_decorator
    def get_shares_full(self, start=None, end=None):
        logger = utils.get_yf_logger()


        # Process dates
        tz = self._get_ticker_tz(timeout=10)
        dt_now = pd.Timestamp.now('UTC').tz_convert(tz)
        if start is not None:
            start = utils._parse_user_dt(start, tz)
        if end is not None:
            end = utils._parse_user_dt(end, tz)
        if end is None:
            end = dt_now
        if start is None:
            start = pd.Timestamp(0, unit='s', tz='UTC').tz_convert(tz)  # jfinance: 全期間（yfinance は 18 か月）
        if start >= end:
            logger.error("Start date must be before end")
            return None
        start = start.floor("D")
        end = end.ceil("D")

        # Fetch
        ts_url_base = f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{self.ticker}?symbol={self.ticker}"
        shares_url = f"{ts_url_base}&period1={int(start.timestamp())}&period2={int(end.timestamp())}"
        try:
            json_data = self._data.cache_get(url=shares_url)
            json_data = json_data.json()
        except (_json.JSONDecodeError, requests.exceptions.RequestException):
            if not YfConfig.debug.hide_exceptions:
                raise
            logger.error(f"{self.ticker}: Yahoo web request for share count failed")
            return None
        try:
            fail = json_data["finance"]["error"]["code"] == "Bad Request"
        except KeyError:
            fail = False
        if fail:
            if not YfConfig.debug.hide_exceptions:
                raise requests.exceptions.HTTPError("Yahoo web request for share count returned 'Bad Request'")
            logger.error(f"{self.ticker}: Yahoo web request for share count failed")
            return None

        shares_data = json_data["timeseries"]["result"]
        if "shares_out" not in shares_data[0]:
            return None
        try:
            df = pd.Series(shares_data[0]["shares_out"], index=pd.to_datetime(shares_data[0]["timestamp"], unit="s"))
        except Exception as e:
            if not YfConfig.debug.hide_exceptions:
                raise
            logger.error(f"{self.ticker}: Failed to parse shares count data: {e}")
            return None

        df.index = df.index.tz_localize(tz)
        df = df.sort_index()
        return df

    def get_isin(self) -> Optional[str]:
        # *** experimental ***
        if self._isin is not None:
            return self._isin

        ticker = self.ticker.upper()

        if "-" in ticker or "^" in ticker:
            self._isin = '-'
            return self._isin

        if self._quote.info is None:
            # Don't print error message cause self._quote.info will print one
            return None
        # jfinance: 第三者のサイト（businessinsider）ではなく、EDINET の企業一覧の ISIN（info の isin）
        self._isin = self._quote.info.get('isin') or '-'
        return self._isin

    def get_funds_data(self) -> Optional[FundsData]:
        if not self._funds_data:
            self._funds_data = FundsData(self._data, self.ticker)
        
        return self._funds_data

