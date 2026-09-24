"""jfinance クライアントの結合テスト（サーバが要る）。

    JFINANCE_BASE_URL=http://127.0.0.1:4611 python client/tests/test_client.py

値は EDINET の実データで確かめたもの（2026-09-19 時点）。
"""

from __future__ import annotations

import os
import sys
import time
import warnings

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import jfinance as jf  # noqa: E402

warnings.simplefilter("ignore")
fail = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fail
    print(("  ok   " if ok else "  NG   ") + name + ("" if ok or not detail else f"\n         {detail}"))
    fail += 0 if ok else 1


def timed(fn):
    t = time.perf_counter()
    v = fn()
    return v, (time.perf_counter() - t) * 1000


print(f"== jfinance {jf.__version__} → {jf.get_base_url()}")

print("== 役員報酬の全年度（＋α。カルロス・ゴーン氏）")
oc, ms = timed(lambda: jf.Ticker("7201.T").officer_compensation)
g = oc[oc["name"].astype(str).str.contains("ゴーン")].set_index("fiscalYear") if not oc.empty else pd.DataFrame()
check(f"officer_compensation（{ms:.0f} ms）が表になる", isinstance(oc, pd.DataFrame) and len(oc) >= 10, str(oc.shape))
expect = {2014: 2313000000, 2015: 2213000000, 2016: 2894000000, 2017: 3740000000, 2018: 2869000000, 2019: 1652000000}
for fy, v in expect.items():
    got = g["totalPay"].get(fy) if not g.empty else None
    check(f"ゴーン氏 {fy} 年度 = {v / 1e8:.2f} 億円", got == v, str(got))
check("2014 年度は API 側の訂正表で直し、出典が付く",
      not g.empty and str(g["correctionSource"].get(2014) or "").startswith("https://"))
check("2015〜2018 年度は DB の訂正報告書で直っている（出典の書類は S100FRS*）",
      not g.empty and all(str(g["sourceDocumentId"].get(y)).startswith("S100FRS") for y in (2015, 2016, 2017, 2018)))

print("== ＋α の財務キー")
jp, ms = timed(lambda: jf.Ticker("7203.T").get_jp_financials())
check(f"get_jp_financials（{ms:.0f} ms）", isinstance(jp, pd.DataFrame) and "BookValuePerShare" in jp.index, str(jp.index[:5].tolist()))
check("従業員数に値がある", "NumberOfEmployees" in jp.index and jp.loc["NumberOfEmployees"].notna().sum() >= 3)
check("列は期末日の降順", list(jp.columns) == sorted(jp.columns, reverse=True))

print("== 投資信託（1306.T = G02925）")
ff, ms = timed(lambda: jf.Ticker("1306.T").get_fund_financials())
check(f"get_fund_financials（{ms:.0f} ms）", isinstance(ff, pd.DataFrame) and "FundNetAssets" in ff.index, str(ff.index[:5].tolist()))
v = ff.loc["FundNetAssets"].get(pd.Timestamp("2025-07-10")) if "FundNetAssets" in ff.index else None
check("純資産 2025-07-10 = 23,589,269,322,163 円（有報）", v == 23589269322163, str(v))
fs = jf.Ticker("G02925").get_fund_financials("semiannual")
v = fs.loc["FundNetAssets"].get(pd.Timestamp("2026-01-10")) if "FundNetAssets" in fs.index else None
check("半期 2026-01-10 = 30,049,445,684,255 円（半期報告書）", v == 30049445684255, str(v))
bs = jf.Ticker("1306.T").balance_sheet
check("yfinance の balance_sheet でもファンドの総資産が出る", "Total Assets" in bs.index and bs.loc["Total Assets"].notna().any(),
      str(bs.index[:5].tolist()))
q = jf.Ticker("1306.T").get_fund_financials("quarterly")
check("四半期はファンドに無いので空欄", isinstance(q, pd.DataFrame) and (q.empty or q.isna().all().all()))

print("== 2013 年度以前の PDF 由来の指標")
from jfinance._http import new_session  # noqa: E402

_SESSION = new_session()


def get_json(url):
    # jfinance と同じ通信部品（curl_cffi）で叩く。標準の urllib は既定の User-Agent がサーバで拒否され（403）、
    # 環境によっては CA 証明書の置き場所が無く HTTPS の検証にも失敗する
    r = _SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def ts(base, sym, typ):
    u = f"{base}/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}?type={typ}&period1=0&period2=1900000000"
    d = get_json(u)
    return {p["asOfDate"]: p for p in d["timeseries"]["result"][0][typ]}


