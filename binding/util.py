"""Small utilities: memoize and stderr logging for analyze/emit."""
from __future__ import print_function

import sys
from functools import lru_cache


_MEMOIZED_FUNCTIONS = []


def memoize(func):
    @lru_cache(maxsize=1000000)
    def memoized(*args, **kwargs):
        return func(*args, **kwargs)

    _MEMOIZED_FUNCTIONS.append(memoized)
    return memoized


def clear_memoized():
    """Clear caches whose values may refer to a previous translation unit."""
    for memoized in _MEMOIZED_FUNCTIONS:
        memoized.cache_clear()


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
