"""EDINET の項目で銘柄を絞り込む（jfinance だけのもの）。

yfinance の ``screen``・``EquityQuery`` と同じ書き方で、項目だけが EDINET のもの（有報の財務指標・東証の業種・市場区分）。
Yahoo の項目（株価・時価総額など）は使えないので、名前を ``edinet_screen``・``EdinetQuery`` にしている。

    import jfinance as jf
    q = jf.EdinetQuery("and", [
        jf.EdinetQuery("eq", ["sector", "automobiles-transportation-equipment"]),
        jf.EdinetQuery("gt", ["roe", 0.1]),
    ])
    jf.edinet_screen(q, sortField="revenue")["quotes"]

条件の土台（演算子の検証・``to_dict``）は yfinance の ``QueryBase``（jfinance/screener/query.py にコピー）。
"""

from __future__ import annotations

from typing import Dict, Optional

from ..data import YfData
from ..screener.query import QueryBase
from ..utils import dynamic_docstring, generate_list_table_from_dict_universal
from . import _server
from ._screen_fields import CATEGORICAL_VALUES, METRIC_FIELDS

_FIELDS = {**METRIC_FIELDS, "categorical": {k: k for k in CATEGORICAL_VALUES}}


class EdinetQuery(QueryBase):
    """
    EDINET の項目で条件を作る。演算子は yfinance の EquityQuery と同じ:
    値の比較 ``eq``・``is-in``・``btwn``・``gt``・``lt``・``gte``・``lte``、組み合わせ ``and``・``or``。

    - 数値の項目（``revenue``・``roe``・``employees`` など）は有報の値。比率は小数（0.1 = 10%）
    - 分類の項目: ``industry``（東証 33 業種のキー）・``sector``（TOPIX-17 のキー）・``market``（prime / standard / growth / pro）・
      ``listing``（listed / unlisted）・``accountingStandard``・``fiscalMonth``（決算月 1〜12）
    """

    @dynamic_docstring({"valid_operand_fields_table": generate_list_table_from_dict_universal(_FIELDS)})
    @property
    def valid_fields(self) -> Dict:
        """
        Valid operands, grouped by category.
        {valid_operand_fields_table}
        """
        return _FIELDS

    @property
    def valid_values(self) -> Dict:
        """分類の項目で使える値"""
        return CATEGORICAL_VALUES


def edinet_screen(query: EdinetQuery, offset: Optional[int] = None, size: Optional[int] = None,
                  sortField: Optional[str] = None, sortAsc: Optional[bool] = None,
                  year: Optional[int] = None, scope: str = "consolidated", session=None) -> dict:
    """条件に合う会社を返す。返り値は yfinance の ``screen`` と同じ形（``quotes``・``total``・``start``・``count``）。

    :Parameters:
        query : EdinetQuery
        offset : int  先頭から飛ばす件数。既定 0
        size : int  返す件数。既定 100、最大 250
        sortField : str  並べる項目（数値の項目）。既定は証券コード順
        sortAsc : bool  昇順か。既定 False
        year : int  年度（rm_screen の年度。既定はほぼ全社がそろった最新の年度。返り値の ``fiscalYear``）
        scope : str  ``consolidated``（連結。既定）か ``standalone``（単体）
    """
    if not isinstance(query, EdinetQuery):
        raise TypeError("query must be EdinetQuery")
    if size is not None and size > 250:
        raise ValueError("jfinance limits query size to 250, reduce size.")
    body = {"query": query.to_dict(), "offset": offset or 0, "size": size or 100, "scope": scope,
            "sortType": "ASC" if sortAsc else "DESC"}
    if sortField is not None:
        body["sortField"] = sortField
    if year is not None:
        body["year"] = int(year)
    data = YfData(session=session)
    r = data.post(_server.get_base_url() + "/jf/v1/screener", body=body)
    r.raise_for_status()
    return r.json()["finance"]["result"][0]
