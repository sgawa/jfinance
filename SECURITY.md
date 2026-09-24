# Security

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private reporting:
**Security → Report a vulnerability** on this repository.

That channel needs no email address and is visible only to the maintainer.

## What is in scope

| | |
|---|---|
| **In scope** | The `jfinance` package in this repository — anything that could run code, leak data, or be abused through a crafted response or a crafted symbol |
| Out of scope | The server (`query1.jfnc.org`) is operated separately. Report server problems through the same channel; do not test against it |

**Please do not run scanners or load tests against `query1.jfnc.org`.** It is a small server
with a per-IP rate limit, and traffic like that takes it down for everyone. If you need to
test something at volume, ask first.

## What to expect

jfinance is maintained by one person. There is no SLA. You will get an acknowledgement, and
a fix or an explanation of why it is not one.

## Supported versions

The latest release only.
