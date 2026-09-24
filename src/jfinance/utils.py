# このファイルは yfinance 1.5.2 の `utils.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: ログ・ISIN・行名の整形・日付の解釈
# 変えた点（Apache License 2.0 第 4 条 b）:
#   - 残した定義だけ: IndentLoggerAdapter, _indentation_level, IndentationContext, get_indented_logger, log_indent_decorator, MultiLineFormatter, yf_logger, yf_log_indented, YFLogFormatter, get_yf_logger, enable_debug_mode, _enable_debug_mode, _disable_debug_mode, is_isin, get_all_by_isin, get_ticker_by_isin, get_info_by_isin, camel2title, snake_case_2_camelCase, _parse_user_dt, is_valid_timezone, dynamic_docstring, _generate_table_configurations, generate_list_table_from_dict, generate_list_table_from_dict_universal（株価の処理（調整・補正・間隔・進捗表示）と財務の旧形式の整形を削る）
#   - 名前 yfinance → jfinance（import・ロガー名・repr）
#   - 差し替えた: ISIN の検索は jfinance のサーバの search で引く（元は第三者のサイトを使う版もあった）。ニュースは持たない

#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# jfinance - market data downloader
# https://github.com/ranaroussi/jfinance
#
# Copyright 2017-2019 Ran Aroussi
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import print_function

import datetime as _datetime
import logging
import re
import re as _re
import sys as _sys
import threading
from functools import wraps
from inspect import getmembers
from types import FunctionType
from typing import List, Optional
import warnings

import numpy as _np
import pandas as _pd
from pandas.api.types import is_float_dtype
import pytz as _tz
from dateutil.relativedelta import relativedelta
from pytz import UnknownTimeZoneError

from jfinance import const
from jfinance.exceptions import YFException
from jfinance.config import YfConfig

# Use the third-party ``frozendict`` package if installed; otherwise fall
# back to a small pure-Python equivalent (PEP 814).
try:
    from frozendict import frozendict  # type: ignore[import-not-found]
except ImportError:
    class frozendict(dict):  # type: ignore[no-redef]
        """Hashable, read-only ``dict`` used as an ``lru_cache`` key."""
        __slots__ = ()

        def __hash__(self):  # type: ignore[override]
            return hash(frozenset(self.items()))

        def __setitem__(self, *args, **kwargs):
            raise TypeError(f"'{type(self).__name__}' object doesn't support item assignment")

        def __delitem__(self, *args, **kwargs):
            raise TypeError(f"'{type(self).__name__}' object doesn't support item deletion")

        def _readonly(self, *args, **kwargs):
            raise AttributeError(f"'{type(self).__name__}' object is read-only")

        pop = _readonly  # type: ignore[assignment]
        popitem = _readonly  # type: ignore[assignment]
        clear = _readonly  # type: ignore[assignment]
        update = _readonly  # type: ignore[assignment]
        setdefault = _readonly  # type: ignore[assignment]


# From https://stackoverflow.com/a/59128615
# Logging
# Note: most of this logic is adding indentation with function depth,
#       so that DEBUG log is readable.
class IndentLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        if get_yf_logger().isEnabledFor(logging.DEBUG):
            i = ' ' * self.extra['indent']
            if not isinstance(msg, str):
                msg = str(msg)
            msg = '\n'.join([i + m for m in msg.split('\n')])
        return msg, kwargs


_indentation_level = threading.local()


class IndentationContext:
    def __init__(self, increment=1):
        self.increment = increment

    def __enter__(self):
        _indentation_level.indent = getattr(_indentation_level, 'indent', 0) + self.increment

    def __exit__(self, exc_type, exc_val, exc_tb):
        _indentation_level.indent -= self.increment


def get_indented_logger(name=None):
    # Never cache the returned value! Will break indentation.
    return IndentLoggerAdapter(logging.getLogger(name), {'indent': getattr(_indentation_level, 'indent', 0)})


def log_indent_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_indented_logger('jfinance')
        logger.debug(f'Entering {func.__name__}()')

        with IndentationContext():
            result = func(*args, **kwargs)

        logger.debug(f'Exiting {func.__name__}()')
        return result

    return wrapper


