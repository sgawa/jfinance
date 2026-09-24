"""yfinance のソースをコピーして jfinance の土台を作る。

    pip install "yfinance==1.5.2"
    python tools/vendor_yfinance.py            # src/jfinance/ の下に書き出す
    python tools/vendor_yfinance.py --check    # 書き出したものが今のファイルと同じか（CI・公開前の確認）

■ なぜ手でコピーしないか
  yfinance から何を削り、何を差し替えたかを、このファイルだけで追えるようにするため。
  yfinance が更新されたら、版を上げてこのスクリプトを流し直す。差し替え元の文字列が見つからなければ
  止まるので、どこが変わったかがすぐ分かる。

■ 変えるのは次の 3 種類だけ（行の中身を書き換えない。削るか、決まった文字列を差し替える）
  1. 削る: EDINET に無い機能（株価・配当・オプション・アナリスト・ニュース・リアルタイム・Yahoo の認証）
  2. 差し替える: 通信先を jfinance のサーバにする・Yahoo の認証をしない・第三者のサイトを使わない
  3. 名前: モジュール名 yfinance → jfinance（ログの名前・repr も含む）

■ ライセンス
  yfinance は Apache License 2.0（Copyright 2017-2019 Ran Aroussi）。書き出す各ファイルの冒頭に、
  元のファイルと変えた点を書く（Apache License 2.0 第 4 条 b）。
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import re
import sys

YF_VERSION = "1.5.2"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "src", "jfinance")

# ============================================================================ 共通の差し替え

# 株価の例外は持たない（exceptions.py から削る）ので、import からも外す
_BASE_IMPORT_EXC = ("from .exceptions import YFDataException, YFEarningsDateMissing, YFRateLimitError",
                    "from .exceptions import YFDataException, YFRateLimitError")

# ============================================================================ ファイルごとの指示
#
#   drop     … 削る定義（トップレベルの関数・クラス・代入の名前、または "クラス.メソッド"）
#   keep     … これだけ残す（トップレベルの関数・クラス・代入。import などの文は残す）
#   replace  … (元の文字列, 新しい文字列, 理由)。元の文字列はちょうど 1 回現れること
#
SPECS: list[dict] = [
    {"src": "exceptions.py", "why": "例外（同じ名前・同じ継承）",
     "drop": ["YFTzMissingError", "YFPricesMissingError", "YFEarningsDateMissing", "YFInvalidPeriodError"],
     "drop_why": "株価の例外（EDINET に株価は無い）"},

    {"src": "config.py", "why": "設定（network・debug・locale）"},

    {"src": "shared.py", "why": "共有の状態"},

    {"src": "_http.py", "why": "HTTP の実装（curl_cffi が無ければ requests）",
     "replace": [
         ('    if HAS_CURL_CFFI or _fallback_warned:\n        return\n',
          '    if True:  # jfinance: jfinance のサーバは requests でも答えるので警告しない\n        return\n',
          "curl_cffi が無いときの「Yahoo に拒否されうる」警告を出さない"),
     ]},

    {"src": "data.py", "why": "通信（シングルトン・再試行・プロキシ・LRU キャッシュ）",
     "drop": ["YfData.set_login_cookies", "YfData._set_logged_in", "YfData._set_cookie_strategy",
              "YfData._save_cookie_curlCffi", "YfData._load_cookie_curlCffi", "YfData._get_cookie_basic",
              "YfData._get_crumb_basic", "YfData._get_cookie_and_crumb_basic", "YfData._get_cookie_csrf",
              "YfData._get_crumb_csrf", "YfData._get_cookie_and_crumb", "YfData._is_this_consent_url",
              "YfData._accept_consent_form", "_SUBSCRIPTIONS_URL", "_TIER_NAMES", "Auth"],
     "drop_why": "Yahoo の cookie・crumb・同意画面・ログイン",
     "replace": [
         ("from bs4 import BeautifulSoup\n", "", "同意画面の解析をしないので bs4 は要らない"),
         ("from . import utils, cache\n", "from . import utils\nfrom .jp import _server\n",
          "cookie のディスクキャッシュを使わない。通信先を決める jp._server を使う"),
         ("""        # Accept cookie-consent if redirected to consent page
        if not self._is_this_consent_url(response.url):
            # "Consent Page not detected"
            pass
        else:
            # "Consent Page detected"
            response = self._accept_consent_form(response, timeout)
