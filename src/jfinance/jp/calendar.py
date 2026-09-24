"""日ごとの提出の実績（jfinance だけのもの）。

yfinance の ``Calendars`` は決算発表・IPO などの**予定**。EDINET にあるのは提出の**実績**なので、名前を ``FilingCalendar`` にしている。

    cal = jf.FilingCalendar("2026-06-25", "2026-06-26")
    cal.get_filings(types=["120"])      # 有価証券報告書だけ
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional, Union

import pandas as pd

from ..config import YfConfig
from ..data import YfData
from . import _server

_COLUMNS = ["Filing Date", "Symbol", "Name", "Type", "Title", "Period End", "Doc Type Code", "EDINET Code",
            "Fund Code", "Document ID"]
_KEYS = ["filingDate", "symbol", "name", "type", "title", "periodEnd", "docTypeCode", "edinetCode", "fundCode",
         "documentId"]

DateLike = Union[str, _dt.date, _dt.datetime, pd.Timestamp]


def _day(d: Optional[DateLike]) -> str:
    return (pd.Timestamp.now("Asia/Tokyo") if d is None else pd.Timestamp(d)).strftime("%Y-%m-%d")


class FilingCalendar:
    """期間（最長 31 日）の提出書類の一覧。``start``・``end`` を省略すると今日。

    書類の種類コードの例: 120 有価証券報告書・130 訂正有価証券報告書・140 四半期報告書・160 半期報告書・
    180 臨時報告書・220 自己株券買付状況報告書・350 大量保有報告書・変更報告書
    """

    def __init__(self, start: Optional[DateLike] = None, end: Optional[DateLike] = None, session=None):
        self._start = _day(start)
        self._end = _day(end) if end is not None else self._start
        self.session = session
        self._cache: dict = {}

    def get_filings(self, types: Optional[list] = None, limit: int = 100, offset: int = 0) -> pd.DataFrame:
        """提出書類（新しい順）。``types`` は書類の種類コードのリスト。``limit`` は最大 1000"""
        key = (tuple(types or []), limit, offset)
        if key not in self._cache:
            params = {"start": self._start, "end": self._end, "types": ",".join(types or []), "size": limit,
                      "offset": offset, "lang": YfConfig.locale.lang}
            d = YfData(session=self.session).get_raw_json(_server.get_base_url() + "/jf/v1/filings", params=params)
            rows = [[r.get(k) for k in _KEYS] for r in d["filings"]["rows"]]
            df = pd.DataFrame(rows, columns=_COLUMNS)
            for c in ("Filing Date", "Period End"):
                df[c] = pd.to_datetime(df[c], unit="s")
            df.attrs["total"] = d["filings"]["total"]
            self._cache[key] = df
        return self._cache[key]

    @property
    def filings(self) -> pd.DataFrame:
        """``get_filings()`` と同じ（すべての種類、先頭 100 件）。総件数は ``.attrs["total"]``"""
        return self.get_filings()