class MultiLineFormatter(logging.Formatter):
    # The 'fmt' formatting further down is only applied to first line
    # of log message, specifically the padding after %level%.
    # For multi-line messages, need to manually copy over padding.
    def __init__(self, fmt):
        super().__init__(fmt)
        # Extract amount of padding
        match = _re.search(r'%\(levelname\)-(\d+)s', fmt)
        self.level_length = int(match.group(1)) if match else 0

    def format(self, record):
        original = super().format(record)
        lines = original.split('\n')
        levelname = lines[0].split(' ')[0]
        if len(lines) <= 1:
            return original
        else:
            # Apply padding to all lines below first
            formatted = [lines[0]]
            if self.level_length == 0:
                padding = ' ' * len(levelname)
            else:
                padding = ' ' * self.level_length
            padding += ' '  # +1 for space between level and message
            formatted.extend(padding + line for line in lines[1:])
            return '\n'.join(formatted)


yf_logger = None
yf_log_indented = False


class YFLogFormatter(logging.Filter):
    # Help be consistent with structuring YF log messages
    def filter(self, record):
        msg = record.msg
        if hasattr(record, 'yf_cat'):
            msg = f"{record.yf_cat}: {msg}"
        if hasattr(record, 'yf_interval'):
            msg = f"{record.yf_interval}: {msg}"
        if hasattr(record, 'yf_symbol'):
            msg = f"{record.yf_symbol}: {msg}"
        record.msg = msg
        return True


def get_yf_logger():
    global yf_logger
    global yf_log_indented

    if yf_log_indented and not YfConfig.debug.logging:
        _disable_debug_mode()
    elif YfConfig.debug.logging and not yf_log_indented:
        _enable_debug_mode()

    if yf_log_indented:
        yf_logger = get_indented_logger('jfinance')
    elif yf_logger is None:
        yf_logger = logging.getLogger('jfinance')
        yf_logger.addFilter(YFLogFormatter())
    return yf_logger


def enable_debug_mode():
    warnings.warn("enable_debug_mode() is replaced by: yf.config.debug.logging = True (or False to disable)", DeprecationWarning)
    _enable_debug_mode()

def _enable_debug_mode():
    global yf_logger
    global yf_log_indented
    if not yf_log_indented:
        yf_logger = logging.getLogger('jfinance')
        yf_logger.setLevel(logging.DEBUG)
        if yf_logger.handlers is None or len(yf_logger.handlers) == 0:
            h = logging.StreamHandler()
            # Ensure different level strings don't interfere with indentation
            formatter = MultiLineFormatter(fmt='%(levelname)-8s %(message)s')
            h.setFormatter(formatter)
            yf_logger.addHandler(h)
        yf_logger = get_indented_logger()
        yf_log_indented = True


def _disable_debug_mode():
    global yf_logger
    global yf_log_indented
    if yf_log_indented:
        yf_logger = logging.getLogger('jfinance')
        yf_logger.setLevel(logging.NOTSET)
        yf_logger = None
        yf_log_indented = False


def is_isin(string):
    return bool(_re.match("^([A-Z]{2})([A-Z0-9]{9})([0-9])$", string))


def get_all_by_isin(isin):
    if not (is_isin(isin)):
        raise ValueError("Invalid ISIN number")

    # Deferred this to prevent circular imports
    from .search import Search

    search = Search(query=isin, max_results=1)

    # Extract the first quote and news
    ticker = search.quotes[0] if search.quotes else {}
    news = []  # jfinance: ニュースは持たない

    return {
        'ticker': {
            'symbol': ticker.get('symbol', ''),
            'shortname': ticker.get('shortname', ''),
            'longname': ticker.get('longname', ''),
            'type': ticker.get('quoteType', ''),
            'exchange': ticker.get('exchDisp', ''),
        },
        'news': news
    }


def get_ticker_by_isin(isin):
    data = get_all_by_isin(isin)
    return data.get('ticker', {}).get('symbol', '')


def get_info_by_isin(isin):
    data = get_all_by_isin(isin)
    return data.get('ticker', {})


