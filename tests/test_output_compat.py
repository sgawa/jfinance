"""返り値の互換テスト: 同じサーバに対して yfinance と jfinance を実行し、返り値を比べる。

    JFINANCE_BASE_URL=https://query1.jfnc.org python tests/test_output_compat.py

■ yfinance は「正解の形」を作るためだけに使う（pip install "jfinance[compat-test]"）。jfinance 本体は使わない。
  yfinance を jfinance のサーバへ向けるため、このテストの中でだけ yfinance の通信先を差し替える。
■ 比べるもの: 型・DataFrame の行と列（名前・順番）・値。Yahoo と同じ名前で出すものだけを比べる
  （持たないもの・独自の名前のものは tests/test_api_compat.py と tests/test_client.py）。
  財務諸表の開始日は yfinance が 2016-12-31 に固定しているので、jfinance も同じ開始日にして比べる
  （jfinance の既定は全期間）。
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import time
import warnings

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import jfinance as jf  # noqa: E402

try:
    import yfinance as yf
    from curl_cffi import requests as cr
    from yfinance.data import YfData
except ImportError:
    print("yfinance が無いので飛ばす（pip install \"jfinance[compat-test]\"）")
    sys.exit(0)

warnings.simplefilter("ignore")
BASE = jf.get_base_url()


class _ToJf(cr.Session):
    """yfinance の Yahoo 宛ての要求を jfinance のサーバへ向ける（このテストの中だけ）

    公開サーバに向けると回数制限（既定 60 回・毎秒 0.5 回回復）に当たる。
    サーバは 429 に ``Retry-After`` を付けて返すので、**それに従って待ち直す**。
    yfinance 側は 429 を即座に例外にするため、ここで吸収しないとテストが途中で落ちる。
    """

    def request(self, method, url, *a, **k):
        for h in ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com", "https://finance.yahoo.com"):
            if url.startswith(h):
                url = BASE + url[len(h):]
        for _ in range(6):
            res = super().request(method, url, *a, **k)
            if res.status_code != 429:
                return res
            time.sleep(float(res.headers.get("Retry-After", 10)))
        return res


YfData._get_cookie_and_crumb = lambda self, timeout=30: ("jfinance", "basic")
SESSION = _ToJf()
jf.set_financials_start(pd.Timestamp(dt.datetime(2016, 12, 31).astimezone()))   # yfinance と同じ開始日

fail = 0
n = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fail, n
    n += 1
    print(("  ok   " if ok else "  NG   ") + name + ("" if ok or not detail else f"\n         {detail}"))
    fail += 0 if ok else 1


def same(name, a, b):
    """a = yfinance, b = jfinance"""
    try:
        if isinstance(a, pd.DataFrame) or isinstance(b, pd.DataFrame):
            ok = isinstance(b, pd.DataFrame) and isinstance(a, pd.DataFrame)
            if ok:
                pd.testing.assert_frame_equal(a, b, check_dtype=False, check_index_type=False,
                                              check_column_type=False, check_names=True)
            check(name, ok)
        elif isinstance(a, pd.Series) or isinstance(b, pd.Series):
            pd.testing.assert_series_equal(a, b, check_dtype=False, check_index_type=False, check_names=False)
            check(name, True)
        else:
            check(name, a == b, f"yfinance {str(a)[:150]}\n         jfinance {str(b)[:150]}")
    except AssertionError as e:
        check(name, False, str(e).replace("\n", " ")[:300])


def run(sym: str, company: bool) -> None:
    y = yf.Ticker(sym, session=SESSION)
    j = jf.Ticker(sym)
    print(f"== {sym}")
    # trailingPegRatio は株価に依存するので jfinance は持たない（yfinance は None を入れる）
    same("info（trailingPegRatio を除く）", {k: v for k, v in y.info.items() if k != "trailingPegRatio"}, j.info)
    same("info に trailingPegRatio は無い", False, "trailingPegRatio" in j.info)
    for attr in ["financials", "income_stmt", "balance_sheet", "cashflow", "quarterly_financials",
                 "quarterly_balance_sheet", "quarterly_cashflow"]:
        same(attr, getattr(y, attr), getattr(j, attr))
    same("get_income_stmt(pretty=False)", y.get_income_stmt(), j.get_income_stmt())
    same("get_income_stmt(freq='trailing')", y.get_income_stmt(freq="trailing"), j.get_income_stmt(freq="trailing"))
    same("get_balance_sheet(as_dict=True)", pd.DataFrame(y.get_balance_sheet(as_dict=True)),
         pd.DataFrame(j.get_balance_sheet(as_dict=True)))
    if company:
        for attr in ["major_holders", "institutional_holders", "insider_roster_holders"]:
            same(attr, getattr(y, attr), getattr(j, attr))
        start = "2020-01-01"
        same("get_shares_full(start)", y.get_shares_full(start=start), j.get_shares_full(start=start))
    same("sec_filings", y.sec_filings, j.sec_filings)
    if not company:
        yd, jd = y.funds_data, j.funds_data
        same("funds_data.fund_overview", yd.fund_overview, jd.fund_overview)
        same("funds_data.fund_operations", yd.fund_operations, jd.fund_operations)
    # 持たない名前は jfinance に無い（呼ぶと AttributeError）
    for attr in ["history", "fast_info", "dividends", "calendar", "news", "options", "analyst_price_targets",
                 "mutualfund_holders", "insider_transactions", "insider_purchases", "ttm_financials"]:
        same(f"{attr} は持たない", False, hasattr(j, attr))


run("7203.T", True)
run("E02142", True)
run("1306.T", False)

print("== Search・Lookup")
same("Search.quotes", yf.Search("トヨタ", session=SESSION).quotes, jf.Search("トヨタ").quotes)
same("Lookup.get_all", yf.Lookup("日産", session=SESSION).get_all(), jf.Lookup("日産").get_all())

print(f"\n{n} 項目を比べた")
print("すべて通過" if fail == 0 else f"★NG {fail} 件")
sys.exit(0 if fail == 0 else 1)
