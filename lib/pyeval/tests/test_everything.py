import sys
import unittest
from types import ModuleType, FunctionType
import pprint
from cStringIO import StringIO
import math
import re
import os

import pyeval
from pyeval.tests.fakeio import FakeIO



# Unless there's a specific exception, all testing uses this encoding:
os.environ['LC_TYPE'] = 'utf-8'



class mainTests (unittest.TestCase):

    def _test_main(self, expected, args):
        displays = []
        pyeval.main(args, displays.append)
        self.assertEqual([expected], displays)

    def test_a1(self):
        self._test_main('B', ['a1', 'A', 'B', 'C'])

    def test_42(self):
        self._test_main(42, ['42', 'A', 'B', 'C'])

    def test_math_pi(self):
        self._test_main(math.pi, ['math.pi', 'A', 'B', 'C'])



class pyevalTests (unittest.TestCase):
    """High-level tests of pyeval.pyeval."""

    def test_autoimportTopLevel(self):
        import math
        self.assertIs(math, pyeval.pyeval('math')._ai_mod)

    def test_autoimportSubmodule(self):
        ai = pyeval.pyeval('faketestpackage.faketestmodule')
        self.assertIs(ModuleType, type(ai._ai_mod))

    def test_unboundRaisesNameError(self):
        self.assertRaises(NameError, pyeval.pyeval, 'BLORK_IS_NOT_BOUND')



class displayPrettyTests (unittest.TestCase):
    """displayPretty should behave like standard sys.displayhook, except pformat is used."""

    def test_displayNone(self):
        fio = FakeIO()

        with fio:
            pyeval.displayPretty(None)

        self.assertEqual('', fio.fakeout.getvalue())
        self.assertEqual('', fio.fakeerr.getvalue())

    def test_displayValues(self):
        for value in [42, "banana", range(1024), vars()]:
            f = StringIO()
            pprint.pprint(value, f)
            expected = f.getvalue()

            fio = FakeIO()

            with fio:
                pyeval.displayPretty(value)

            self.assertEqual(expected, fio.fakeout.getvalue())
            self.assertEqual('', fio.fakeerr.getvalue())



class MagicScopeTests (unittest.TestCase):
    def setUp(self):
        self.caught = []
        self.scope = pyeval.MagicScope(self.caught.append)

        self.args = [self.a0, self.a1] = ['foo', 'bar']
        self.scope.registerArgsMagic(self.args)

    def test_inputCaching(self):
        rawin = 'foo\nbar\n\n'
        stripin = rawin.strip()
        rlines = rawin.split('\n')
        lines = [ l.strip() for l in rlines ]

        with FakeIO(rawin):
            for i in range(2):
                self.assertEqual(rawin, self.scope['ri'])
                self.assertEqual(stripin, self.scope['i'])
                self.assertEqual(rlines, self.scope['rlines'])
                self.assertEqual(lines, self.scope['lines'])
                self.assertIsInstance(self.scope['help'], pyeval.HelpBrowser)
                self.assertEqual(self.args, self.scope['args'])
                self.assertEqual(self.a0, self.scope['a0'])
                self.assertEqual(self.a1, self.scope['a1'])

    def test_fallthrough(self):
        key = '6ff25ffc'
        x = self.scope[key]
        self.assertIsNone(x)
        self.assertEqual([key], self.caught)

    def test_registerMagic(self):

        callCount = [0]

        @self.scope.registerMagic
        def x():
            callCount[0] += 1
            return callCount[0]

        self.assertEqual(1, self.scope['x'])
        self.assertEqual(1, self.scope['x'])
        self.assertEqual(1, self.scope['x'])

    def test_getMagicDocs(self):
        for (k, v) in self.scope.getMagicDocs():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

    def test_magic_sh(self):

        def test_output(arg, expected):
            sh = self.scope['sh']

            fio = FakeIO()
            with fio:
                result = sh(arg)

            self.assertIsNone(result, 'sh() returned non-None: %r' % (result,))
            self.assertEqual(expected, fio.fakeout.getvalue())
            self.assertEqual('', fio.fakeerr.getvalue())

        test_output(None, '')
        test_output('foo', 'foo\n')
        test_output(42, '42\n')
        test_output(['foo', 42], 'foo\n42\n')
        test_output( ( x for x in ['foo', 42] ), 'foo\n42\n')
        test_output( {'x': 'xylophone', 'y': 'yam'}, 'y\nx\n')

    def test_magicFunctionNamesMatchBinding(self):
        for (name, _) in self.scope.getMagicDocs():
            with FakeIO():
                value = self.scope[name]

            if isinstance(value, FunctionType):
                self.assertEqual(name, value.__name__)



