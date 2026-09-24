"""東証の業種（jfinance だけのもの）。

yfinance の ``Sector``・``Industry``（Yahoo の業種分類。中身の大半が時価総額など株価に依存）の代わりに、
東証の業種分類で同じような使い方をする。

    jf.JpSector("automobiles-transportation-equipment").top_companies   # TOPIX-17 業種
    jf.JpIndustry("transportation-equipment").top_companies             # 東証 33 業種
    jf.JpSector.all()                                                   # TOPIX-17 の一覧

- 業種の英語名は JPX の公表した英語名（``config.locale.lang`` を ``ja-JP`` にすると和文名）
- ``top_companies`` は**最新の年度の売上高**の順（Yahoo は時価総額の比重の順。株価が無いので売上高で並べる）
"""

from __future__ import annotations

import pandas as pd

from ..config import YfConfig
from ..data import YfData
from . import _server


def _get(path: str, session=None) -> dict:
    params = {"lang": YfConfig.locale.lang, "region": YfConfig.locale.region}
    return YfData(session=session).get_raw_json(_server.get_base_url() + path, params=params)


def _companies(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["symbol", "name", "edinetCode", "revenue", "fiscalYear"])
    return df.set_index("symbol")


class _JpDomain:
    _PATH = ""
    _ROOT = ""

    def __init__(self, key: str, session=None):
        self._key = key
        self.session = session
        self._data = None

    def _fetch(self) -> dict:
        if self._data is None:
            self._data = _get(f"{self._PATH}/{self._key}", self.session)[self._ROOT]
        return self._data

    @property
    def key(self) -> str:
        return self._key

    @property
    def name(self) -> str:
        return self._fetch()["name"]

    @property
    def overview(self) -> dict:
        """社数など。``topCompaniesBasis`` は top_companies の並べ方"""
        return dict(self._fetch()["overview"])

    @property
    def top_companies(self) -> pd.DataFrame:
        """属する上場会社（最新の年度の売上高の順）。Columns: name edinetCode revenue fiscalYear"""
        return _companies(self._fetch()["topCompanies"])


class JpSector(_JpDomain):
    """TOPIX-17 の 1 業種。キーは ``JpSector.all()`` の ``key``。"""
    _PATH = "/jf/v1/sectors"
    _ROOT = "sector"

    @property
    def industries(self) -> pd.DataFrame:
        """属する東証 33 業種。index = キー、Columns: name companiesCount"""
        df = pd.DataFrame(self._fetch()["industries"], columns=["key", "name", "companiesCount"])
        return df.set_index("key")

    @staticmethod
    def all(session=None) -> pd.DataFrame:
        """TOPIX-17 の一覧。index = キー、Columns: name companiesCount industriesCount"""
        df = pd.DataFrame(_get("/jf/v1/sectors", session)["sectors"],
                          columns=["key", "name", "companiesCount", "industriesCount"])
        return df.set_index("key")


class JpIndustry(_JpDomain):
    """東証 33 業種の 1 業種。キーは ``JpSector(...).industries`` の index（yuhodb.com の URL と同じ）。"""
    _PATH = "/jf/v1/industries"
    _ROOT = "industry"

    @property
    def sector_key(self) -> str:
        return self._fetch()["sectorKey"]

    @property
    def sector_name(self) -> str:
        return self._fetch()["sectorName"]