rev, ms = timed(lambda: ts(jf.get_base_url(), "7203.T", "annualTotalRevenue"))
p13, p14, p05 = rev.get("2013-03-31", {}), rev.get("2014-03-31", {}), rev.get("2005-03-31", {})
check(f"時系列（{ms:.0f} ms）が 2005 年度まで遡る", "2005-03-31" in rev, str(sorted(rev)[:3]))
check("2013 年度は PDF 由来の連結 22,064,192 百万円（XBRL は単体しか無い年）",
      p13.get("reportedValue", {}).get("raw") == 22064192000000 and p13.get("source") == "pdf" and p13.get("consolidated") == "consolidated",
      str(p13))
check("PDF 由来の点に出所・確からしさ・期末日の精度が付く",
      p13.get("sourceKind") in ("edinet_official", "kabupro") and p13.get("confidence") is not None and p13.get("periodEndPrecision") in ("day", "month"))
check("2014 年度は XBRL の連結 25,691,911 百万円", p14.get("reportedValue", {}).get("raw") == 25691911000000 and p14.get("source") == "xbrl", str(p14))
check("2005 年度（PDF 由来）18,551,526 百万円", p05.get("reportedValue", {}).get("raw") == 18551526000000, str(p05))
nolegacy = os.environ.get("JF_NOLEGACY_URL")
if nolegacy:
    off = ts(nolegacy, "7203.T", "annualTotalRevenue")
    check("設定 JF_LEGACY=0 では PDF 由来を混ぜない（最古は XBRL の 2010 年度・単体）",
          all(p.get("source") == "xbrl" for p in off.values()) and min(off) == "2010-03-31"
          and off["2013-03-31"]["reportedValue"]["raw"] == 9755964000000, str(sorted(off)[:2]))
jf.set_financials_start("2000-01-01")
fin = jf.Ticker("7203.T").financials
jf.set_financials_start(None)
v = fin.loc["Total Revenue"].get(pd.Timestamp("2013-03-31")) if "Total Revenue" in fin.index else None
check("set_financials_start で Ticker.financials に 2013 年度以前も出る", v == 22064192000000, str(fin.columns[-3:].tolist()))

print("== 株主（名前の線引き: 2026-09-19 決定）")
t = jf.Ticker("7203.T")
ms_ = t.major_shareholders
check("major_shareholders（独自）: 有報の大株主の 1 位は日本マスタートラスト信託銀行",
      not ms_.empty and "日本マスタートラスト" in str(ms_.iloc[0]["Holder"]) and ms_.iloc[0]["Rank"] == 1, str(ms_.head(2)))
ih = jf.Ticker("8035.T").institutional_holders
check("institutional_holders（Yahoo 名）: 大量保有報告書の特例報告の機関投資家（8035 にブラックロック・ジャパン）",
      "ブラックロック・ジャパン株式会社" in set(ih["Holder"]), str(ih.head(3)))
check("institutional_holders の列は yfinance と同じ",
      list(ih.columns[:6]) == ["Date Reported", "Holder", "pctHeld", "Shares", "Value", "pctChange"], str(list(ih.columns)))
check("institutional_holders: 7203 は特例報告の保有者が 5% 以下に減ったので空（事業会社のトヨタ不動産などは入らない）",
      t.institutional_holders.empty, str(t.institutional_holders))
raw = get_json(f"{jf.get_base_url()}/v10/finance/quoteSummary/7203.T?modules=fundOwnership,insiderTransactions,netSharePurchaseActivity")
r0 = raw["quoteSummary"]["result"][0]
check("Yahoo の fundOwnership・insiderTransactions・netSharePurchaseActivity は空（EDINET に同じものが無い）",
      r0["fundOwnership"]["ownershipList"] == [] and r0["insiderTransactions"]["transactions"] == []
      and set(r0["netSharePurchaseActivity"]) == {"maxAge"}, str(r0)[:200])

print("== 大量保有の売買の集計（large_holder_activity）")
ip, ms = timed(lambda: t.large_holder_activity)
row = {r.iloc[0]: (r["Shares"], r["Trans"]) for _, r in ip.iterrows()}
lh = jf.Ticker("1301.T").large_holders
check("large_holders: 社名が変わった保有者は最新の名前で 1 行（E12430 日興アセット → アモーヴァ）",
      (lh["Holder EDINET Code"] == "E12430").sum() == 1
      and lh.loc[lh["Holder EDINET Code"] == "E12430", "Holder"].iloc[0].startswith("アモーヴァ")
      and not lh["Holder EDINET Code"].dropna().duplicated().any(), str(lh.head(3)))
