from __future__ import print_function

import os
import socket
import warnings
import re

import pytest

import aspectlib
from aspectlib.test import mock
from aspectlib.test import record

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

LOG_TEST_SOCKET = r"""^\{_?socket(object)?\}.connect\(\('127.0.0.1', 1\)\) +<<< .*tests/test_integrations.py:\d+:test_socket.*
\{_?socket(object)?\}.connect \~ raised .*(ConnectionRefusedError|error)\((10061|111), '.*refused.*'\)\n$"""


def test_mock_builtin():
    with aspectlib.weave(open, mock('foobar')):
        assert open('???') == 'foobar'

    assert open(__file__) != 'foobar'


def test_mock_builtin_os():
    print(os.open.__name__)
    with aspectlib.weave('os.open', mock('foobar')):
        assert os.open('???') == 'foobar'

    assert os.open(__file__, 0) != 'foobar'


def test_record_warning():
    with aspectlib.weave('warnings.warn', record):
        warnings.warn('crap')
        assert warnings.warn.calls, [(None, ('crap',) == {})]


@pytest.mark.skipif(not hasattr(os, 'fork'), reason="os.fork not available")
def test_fork():
    with aspectlib.weave('os.fork', mock('foobar')):
        pid = os.fork()
        if not pid:
            os._exit(0)
        assert pid == 'foobar'

    pid = os.fork()
    if not pid:
        os._exit(0)
    assert pid != 'foobar'

def test_socket(target=socket.socket):
    buf = StringIO()
    with aspectlib.weave(target, aspectlib.debug.log(
        print_to=buf,
        stacktrace=2,
        module=False
    ), lazy=True):
        s = socket.socket()
        try:
            s.connect(('127.0.0.1', 1))
        except Exception:
            pass

    print(buf.getvalue())
    assert re.match(LOG_TEST_SOCKET, buf.getvalue())

    s = socket.socket()
    try:
        s.connect(('127.0.0.1', 1))
    except Exception:
        pass

    assert re.match(LOG_TEST_SOCKET, buf.getvalue())


def test_socket_as_string_target():
    test_socket(target='socket.socket')


def test_socket_meth(meth=socket.socket.close):
    calls = []
    with aspectlib.weave(meth, record(history=calls)):
        s = socket.socket()
        assert s.close() is None
    assert calls == [(s, (), {})]
    del calls[:]

    s = socket.socket()
    assert s.close() is None
    assert calls == []


def test_socket_meth_as_string_target():
    test_socket_meth('socket.socket.close')