class AutoImporterTests (unittest.TestCase):
    def setUp(self):
        import logging
        self.logging = logging
        from logging import handlers
        self.handlers = handlers

        self.parent = pyeval.AutoImporter(pyeval.import_last('logging'))
        self.child = self.parent.handlers

    def test___repr__(self):
        r = repr(self.child)
        self.assertNotEqual(-1, r.find('AutoImporter'))
        self.assertNotEqual(-1, r.find('logging.handlers'))

    def test__ai_mod(self):
        self.assertIs(self.logging, self.parent._ai_mod)
        self.assertIs(self.handlers, self.child._ai_mod)

    def test__ai_name(self):
        self.assertEqual('logging', self.parent._ai_name)
        self.assertEqual('logging.handlers', self.child._ai_name)

    def test__ai_path(self):
        def getsrc(m):
            path = m.__file__
            assert path.endswith('.pyc')
            return path[:-1]

        self.assertEqual(getsrc(self.logging), self.parent._ai_path)
        self.assertEqual(getsrc(self.logging.handlers), self.child._ai_path)

    def test_attr(self):
        self.assertIs(self.logging.basicConfig, self.parent.basicConfig)
        self.assertIs(self.handlers.MemoryHandler, self.child.MemoryHandler)

    def test_AttributeError(self):
        try:
            self.assertRaises(AttributeError, self.parent.__getattr__, 'WOMBATS!')
        except ImportError:
            self.fail('A missing attribute on an AutoImporter resulted in an ImportError.')


class HelpBrowserTests (unittest.TestCase):
    def setUp(self):
        self.delegateCalls = []
        self.help = pyeval.HelpBrowser(pyeval.MagicScope(), self.delegateCalls.append)

    def test___repr__(self):
        self.assertNotEqual(-1, repr(self.help).find(pyeval.dedent(self.help.HelpText)))
        self.assertEqual([], self.delegateCalls)

    def test_autoImporter(self):
        magic = pyeval.MagicScope()
        ai = magic['sys']
        self.assertIsInstance(ai, pyeval.AutoImporter)
        self.help(ai)
        self.assertEqual([sys], self.delegateCalls)



class DocExampleVerificationTests (unittest.TestCase):

    IndentRgx = re.compile(r'^    .*?$', re.MULTILINE)
    InvocationRgx = re.compile(r"^    \$")
    PyevalInvocationRgx = re.compile(
        r"^    \$ (echo (?P<EFLAG>-e )?'(?P<INPUT>.*?)' \| )?pyeval '(?P<EXPR>.*?)' ?(?P<ARGS>.*?)$")


    def _parseEntries(self, text):
        entry = None
        for m in self.IndentRgx.finditer(text):
            match = m.group(0)
            m2 = self.InvocationRgx.match(match)
            if m2 is None:
                entry[3].append(m.group(0)[4:])
            else:
                if entry is not None and entry[0] is not None:
                    yield entry

                m3 = self.PyevalInvocationRgx.match(match)
                if m3 is not None:
                    args = m3.group('ARGS').split()
                    teststdin = m3.group('INPUT')
                    if teststdin is not None:
                        if m3.group('EFLAG') is not None:
                            teststdin = teststdin.replace('\\n', '\n')
                    entry = (m3.group('EXPR'), args, teststdin, [])
                else:
                    # This is an non-tested example, such as a non-call to pyeval.
                    entry = (None, None, None, [])

        if entry is not None and entry[0] is not None:
            yield entry


    def test_docs(self):

        hb = pyeval.HelpBrowser(pyeval.MagicScope())

        count = 0

        for topic in hb.getAllSubtopics():
            for (expr, args, inputText, outlines) in self._parseEntries(repr(topic)):
                count += 1
                try:
                    if inputText is None:
                        inputText = ''

                    expectedOut = '\n'.join(outlines)

                    # Implement wildcard matches on "...":
                    expectedRawPattern = re.escape(expectedOut)
                    expectedPattern = expectedRawPattern.replace(r'\.\.\.', '.*?')
                    expectedRgx = re.compile(expectedPattern, re.DOTALL)

                    fio = FakeIO(inputText + '\n')

                    with fio:
                        pyeval.main([expr] + args)

                    self.assertRegexpMatches(fio.fakeout.getvalue(), expectedRgx)
                    self.assertEqual('', fio.fakeerr.getvalue())

                except Exception, e:
                    e.args += ('In topic %r' % (topic.fullname,),
                               'In EXPR %r' % (expr,),
                               )
                    raise
