## 何を / What

## なぜ / Why

## 確認したこと / How it was checked

```bash
python tests/test_api_compat.py
python tools/vendor_yfinance.py --check
```

---

- [ ] 生成ファイル（`_keys.py`・`_screen_fields.py`・`financial_keys.md`・`compatibility.md`・`yf_api_reference.json`）を手で直していない
- [ ] yfinance からの写し（`src/jfinance/`）を手で直していない（直すなら `tools/vendor_yfinance.py`）
- [ ] 公開名・返り値の形を変えた場合、その理由を上に書いた
