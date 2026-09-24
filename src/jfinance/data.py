# このファイルは yfinance 1.5.2 の `data.py` を tools/vendor_yfinance.py がコピーして作った。手で直さない。
# 元: https://github.com/ranaroussi/yfinance （Apache License 2.0, Copyright 2017-2019 Ran Aroussi）
# 中身: 通信（シングルトン・再試行・プロキシ・LRU キャッシュ）
# 変えた点（Apache License 2.0 第 4 条 b）:
#   - 削った: YfData.set_login_cookies, YfData._set_logged_in, YfData._set_cookie_strategy, YfData._save_cookie_curlCffi, YfData._load_cookie_curlCffi, YfData._get_cookie_basic, YfData._get_crumb_basic, YfData._get_cookie_and_crumb_basic, YfData._get_cookie_csrf, YfData._get_crumb_csrf, YfData._get_cookie_and_crumb, YfData._is_this_consent_url, YfData._accept_consent_form, _SUBSCRIPTIONS_URL, _TIER_NAMES, Auth（Yahoo の cookie・crumb・同意画面・ログイン）
#   - 名前 yfinance → jfinance（import・ロガー名・repr）
#   - 差し替えた: 同意画面の解析をしないので bs4 は要らない
#   - 差し替えた: cookie のディスクキャッシュを使わない。通信先を決める jp._server を使う
#   - 差し替えた: Yahoo の同意画面は来ない
#   - 差し替えた: crumb を取らない。Yahoo の URL を jfinance のサーバの URL にする（それ以外の宛先は拒否）
#   - 差し替えた: cookie の方式を切り替えて再送しない。429 はそのまま例外にする

import functools
from functools import lru_cache
import socket
import time as _time

from ._http import requests, new_session, is_supported_session, cookie_jar
from urllib.parse import urlsplit, urljoin
import datetime

from . import utils
from .jp import _server
from .utils import frozendict
from .config import YfConfig
import threading

from .exceptions import YFException, YFDataException, YFRateLimitError


def _is_transient_error(exception):
    """Check if error is transient (network/timeout) and should be retried."""
    if isinstance(exception, (TimeoutError, socket.error, OSError)):
        return True
    error_type_name = type(exception).__name__
    transient_error_types = {
        'Timeout', 'TimeoutError', 'ConnectionError', 'ConnectTimeout',
        'ReadTimeout', 'ChunkedEncodingError', 'RemoteDisconnected',
    }
    return error_type_name in transient_error_types

cache_maxsize = 64


def _normalize_proxy(proxy):
    if isinstance(proxy, str):
        return {"http": proxy, "https": proxy}
    return proxy


def lru_cache_freezeargs(func):
    """
    Decorator transforms mutable dictionary and list arguments into immutable types
    Needed so lru_cache can cache method calls what has dict or list arguments.
    """

    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        args = tuple([frozendict(arg) if isinstance(arg, dict) else arg for arg in args])
        kwargs = {k: frozendict(v) if isinstance(v, dict) else v for k, v in kwargs.items()}
        args = tuple([tuple(arg) if isinstance(arg, list) else arg for arg in args])
        kwargs = {k: tuple(v) if isinstance(v, list) else v for k, v in kwargs.items()}
        return func(*args, **kwargs)

    # copy over the lru_cache extra methods to this wrapper to be able to access them
    # after this decorator has been applied
    wrapped.cache_info = func.cache_info
    wrapped.cache_clear = func.cache_clear
    return wrapped


class SingletonMeta(type):
    """
    Metaclass that creates a Singleton instance.
    """
    _instances = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
            else:
                # Update the existing instance
                if 'session' in kwargs or (args and len(args) > 0):
                    session = kwargs.get('session') if 'session' in kwargs else args[0]
                    cls._instances[cls]._set_session(session)
            return cls._instances[cls]


