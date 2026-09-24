# このファイルは yfinance 1.5.2 の `tickers.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: Tickers
# 変えた点（Apache License 2.0 第 4 条 b）:
#   - 削った: Tickers.history, Tickers.download, Tickers.news, Tickers.live（株価・ニュース・リアルタイム）
#   - 名前 yfinance → jfinance（import・ロガー名・repr）
#   - 差し替えた: download を持たない
#   - 差し替えた: リアルタイムを持たない
#   - 差し替えた: 株価の期間の既定値は要らない

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

from . import Ticker
from .data import YfData


class Tickers:

    def __repr__(self):
        return f"jfinance.Tickers object <{','.join(self.symbols)}>"

    def __init__(self, tickers, session=None):
        tickers = tickers if isinstance(
            tickers, list) else tickers.replace(',', ' ').split()
        self.symbols = [ticker.upper() for ticker in tickers]
        self.tickers = {ticker: Ticker(ticker, session=session) for ticker in self.symbols}

        self._data = YfData(session=session)

        self._message_handler = None
        self.ws = None

        # self.tickers = _namedtuple(
        #     "Tickers", ticker_objects.keys(), rename=True
        # )(*ticker_objects.values())

