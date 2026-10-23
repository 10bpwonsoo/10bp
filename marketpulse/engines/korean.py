"""
한국어 조사 처리.

템플릿에 "은(는)" 같은 이중 표기를 남기면 현업용 화면에서 조악하게 읽힌다.
앞 글자의 받침 유무로 올바른 조사를 고른다.

한글 음절은 U+AC00 ~ U+D7A3 에 배치되어 있고
    (코드포인트 - 0xAC00) % 28
이 0 이 아니면 받침이 있다.

숫자와 영문으로 끝나는 경우도 처리한다. "+66" 은 "육십육" 으로 읽혀 받침이
없고, "VIX" 는 "엑스" 로 읽혀 받침이 있다.
"""

from __future__ import annotations

import re

_HANGUL_START = 0xAC00
_HANGUL_END = 0xD7A3

#: 숫자를 한국어로 읽었을 때 받침이 있는가. 0(영) 1(일) 3(삼) 6(육) 7(칠) 8(팔)
_DIGIT_HAS_BATCHIM = {
    "0": True, "1": True, "2": False, "3": True, "4": False,
    "5": False, "6": True, "7": True, "8": True, "9": False,
}

#: 알파벳 이름을 한국어로 읽었을 때 받침이 있는가. (에이·비·씨 …)
_ALPHA_HAS_BATCHIM = {
    "l": True, "m": True, "n": True, "r": True,
}

_PAIRS = [
    ("은", "는"),
    ("이", "가"),
    ("을", "를"),
    ("과", "와"),
    ("으로", "로"),
]

_PATTERN = re.compile(
    "|".join(rf"{a}\({b}\)" for a, b in _PAIRS)
    + "|"
    + "|".join(rf"{b}\({a}\)" for a, b in _PAIRS)
)


def has_batchim(text: str) -> bool | None:
    """마지막 글자에 받침이 있는가. 판단할 수 없으면 None."""
    stripped = text.rstrip().rstrip(")]}%")
    if not stripped:
        return None
    ch = stripped[-1]

    code = ord(ch)
    if _HANGUL_START <= code <= _HANGUL_END:
        return (code - _HANGUL_START) % 28 != 0
    if ch.isdigit():
        return _DIGIT_HAS_BATCHIM[ch]
    if ch.isascii() and ch.isalpha():
        return _ALPHA_HAS_BATCHIM.get(ch.lower(), False)
    return None


def fix_particles(text: str) -> str:
    """
    "은(는)" 같은 이중 표기를 앞 글자에 맞는 하나로 줄인다.

    판단할 수 없으면 원문을 그대로 둔다. 틀린 조사를 쓰느니 이중 표기가 낫다.
    """

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        first, second = token[: token.index("(")], token[token.index("(") + 1 : -1]
        batchim = has_batchim(text[: match.start()])
        if batchim is None:
            return token
        # 각 쌍의 앞 원소가 '받침 있음' 용이다. 템플릿이 순서를 뒤집어 써도
        # 맞도록 쌍 목록에서 정방향을 찾는다.
        for with_b, without_b in _PAIRS:
            if {first, second} == {with_b, without_b}:
                return with_b if batchim else without_b
        return token

    return _PATTERN.sub(replace, text)