class YfData(metaclass=SingletonMeta):
    """
    Have one place to retrieve data from Yahoo API in order to ease caching and speed up operations.
    Singleton means one session one cookie shared by all threads.
    """

    def __init__(self, session=None):
        self._crumb = None
        self._cookie = None
        # Whether the user has supplied login cookies (see set_login_cookies).
        # When logged in, the cookie-strategy toggle must not wipe the jar, or
        # it would silently log the user out. Auth corrects this flag to reflect
        # the real login state once it has been verified.
        self._logged_in = False

        # Default to using 'basic' strategy
        self._cookie_strategy = 'basic'
        # If it fails, then fallback method is 'csrf'
        # self._cookie_strategy = 'csrf'

        self._cookie_lock = threading.Lock()

        # Set to True after a single-URL fundamentals-timeseries fetch has
        # failed (typically a silent drop on WSL2 NAT or restrictive corporate
        # proxy). Sticky so a loop over tickers doesn't pay one timeout per
        # ticker; reverted if the chunked fallback also fails.
        self.fundamentals_use_chunked: bool = False

        self._session = None
        self._set_session(session or new_session())

    def _set_session(self, session):
        if session is None:
            return

        # Test for an active cache, not the attribute's presence: curl_cffi >= 0.16
        # Sessions always expose `.cache` (None when disabled).
        if getattr(session, "cache", None) is not None:
            raise YFDataException("Caching sessions (e.g. requests_cache) are not supported. Solution: stop setting session, let jfinance handle.")

        if not is_supported_session(session):
            raise YFDataException(f"Unsupported session type {type(session)}; expected curl_cffi or requests Session. Solution: stop setting session, let jfinance handle.")

        with self._cookie_lock:
            self._session = session
            if YfConfig.network.proxy is not None:
                self._session.proxies = _normalize_proxy(YfConfig.network.proxy)

    @utils.log_indent_decorator
    def get(self, url, params=None, timeout=30):
        response = self._make_request(url, request_method = self._session.get, params=params, timeout=timeout)


        return response

    @utils.log_indent_decorator
    def post(self, url, body=None, params=None, timeout=30, data=None):
        return self._make_request(url, request_method = self._session.post, body=body, params=params, timeout=timeout, data=data)

    @utils.log_indent_decorator
    def _make_request(self, url, request_method, body=None, params=None, timeout=30, data=None):
        # Important: treat input arguments as immutable.

        if len(url) > 200:
            utils.get_yf_logger().debug(f'url={url[:200]}...')
        else:
            utils.get_yf_logger().debug(f'url={url}')
        utils.get_yf_logger().debug(f'params={params}')

        # sync with config
        self._session.proxies = _normalize_proxy(YfConfig.network.proxy)

        if params is None:
            params = {}
        if 'crumb' in params:
            raise YFException("Don't manually add 'crumb' to params dict, let data.py handle it")

        crumbs = {}  # jfinance: crumb は要らない

        request_args = {
            'url': _server.to_server_url(url),
            'params': {**params, **crumbs},
            'timeout': timeout
        }

        if body:
            request_args['json'] = body
        
        if data:
            request_args['data'] = data
            request_args['headers'] = {"Content-Type": "application/json"}

        for attempt in range(YfConfig.network.retries + 1):
            try:
                response = request_method(**request_args)
                break
            except Exception as e:
                if _is_transient_error(e) and attempt < YfConfig.network.retries:
                    _time.sleep(2 ** attempt)
                else:
                    raise
        utils.get_yf_logger().debug(f'response code={response.status_code}')
        # Raise exception if rate limited
        if response.status_code == 429:
            raise YFRateLimitError()

        return response

    @lru_cache_freezeargs
    @lru_cache(maxsize=cache_maxsize)
    def cache_get(self, url, params=None, timeout=30):
        return self.get(url, params, timeout)

    def get_raw_json(self, url, params=None, timeout=30):
        utils.get_yf_logger().debug(f'get_raw_json(): {url}')
        response = self.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()

# Yahoo Finance subscription tier ids. The subscriptions response reports the
# account's tier as an integer in subscriptionView[].tier; tierRanking is
# [3, 4, 5, 6] (there is no tier 1/2, and tier 4 is unmarketed). Reading the id
# is more stable than inferring from granted features, which Yahoo reshuffles
# between tiers for marketing reasons.
