# このファイルは yfinance 1.5.2 の `ticker.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: Ticker（属性の名前）
# 変えた点（Apache License 2.0 第 4 条 b）:
#   - 削った: Ticker._download_options, Ticker._options2df, Ticker.option_chain, Ticker.dividends, Ticker.capital_gains, Ticker.splits, Ticker.actions, Ticker.fast_info, Ticker.valuation, Ticker.calendar, Ticker.recommendations, Ticker.recommendations_summary, Ticker.upgrades_downgrades, Ticker.earnings, Ticker.quarterly_earnings, Ticker.analyst_price_targets, Ticker.earnings_estimate, Ticker.revenue_estimate, Ticker.earnings_history, Ticker.eps_trend, Ticker.eps_revisions, Ticker.growth_estimates, Ticker.sustainability, Ticker.options, Ticker.news, Ticker.earnings_dates, Ticker.history_metadata, Ticker.mutualfund_holders, Ticker.insider_purchases, Ticker.insider_transactions, Ticker.ttm_income_stmt, Ticker.ttm_incomestmt, Ticker.ttm_financials, Ticker.ttm_cash_flow, Ticker.ttm_cashflow（株価・配当・オプション・アナリスト・ニュース・決算日・ESG スコア。投資信託の保有と役員の売買。直近 12 か月（TTM。複数の書類にまたがる計算値で出典が 1 つに決まらないのでサーバが出さない））
#   - 名前 yfinance → jfinance（import・ロガー名・repr）
#   - 差し替えた: 独自の機能を足す
#   - 差し替えた: 独自の機能（jfinance/jp/ticker.py）を足す

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

from collections import namedtuple as _namedtuple

import pandas as _pd

from .base import TickerBase
from .const import _BASE_URL_
from .scrapers.funds import FundsData
from .jp.ticker import JpTickerMixin


class Ticker(TickerBase, JpTickerMixin):
    def __init__(self, ticker, session=None):
        super(Ticker, self).__init__(ticker, session=session)
        self._expirations = {}
        self._underlying  = {}

    def __repr__(self):
        return f'jfinance.Ticker object <{self.ticker}>'

    # ------------------------

    @property
    def isin(self):
        return self.get_isin()

    @property
    def major_holders(self) -> _pd.DataFrame:
        return self.get_major_holders()

    @property
    def institutional_holders(self) -> _pd.DataFrame:
        return self.get_institutional_holders()

    @property
    def insider_roster_holders(self) -> _pd.DataFrame:
        return self.get_insider_roster_holders()

    @property
    def shares(self) -> _pd.DataFrame:
        return self.get_shares()

    @property
    def info(self) -> dict:
        return self.get_info()

    @property
    def sec_filings(self) -> dict:
        return self.get_sec_filings()

    @property
    def income_stmt(self) -> _pd.DataFrame:
        return self.get_income_stmt(pretty=True)

    @property
    def quarterly_income_stmt(self) -> _pd.DataFrame:
        return self.get_income_stmt(pretty=True, freq='quarterly')

    @property
    def incomestmt(self) -> _pd.DataFrame:
        return self.income_stmt

    @property
    def quarterly_incomestmt(self) -> _pd.DataFrame:
        return self.quarterly_income_stmt

    @property
    def financials(self) -> _pd.DataFrame:
        return self.income_stmt

    @property
    def quarterly_financials(self) -> _pd.DataFrame:
        return self.quarterly_income_stmt

    @property
    def balance_sheet(self) -> _pd.DataFrame:
        return self.get_balance_sheet(pretty=True)

    @property
    def quarterly_balance_sheet(self) -> _pd.DataFrame:
        return self.get_balance_sheet(pretty=True, freq='quarterly')

    @property
    def balancesheet(self) -> _pd.DataFrame:
        return self.balance_sheet

    @property
    def quarterly_balancesheet(self) -> _pd.DataFrame:
        return self.quarterly_balance_sheet

    @property
    def cash_flow(self) -> _pd.DataFrame:
        return self.get_cash_flow(pretty=True, freq="yearly")

    @property
    def quarterly_cash_flow(self) -> _pd.DataFrame:
        return self.get_cash_flow(pretty=True, freq='quarterly')

    @property
    def cashflow(self) -> _pd.DataFrame:
        return self.cash_flow

    @property
    def quarterly_cashflow(self) -> _pd.DataFrame:
        return self.quarterly_cash_flow

    @property
    def funds_data(self) -> FundsData:
        return self.get_funds_data()
