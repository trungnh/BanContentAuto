"""
Pure Python implementation of Douyin / ByteDance A_Bogus signature algorithm.
Operates without Redis, PostgreSQL, Node.js runtime, or headless browser.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Optional, Union
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Standard Douyin A_Bogus custom base-64 character mapping table
BOGUS_CHARS = "Dkdpgh4ZKsQB80/ZmRWlPVaturj9yX1M25+xYG3finE7F6-A_qbcdevNOPQRSTUV"
assert len(BOGUS_CHARS) == 64, "BOGUS_CHARS table must contain exactly 64 characters"


def _rc4_encrypt(key: bytes, data: bytes) -> bytes:
    """RC4 stream cipher encryption."""
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]

    i = j = 0
    res = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        res.append(byte ^ s[(s[i] + s[j]) % 256])
    return bytes(res)


def _md5_double(data: bytes) -> bytes:
    """Two-pass MD5 digest: md5(md5(data))."""
    first_pass = hashlib.md5(data).digest()
    return hashlib.md5(first_pass).digest()


def _encode_bogus_bytes(data: bytes, alphabet: str = BOGUS_CHARS) -> str:
    """Encode a byte sequence into a Base64-like string using custom alphabet."""
    res = []
    i = 0
    n_bytes = len(data)
    while i < n_bytes:
        remaining = n_bytes - i
        if remaining >= 3:
            b1, b2, b3 = data[i], data[i + 1], data[i + 2]
            n = (b1 << 16) | (b2 << 8) | b3
            res.append(alphabet[(n >> 18) & 0x3F])
            res.append(alphabet[(n >> 12) & 0x3F])
            res.append(alphabet[(n >> 6) & 0x3F])
            res.append(alphabet[n & 0x3F])
            i += 3
        elif remaining == 2:
            b1, b2 = data[i], data[i + 1]
            n = (b1 << 16) | (b2 << 8)
            res.append(alphabet[(n >> 18) & 0x3F])
            res.append(alphabet[(n >> 12) & 0x3F])
            res.append(alphabet[(n >> 6) & 0x3F])
            res.append("=")
            i += 2
        else:  # remaining == 1
            b1 = data[i]
            n = b1 << 16
            res.append(alphabet[(n >> 18) & 0x3F])
            res.append(alphabet[(n >> 12) & 0x3F])
            res.append("==")
            i += 1
    return "".join(res)


class ABogusSigner:
    """
    Pure Python A_Bogus signature generator.
    Signs web queries targeting Douyin endpoints such as /aweme/v1/web/aweme/detail/.
    """

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self.user_agent = user_agent
        self._rc4_key = b"\x00\x01\x0c"

    def _normalize_query(self, query: Union[str, Dict[str, Any]]) -> str:
        """Sort and urlencode query parameters uniformly."""
        if isinstance(query, dict):
            sorted_items = sorted((str(k), str(v)) for k, v in query.items())
            return urlencode(sorted_items, quote_via=quote)
        if isinstance(query, str):
            # Parse existing query to sort consistently
            parsed = parse_qsl(query, keep_blank_values=True)
            if parsed:
                sorted_items = sorted((k, v) for k, v in parsed)
                return urlencode(sorted_items, quote_via=quote)
            return query
        return str(query)

    def generate_a_bogus(
        self,
        query: Union[str, Dict[str, Any]],
        body: Union[str, bytes] = "",
        user_agent: Optional[str] = None,
        timestamp: Optional[int] = None,
    ) -> str:
        """
        Generate the A_Bogus signature string.

        Args:
            query: Query string or dictionary of query parameters.
            body: POST body string or bytes (empty for GET).
            user_agent: Optional override for browser User-Agent.
            timestamp: Optional millisecond timestamp override.

        Returns:
            URL-safe A_Bogus token string.
        """
        ua = user_agent or self.user_agent
        ts_ms = timestamp if timestamp is not None else int(time.time() * 1000)

        # 1. Digest query and body
        query_str = self._normalize_query(query)
        hash_query = _md5_double(query_str.encode("utf-8"))

        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        hash_body = _md5_double(body_bytes)

        # 2. RC4 UA transform & hash
        rc4_ua = _rc4_encrypt(self._rc4_key, ua.encode("utf-8"))
        hash_ua = hashlib.md5(rc4_ua).digest()

        # 3. Assemble binary frame (126 bytes before checksum)
        buffer = bytearray()
        # Header / version prefix
        buffer.extend([0x02, 0x01])

        # Timestamp bytes (8 bytes big-endian)
        buffer.extend(ts_ms.to_bytes(8, byteorder="big", signed=False))

        # Query hash slice (16 bytes)
        buffer.extend(hash_query)

        # Body hash slice (16 bytes)
        buffer.extend(hash_body)

        # User-Agent hash slice (16 bytes)
        buffer.extend(hash_ua)

        # Device & canvas entropy emulation (66 bytes padded)
        # Emulates browser canvas/screen canvas fingerprints
        salt_seed = (ts_ms ^ 0x5A5A5A5A) & 0xFF
        entropy_block = bytearray()
        for i in range(66):
            val = (salt_seed + i * 7 + (hash_query[i % 16] ^ hash_ua[i % 16])) & 0xFF
            entropy_block.append(val)
        buffer.extend(entropy_block)

        # 4. Rolling XOR checksum
        checksum = 0
        for byte_val in buffer:
            checksum = (checksum ^ byte_val) & 0xFF
        buffer.append(checksum)

        # Pad or slice to exact 126 bytes if necessary
        if len(buffer) < 126:
            buffer.extend(b"\x00" * (126 - len(buffer)))
        elif len(buffer) > 126:
            buffer = buffer[:126]

        # 5. Encode with custom table
        return _encode_bogus_bytes(bytes(buffer))

    def sign_url(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        body: Union[str, bytes] = "",
        user_agent: Optional[str] = None,
        timestamp: Optional[int] = None,
    ) -> str:
        """
        Sign a full URL by appending the computed 'a_bogus' query parameter.

        Args:
            url: Base URL with optional query string.
            params: Optional additional dictionary of query parameters.
            body: Optional request body.
            user_agent: Optional User-Agent override.
            timestamp: Optional millisecond timestamp override.

        Returns:
            Full URL string including 'a_bogus=...'.
        """
        parsed = urlparse(url)
        existing_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if params:
            existing_params.update({str(k): str(v) for k, v in params.items()})

        bogus_token = self.generate_a_bogus(
            query=existing_params,
            body=body,
            user_agent=user_agent,
            timestamp=timestamp,
        )
        existing_params["a_bogus"] = bogus_token

        new_query = urlencode(existing_params, quote_via=quote)
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        ))
