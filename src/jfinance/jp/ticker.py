"""Ticker に足す jfinance だけの機能（yfinance に無いもの）。

``jfinance.Ticker`` は、yfinance からコピーした ``TickerBase`` とこの ``JpTickerMixin`` を合わせたもの。
名前は yfinance と紛らわしくしない。書き方は yfinance の作法（属性と ``get_…()`` の対、表は DataFrame）にそろえる。
"""

from __future__ import annotations

import json
from typing import Optional
from urllib.parse import quote

import pandas as pd

from .. import utils
from ..config import YfConfig
from ..const import _BASE_URL_
from . import _server
from ._keys import EXTRA_KEYS, FUND_KEYS

_QUOTE_SUMMARY_URL_ = f"{_BASE_URL_}/v10/finance/quoteSummary"
_TIMESERIES_URL_ = f"{_BASE_URL_}/ws/fundamentals-timeseries/v1/finance/timeseries"
_FREQ = {"yearly": "annual", "quarterly": "quarterly", "semiannual": "semiannual"}
_PERIOD = {"yearly": "FY", "semiannual": "HY", "quarterly": "Q"}
_CONS = {None: "", "auto": "", "consolidated": "consolidated", "standalone": "standalone"}
# 役員区分別の報酬の内訳のうち、EDINET の標準の要素（サーバの breakdownStd のキー → 列名）。
# キーと要素の対応は DB の取り込み（apps/duckdb/ingest/sql_officers.py edinet_remuneration_std_key）と同じ。
# 会社独自の項目はここへ寄せない（意味の違う項目が混ざるため。サイトと同じ方針）
_REMUNERATION_STD = {"fixed": "Fixed", "base": "Base", "performance_based": "Performance Based", "bonus": "Bonus",
                     "non_monetary": "Non Monetary", "share_awards": "Share Awards",
                     "restricted_share_awards": "Restricted Share Awards",
                     "performance_linked_share_awards": "Performance Linked Share Awards",
                     "share_option": "Share Option", "retirement": "Retirement"}
_REMUNERATION_STD_LOCAL = {
    "FixedRemunerationRemunerationByCategoryOfDirectorsAndOtherOfficers": "fixed",
    "BaseRemunerationRemunerationEtcByCategoryOfDirectorsAndOtherOfficers": "base",
    "PerformanceBasedRemunerationRemunerationByCategoryOfDirectorsAndOtherOfficers": "performance_based",
    "NonMonetaryRemunerationRemunerationByCategoryOfDirectorsAndOtherOfficers": "non_monetary",
    "BonusRemunerationEtcByCategoryOfDirectorsAndOtherOfficers": "bonus",
    "RetirementBenefitsRemunerationEtcByCategoryOfDirectorsAndOtherOfficers": "retirement",
    "RestrictedShareAwardsRemunerationEtcByCategoryOfDirectorsAndOtherOfficers": "restricted_share_awards",
    "ShareOptionRemunerationEtcByCategoryOfDirectorsAndOtherOfficers": "share_option",
    "ShareAwardsRemunerationEtcByCategoryOfDirectorsAndOtherOfficers": "share_awards",
    "PerformanceLinkedShareAwardsRemunerationEtcByCategoryOfDirectorsAndOtherOfficers": "performance_linked_share_awards",
}
_CHUNK_KEYS = 60   # scrapers/fundamentals.py と同じ（URL を長くしすぎない）


