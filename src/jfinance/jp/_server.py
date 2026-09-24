"""通信先（jfinance のサーバ）と、財務の開始日。

yfinance からコピーしたコードは Yahoo の URL（``https://query2.finance.yahoo.com/...``）を組み立てる。
``YfData`` が送る直前に :func:`to_server_url` で jfinance のサーバの URL に置き換える。
**Yahoo・第三者のサイトには一切送らない**（置き換えられない宛先は例外にする）。
"""

from __future__ import annotations

import datetime as _dt
import os

DEFAULT_BASE_URL = "https://query1.jfnc.org"

# jfinance のサーバは Yahoo Finance と同じパスで答えるので、ホストだけを置き換える
_YAHOO_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com", "https://finance.yahoo.com")

_base_url = os.environ.get("JFINANCE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
_financials_start = _dt.datetime.fromtimestamp(0, _dt.timezone.utc)


def set_base_url(url: str) -> None:
    """接続先のサーバを変える（環境変数 ``JFINANCE_BASE_URL`` でも同じ）。"""
    global _base_url
    _base_url = url.rstrip("/")


def get_base_url() -> str:
    return _base_url


def to_server_url(url: str) -> str:
    """Yahoo の URL を jfinance のサーバの URL にする。すでにサーバの URL ならそのまま。"""
    if url.startswith(_base_url + "/") or url == _base_url:
        return url
    for h in _YAHOO_HOSTS:
        if url.startswith(h + "/") or url == h:
            return _base_url + url[len(h):]
    from ..exceptions import YFException
    raise YFException(f"jfinance does not send requests outside the jfinance server: {url.split('?')[0]}")


def set_financials_start(start) -> None:
    """財務諸表（``financials`` など）の開始日。

    既定（``None``）は**サーバにあるすべての年度**。yfinance と同じにしたいときは
    ``set_financials_start("2016-12-31")``（yfinance は 2016-12-31 に固定している）。
    """
    global _financials_start
    if start is None:
        _financials_start = _dt.datetime.fromtimestamp(0, _dt.timezone.utc)
        return
    import pandas as pd
    ts = pd.Timestamp(start)
    _financials_start = (ts.tz_localize("UTC") if ts.tzinfo is None else ts).to_pydatetime()


def financials_start() -> _dt.datetime:
    return _financials_start


_basis = {"consolidation": "auto", "version": "latest"}


def set_financials_basis(consolidation: str = "auto", version: str = "latest") -> None:
    """財務諸表（``financials``・``balance_sheet``・``cashflow`` など）の連結区分と版。

    - ``consolidation``: ``"auto"``（既定。連結を優先し、連結が無ければ単体）・``"consolidated"``（連結だけ）・
      ``"standalone"``（単体だけ）
    - ``version``: ``"latest"``（既定。訂正報告書を反映）・``"as_filed"``（提出時の値。訂正で変わった値は訂正前に戻す）
    """
    if consolidation not in ("auto", "consolidated", "standalone"):
        raise ValueError("consolidation must be 'auto', 'consolidated' or 'standalone'")
    if version not in ("latest", "as_filed"):
        raise ValueError("version must be 'latest' or 'as_filed'")
    _basis.update(consolidation=consolidation, version=version)


def financials_query() -> str:
    """財務の時系列の URL に足すパラメータ（既定のときは足さない。Yahoo と同じ URL のまま）"""
    if _basis == {"consolidation": "auto", "version": "latest"}:
        return ""
    return f"&consolidation={_basis['consolidation']}&version={_basis['version']}"