lh2 = jf.Ticker("2162.T").large_holders
check("large_holders: 発行者のコードが入った行は名前で分ける（個人と会社が同じ E05676）",
      (lh2["Holder EDINET Code"] == "E05676").sum() >= 2, str(lh2[lh2["Holder EDINET Code"] == "E05676"]))
lh3 = jf.Ticker("3903.T").large_holders["Holder"].tolist()
check("large_holders: 旧名の行を、その法人のいまの名前で見せる（日興アセット → アモーヴァ）",
      any("アモーヴァ" in h for h in lh3) and not any("日興アセット" in h for h in lh3), str(lh3[:12]))
check(f"large_holder_activity（{ms:.0f} ms）に値が入る", row.get("Purchases", (None,))[0] is not None and row.get("Sales", (None,))[0] is not None, str(row))
b, s_ = row["Purchases"][0], row["Sales"][0]
check("Net = Purchases − Sales", row["Net Shares Purchased (Sold)"][0] == b - s_)
check("Total Large Holder Shares Held = 大量保有の保有者の保有株数の合計",
      row["Total Large Holder Shares Held"][0] == int(t.large_holders["Shares"].fillna(0).sum()))
raw = get_json(f"{jf.get_base_url()}/v10/finance/quoteSummary/7203.T?modules=largeHolderActivity")
nsp = raw["quoteSummary"]["result"][0]["largeHolderActivity"]
check("窓の終わり（asOfDate）と定義（basis）が付く", nsp.get("period") == "6m" and nsp.get("asOfDate") and "6 months" in nsp.get("basis", ""), str(nsp))
tx = t.large_holder_transactions
check("large_holder_transactions: 豊田自動織機の処分（2026-05-25）がある",
      ((tx["Holder"] == "株式会社豊田自動織機") & (tx["Action"] == "dispose") & (tx["Date"] == pd.Timestamp("2026-05-25"))).any(),
      str(tx.head(3)))

def _refuses_outside():
    from jfinance.data import YfData
    try:
        YfData().get("https://markets.businessinsider.com/ajax/SearchController_Suggest?query=x")
    except jf.exceptions.YFException:
        return True
    return False


print("== 独自の機能（業種・スクリーナー・提出の実績・排出量）")
s = jf.JpSector("automobiles-transportation-equipment")
check("JpSector: 自動車・輸送機の売上高 1 位はトヨタ", s.top_companies.index[0] == "7203.T" and "transportation-equipment" in s.industries.index,
      str(s.top_companies.head(2)))
check("JpSector.all() は TOPIX-17 の 17 業種", len(jf.JpSector.all()) == 17)
check("JpIndustry: 銀行業は TOPIX-17 の銀行", jf.JpIndustry("banks").sector_key == "banks")
q = jf.EdinetQuery("and", [jf.EdinetQuery("eq", ["sector", "automobiles-transportation-equipment"]),
                           jf.EdinetQuery("gt", ["roe", 0.1])])
r = jf.edinet_screen(q, sortField="revenue", size=5)
check("edinet_screen: 条件（ROE > 10%）がすべての行に効いている", r["total"] > 0 and all(x["roe"] > 0.1 for x in r["quotes"]),
      str([(x["symbol"], x.get("roe")) for x in r["quotes"]]))
check("edinet_screen: 売上高の降順", [x["revenue"] for x in r["quotes"]] == sorted([x["revenue"] for x in r["quotes"]], reverse=True))
try:
    jf.EdinetQuery("gt", ["marketcap", 1])
    check("EdinetQuery: EDINET に無い項目（時価総額）は作れない", False)
except ValueError:
    check("EdinetQuery: EDINET に無い項目（時価総額）は作れない", True)
def _post(body):
    return _SESSION.post(jf.get_base_url() + "/jf/v1/screener", json=body, timeout=30).status_code


check("サーバのスクリーナーは許可リストに無い項目・演算子・値を 400 で断る",
      _post({"query": {"operator": "GT", "operands": ["revenue) or (1=1", 1]}}) == 400
      and _post({"query": {"operator": "LIKE", "operands": ["revenue", 1]}}) == 400
      and _post({"query": {"operator": "EQ", "operands": ["industry", "x' or '1'='1"]}}) == 400
      and _post({"query": {"operator": "GT", "operands": ["revenue", "1 or 1=1"]}}) == 400)