def camel2title(strings: List[str], sep: str = ' ', acronyms: Optional[List[str]] = None) -> List[str]:
    if isinstance(strings, str) or not hasattr(strings, '__iter__'):
        raise TypeError("camel2title() 'strings' argument must be iterable of strings")
    if len(strings) == 0:
        return strings
    if not isinstance(strings[0], str):
        raise TypeError("camel2title() 'strings' argument must be iterable of strings")
    if not isinstance(sep, str) or len(sep) != 1:
        raise ValueError(f"camel2title() 'sep' argument = '{sep}' must be single character")
    if _re.match("[a-zA-Z0-9]", sep):
        raise ValueError(f"camel2title() 'sep' argument = '{sep}' cannot be alpha-numeric")
    if _re.escape(sep) != sep and sep not in {' ', '-'}:
        # Permit some exceptions, I don't understand why they get escaped
        raise ValueError(f"camel2title() 'sep' argument = '{sep}' cannot be special character")

    if acronyms is None:
        pat = "([a-z])([A-Z])"
        rep = rf"\g<1>{sep}\g<2>"
        return [_re.sub(pat, rep, s).title() for s in strings]

    # Handling acronyms requires more care. Assumes Yahoo returns acronym strings upper-case
    if isinstance(acronyms, str) or not hasattr(acronyms, '__iter__') or not isinstance(acronyms[0], str):
        raise TypeError("camel2title() 'acronyms' argument must be iterable of strings")
    for a in acronyms:
        if not _re.match("^[A-Z]+$", a):
            raise ValueError(f"camel2title() 'acronyms' argument must only contain upper-case, but '{a}' detected")

    # Insert 'sep' between lower-then-upper-case
    pat = "([a-z])([A-Z])"
    rep = rf"\g<1>{sep}\g<2>"
    strings = [_re.sub(pat, rep, s) for s in strings]

    # Insert 'sep' after acronyms
    for a in acronyms:
        pat = f"({a})([A-Z][a-z])"
        rep = rf"\g<1>{sep}\g<2>"
        strings = [_re.sub(pat, rep, s) for s in strings]

    # Apply str.title() to non-acronym words
    strings = [s.split(sep) for s in strings]
    strings = [[j.title() if j not in acronyms else j for j in s] for s in strings]
    strings = [sep.join(s) for s in strings]

    return strings


def snake_case_2_camelCase(s):
    sc = s.split('_')[0] + ''.join(x.title() for x in s.split('_')[1:])
    return sc


def _parse_user_dt(dt, exchange_tz=_tz.utc):
    if isinstance(dt, int):
        dt = _pd.Timestamp(dt, unit="s", tz=exchange_tz)
    else:
        # Convert str/date -> datetime, set tzinfo=exchange, get timestamp:
        if isinstance(dt, str):
            dt = _datetime.datetime.strptime(str(dt), '%Y-%m-%d')
        if isinstance(dt, _datetime.date) and not isinstance(dt, _datetime.datetime):
            dt = _datetime.datetime.combine(dt, _datetime.time(0))
        if isinstance(dt, _datetime.datetime):
            if dt.tzinfo is None:
                # Assume user is referring to exchange's timezone
                dt = _pd.Timestamp(dt).tz_localize(exchange_tz)
            else:
                dt = _pd.Timestamp(dt).tz_convert(exchange_tz)
        else: # if we reached here, then it hasn't been any known type
            raise ValueError(f"Unable to parse input dt {dt} of type {type(dt)}")
    return dt


def is_valid_timezone(tz: str) -> bool:
    try:
        _tz.timezone(tz)
    except UnknownTimeZoneError:
        return False
    return True


def dynamic_docstring(placeholders: dict):
    """
    A decorator to dynamically update the docstring of a function or method.
    
    Args:
        placeholders (dict): A dictionary where keys are placeholder names and values are the strings to insert.
    """
    def decorator(func):
        if func.__doc__:
            docstring = func.__doc__
            # Replace each placeholder with its corresponding value
            for key, value in placeholders.items():
                docstring = docstring.replace(f"{{{key}}}", value)
            func.__doc__ = docstring
        return func
    return decorator

def _generate_table_configurations(title = None) -> str:
    import textwrap
    if title is None:
        title = "Permitted Keys/Values"
    table = textwrap.dedent(f"""
    .. list-table:: {title}
       :widths: 25 75
       :header-rows: 1

       * - Key
         - Values
    """)

    return table

