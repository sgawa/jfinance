# このファイルは yfinance 1.5.2 の `lookup.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: Lookup
# 変えた点（Apache License 2.0 第 4 条 b）:
#   - 削った: Lookup.get_index, Lookup.get_future, Lookup.get_currency, Lookup.get_cryptocurrency, Lookup.index, Lookup.future, Lookup.currency, Lookup.cryptocurrency（指数・先物・通貨・暗号資産（EDINET に無い））
#   - 名前 yfinance → jfinance（import・ロガー名・repr）

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

import json as _json
import pandas as pd

from . import utils
from .config import YfConfig
from .const import _QUERY1_URL_
from .data import YfData
from .exceptions import YFDataException

LOOKUP_TYPES = ["all", "equity", "mutualfund", "etf", "index", "future", "currency", "cryptocurrency"]


class Lookup:
    """
    Fetches quote (ticker) lookups from Yahoo Finance.

    :param query: The search query for financial data lookup.
    :type query: str
    :param session: Custom HTTP session for requests (default None).
    :param timeout: Request timeout in seconds (default 30).
    :param raise_errors: Raise exceptions on error (default True).
    """

    def __init__(self, query: str, session=None, timeout=30, raise_errors=True):
        self.session = session
        self._data = YfData(session=self.session)

        self.query = query

        self.timeout = timeout
        self.raise_errors = raise_errors

        self._logger = utils.get_yf_logger()

        self._cache = {}

    def _fetch_lookup(self, lookup_type="all", count=25) -> dict:
        cache_key = (lookup_type, count)
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{_QUERY1_URL_}/v1/finance/lookup"
        params = {
            "query": self.query,
            "type": lookup_type,
            "start": 0,
            "count": count,
            "formatted": False,
            "fetchPricingData": True,
            "lang": "en-US",
            "region": "US"
        }

        self._logger.debug(f'GET Lookup for ticker ({self.query}) with parameters: {str(dict(params))}')

        data = self._data.get(url=url, params=params, timeout=self.timeout)
        if data is None or "Will be right back" in data.text:
            raise YFDataException("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***")
        try:
            data = data.json()
        except _json.JSONDecodeError:
            if not YfConfig.debug.hide_exceptions:
                raise
            self._logger.error(f"{self.ticker}: 'lookup' fetch received faulty data")
            data = {}

        # Error returned
        if data.get("finance", {}).get("error", {}):
            error = data.get("finance", {}).get("error", {})
            raise YFDataException(f"{self.ticker}: 'lookup' fetch returned error: {error}")

        self._cache[cache_key] = data
        return data

    @staticmethod
    def _parse_response(response: dict) -> pd.DataFrame:
        finance = response.get("finance", {})
        result = finance.get("result", [])
        result = result[0] if len(result) > 0 else {}
        documents = result.get("documents", [])
        df = pd.DataFrame(documents)
        if "symbol" not in df.columns:
            return pd.DataFrame()
        return df.set_index("symbol")

    def _get_data(self, lookup_type: str, count: int = 25) -> pd.DataFrame:
        return self._parse_response(self._fetch_lookup(lookup_type, count))

    def get_all(self, count=25) -> pd.DataFrame:
        """
        Returns all available financial instruments.

        :param count: The number of results to retrieve.
        :type count: int
        """
        return self._get_data("all", count)

    def get_stock(self, count=25) -> pd.DataFrame:
        """
        Returns stock related financial instruments.

        :param count: The number of results to retrieve.
        :type count: int
        """
        return self._get_data("equity", count)

    def get_mutualfund(self, count=25) -> pd.DataFrame:
        """
        Returns mutual funds related financial instruments.

        :param count: The number of results to retrieve.
        :type count: int
        """
        return self._get_data("mutualfund", count)

    def get_etf(self, count=25) -> pd.DataFrame:
        """
        Returns ETFs related financial instruments.

        :param count: The number of results to retrieve.
        :type count: int
        """
        return self._get_data("etf", count)

    @property
    def all(self) -> pd.DataFrame:
        """Returns all available financial instruments."""
        return self._get_data("all")

    @property
    def stock(self) -> pd.DataFrame:
        """Returns stock related financial instruments."""
        return self._get_data("equity")

    @property
    def mutualfund(self) -> pd.DataFrame:
        """Returns mutual funds related financial instruments."""
        return self._get_data("mutualfund")

    @property
    def etf(self) -> pd.DataFrame:
        """Returns ETFs related financial instruments."""
        return self._get_data("etf")