f = jf.FilingCalendar("2026-06-25").get_filings(types=["120"], limit=5)
check("FilingCalendar: 2026-06-25 の有報", f.attrs["total"] > 100 and (f["Doc Type Code"] == "120").all(), str(f.head(2)))
em = jf.Ticker("9432.T").emissions
check("emissions: NTT の 2026-03-31 期の Scope1And2 = 2,041,000 tCO2e（有報）",
      em.loc["Scope1And2", pd.Timestamp("2026-03-31")] == 2041000, str(em))
rf = jf.Ticker("9432.T").report_filing_dates
check("report_filing_dates: NTT の有報 2026-06-16", (rf.index == pd.Timestamp("2026-06-16")).any()
      and rf.loc[pd.Timestamp("2026-06-16"), "Report Type"] == "annual", str(rf.head(3)))

print("== 段 4（サイトで見えるデータ。独自の名前）")
t = jf.Ticker("7203.T")
e = t.employees
check("employees: トヨタ 2026 年度 連結 390,927 人・提出会社 73,133 人（有報）",
      int(e.loc[e["Fiscal Year"] == 2026, "Consolidated Employees"].iloc[0]) == 390927
      and int(e.loc[e["Fiscal Year"] == 2026, "Employees"].iloc[0]) == 73133, str(e.head(2)))
check("employees(by_segment=True): セグメント別の人数", not t.get_employees(by_segment=True).empty)
o = t.get_officers(2020)
check("get_officers(2020): 2020 年度の有報の役員に豊田章男氏", o.attrs["fiscal_year"] == 2020 and (o["Name"] == "豊田章男").any(),
      str(o.head(2)))
r = t.officer_remuneration
check("officer_remuneration: 2026 年度 監査役 8,000 万円・6 人", ((r["Fiscal Year"] == 2026) & (r["Total Amount"] == 80000000)
      & (r["Officer Count"] == 6)).any(), str(r.head(2)))
nr = jf.Ticker("7201.T")
ra = nr.get_officer_remuneration(breakdown="all")
ex = ra[(ra["Fiscal Year"] == 2026) & (ra["Category"] == "jpcrp_cor:ExecutiveOfficersMember")]
rs = nr.officer_remuneration
exs = rs[(rs["Fiscal Year"] == 2026) & (rs["Category"] == "jpcrp_cor:ExecutiveOfficersMember")]
check("officer_remuneration(breakdown='all'): 日産 2026 年度 執行役の全項目の合計 = 総額 14.29 億円・標準の Base は 4.67 億円",
      ex["Value"].sum() == 1429000000 and (ex["Standard"] == "Base").sum() == 1
      and exs["Total Amount"].iloc[0] == 1429000000 and exs["Base"].iloc[0] == 467000000, str(ex))
check("officer_remuneration: 内訳の列は標準の要素だけ（会社独自の項目を寄せない）",
      set(rs.columns) == {"Fiscal Year", "Category", "Category Label", "Total Amount", "Officer Count", "Base", "Document ID"},
      str(list(rs.columns)))
a = t.audit_fees
check("audit_fees: 2026 年度 監査証明業務の報酬 合計 23.86 億円", ((a["Fiscal Year"] == 2026) & (~a["Network Firms"])
      & (a["Audit Total"] == 2386000000)).any(), str(a.head(2)))
dv = t.dividend_resolutions
check("dividend_resolutions: 2026-05-08 取締役会決議 1 株 50 円", ((dv["Resolution Date"] == pd.Timestamp("2026-05-08"))
      & (dv["Dividend Per Share"] == 50)).any(), str(dv.head(2)))
ms_ = t.get_major_shareholders(year=2015)
check("get_major_shareholders(year=2015): 1 位は日本トラスティ・サービス信託銀行", "日本トラスティ" in str(ms_.iloc[0]["Holder"]),
      str(ms_.head(1)))
check("large_holding_reports・get_filings(types=['120'])", t.large_holding_reports.attrs["total"] > 0
      and (t.get_filings(types=["120"])["Doc Type Code"] == "120").all())
