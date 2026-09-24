# jfinance

jfinance は、EDINET に提出された企業開示データ（財務諸表・役員と報酬・大株主・大量保有報告書・投資信託）を
無料で取得するための Python ライブラリです。**2016 年度以降**の有価証券報告書・半期報告書・四半期報告書・
大量保有報告書等を収録しています。API は yfinance 互換です。

[English README](README.md)

## インストール

```bash
pip install jfinance
```

インストールせずに試せます: [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sgawa/jfinance/blob/main/examples/quickstart.ipynb)

Python 3.9 以上が必要です。`pandas`・`numpy`・`requests`・`pytz` は依存パッケージとして同時に導入されます。
（`curl_cffi` が導入されている場合、そちらを使用します。）

社名および業種は既定で英語表示となります。`jf.config.locale.lang = "ja-JP"` を設定すると日本語で取得できます。
英語の出典が存在しない項目（事業の内容、役員および株主の氏名など）は、いずれの設定でも日本語のまま返します。

## ドキュメント

<https://jfnc.org/ja/docs/> を参照してください。

- [インストール](https://jfnc.org/ja/docs/install/) 
- [証券コード](https://jfnc.org/ja/docs/symbols/) 
- [Ticker](https://jfnc.org/ja/docs/reference/ticker/) 
- [収録範囲](https://jfnc.org/ja/docs/data/coverage/)
- [データの注意](https://jfnc.org/ja/docs/data/notes/) 
- [利用条件](https://jfnc.org/ja/docs/terms/) 
- [HTTP API](https://jfnc.org/ja/docs/http-api/) 

## データの取得先

データは作者が運営するサーバー（`https://query1.jfnc.org`）から取得します。
利用登録および API キーは不要、SLAはございません。IP アドレス単位のレート制限を設けています。

**EDINET の閲覧期間が満了した書類に対する訂正報告書は取得できないため、反映されない場合があります。**
古い年度ほど訂正前の値が残っている可能性があります。同じ注意書きは `jf.NOTICE_CORRECTIONS` および
すべての HTTP 応答のヘッダ `X-JF-Notice` からも取得できます。

## 使用例

```python
import jfinance as jf

t = jf.Ticker("7203.T")          # トヨタ自動車。"E02144"（EDINET コード）・"JP3633400001"（ISIN）でも同じ
t.info                            # 会社名・業種・従業員数・事業の内容・役員と個別報酬
t.financials                      # 損益計算書（年次）。balance_sheet・cashflow・quarterly_* も同じ
t.major_holders                   # 株主構成（有報の「所有者別状況」）
t.sec_filings                     # EDINET の提出書類
jf.Ticker("8035.T").institutional_holders   # 機関投資家（大量保有報告書の特例報告）

# jfinance 独自のもの
t.major_shareholders              # 有報の大株主（上位 10 名）
t.large_holders                   # 大量保有報告書の保有者
t.large_holder_transactions       # その売買（large_holder_activity は直近 6 か月の集計）
t.officer_compensation            # 役員の個別報酬（1 億円以上）の全年度。訂正報告書を反映
t.emissions                       # 温室効果ガス排出量（tCO2e。有報の開示）
t.report_filing_dates             # 有報・半期報告書・四半期報告書の提出日
t.get_jp_financials()             # 経常利益・1 株当たり純資産・従業員数・銀行／保険の科目など
t.get_statements()                # 有報の財務諸表の全科目（表示の順・階層のまま）
t.segments, t.employees           # セグメント情報・従業員の状況（平均年齢・勤続・給与）
t.get_officers(year=2020)         # 任意の年度の役員。t.officer_remuneration（区分別報酬）・t.audit_fees（監査報酬）
t.dividend_resolutions            # 剰余金の配当（決議日・1 株配当・総額）
t.get_filings(types=["120"])      # 提出書類の全件（絞り込み・ページ送り）
jf.set_financials_basis(consolidation="standalone", version="as_filed")   # 単体・訂正前の財務諸表
jf.JpSector("automobiles-transportation-equipment").top_companies   # 東証の業種
jf.edinet_screen(jf.EdinetQuery("gt", ["roe", 0.2]), sortField="revenue")   # EDINET の項目のスクリーナー
jf.FilingCalendar("2026-06-25").get_filings(types=["120"])          # その日の提出書類

f = jf.Ticker("1306.T")          # 上場投信。"G02925"（EDINET のファンドコード）でも同じ
f.get_fund_financials()           # 純資産・元本・信託報酬・分配金など 25 項目（決算日ごと）
```

## ライセンスと出典

**ソースコードとデータでライセンスが異なります。**

| 対象 | ライセンス |
|---|---|
| ソースコード | **Apache License 2.0**（[LICENSE](LICENSE)・[NOTICE](NOTICE)） |
| API が返すデータ | **EDINET の利用条件に従います**（下記）。jfinance が独自に許諾するものではありません |

### 含まれるソフトウェア

- **yfinance** — Copyright 2017-2019 Ran Aroussi、Apache License 2.0。
  `src/jfinance/` の一部は yfinance 1.5.2 のソースを複製したものです。
  複製の手順と変更内容は [`tools/vendor_yfinance.py`](tools/vendor_yfinance.py) に記録しています。

### データの出典（再配布・再公開する場合も同じ表示が必要です）

    出典：EDINET閲覧（提出）サイト（https://disclosure2.edinet-fsa.go.jp/）、
          PDL1.0（https://www.digital.go.jp/resources/open_data/public_data_license_v1.0）
    EDINET閲覧（提出）サイト（https://disclosure2.edinet-fsa.go.jp/）をもとに jfinance 作成

EDINET のコンテンツは公共データ利用規約（第1.0版）に基づいて利用しています。
jfinance は値の選択・訂正報告書の反映・yfinance 形式への再構成を行っているため、規約上の**編集・加工**に該当します。
**国が作成した未加工の情報として公表・利用しないでください。**

### EDINET タクソノミ

科目名・財務諸表の名称・セグメント名などのラベルは、EDINET タクソノミからの引用です。
EDINET タクソノミには PDL1.0 が適用されず、「EDINETタクソノミの知的所有権について」が適用されます。

    EDINETタクソノミ © Copyright 2014 Financial Services Agency, The Japanese Government

jfinance はラベルを改変・修正・翻訳していません（金融庁の事前の許可が必要なため）。
同文書の全文を [`licenses/EDINET_Taxonomy_Legal_Statement.txt`](licenses/EDINET_Taxonomy_Legal_Statement.txt)
に同梱しています。EDINET タクソノミには XBRL International, Inc.（XII）の著作権に帰属する内容が
一部含まれており、同文書は XII の知的財産権ポリシーに準拠した利用を条件としています。
