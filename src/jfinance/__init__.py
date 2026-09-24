#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# jfinance — EDINET（金融庁の電子開示システム）のデータを、yfinance と同じ書き方で。
#
# yfinance（https://github.com/ranaroussi/yfinance, Apache License 2.0, Copyright 2017-2019 Ran Aroussi）の
# __init__.py をもとにした。変えた点: EDINET に無い機能（download・Market・WebSocket・Calendars・Sector・Industry・
# screen・Auth・set_tz_cache_location）を import しない。jfinance だけのもの（set_base_url・EdinetQuery・JpSector・
# FilingCalendar など。jfinance/jp/）を足す。
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

from . import version
from .search import Search
from .lookup import Lookup
from .ticker import Ticker
from .tickers import Tickers
from .utils import enable_debug_mode
from .config import YfConfig as config
from .jp._server import set_base_url, get_base_url, set_financials_start, set_financials_basis, DEFAULT_BASE_URL
from .jp.screener import EdinetQuery, edinet_screen
from .jp.sector import JpSector, JpIndustry
from .jp.calendar import FilingCalendar

__version__ = version.version
__author__ = "jfinance contributors"

import warnings
warnings.filterwarnings('default', category=DeprecationWarning, module='^jfinance')

__all__ = ['Search', 'Lookup', 'Ticker', 'Tickers', 'enable_debug_mode']

# Config stuff:
_NOTSET=object()
def set_config(proxy=_NOTSET, retries=_NOTSET):
    if proxy is not _NOTSET:
        warnings.warn("Set proxy via new config control: yf.config.network.proxy = proxy", DeprecationWarning)
        config.network.proxy = proxy
    if retries is not _NOTSET:
        warnings.warn("Set retries via new config control: yf.config.network.retries = retries", DeprecationWarning)
        config.network.retries = retries
__all__ += ['config', 'set_config']

# jfinance だけのもの
NOTICE_CORRECTIONS = (
    "EDINET の閲覧期間が満了した書類への訂正報告書は取得できないため、反映できない場合があります。"
)
__all__ += ['set_base_url', 'get_base_url', 'set_financials_start', 'set_financials_basis', 'DEFAULT_BASE_URL', 'NOTICE_CORRECTIONS',
            'EdinetQuery', 'edinet_screen', 'JpSector', 'JpIndustry', 'FilingCalendar']
