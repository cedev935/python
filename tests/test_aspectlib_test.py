from __future__ import print_function

import unittest

from aspectlib.test import record, mock


def module_fun(a, b=2):
    pass

def module_fun2(a, b=2):
    pass


class AOPTestCase(unittest.TestCase):
    def test_record(self):
        @record
        def fun(a, b=2):
            pass

        fun(2, 3)
        fun(3, b=4)
        self.assertEqual(fun.calls, [
            (None, (2, 3), {}),
            (None, (3, ), {'b': 4}),
        ])

    def test_record_with_call(self):
        called = []
        @record(call=True)
        def fun():
            called.append(True)

        fun()
        self.assertEqual(fun.calls, [
            (None, (), {}),
        ])
        self.assertEqual(called, [True])

    def test_record_as_context(self):
        with record(module_fun) as history:
            module_fun(2, 3)
            module_fun(3, b=4)

        self.assertEqual(history.calls, [
            (None, (2, 3), {}),
            (None, (3, ), {'b': 4}),
        ])
        del history.calls[:]

        module_fun(2, 3)
        module_fun(3, b=4)
        self.assertEqual(history.calls, [])

    def test_bad_mock(self):
        self.assertRaises(TypeError, mock)
        self.assertRaises(TypeError, mock, call=False)

    def test_simple_mock(self):
        self.assertEqual("foobar", mock("foobar")(module_fun)(1))

    def test_mock_no_calls(self):
        with record(module_fun) as history:
            self.assertEqual("foobar", mock("foobar")(module_fun)(2))
        self.assertEqual(history.calls, [])

    def test_mock_with_calls(self):
        with record(module_fun) as history:
            self.assertEqual("foobar", mock("foobar", call=True)(module_fun)(3))
        self.assertEqual(history.calls, [(None, (3,), {})])

    def test_mock_with_calls_and_default_value(self):
        with record(module_fun) as history:
            self.assertEqual("foobar", mock("foobar", call=True)(module_fun)(3))
        self.assertEqual(history.calls, [(None, (3,), {})])

    def test_double_recording(self):
        with record(module_fun) as history:
            with record(module_fun2) as history2:
                module_fun(2, 3)
                module_fun2(2, 3)

        self.assertEqual(history.calls, [
            (None, (2, 3), {}),
        ])
        del history.calls[:]
        self.assertEqual(history2.calls, [
            (None, (2, 3), {}),
        ])
        del history2.calls[:]

        module_fun(2, 3)
        self.assertEqual(history.calls, [])
        self.assertEqual(history2.calls, [])
