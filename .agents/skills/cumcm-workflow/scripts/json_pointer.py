"""Resolve the string representation of an RFC 6901 JSON Pointer."""
import re
from typing import Any


def resolve_json_pointer(data: Any, pointer: str) -> tuple[Any, bool]:
    if pointer == '':
        return data, True
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        return None, False
    current = data
    for raw in pointer[1:].split('/'):
        if re.search(r'~(?:[^01]|$)', raw):
            return None, False
        token = raw.replace('~1', '/').replace('~0', '~')
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and re.fullmatch(r'0|[1-9][0-9]*', token):
            # Compare before converting: arbitrarily long indices must fail cleanly.
            maximum = str(len(current) - 1)
            if not current or len(token) > len(maximum) or (len(token) == len(maximum) and token > maximum):
                return None, False
            current = current[int(token)]
        else:
            return None, False
    return current, True
