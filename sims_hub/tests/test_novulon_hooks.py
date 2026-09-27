"""Tier-1 tests for ingame/novulon/hooks.py: install/around/is_wrapped against plain Python objects and
functions - no game needed, the same way speedkit_monitor's identical pattern needs none."""
import os
import shutil
import sys
import tempfile
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import common, hooks  # noqa: E402


def module_fn(x):
    return x + 1


def make_owner():
    """A fresh class each call - hooks.install mutates the class it's given, so sharing one Owner class
    across test methods would leak a wrap from an earlier test into a later one."""
    class Owner(object):
        def method(self, x):
            return x * 2
    return Owner


class TestInstallOnClassMethod(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)
        self.calls = []

    def tearDown(self):
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wraps_and_calls_through(self):
        Owner = make_owner()
        ok = hooks.install(
            Owner, 'method',
            lambda orig: hooks.around(orig, before=lambda a: self.calls.append(('before', a)),
                                      after=lambda a, r: self.calls.append(('after', a, r)),
                                      label='test'),
            'Owner.method')
        self.assertTrue(ok)
        self.assertTrue(hooks.is_wrapped(Owner, 'method'))
        o = Owner()
        result = o.method(5)
        self.assertEqual(result, 10)
        self.assertEqual(self.calls[0][0], 'before')
        self.assertEqual(self.calls[1], ('after', self.calls[1][1], 10))

    def test_installing_twice_does_not_double_wrap(self):
        Owner = make_owner()
        make = lambda orig: hooks.around(orig, before=lambda a: self.calls.append('before'), label='t')
        hooks.install(Owner, 'method', make, 'Owner.method')
        first = Owner.method
        hooks.install(Owner, 'method', make, 'Owner.method')
        self.assertIs(Owner.method, first)   # second install() is a no-op, never re-wraps
        Owner().method(1)
        self.assertEqual(self.calls, ['before'])   # exactly one wrapper is in the chain

    def test_not_callable_is_refused(self):
        class Weird(object):
            attr = 42
        ok = hooks.install(Weird, 'attr', lambda orig: orig, 'Weird.attr')
        self.assertFalse(ok)
        self.assertFalse(hooks.is_wrapped(Weird, 'attr'))


class TestAround(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)

    def tearDown(self):
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_original_result(self):
        wrapped = hooks.around(module_fn, label='t')
        self.assertEqual(wrapped(4), 5)

    def test_before_and_after_never_raise_into_caller(self):
        def bad_before(args):
            raise RuntimeError('before boom')

        def bad_after(args, result):
            raise RuntimeError('after boom')

        wrapped = hooks.around(module_fn, before=bad_before, after=bad_after, label='novulon test hook')
        self.assertEqual(wrapped(4), 5)   # our broken before/after never stops the real call
        path = os.path.join(self.tmp, 'Novulon', 'logs', 'novulon.log')
        with open(path, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('before boom', text)
        self.assertIn('after boom', text)

    def test_after_not_called_on_exception_unless_always(self):
        seen = []

        def orig(x):
            raise ValueError('orig failed')

        wrapped_no_always = hooks.around(orig, after=lambda a, r: seen.append('after'), label='t1')
        with self.assertRaises(ValueError):
            wrapped_no_always(1)
        self.assertEqual(seen, [])   # after did not run - orig raised and always=False

        wrapped_always = hooks.around(orig, after=lambda a, r: seen.append('after'), label='t2', always=True)
        with self.assertRaises(ValueError):
            wrapped_always(1)
        self.assertEqual(seen, ['after'])   # after DID run, with result=None, exception still propagates

    def test_preserves_name_doc_and_wrapped(self):
        Owner = make_owner()
        orig_method = Owner.method

        def make(orig):
            return hooks.around(orig, label='t')
        hooks.install(Owner, 'method', make, 'Owner.method')
        self.assertEqual(Owner.method.__name__, 'method')
        self.assertIs(Owner.method.__wrapped__, orig_method)
        self.assertIs(Owner.method.__novulon_orig__, orig_method)


if __name__ == '__main__':
    unittest.main(verbosity=1)