sg = t.segments
check("segments: 自動車セグメントの売上高がある", ((sg["Metric"] == "seg_revenue") & (sg["Segment Label"] == "Automotive")).any())
check("segments・employees の連結区分は consolidated / standalone（言語に依らない）",
      set(sg["Consolidated"].dropna()) <= {"consolidated", "standalone"} and "consolidated" in set(sg["Consolidated"])
      and set(t.get_employees(by_segment=True)["Consolidated"].dropna()) <= {"consolidated", "standalone"})
bad = _SESSION.get(jf.get_base_url() + "/jf/v1/ticker/7203.T/officers", params={"year": "abc"}, timeout=30)
bad2 = _SESSION.get(jf.get_base_url() + "/jf/v1/ticker/7203.T/nothing", timeout=30)
check("独自の口: year=abc は 400、エラーは {\"result\": null, \"error\": {…}}",
      bad.status_code == 400 and bad.json().get("result") is None and bad.json()["error"]["code"] == "Bad Request"
      and bad2.status_code == 404 and bad2.json().get("result") is None and "error" in bad2.json(), bad.text[:200])
st = t.statements
ns = st[st["Local Name"] == "NetSales"]
check("statements: 単体の売上高 2013 年度 9,755,964 百万円（XBRL）", not ns.empty and ns.iloc[0][2013] == 9755964000000,
      str(ns.head(1)))
jf.set_financials_basis(consolidation="standalone")
v_st = jf.Ticker("7201.T").financials.loc["Total Revenue", pd.Timestamp("2026-03-31")]
jf.set_financials_basis(version="as_filed")
v_af = jf.Ticker("6995.T").financials.loc["Total Revenue", pd.Timestamp("2022-03-31")]
jf.set_financials_basis()
v_lt = jf.Ticker("6995.T").financials.loc["Total Revenue", pd.Timestamp("2022-03-31")]
check("set_financials_basis: 日産 単体 2026 年 3 月期 3,601,971 百万円", v_st == 3601971000000, str(v_st))
check("set_financials_basis(version='as_filed'): 6995 の 2022 年 3 月期 訂正前 487,303 百万円・訂正後 487,243 百万円",
      v_af == 487303000000 and v_lt == 487243000000, f"{v_af} {v_lt}")
i = t.info
check("info: fullTimeEmployees は企業集団全体（トヨタ 2026 年度 390,927 人。連結経営指標等に無い年）",
      t.info.get("fullTimeEmployees") == 390927, str(t.info.get("fullTimeEmployees")))
check("info: fullTimeEmployees（日産 2026 年度 120,079 人）", jf.Ticker("7201.T").info.get("fullTimeEmployees") == 120079)
check("info: 法人番号・上場区分・JpSector のキー", i.get("corporateNumber") == "1180301018771" and i.get("listingStatus") == "listed"
      and i.get("sectorKey") == "automobiles-transportation-equipment")

print("== yfinance の書き方がそのまま使える")
t = jf.Ticker("E02144")
check("info", "TOYOTA" in str(t.info.get("shortName")))
check("Search", any(x.get("symbol") == "7203.T" for x in jf.Search("トヨタ").quotes))
print("== 言語（既定は英語。yfinance と同じ config.locale.lang で日本語）")
i = jf.Ticker("7203.T").info
check("既定は英語の社名・JPX の英語の業種名", i.get("shortName") == "TOYOTA MOTOR CORPORATION" and i.get("industry") == "Transportation"
      and i.get("sector") == "Automobiles & Transportation Equipment", str({k: i.get(k) for k in ("shortName", "industry", "sector")}))
jf.config.locale.lang = "ja-JP"
i = jf.Ticker("7203.T").info
jf.config.locale.lang = "en-US"
check("lang = ja-JP で日本語", i.get("shortName") == "トヨタ自動車株式会社" and i.get("industry") == "輸送用機器",
      str({k: i.get(k) for k in ("shortName", "industry", "sector")}))
check("ISIN で指定できる（サーバの search で記号に直す）", jf.Ticker("JP3633400001").ticker == "7203.T")
check("(記号, 取引所コード) で指定できる", jf.Ticker(("7203", "XTKS")).ticker == "7203.T")
for name in ["history", "fast_info", "dividends", "news", "mutualfund_holders", "insider_transactions"]:
    check(f"{name} は持たない（AttributeError）", not hasattr(t, name))
check("jfinance のサーバ以外へは送らない", _refuses_outside())

print()
print("すべて通過" if fail == 0 else f"★NG {fail} 件")
sys.exit(0 if fail == 0 else 1)
