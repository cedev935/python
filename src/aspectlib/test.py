from collections import namedtuple
from functools import partial
from functools import wraps

from wrapt.decorators import FunctionWrapper

import aspectlib

_Call = namedtuple('Call', ('self', 'args', 'kwargs'))
_DEFAULT = object()
_DEFAULT_FALSE = object()


def mock(return_value, call=_DEFAULT_FALSE):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if call and call is not _DEFAULT_FALSE:
                func(*args, **kwargs)
            return return_value
        return wrapper
    return decorator


class _RecordingWrapper(FunctionWrapper):
    calls = None

    def __init__(self, wrapped, wrapper, calls):
        super(_RecordingWrapper, self).__init__(wrapped, wrapper)
        self.calls = calls

    def __enter__(self):
        self._self_entanglement = aspectlib.weave(self.__wrapped__, lambda _: self)
        return self

    def __exit__(self, *args):
        self._self_entanglement.rollback()


def record(func=None, call=_DEFAULT_FALSE, history=None):
    def record_decorator(func):
        calls = list() if history is None else history

        def record_wrapper(wrapped, instance, args, kwargs):
            calls.append(_Call(instance, args, kwargs))
            if call and call is not _DEFAULT_FALSE:
                return wrapped(*args, **kwargs)
        recorded = _RecordingWrapper(func, record_wrapper, calls)
        return recorded

    if func:
        return record_decorator(func)
    else:
        return partial(record, call=call, history=history)
