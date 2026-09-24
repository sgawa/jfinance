# このファイルは yfinance 1.5.2 の `shared.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: 共有の状態
# 変えた点（Apache License 2.0 第 4 条 b）:
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

import threading

_DFS = {}
_PROGRESS_BAR = None
_ERRORS = {}
_TRACEBACKS = {}
_ISINS = {}
_LOCK = threading.Lock()
