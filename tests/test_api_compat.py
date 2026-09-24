"""名前と引数の互換テスト（サーバも yfinance も要らない）。

yf_api_reference.json（yfinance の公開 API と、名前ごとの決定）と jfinance を比べる。

    python tests/test_api_compat.py

■ 確かめること（名前の線引き: Yahoo と同じものだけ Yahoo の名前、同じものが無いものは持たない、近いものは独自の名前）
  - Yahoo と同じ（jf = "yahoo"）… jfinance に同じ名前・同じ種類・同じ引数（名前と順番）がある
  - 持たない（jf = "absent"）… jfinance に**その名前が無い**
  - 独自の名前 … jfinance にあり、yfinance の名前と重ならない
  - jfinance の公開の名前は、上のどれかに必ず入る（決めていない名前が紛れ込んでいない）
  - jfinance は yfinance を読み込まない
"""

from __future__ import annotations

import inspect
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import jfinance as jf  # noqa: E402
from jfinance.scrapers.funds import FundsData  # noqa: E402

REF = json.load(open(os.path.join(os.path.dirname(__file__), "yf_api_reference.json"), encoding="utf-8"))
CLASSES = {"Ticker": jf.Ticker, "Tickers": jf.Tickers, "Search": jf.Search, "Lookup": jf.Lookup, "FundsData": FundsData}
# 公開の名前として数えないもの（モジュールの中の部品。yfinance も同じ名前で持つ）
MODULE_PARTS = {"base", "const", "data", "exceptions", "lookup", "scrapers", "search", "shared", "ticker", "tickers",
                "utils", "version", "jp", "warnings", "_http", "screener"}

fail = 0
n = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fail, n
    n += 1
    if not ok:
        print(f"  NG   {name}" + (f"\n         {detail}" if detail else ""))
        fail += 1


def params(f) -> list:
    return [p.name for p in inspect.signature(f).parameters.values() if p.name != "self"]


def public_members(cls) -> set:
    return {x for x in dir(cls) if not x.startswith("_")}


print(f"== yfinance {REF['yfinance_version']} の公開 API と比べる")
check("jfinance は yfinance を読み込まない", "yfinance" not in sys.modules)

# モジュール関数・クラス
for name, m in REF["top_level"].items():
    if m["jf"] == "absent":
        check(f"jfinance.{name} は持たない（{m['reason']}）", not hasattr(jf, name))
        continue
    check(f"jfinance.{name} がある", hasattr(jf, name))
    if hasattr(jf, name) and m["kind"] in ("class", "function"):
        obj = getattr(jf, name)
        got = params(obj.__init__ if inspect.isclass(obj) else obj)
        want = [p for p in m["params"] if p != "self"]
        check(f"jfinance.{name} の引数", got == want, f"yfinance {want}\n         jfinance {got}")
own_top = set(REF["jfinance_own"]["top_level"])
for name in own_top:
    check(f"独自 jfinance.{name} がある", hasattr(jf, name))
    check(f"独自 jfinance.{name} は yfinance と重ならない", name not in REF["top_level"])
extra = {x for x in dir(jf) if not x.startswith("_")} - set(REF["top_level"]) - own_top - MODULE_PARTS
check("jfinance の公開の名前はすべて決めたもの", not extra, f"決めていない名前: {sorted(extra)}")

# クラスのメンバー
for cname, cls in CLASSES.items():
    for name, m in REF[cname].items():
        a = inspect.getattr_static(cls, name, None)
        if m["jf"] == "absent":
            check(f"{cname}.{name} は持たない（{m['reason']}）", a is None)
            continue
        if a is None:
            check(f"{cname}.{name} がある", False)
            continue
        kind = "property" if isinstance(a, property) else "method"
        check(f"{cname}.{name} は {m['kind']}", kind == m["kind"], f"jfinance は {kind}")
        if m["kind"] == "method" and kind == "method":
            want = [p[0] for p in m["params"]]
            got = params(getattr(cls, name))
            check(f"{cname}.{name} の引数", got == want, f"yfinance {want}\n         jfinance {got}")
    own = set(REF["jfinance_own"].get(cname, []))
    for name in own:
        check(f"独自 {cname}.{name} がある", inspect.getattr_static(cls, name, None) is not None)
        check(f"独自 {cname}.{name} は yfinance と重ならない", name not in REF[cname])
    extra = public_members(cls) - set(REF[cname]) - own
    check(f"{cname} の公開の名前はすべて決めたもの", not extra, f"決めていない名前: {sorted(extra)}")

check("jfinance は yfinance を読み込まない（最後にもう一度）", "yfinance" not in sys.modules)
print(f"  {n} 項目を比べた")
print("すべて通過" if fail == 0 else f"★NG {fail} 件")
sys.exit(0 if fail == 0 else 1)