""", "", "Yahoo の同意画面は来ない"),
         ("""        crumb, strategy = self._get_cookie_and_crumb()
        if crumb is not None:
            crumbs = {'crumb': crumb}
        else:
            crumbs = {}

        request_args = {
            'url': url,""", """        crumbs = {}  # jfinance: crumb は要らない

        request_args = {
            'url': _server.to_server_url(url),""",
          "crumb を取らない。Yahoo の URL を jfinance のサーバの URL にする（それ以外の宛先は拒否）"),
         ("""        if response.status_code >= 400:
            # Retry with other cookie strategy
            if strategy == 'basic':
                self._set_cookie_strategy('csrf')
            else:
                self._set_cookie_strategy('basic')
            crumb, strategy = self._get_cookie_and_crumb(timeout)
            request_args['params']['crumb'] = crumb
            response = request_method(**request_args)
            utils.get_yf_logger().debug(f'response code={response.status_code}')

            # Raise exception if rate limited
            if response.status_code == 429:
                raise YFRateLimitError()
""", """        # Raise exception if rate limited
        if response.status_code == 429:
            raise YFRateLimitError()
""", "cookie の方式を切り替えて再送しない。429 はそのまま例外にする"),
     ]},

    {"src": "utils.py", "why": "ログ・ISIN・行名の整形・日付の解釈",
     "keep": ["IndentLoggerAdapter", "_indentation_level", "IndentationContext", "get_indented_logger",
              "log_indent_decorator", "MultiLineFormatter", "yf_logger", "yf_log_indented", "YFLogFormatter",
              "get_yf_logger", "enable_debug_mode", "_enable_debug_mode", "_disable_debug_mode", "is_isin",
              "get_all_by_isin", "get_ticker_by_isin", "get_info_by_isin", "camel2title",
              "snake_case_2_camelCase", "_parse_user_dt", "is_valid_timezone", "dynamic_docstring",
              "_generate_table_configurations", "generate_list_table_from_dict",
              "generate_list_table_from_dict_universal"],
     "keep_why": "株価の処理（調整・補正・間隔・進捗表示）と財務の旧形式の整形を削る",
     "replace": [
         ("    news = search.news\n", "    news = []  # jfinance: ニュースは持たない\n",
          "ISIN の検索は jfinance のサーバの search で引く（元は第三者のサイトを使う版もあった）。ニュースは持たない"),
     ]},

    {"src": "const.py", "why": "定数（財務のキー・quoteSummary のモジュール・取引所コード）",
     "keep": ["_QUERY1_URL_", "_BASE_URL_", "_ROOT_URL_", "_SENTINEL_", "fundamentals_keys",
              "quote_summary_valid_modules", "_MIC_TO_YAHOO_SUFFIX"],
     "keep_strict": True,
     "keep_why": "株価・業種・スクリーナー（Yahoo の項目）・User-Agent の表を削る"},

    {"src": "scrapers/__init__.py", "why": "パッケージ"},

    {"src": "scrapers/fundamentals.py", "why": "財務諸表（時系列から表を組み立てる）",
     "replace": [
         ("from jfinance.exceptions import YFException, YFNotImplementedError\n",
          "from jfinance.exceptions import YFException, YFNotImplementedError\nfrom jfinance.jp import _server\n",
          "財務の開始日を jp._server から取る"),
         ('        allowed_timescales = ["yearly", "quarterly", "trailing"]\n',
          '        allowed_timescales = ["yearly", "quarterly", "trailing", "semiannual"]  # jfinance: 半期を足す\n',
          "freq に semiannual（半期報告書）を足す。日本は 2024 年に四半期報告書が廃止された"),
         ('        timescale_translation = {"yearly": "annual", "quarterly": "quarterly", "trailing": "trailing"}\n',
          '        timescale_translation = {"yearly": "annual", "quarterly": "quarterly", "trailing": "trailing",\n'
          '                                 "semiannual": "semiannual"}  # jfinance: 半期を足す\n',
          "同上"),
         ("        # Yahoo returns maximum 4 years or 5 quarters, regardless of start_dt:\n"
          "        start_dt = datetime.datetime(2016, 12, 31)\n",
          "        # jfinance: 既定はサーバにあるすべての年度（yfinance は 2016-12-31 から）。jf.set_financials_start() で変えられる\n"
          "        start_dt = _server.financials_start()\n",
          "既定で全年度を返す（yfinance は 2016-12-31 以降に固定）"),
         ('        period_qs = f"&period1={int(start_dt.timestamp())}&period2={int(end.timestamp())}"\n',
          '        period_qs = f"&period1={int(start_dt.timestamp())}&period2={int(end.timestamp())}"'
          ' + _server.financials_query()  # jfinance: 連結区分・版\n',
          "jf.set_financials_basis() の連結区分・版をサーバへ送る（既定のときは何も足さない）"),
     ]},

    {"src": "scrapers/holders.py", "why": "株主"},

    {"src": "scrapers/funds.py", "why": "投資信託（funds_data）"},

    {"src": "scrapers/quote.py", "why": "info と提出書類",
     "drop": ["FastInfo", "Quote.sustainability", "Quote.recommendations", "Quote.upgrades_downgrades",
              "Quote.calendar", "Quote.valuation_measures", "Quote.get_valuation_measures",
              "Quote._fetch_valuation_measures", "Quote._fetch_complementary", "Quote._fetch_calendar"],
     "drop_why": "株価・評価指標・ESG スコア・アナリスト・決算予定",
     "replace": [
         ("            self._fetch_info()\n            self._fetch_complementary()\n",
          "            self._fetch_info()\n",
          "trailingPegRatio（株価に依存）を取りに行かない"),
     ]},

    {"src": "base.py", "why": "Ticker の本体",
     "drop": ["TickerBase.history", "TickerBase._lazy_load_price_history", "TickerBase.get_recommendations",
              "TickerBase.get_recommendations_summary", "TickerBase.get_upgrades_downgrades",
              "TickerBase.get_calendar", "TickerBase.get_fast_info", "TickerBase.get_valuation_measures",
              "TickerBase.get_sustainability", "TickerBase.get_analyst_price_targets",
              "TickerBase.get_earnings_estimate", "TickerBase.get_revenue_estimate",
              "TickerBase.get_earnings_history", "TickerBase.get_eps_trend", "TickerBase.get_eps_revisions",
              "TickerBase.get_growth_estimates", "TickerBase.get_earnings", "TickerBase.get_dividends",
              "TickerBase.get_capital_gains", "TickerBase.get_splits", "TickerBase.get_actions",
              "TickerBase.get_news", "TickerBase.get_earnings_dates",
              "TickerBase._get_earnings_dates_using_scrape", "TickerBase._get_earnings_dates_using_screener",
              "TickerBase.get_history_metadata", "TickerBase.live",
              "TickerBase.get_mutualfund_holders", "TickerBase.get_insider_purchases",
              "TickerBase.get_insider_transactions"],
     "drop_why": "株価・配当・アナリスト・ニュース・決算日・リアルタイム・ESG スコア。投資信託の保有と役員の売買"
                 "（EDINET に同じものが無い。大量保有報告書は jp/ticker.py の独自の名前で出す）",
     "replace": [
         ("from . import utils, cache\n", "from . import utils\n", "タイムゾーン・ISIN のディスクキャッシュを使わない"),
         (_BASE_IMPORT_EXC[0] + "\n", _BASE_IMPORT_EXC[1] + "\n", "株価の例外を持たない"),
         ("from .live import WebSocket\n", "", "リアルタイムを持たない"),
         ("from .scrapers.analysis import Analysis\n", "", "アナリストを持たない"),
         ("from .scrapers.quote import Quote, FastInfo\n", "from .scrapers.quote import Quote\n", "fast_info を持たない"),
         ("from .scrapers.history import PriceHistory\n", "", "株価を持たない"),
         ("from bs4 import BeautifulSoup\n", "", "決算日のスクレイピングをしない"),
         ("        self._analysis = Analysis(self._data, self.ticker)\n", "", "アナリストを持たない"),
         ("""            c = cache.get_isin_cache()
            self.ticker = c.lookup(isin)
            if not self.ticker:
                self.ticker = utils.get_ticker_by_isin(isin)
            if self.ticker == "":
                raise ValueError(f"Invalid ISIN number: {isin}")
            if self.ticker:
                c.store(isin, self.ticker)
""", """            self.ticker = utils.get_ticker_by_isin(isin)
            if self.ticker == "":
                raise ValueError(f"Invalid ISIN number: {isin}")
""", "ISIN はサーバの search で引く。ディスクに保存しない"),
         ("""        c = cache.get_tz_cache()
        tz = c.lookup(self.ticker)

        if tz and not utils.is_valid_timezone(tz):
            # Clear from cache and force re-fetch
            c.store(self.ticker, None)
            tz = None
""", "        tz = None  # jfinance: タイムゾーンをディスクに保存しない\n", "タイムゾーンのディスクキャッシュを使わない"),
         ("""            if utils.is_valid_timezone(tz):
                c.store(self.ticker, tz)
            else:
                tz = None
""", """            if not utils.is_valid_timezone(tz):
                tz = None
""", "同上"),
         ("            start = end - pd.Timedelta(days=548)  # 18 months\n",
          "            start = pd.Timestamp(0, unit='s', tz='UTC').tz_convert(tz)  # jfinance: 全期間（yfinance は 18 か月）\n",
          "既定で全期間を返す"),
         ("""        q = ticker

        if self._quote.info is None:
            # Don't print error message cause self._quote.info will print one
            return None
        if "shortName" in self._quote.info:
            q = self._quote.info['shortName']

        url = f'https://markets.businessinsider.com/ajax/SearchController_Suggest?max_results=25&query={urlencode(q)}'
        data = self._data.cache_get(url=url).text

        search_str = f'"{ticker}|'
        if search_str not in data:
            if q.lower() in data.lower():
                search_str = '"|'
                if search_str not in data:
                    self._isin = '-'
                    return self._isin
            else:
                self._isin = '-'
                return self._isin

        self._isin = data.split(search_str)[1].split('"')[0].split('|')[0]
        return self._isin
""", """        if self._quote.info is None:
            # Don't print error message cause self._quote.info will print one
            return None
        # jfinance: 第三者のサイト（businessinsider）ではなく、EDINET の企業一覧の ISIN（info の isin）
        self._isin = self._quote.info.get('isin') or '-'
        return self._isin
""", "ISIN を第三者のサイトで引かず、EDINET の値を使う"),
     ]},

    {"src": "ticker.py", "why": "Ticker（属性の名前）",
     "drop": ["Ticker._download_options", "Ticker._options2df", "Ticker.option_chain", "Ticker.dividends",
              "Ticker.capital_gains", "Ticker.splits", "Ticker.actions", "Ticker.fast_info", "Ticker.valuation",
              "Ticker.calendar", "Ticker.recommendations", "Ticker.recommendations_summary",
              "Ticker.upgrades_downgrades", "Ticker.earnings", "Ticker.quarterly_earnings",
              "Ticker.analyst_price_targets", "Ticker.earnings_estimate", "Ticker.revenue_estimate",
              "Ticker.earnings_history", "Ticker.eps_trend", "Ticker.eps_revisions", "Ticker.growth_estimates",
              "Ticker.sustainability", "Ticker.options", "Ticker.news", "Ticker.earnings_dates",
              "Ticker.history_metadata", "Ticker.mutualfund_holders", "Ticker.insider_purchases",
              "Ticker.insider_transactions", "Ticker.ttm_income_stmt", "Ticker.ttm_incomestmt",
              "Ticker.ttm_financials", "Ticker.ttm_cash_flow", "Ticker.ttm_cashflow"],
     "drop_why": "株価・配当・オプション・アナリスト・ニュース・決算日・ESG スコア。投資信託の保有と役員の売買。"
                 "直近 12 か月（TTM。複数の書類にまたがる計算値で出典が 1 つに決まらないのでサーバが出さない）",
     "replace": [
         ("from .scrapers.funds import FundsData\n",
          "from .scrapers.funds import FundsData\nfrom .jp.ticker import JpTickerMixin\n", "独自の機能を足す"),
         ("class Ticker(TickerBase):\n", "class Ticker(TickerBase, JpTickerMixin):\n",
          "独自の機能（jfinance/jp/ticker.py）を足す"),
     ]},

    {"src": "tickers.py", "why": "Tickers",
     "drop": ["Tickers.history", "Tickers.download", "Tickers.news", "Tickers.live"],
     "drop_why": "株価・ニュース・リアルタイム",
     "replace": [
         ("from . import Ticker, multi\n", "from . import Ticker\n", "download を持たない"),
         ("from .live import WebSocket\n", "", "リアルタイムを持たない"),
         ("from .const import period_default\n", "", "株価の期間の既定値は要らない"),
     ]},

    {"src": "search.py", "why": "Search",
     "drop": ["Search.news", "Search.lists", "Search.research", "Search.nav"],
     "drop_why": "ニュース・リスト・リサーチ・ナビ（EDINET に無い）",
     "replace": [
         ("""        self._all = {"quotes": self._quotes, "news": self._news, "lists": self._lists, "research": self._research,
                     "nav": self._nav}
""", """        self._all = {"quotes": self._quotes}  # jfinance: ニュースなどは持たない
""", "all にはあるものだけを入れる"),
     ]},

    {"src": "screener/query.py", "why": "スクリーナーの条件式（QueryBase）。jfinance の EdinetQuery の土台",
     "drop": ["EquityQuery", "FundQuery", "ETFQuery"],
     "drop_why": "Yahoo の項目の条件式（EDINET の項目は jp/screener.py の EdinetQuery）",
     "replace": [
         ("from jfinance.const import EQUITY_SCREENER_EQ_MAP, EQUITY_SCREENER_FIELDS\n"
          "from jfinance.const import FUND_SCREENER_EQ_MAP, FUND_SCREENER_FIELDS\n"
          "from jfinance.const import ETF_SCREENER_EQ_MAP, ETF_SCREENER_FIELDS\n", "",
          "Yahoo の項目の表を使わない"),
     ]},

    {"src": "lookup.py", "why": "Lookup",
     "drop": ["Lookup.get_index", "Lookup.get_future", "Lookup.get_currency", "Lookup.get_cryptocurrency",
              "Lookup.index", "Lookup.future", "Lookup.currency", "Lookup.cryptocurrency"],
     "drop_why": "指数・先物・通貨・暗号資産（EDINET に無い）"},
]

HEADER = '''# このファイルは yfinance {ver} の `{src}` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: {why}
# 変えた点（Apache License 2.0 第 4 条 b）:
{changes}
'''


def _yf_dir() -> str:
    spec = importlib.util.find_spec("yfinance")
    if spec is None or not spec.origin:
        sys.exit("yfinance が無い: pip install \"yfinance=={}\"".format(YF_VERSION))
    d = os.path.dirname(spec.origin)
    from importlib.metadata import version
    v = version("yfinance")
    if v != YF_VERSION:
        sys.exit(f"yfinance {v} が入っている。{YF_VERSION} にするか、YF_VERSION を上げて差し替えを確かめる")
    return d


def _node_name(node) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _span(node, lines: list[str]) -> tuple[int, int]:
    """定義の行の範囲（デコレータと、直後の空行を含む。0 始まり・end は含まない）"""
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]) - 1
    end = node.end_lineno
    while end < len(lines) and lines[end].strip() == "":
        end += 1
    return start, end


def _cut(text: str, drop: list[str], keep: list[str] | None, strict: bool = False) -> str:
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    spans: list[tuple[int, int]] = []
    found: set[str] = set()
    for node in tree.body:
        name = _node_name(node)
        if keep is not None and name is None and strict and not isinstance(node, (ast.Import, ast.ImportFrom)):
            spans.append(_span(node, lines))   # 名前の無い文（for など）も削る
            continue
        if keep is not None and name is not None:
            if name in keep:
                found.add(name)
            else:
                spans.append(_span(node, lines))
            continue
        if name in drop:
            spans.append(_span(node, lines))
            found.add(name)
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                full = f"{node.name}.{_node_name(sub)}"
                if full in drop:
                    spans.append(_span(sub, lines))
                    found.add(full)
    wanted = set(keep if keep is not None else drop)
    missing = wanted - found
    if missing:
        raise SystemExit(f"見つからない定義: {sorted(missing)}")
    for s, e in sorted(spans, reverse=True):
        del lines[s:e]
    return "".join(lines)


def build(spec: dict, yf: str) -> str:
    with open(os.path.join(yf, spec["src"]), encoding="utf-8") as f:
        text = f.read()
    changes: list[str] = []
    text = _cut(text, spec.get("drop", []), spec.get("keep"), spec.get("keep_strict", False))
    if spec.get("drop"):
        changes.append(f"削った: {', '.join(spec['drop'])}（{spec['drop_why']}）")
    if spec.get("keep") is not None:
        changes.append(f"残した定義だけ: {', '.join(spec['keep'])}（{spec['keep_why']}）")
    text = re.sub(r"\byfinance\b", "jfinance", text)
    changes.append("名前 yfinance → jfinance（import・ロガー名・repr）")
    for old, new, why in spec.get("replace", []):
        old_j = re.sub(r"\byfinance\b", "jfinance", old)
        n = text.count(old_j)
        if n != 1:
            raise SystemExit(f"{spec['src']}: 差し替え元が {n} 回現れる（1 回のはず）: {old_j[:80]!r}")
        text = text.replace(old_j, new)
        changes.append(f"差し替えた: {why}")
    changes_txt = "\n".join(f"#   - {c}" for c in changes)
    return HEADER.format(ver=YF_VERSION, src=spec["src"], why=spec["why"], changes=changes_txt) + "\n" + text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="書き出さずに、今のファイルと同じかだけ確かめる")
    args = ap.parse_args()
    yf = _yf_dir()
    bad = []
    for spec in SPECS:
        out = build(spec, yf)
        path = os.path.join(OUT, spec["src"])
        if args.check:
            cur = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if cur != out:
                bad.append(spec["src"])
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"書き出し: src/jfinance/{spec['src']}")
    if args.check:
        if bad:
            sys.exit(f"コピーが古い（tools/vendor_yfinance.py を流し直す）: {bad}")
        print(f"コピーは最新（yfinance {YF_VERSION}、{len(SPECS)} ファイル）")


if __name__ == "__main__":
    main()