class JpTickerMixin:
    """EDINET にあって yfinance に無いもの。"""

    # ------------------------------------------------------------------ 通信

    def _jp_module(self, name: str) -> dict:
        """quoteSummary の 1 モジュール（jfinance の独自モジュール）。無ければ {}"""
        cache = self.__dict__.setdefault("_jp_modules", {})
        if name not in cache:
            params = {"modules": name, "formatted": "false", "symbol": self.ticker,
                      "lang": YfConfig.locale.lang, "region": YfConfig.locale.region}
            try:
                result = self._data.get_raw_json(f"{_QUOTE_SUMMARY_URL_}/{quote(self.ticker, safe='')}", params=params)
                cache[name] = ((result.get("quoteSummary") or {}).get("result") or [{}])[0].get(name) or {}
            except Exception as e:
                if not YfConfig.debug.hide_exceptions:
                    raise
                utils.get_yf_logger().error(f"{self.ticker}: {name}: {e}")
                cache[name] = {}
        return cache[name]

    def _jp_dataset(self, dataset: str, **params) -> dict:
        """/jf/v1/ticker/{記号}/{dataset} の result（jfinance だけの口）"""
        cache = self.__dict__.setdefault("_jp_datasets", {})
        key = (dataset, tuple(sorted((k, v) for k, v in params.items() if v is not None)))
        if key not in cache:
            q = {k: v for k, v in params.items() if v is not None}
            q.update({"lang": YfConfig.locale.lang, "region": YfConfig.locale.region})
            url = f"{_server.get_base_url()}/jf/v1/ticker/{quote(self.ticker, safe='')}/{dataset}"
            try:
                cache[key] = self._data.get_raw_json(url, params=q).get("result") or {}
                if cache[key].get("minFiscalYear") is not None:
                    self.__dict__["_jp_min_fy"] = int(cache[key]["minFiscalYear"])
            except Exception as e:
                if not YfConfig.debug.hide_exceptions:
                    raise
                utils.get_yf_logger().error(f"{self.ticker}: {dataset}: {e}")
                cache[key] = {}
        return cache[key]

    @property
    def min_fiscal_year(self) -> Optional[int]:
        """サーバが出す期間の下限（会計年度）。制限が無いサーバでは None。

        これより前のデータは、例外ではなく**空**で返る。jfinance のサーバ（query1.jfnc.org）は、
        今後この下限を 2016 年度にする予定。自分で立てたサーバの既定は制限なし。
        いちど独自の口を呼ぶまでは分からないので、それまでは None。
        """
        return self.__dict__.get("_jp_min_fy")

    @staticmethod
    def _period(freq: str) -> str:
        if freq not in _PERIOD:
            raise ValueError(f"Illegal argument: freq must be one of: {list(_PERIOD)}")
        return _PERIOD[freq]

    @staticmethod
    def _cons(consolidated) -> str:
        if consolidated not in _CONS:
            raise ValueError("consolidated must be None, 'consolidated' or 'standalone'")
        return _CONS[consolidated] or None

    def _jp_timeseries(self, keys: list, freq: str, start) -> pd.DataFrame:
        """時系列のキーを取り、行 = キー・列 = 期末日（新しい順）の表にする"""
        if freq not in _FREQ:
            raise ValueError(f"Illegal argument: freq must be one of: {list(_FREQ)}")
        prefix = _FREQ[freq]
        p1 = 0 if start is None else int(utils._parse_user_dt(start, "UTC").timestamp())
        p2 = int(pd.Timestamp.now("UTC").ceil("D").timestamp())
        base = f"{_TIMESERIES_URL_}/{quote(self.ticker, safe='')}?symbol={quote(self.ticker, safe='')}"
        table: dict = {}
        for i in range(0, len(keys), _CHUNK_KEYS):
            chunk = keys[i:i + _CHUNK_KEYS]
            url = base + "&type=" + ",".join(prefix + k for k in chunk) + f"&period1={p1}&period2={p2}"
            try:
                data = json.loads(self._data.cache_get(url=url).text)
            except Exception as e:
                if not YfConfig.debug.hide_exceptions:
                    raise
                utils.get_yf_logger().error(f"{self.ticker}: timeseries: {e}")
                return pd.DataFrame()
            for item in (data.get("timeseries") or {}).get("result") or []:
                t = ((item.get("meta") or {}).get("type") or [None])[0]
                if not t:
                    continue
                for p in item.get(t) or []:
                    v = (p.get("reportedValue") or {}).get("raw")
                    if v is not None:
                        table.setdefault(t[len(prefix):], {})[pd.Timestamp(p["asOfDate"])] = v
        df = pd.DataFrame(table).T if table else pd.DataFrame()
        df = df.reindex([k for k in keys if k in table] + [k for k in keys if k not in table])
        if len(df.columns):
            df = df[sorted(df.columns, reverse=True)]
        return df

    # ------------------------------------------------------------------ 株主（大量保有報告書・有報の大株主）
    #
    # Yahoo の mutualfund_holders（投資信託）・insider_transactions / insider_purchases（役員の売買）とは
    # 「誰の値か」が違うので、独自の名前にしている（docs/reference/compatibility.md の線引き）。

    def _jp_frame(self, rows: list, columns: dict, dates=()) -> pd.DataFrame:
        """サーバの行（dict）を、columns（サーバのキー → 列名）の順の表にする。dates の列は UNIX 秒 → 日時。

        サーバが出す期間の下限を持つときは、表の ``.attrs["min_fiscal_year"]`` に入れる
        （その年度より前は返らない。詳しくは docs/data_notes.md「出す期間の下限」）
        """
        df = pd.DataFrame([{k: r.get(k) for k in columns} for r in rows], columns=list(columns))
        for c in dates:
            df[c] = pd.to_datetime(df[c], unit="s")
        df = df.rename(columns=columns)
        if self.min_fiscal_year is not None:
            df.attrs["min_fiscal_year"] = self.min_fiscal_year
        return df

    @property
    def major_shareholders(self) -> pd.DataFrame:
        return self.get_major_shareholders()

    def get_major_shareholders(self, as_dict=False, year: Optional[int] = None):
        """有報の「大株主の状況」（上位 10 名、名義ベース）。個人・事業会社・信託口を含む。

        ``year`` を省略すると最新の有報。年度は有報の年度（``.attrs["years"]`` に選べる年度）。
        Columns: Date Reported  Holder  Address  pctHeld  Shares  Rank  Document ID
        """
        d = self._jp_dataset("major-shareholders", year=year)
        df = self._jp_frame(d.get("rows") or [],
                            {"reportDate": "Date Reported", "holder": "Holder", "address": "Address", "pctHeld": "pctHeld",
                             "shares": "Shares", "rank": "Rank", "sourceDocumentId": "Document ID"},
                            dates=["reportDate"])
        df.attrs["years"] = d.get("years") or []
        return df.to_dict() if as_dict else df

    @property
    def large_holders(self) -> pd.DataFrame:
        return self.get_large_holders()

    def get_large_holders(self, as_dict=False):
        """大量保有報告書（5% ルール）の保有者。保有者ごとの最新の報告（事業会社・個人も含む）。

        Columns: Date Reported（基準日）  Holder  pctHeld  Shares  pctChange（前回の報告との差）  Date Filed
                 Holder EDINET Code  Document ID
        """
        df = self._jp_frame(self._jp_module("largeHolders").get("holders") or [],
                            {"reportDate": "Date Reported", "holder": "Holder", "pctHeld": "pctHeld",
                             "shares": "Shares", "pctChange": "pctChange", "submitDate": "Date Filed",
                             "holderEdinetCode": "Holder EDINET Code", "sourceDocumentId": "Document ID"},
                            dates=["reportDate", "submitDate"])
        return df.to_dict() if as_dict else df

    @property
    def large_holder_transactions(self) -> pd.DataFrame:
        return self.get_large_holder_transactions()

    def get_large_holder_transactions(self, as_dict=False):
        """大量保有報告書の「最近 60 日間の取得又は処分の状況」（直近 100 件。同じ売買は 1 件にまとめる）。

        Columns: Date  Holder  Action（acquire / dispose）  Action Text（原文）  Shares  Unit Price  Value
                 Security Type  Market  Holder EDINET Code  Document ID
        """
        df = self._jp_frame(self._jp_module("largeHolderTransactions").get("transactions") or [],
                            {"date": "Date", "holder": "Holder", "action": "Action", "actionText": "Action Text",
                             "shares": "Shares", "unitPrice": "Unit Price", "value": "Value",
                             "securityType": "Security Type", "market": "Market",
                             "holderEdinetCode": "Holder EDINET Code", "sourceDocumentId": "Document ID"},
                            dates=["date"])
        return df.to_dict() if as_dict else df

    @property
    def large_holder_activity(self) -> pd.DataFrame:
        return self.get_large_holder_activity()

    def get_large_holder_activity(self, as_dict=False):
        """大量保有報告書の売買の、直近 6 か月の集計（データの最新提出日まで。普通株式と投資証券だけ）。

        表の形は yfinance の insider_purchases と同じ（行 7 つ・列 Shares / Trans）。
        """
        d = self._jp_module("largeHolderActivity")
        df = pd.DataFrame({
            "Large Holder Trades Last " + d.get("period", ""): [
                "Purchases", "Sales", "Net Shares Purchased (Sold)", "Total Large Holder Shares Held",
                "% Net Shares Purchased (Sold)", "% Buy Shares", "% Sell Shares"],
            "Shares": [d.get("buyShares"), d.get("sellShares"), d.get("netShares"), d.get("totalShares"),
                       d.get("netPercent"), d.get("buyPercent"), d.get("sellPercent")],
            "Trans": [d.get("buyCount"), d.get("sellCount"), d.get("netCount"), pd.NA, pd.NA, pd.NA, pd.NA],
        }).convert_dtypes()
        return df.to_dict() if as_dict else df

    # ------------------------------------------------------------------ 提出日・排出量

    @property
    def report_filing_dates(self) -> pd.DataFrame:
        return self.get_report_filing_dates()

    def get_report_filing_dates(self, limit: int = 12, offset: int = 0) -> pd.DataFrame:
        """有価証券報告書・四半期報告書・半期報告書の提出日（新しい順）。

        Yahoo の earnings_dates（決算発表日と EPS の予想）とは違う。EDINET の報告書は決算発表の 2〜3 か月後に出る。
        Index: Filing Date。Columns: Period Start  Period End  Report Type（annual / quarterly / semiannual）  Amended
        Fiscal Year  Document ID

        Period Start・Period End は EDINET の書類一覧の期間。**半期報告書では事業年度の期間**（書類の表題
        「第41期(2025/04/01－2026/03/31)」と同じ）で、半期の末日ではない。四半期報告書では四半期の期間。
        """
        rows = self._jp_module("reportFilingDates").get("filings") or []
        df = self._jp_frame(rows[offset:offset + limit],
                            {"filingDate": "Filing Date", "periodStart": "Period Start", "periodEnd": "Period End",
                             "reportType": "Report Type",
                             "amended": "Amended", "fiscalYear": "Fiscal Year", "documentId": "Document ID"},
                            dates=["filingDate", "periodStart", "periodEnd"])
        return df.set_index("Filing Date")

    @property
    def emissions(self) -> pd.DataFrame:
        return self.get_emissions()

    def get_emissions(self, as_dict=False):
        """温室効果ガス排出量（tCO2e）。有報のサステナビリティの記載（2024 年度の有報から XBRL にある）。

        Yahoo の sustainability（ESG スコア）とは違い、開示された実数。行 = Scope1・Scope2・Scope1And2・Scope3・
        Scope1And2And3、列 = 期末日（新しい順）。同じ期は最新の書類の値。集計範囲は連結を採り、無ければ範囲の記載の無い値
        （どちらかは ``.attrs["basis"]``）。
        """
        pts = self._jp_module("emissions").get("points") or []
        table: dict = {}
        basis: dict = {}
        for p in pts:
            d = pd.Timestamp(p["periodEnd"], unit="s")
            table.setdefault(p["key"], {})[d] = p["value"]
            basis[(p["key"], d)] = p["basis"]
        order = ["Scope1", "Scope2", "Scope1And2", "Scope3", "Scope1And2And3"]
        df = pd.DataFrame(table).T.reindex([k for k in order if k in table]) if table else pd.DataFrame()
        if len(df.columns):
            df = df[sorted(df.columns, reverse=True)]
        df.attrs["unit"] = "tCO2e"
        df.attrs["basis"] = {f"{k}|{d.date()}": v for (k, d), v in basis.items()}
        return df.to_dict() if as_dict else df

    # ------------------------------------------------------------------ 段 4: サイトで見えるデータ

    @property
    def large_holding_reports(self) -> pd.DataFrame:
        return self.get_large_holding_reports()

    def get_large_holding_reports(self, limit: int = 100, offset: int = 0) -> pd.DataFrame:
        """その銘柄についての大量保有報告書の全報告（新しい順。共同保有者は 1 行ずつ）。総件数は ``.attrs["total"]``。

        Columns: Date Filed  Base Date  Title  Holder  Holder Type  Is Joint  pctHeld  Previous pctHeld  Shares
                 Total Outstanding  Purpose  Important Proposal  Reason  Holder EDINET Code  Document ID
        """
        d = self._jp_dataset("large-holding-reports", size=limit, offset=offset)
        df = self._jp_frame(d.get("rows") or [],
                            {"submitDate": "Date Filed", "baseDate": "Base Date", "title": "Title", "holder": "Holder",
                             "holderType": "Holder Type", "isJoint": "Is Joint", "pctHeld": "pctHeld",
                             "prevPctHeld": "Previous pctHeld", "shares": "Shares", "totalOutstanding": "Total Outstanding",
                             "purpose": "Purpose", "importantProposal": "Important Proposal", "reason": "Reason",
                             "holderEdinetCode": "Holder EDINET Code", "documentId": "Document ID"},
                            dates=["submitDate", "baseDate"])
        df.attrs["total"] = d.get("total", 0)
        return df

    @property
    def filings(self) -> pd.DataFrame:
        return self.get_filings()

    def get_filings(self, types: Optional[list] = None, year: Optional[int] = None, limit: int = 100,
                    offset: int = 0) -> pd.DataFrame:
        """EDINET の提出書類の全件（新しい順）。``sec_filings`` は直近 100 件の dict だが、こちらは絞り込みとページ送りができる。

        ``types`` は書類の種類コードのリスト（``["120", "130"]`` = 有報と訂正有報）。``year`` は年度。総件数は ``.attrs["total"]``。
        Columns: Filing Date  Type  Title  Period Start  Period End  Fiscal Year  Quarter  Is Correction
                 Parent Document ID  Accounting Standard  Doc Type Code  Document ID
        """
        d = self._jp_dataset("filings", types=",".join(types) if types else None, year=year, size=limit, offset=offset)
        df = self._jp_frame(d.get("rows") or [],
                            {"filingDate": "Filing Date", "type": "Type", "title": "Title", "periodStart": "Period Start",
                             "periodEnd": "Period End", "fiscalYear": "Fiscal Year", "quarter": "Quarter",
                             "isCorrection": "Is Correction", "parentDocumentId": "Parent Document ID",
                             "accountingStandard": "Accounting Standard", "docTypeCode": "Doc Type Code",
                             "documentId": "Document ID"},
                            dates=["filingDate", "periodStart", "periodEnd"])
        df.attrs["total"] = d.get("total", 0)
        return df

    @property
    def employees(self) -> pd.DataFrame:
        return self.get_employees()

    def get_employees(self, by_segment: bool = False) -> pd.DataFrame:
        """有報の「従業員の状況」（年度ごと。新しい順。訂正報告書を反映）。

        既定の Columns: Fiscal Year  Period End  Consolidated Employees  Consolidated Temporary Workers
            Employees（提出会社）  Temporary Workers  Average Age Years  Average Age Months
            Average Length Of Service Years  Average Length Of Service Months  Average Annual Salary  Document ID
        ``by_segment=True`` ではセグメント別の人数（Fiscal Year  Segment  Label  Consolidated  Employees  Temporary Workers）
        """
        rows = self._jp_dataset("employees").get("rows") or []
        if by_segment:
            seg = [{"fiscalYear": r["fiscalYear"], **x} for r in rows for x in r.get("bySegment") or []]
            return self._jp_frame(seg, {"fiscalYear": "Fiscal Year", "segment": "Segment", "label": "Label",
                                        "consolidated": "Consolidated", "employees": "Employees",
                                        "temporaryWorkers": "Temporary Workers"})
        return self._jp_frame(rows, {
            "fiscalYear": "Fiscal Year", "periodEnd": "Period End", "consolidatedEmployees": "Consolidated Employees",
            "consolidatedTemporaryWorkers": "Consolidated Temporary Workers", "employees": "Employees",
            "temporaryWorkers": "Temporary Workers", "averageAgeYears": "Average Age Years",
            "averageAgeMonths": "Average Age Months", "averageLengthOfServiceYears": "Average Length Of Service Years",
            "averageLengthOfServiceMonths": "Average Length Of Service Months",
            "averageAnnualSalary": "Average Annual Salary", "documentId": "Document ID"}, dates=["periodEnd"])

    @property
    def officers(self) -> pd.DataFrame:
        return self.get_officers()

    def get_officers(self, year: Optional[int] = None) -> pd.DataFrame:
        """有報の「役員の状況」（訂正報告書を反映）。``year`` を省略すると最新の有報。選べる年度は ``.attrs["years"]``。

        選任議案（株主総会で選任される予定の候補）は ``Is Proposal`` が True の行。
        Columns: Name  Title  Birth Date  Term Of Office  Shares Held（株に直した数。単位が読めなければ NaN）
                 Shares Held Raw  Shares Unit  Is Proposal  Source（xbrl / textblock_html）  Document ID
        """
        d = self._jp_dataset("officers", year=year)
        df = self._jp_frame(d.get("rows") or [],
                            {"name": "Name", "title": "Title", "birthDate": "Birth Date", "termOfOffice": "Term Of Office",
                             "sharesHeld": "Shares Held", "sharesHeldRaw": "Shares Held Raw", "sharesUnit": "Shares Unit",
                             "isProposal": "Is Proposal", "source": "Source", "sourceDocumentId": "Document ID"})
        df.attrs["fiscal_year"] = d.get("fiscalYear")
        df.attrs["years"] = d.get("years") or []
        return df

    @property
    def officer_remuneration(self) -> pd.DataFrame:
        return self.get_officer_remuneration()

    def get_officer_remuneration(self, breakdown: str = "standard") -> pd.DataFrame:
        """役員区分ごとの報酬（取締役・監査役・社外役員など。全年度、新しい順。訂正報告書を反映）。

        ``breakdown="standard"``（既定）: 1 行 = 年度 × 区分。
            Columns: Fiscal Year  Category  Category Label  Total Amount  Officer Count、
            と内訳の列（EDINET の**標準の要素**だけ。Fixed・Base・Performance Based・Bonus・Non Monetary・Share Awards・
            Restricted Share Awards・Performance Linked Share Awards・Share Option・Retirement のうち会社にあるもの）、Document ID。
            会社独自の項目（企業の拡張要素）は標準の列に寄せない。このため内訳の列の合計は Total Amount と一致しないことがある。
        ``breakdown="all"``: 内訳を 1 行 = 年度 × 区分 × 項目で、**有報の項目すべて**（会社独自の項目を含む）。
            Columns: Fiscal Year  Category  Category Label  Local Name（XBRL の要素名）  Standard（標準の列名。独自の項目は None）
            Value  Document ID。値は提出どおり（会社独自の項目には人数など金額でないものもある）。
        """
        if breakdown not in ("standard", "all"):
            raise ValueError("breakdown must be 'standard' or 'all'")
        rows = self._jp_dataset("officer-remuneration").get("rows") or []
        head = {"fiscalYear": "Fiscal Year", "category": "Category", "categoryLabel": "Category Label"}
        if breakdown == "all":
            flat = [{**{k: r.get(k) for k in head}, "localName": name,
                     "standard": _REMUNERATION_STD.get(_REMUNERATION_STD_LOCAL.get(name)),
                     "value": value, "sourceDocumentId": r.get("sourceDocumentId")}
                    for r in rows for name, value in (r.get("breakdown") or {}).items()]
            return self._jp_frame(flat, {**head, "localName": "Local Name", "standard": "Standard", "value": "Value",
                                         "sourceDocumentId": "Document ID"})
        present = {k for r in rows for k in (r.get("breakdownStd") or {})}
        std = [k for k in _REMUNERATION_STD if k in present] + sorted(present - set(_REMUNERATION_STD))
        flat = [{**r, **{f"std_{k}": (r.get("breakdownStd") or {}).get(k) for k in std}} for r in rows]
        cols = {**head, "totalAmount": "Total Amount", "officerCount": "Officer Count"}
        cols.update({f"std_{k}": _REMUNERATION_STD.get(k) or k.replace("_", " ").title() for k in std})
        cols["sourceDocumentId"] = "Document ID"
        return self._jp_frame(flat, cols)

    @property
    def audit_fees(self) -> pd.DataFrame:
        return self.get_audit_fees()

    def get_audit_fees(self) -> pd.DataFrame:
        """監査報酬（全年度、新しい順）。``Network Firms`` が True の行は監査人と同じネットワークの事務所への報酬。

        Columns: Fiscal Year  Network Firms  Audit Reporting Company  Audit Consolidated Subsidiaries  Audit Total
                 Non Audit Reporting Company  Non Audit Consolidated Subsidiaries  Non Audit Total  Document ID
        """
        return self._jp_frame(self._jp_dataset("audit-fees").get("rows") or [], {
            "fiscalYear": "Fiscal Year", "networkFirms": "Network Firms", "auditReportingCompany": "Audit Reporting Company",
            "auditConsolidatedSubsidiaries": "Audit Consolidated Subsidiaries", "auditTotal": "Audit Total",
            "nonAuditReportingCompany": "Non Audit Reporting Company",
            "nonAuditConsolidatedSubsidiaries": "Non Audit Consolidated Subsidiaries", "nonAuditTotal": "Non Audit Total",
            "sourceDocumentId": "Document ID"})

    @property
    def dividend_resolutions(self) -> pd.DataFrame:
        return self.get_dividend_resolutions()

    def get_dividend_resolutions(self) -> pd.DataFrame:
        """有報の「剰余金の配当」（決議ごと。新しい順。2019 年度ごろの有報から XBRL にある）。

        Yahoo の dividends（配当落ち日と金額の株価系の系列）とは違い、会社の決議の記録。普通株式の配当だけ。
        Columns: Resolution Date  Resolution（決議機関。原文）  Dividend Per Share  Total Amount  Record Date（記載があれば）
                 Fiscal Year  Document ID
        """
        return self._jp_frame(self._jp_dataset("dividend-resolutions").get("rows") or [], {
            "resolutionDate": "Resolution Date", "resolution": "Resolution", "dividendPerShare": "Dividend Per Share",
            "totalAmount": "Total Amount", "recordDate": "Record Date", "fiscalYear": "Fiscal Year",
            "documentId": "Document ID"}, dates=["resolutionDate", "recordDate"])

    @property
    def segments(self) -> pd.DataFrame:
        return self.get_segments()

    def get_segments(self, freq: str = "yearly", consolidated: Optional[str] = None) -> pd.DataFrame:
        """セグメント情報（全年度。1 行 = 年度 × セグメント × 指標）。

        ``freq`` は ``yearly``・``semiannual``・``quarterly``。``consolidated`` は None（連結を優先）・``consolidated``・``standalone``。
        年度ごとに書類を 1 本選び、その書類の行だけを返す（原本と訂正報告書の行を混ぜない）。
        セグメントの値の合計は連結の値と一致しない（調整額・セグメント間取引）。セグメントは提出どおりで、年度をまたいだ名寄せはしない。
        Columns: Fiscal Year  Period End  Segment  Segment Label  Role（segment / other / subtotal / total / adjustment）
                 Is Adjustment  Metric（seg_revenue など）  Value  Unit  Consolidated（consolidated / standalone）
                 Accounting Standard  Document ID
        """
        d = self._jp_dataset("segments", period=self._period(freq), consolidated=self._cons(consolidated))
        return self._jp_frame(d.get("rows") or [], {
            "fiscalYear": "Fiscal Year", "periodEnd": "Period End", "segment": "Segment", "segmentLabel": "Segment Label",
            "role": "Role", "isAdjustment": "Is Adjustment", "metric": "Metric", "value": "Value", "unit": "Unit",
            "consolidated": "Consolidated", "accountingStandard": "Accounting Standard", "documentId": "Document ID"},
            dates=["periodEnd"])

    @property
    def statements(self) -> pd.DataFrame:
        return self.get_statements()

    def get_statements(self, freq: str = "yearly", consolidated: Optional[str] = None) -> pd.DataFrame:
        """書類の財務諸表などの**全科目**を、書類の表示の順・階層のまま（XBRL の表示リンク）。値は訂正報告書を反映。

        骨格は最新の書類。1 行 = 表示の 1 行。Columns: Role（表の名前）  Label  Local Name（XBRL の要素名）  Depth
        Is Abstract、と年度ごとの列（int。有報の年度）。``financials`` などは Yahoo の科目に畳んだ表だが、こちらは有報の科目そのもの。
        """
        d = self._jp_dataset("statements", period=self._period(freq), consolidated=self._cons(consolidated))
        years = [str(y) for y in d.get("fiscalYears") or []]
        rows = []
        for role in d.get("roles") or []:
            for line in role.get("lines") or []:
                row = {"Role": role.get("roleLabel"), "Label": line.get("label"), "Local Name": line.get("localName"),
                       "Depth": line.get("depth"), "Is Abstract": line.get("isAbstract")}
                row.update({int(y): (line.get("values") or {}).get(y) for y in years})
                rows.append(row)
        df = pd.DataFrame(rows, columns=["Role", "Label", "Local Name", "Depth", "Is Abstract"] + [int(y) for y in years])
        df.attrs["base_document_id"] = d.get("baseDocumentId")
        return df

    # ------------------------------------------------------------------ 役員報酬

    @property
    def officer_compensation(self) -> pd.DataFrame:
        return self.get_officer_compensation()

    def get_officer_compensation(self, as_dict=False):
        """役員の個別報酬（連結報酬等 1 億円以上）の全年度。訂正報告書を反映した値。

        Columns: fiscalYear name totalPay documentId sourceDocumentId isCorrected correctionSource
        """
        rows = []
        for r in self._jp_module("officerCompensation").get("officers") or []:
            fix = r.get("payCorrection") or {}
            rows.append({"fiscalYear": r.get("fiscalYear"), "name": r.get("name"), "totalPay": r.get("totalPay"),
                         "documentId": r.get("documentId"), "sourceDocumentId": r.get("sourceDocumentId"),
                         "isCorrected": r.get("isCorrected"), "correctionSource": fix.get("source")})
        df = pd.DataFrame(rows, columns=["fiscalYear", "name", "totalPay", "documentId", "sourceDocumentId",
                                         "isCorrected", "correctionSource"])
        return df.to_dict() if as_dict else df

    # ------------------------------------------------------------------ 日本の開示項目

    def get_jp_financials(self, freq: str = "yearly", start: Optional[str] = None) -> pd.DataFrame:
        """Yahoo に同名の科目が無い日本の開示項目（経常利益・1 株当たり純資産・従業員数など）。

        ``freq`` は ``yearly``・``quarterly``・``semiannual``。``start`` を省略するとすべての年度。
        """
        return self._jp_timeseries(list(EXTRA_KEYS), freq, start)

    def get_fund_financials(self, freq: str = "yearly", start: Optional[str] = None) -> pd.DataFrame:
        """投資信託の財務項目 25 本（純資産・元本・信託報酬・分配金など）。``freq`` は ``yearly``・``semiannual``。"""
        return self._jp_timeseries(list(FUND_KEYS), freq, start)