def generate_list_table_from_dict(data: dict, bullets: bool=True, title: str=None) -> str:
    """
    Generate a list-table for the docstring showing permitted keys/values.
    """
    table = _generate_table_configurations(title)
    for k in sorted(data.keys()):
        values = data[k]
        table += ' '*3 + f"* - {k}\n"
        lengths = [len(str(v)) for v in values]
        if bullets and max(lengths) > 5:
            table += ' '*5 + "-\n"
            for value in sorted(values):
                table += ' '*7 + f"- {value}\n"
        else:
            value_str = ', '.join(sorted(values))
            table += ' '*5 + f"- {value_str}\n"
    return table

# def generate_list_table_from_dict_of_dict(data: dict, bullets: bool=True, title: str=None) -> str:
#     """
#     Generate a list-table for the docstring showing permitted keys/values.
#     """
#     table = _generate_table_configurations(title)
#     for k in sorted(data.keys()):
#         values = data[k]
#         table += ' '*3 + f"* - {k}\n"
#         if bullets:
#             table += ' '*5 + "-\n"
#             for value in sorted(values):
#                 table += ' '*7 + f"- {value}\n"
#         else:
#             table += ' '*5 + f"- {values}\n"
#     return table


def generate_list_table_from_dict_universal(data: dict, bullets: bool=True, title: str=None, concat_keys=[]) -> str:
    """
    Generate a list-table for the docstring showing permitted keys/values.
    """
    table = _generate_table_configurations(title)
    for k in data.keys():
        values = data[k]

        table += ' '*3 + f"* - {k}\n"
        if isinstance(values, dict):
            table_add = ''

            concat_short_lines = k in concat_keys

            if bullets:
                k_keys = sorted(list(values.keys()))
                current_line = ''
                block_format = 'query' in k_keys
                for i in range(len(k_keys)):
                    k2 = k_keys[i]
                    k2_values = values[k2]
                    k2_values_str = None
                    if isinstance(k2_values, set):
                        k2_values = list(k2_values)
                    elif isinstance(k2_values, dict) and len(k2_values) == 0:
                        k2_values = []
                    if isinstance(k2_values, list):
                        k2_values = sorted(k2_values)
                        all_scalar = all(isinstance(k2v, (int, float, str)) for k2v in k2_values)
                        if all_scalar:
                            k2_values_str = _re.sub(r"[{}\[\]']", "", str(k2_values))

                    if k2_values_str is None:
                        k2_values_str = str(k2_values)

                    if len(current_line) > 0 and (len(current_line) + len(k2_values_str) > 40):
                        # new line
                        table_add += current_line + '\n'
                        current_line = ''

                    if concat_short_lines:
                        if current_line == '':
                            current_line += ' '*5
                            if i == 0:
                                # Only add dash to first
                                current_line += "- "
                            else:
                                current_line += "  "
                            # Don't draw bullet points:
                            current_line += '| '
                        else:
                            current_line += '.  '
                        current_line += f"{k2}: " + k2_values_str
                    else:
                        table_add += ' '*5
                        if i == 0:
                            # Only add dash to first
                            table_add += "- "
                        else:
                            table_add += "  "

                        if '\n' in k2_values_str:
                            # Block format multiple lines
                            table_add += '| ' + f"{k2}: " + "\n"
                            k2_values_str_lines = k2_values_str.split('\n')
                            for j in range(len(k2_values_str_lines)):
                                line = k2_values_str_lines[j]
                                table_add += ' '*7 + '|' + ' '*5 + line
                                if j < len(k2_values_str_lines)-1:
                                    table_add += "\n"
                        else:
                            if block_format:
                                table_add += '| '
                            else:
                                table_add += '* '
                            table_add += f"{k2}: " + k2_values_str

                        table_add += "\n"
                if current_line != '':
                    table_add += current_line + '\n'
            else:
                table_add += ' '*5 + f"- {values}\n"

            table += table_add

        else:
            lengths = [len(str(v)) for v in values]
            if bullets and max(lengths) > 5:
                table += ' '*5 + "-\n"
                for value in sorted(values):
                    table += ' '*7 + f"- {value}\n"
            else:
                value_str = ', '.join(sorted(values))
                table += ' '*5 + f"- {value_str}\n"

    return table
