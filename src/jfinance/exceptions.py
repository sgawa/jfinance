# このファイルは yfinance 1.5.2 の `exceptions.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: 例外（同じ名前・同じ継承）
# 変えた点（Apache License 2.0 第 4 条 b）:
#   - 削った: YFTzMissingError, YFPricesMissingError, YFEarningsDateMissing, YFInvalidPeriodError（株価の例外（EDINET に株価は無い））
#   - 名前 yfinance → jfinance（import・ロガー名・repr）

class YFException(Exception):
    def __init__(self, description=""):
        super().__init__(description)


class YFDataException(YFException):
    pass


class YFNotImplementedError(NotImplementedError):
    def __init__(self, method_name):
        super().__init__(f"Have not implemented fetching '{method_name}' from Yahoo API")


class YFTickerMissingError(YFException):
    def __init__(self, ticker, rationale):
        super().__init__(f"${ticker}: possibly delisted; {rationale}")
        self.rationale = rationale
        self.ticker = ticker


class YFRateLimitError(YFException):
    def __init__(self):
        super().__init__("Too Many Requests. Rate limited. Try after a while.")
