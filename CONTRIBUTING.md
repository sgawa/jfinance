# Contributing

Thank you for looking. Please read the two sections below before opening an issue —
they decide **where** your report should go, and most reports land in the wrong place.

jfinance is maintained by one person in their spare time. There is no SLA, and issues may
sit for a while. Small, specific reports get handled much faster than large vague ones.

日本語でも構いません。

---

## 1. Is it the library, or the data?

jfinance is a **client**. The values come from a server (`https://query1.jfnc.org`) that is
not part of this repository.

| What you see | Where it belongs |
|---|---|
| `AttributeError`, `TypeError`, a wrong shape of DataFrame, a crash | **This repo.** Bug report |
| A number is wrong, missing, or not what the filing says | **This repo**, using the *Data problem* template. It will be fixed on the server |
| A name exists in yfinance but not in jfinance | Most are deliberate — EDINET has no equivalent. Ask in Discussions before opening an issue |
| "Can you add US/other markets?" | Out of scope. jfinance is EDINET only |

### Data problems need three things

Without these it cannot be looked into:

1. **The symbol** (`7203.T`, `E02144`, `G02925`)
2. **What you got, and what you expected**
3. **Where the expected value comes from** — the EDINET document (its ID, e.g. `S100YWGX`)
   or a URL on <https://disclosure2.edinet-fsa.go.jp/>

A screenshot of another site is not enough. The original filing is the reference.

Known limitation, please check it first: **amendments to filings past their EDINET public
inspection period cannot be retrieved**, so old fiscal years may hold pre-amendment values.
See the [data notes](https://jfnc.org/docs/data/notes/).

---

## 2. Files you must not edit by hand

CI rejects pull requests that touch these.

### Copied from yfinance

`src/jfinance/` contains files copied from yfinance 1.5.2. They are produced by
`tools/vendor_yfinance.py`, which records exactly what was removed or replaced.

```bash
python tools/vendor_yfinance.py --check     # must pass
```

To change one of them, change the script, not the file.

### Generated

| File | Produced from |
|---|---|
| `src/jfinance/jp/_keys.py` | the mapping tables |
| `src/jfinance/jp/_screen_fields.py` | the server's `/jf/v1/screener/fields` |
| `tests/yf_api_reference.json` | the yfinance API surface |

These are built by tooling that is not in this repository. If one looks wrong, open an
issue rather than editing it — a hand edit will be overwritten by the next build.

The documentation lives in a separate repository and is published at <https://jfnc.org/>.

---

## 3. Running the tests

```bash
python tests/test_api_compat.py      # naming and arguments vs. yfinance (no network)
python tools/vendor_yfinance.py --check
```

Tests that hit the server are **not** run in CI, because repeated requests from one IP hit
the rate limit. Run them locally, sparingly:

```bash
JFINANCE_BASE_URL=https://query1.jfnc.org python tests/test_client.py
pip install "jfinance[compat-test]"   # optional: uses yfinance as the reference
JFINANCE_BASE_URL=https://query1.jfnc.org python tests/test_output_compat.py
```

---

## 4. Pull requests

- One change per pull request
- Say **why**, not only what
- Keep the existing style: comments explain *why*, and state the evidence behind a decision
- New behaviour needs a test
- If it changes a public name or a return shape, say so — compatibility with yfinance is the
  point of this library, and changing it needs a reason

Please open an issue before writing anything large. It is disappointing for both of us if a
big pull request has to be turned down for a reason that one sentence would have settled.

## 5. License

By contributing you agree that your contribution is licensed under the Apache License 2.0,
the same as the rest of the code.
