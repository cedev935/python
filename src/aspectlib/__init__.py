from __future__ import print_function

import re
import sys
import warnings
from collections import deque
from inspect import isclass
from inspect import isfunction
from inspect import isgenerator
from inspect import isgeneratorfunction
from inspect import ismethod
from inspect import ismethoddescriptor
from inspect import isroutine
from inspect import ismodule
from logging import getLogger

try:
    import __builtin__
except ImportError:
    import builtins as __builtin__  # pylint: disable=F0401

try:
    from types import ClassType
except ImportError:
    ClassType = type

from .utils import basestring
from .utils import force_bind
from .utils import make_method_matcher
from .utils import mimic
from .utils import PY2
from .utils import PY3
from .utils import logf
from .utils import Sentinel


__all__ = 'weave', 'Aspect', 'Proceed', 'Return', 'ALL_METHODS', 'NORMAL_METHODS'

logger = getLogger(__name__)
logdebug = logf(logger.debug)
logexception = logf(logger.exception)


UNSPECIFIED = Sentinel('UNSPECIFIED')
ABSOLUTELLY_ALL_METHODS = re.compile('.*')
ALL_METHODS = re.compile('(?!__getattribute__$)')
NORMAL_METHODS = re.compile('(?!__.*__$)')
VALID_IDENTIFIER = re.compile(r'^[^\W\d]\w*$', re.UNICODE if PY3 else 0)


class UnacceptableAdvice(RuntimeError):
    pass


class ExpectedGenerator(TypeError):
    pass


class ExpectedGeneratorFunction(ExpectedGenerator):
    pass


class ExpectedAdvice(TypeError):
    pass


class UnsupportedType(TypeError):
    pass


class Proceed(object):
    """
    Instructs the Aspect Calls to call the decorated function. Can be used multiple times.

    If not used as an instance then the default args and kwargs are used.
    """
    __slots__ = 'args', 'kwargs'

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class Return(object):
    """
    Instructs the Aspect to return a value.
    """
    __slots__ = 'value',

    def __init__(self, value):
        self.value = value


class Aspect(object):
    """
    Container for the advice yielding generator. Can be used as a decorator on other function to change behavior
    according to the advices yielded from the generator.
    """
    __slots__ = 'advising_function'

    def __init__(self, advising_function):
        if not isgeneratorfunction(advising_function):
            raise ExpectedGeneratorFunction("advising_function %s must be a generator function." % advising_function)
        self.advising_function = advising_function

    def __call__(self, cutpoint_function):
        if isgeneratorfunction(cutpoint_function):
            if PY3:
                from aspectlib.py3support import decorate_advising_generator_py3
                return decorate_advising_generator_py3(self.advising_function, cutpoint_function)
            else:
                def advising_generator_wrapper(*args, **kwargs):
                    advisor = self.advising_function(*args, **kwargs)
                    if not isgenerator(advisor):
                        raise ExpectedGenerator("advising_function %s did not return a generator." % self.advising_function)
                    try:
                        advice = next(advisor)
                        while True:
                            logdebug('Got advice %r from %s', advice, self.advising_function)
                            if advice is Proceed or advice is None or isinstance(advice, Proceed):
                                if isinstance(advice, Proceed):
                                    args = advice.args
                                    kwargs = advice.kwargs
                                gen = cutpoint_function(*args, **kwargs)
                                try:
                                    try:
                                        generated = next(gen)
                                    except StopIteration as exc:
                                        logexception("The cutpoint has been exhausted (early).")
                                        result = exc.args and exc.args[0]
                                    else:
                                        while True:
                                            try:
                                                sent = yield generated
                                            except GeneratorExit as exc:
                                                logexception("Got GeneratorExit while consuming the cutpoint")
                                                gen.close()
                                                raise exc
                                            except BaseException as exc:
                                                logexception("Got exception %r. Throwing it the cutpoint", exc)
                                                try:
                                                    generated = gen.throw(*sys.exc_info())
                                                except StopIteration as exc:
                                                    logexception("The cutpoint has been exhausted.")
                                                    result = exc.args and exc.args[0]
                                                    break
                                            else:
                                                try:
                                                    if sent is None:
                                                        generated = next(gen)
                                                    else:
                                                        generated = gen.send(sent)
                                                except StopIteration as exc:
                                                    logexception("The cutpoint has been exhausted.")
                                                    result = exc.args and exc.args[0]
                                                    break
                                except BaseException as exc:
                                    advice = advisor.throw(*sys.exc_info())
                                else:
                                    try:
                                        advice = advisor.send(result)
                                    except StopIteration:
                                        return
                                finally:
                                    gen.close()
                            elif advice is Return:
                                return
                            elif isinstance(advice, Return):
                                raise StopIteration(advice.value)
                            else:
                                raise UnacceptableAdvice("Unknown advice %s" % advice)
                    finally:
                        advisor.close()
                return mimic(advising_generator_wrapper, cutpoint_function)
        else:
            def advising_function_wrapper(*args, **kwargs):
                advisor = self.advising_function(*args, **kwargs)
                if not isgenerator(advisor):
                    raise ExpectedGenerator("advising_function %s did not return a generator." % self.advising_function)
                try:
                    advice = next(advisor)
                    while True:
                        logdebug('Got advice %r from %s', advice, self.advising_function)
                        if advice is Proceed or advice is None or isinstance(advice, Proceed):
                            if isinstance(advice, Proceed):
                                args = advice.args
                                kwargs = advice.kwargs
                            try:
                                result = cutpoint_function(*args, **kwargs)
                            except Exception:
                                advice = advisor.throw(*sys.exc_info())
                            else:
                                try:
                                    advice = advisor.send(result)
                                except StopIteration:
                                    return result
                        elif advice is Return:
                            return
                        elif isinstance(advice, Return):
                            return advice.value
                        else:
                            raise UnacceptableAdvice("Unknown advice %s" % advice)
                finally:
                    advisor.close()
            return mimic(advising_function_wrapper, cutpoint_function)


class Fabric(object):
    pass


class Rollback(object):
    """
    When called, rollbacks all the patches and changes the :func:`weave` has done.
    """
    __slots__ = '_rollbacks'

    def __init__(self, rollback=None):
        if rollback is None:
            self._rollbacks = []
        elif isinstance(rollback, (list, tuple)):
            self._rollbacks = rollback
        else:
            self._rollbacks = [rollback]

    def merge(self, *others):
        self._rollbacks.extend(others)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for rollback in self._rollbacks:
            rollback()

    rollback = __call__ = __exit__


def _checked_apply(aspects, function, module=None):
    logdebug(' > applying aspects %s to function %s.', aspects, function)
    if callable(aspects):
        wrapper = aspects(function)
        assert callable(wrapper), 'Aspect %s did not return a callable (it return %s).' % (aspects, wrapper)
    else:
        wrapper = function
        for aspect in aspects:
            wrapper = aspect(wrapper)
            assert callable(wrapper), 'Aspect %s did not return a callable (it return %s).' % (aspect, wrapper)
    return mimic(wrapper, function, module=module)


def _check_name(name):
    if not VALID_IDENTIFIER.match(name):
        raise SyntaxError(
            "Could not match %r to %r. It should be a string of "
            "letters, numbers and underscore that starts with a letter or underscore." % (
                name, VALID_IDENTIFIER.pattern
            )
        )


def weave(target, aspects, **options):
    """
    Send a message to a recipient

    :param target: The object to weave.
    :type target: string, class, instance, function or builtin

    :param aspects: The aspects to apply to the object.
    :type target: :py:obj:`aspectlib.Aspect`, function decorator or list of

    :param bool subclasses:
        If ``True``, subclasses of target are weaved. *Only available for classes*

    :param bool aliases:
        If ``True``, aliases of target are replaced.

    :param bool lazy:
        If ``True`` only target's ``__init__`` method is patched, the rest of the methods are patched after ``__init__``
        is called. *Only available for classes*.

    :param methods: Methods from target to patch. *Only available for classes*
    :type methods: list or regex or string

    :returns:
        :class:`aspectlib.Rollback` instance

    :raises TypeError:
        If target is a unacceptable object, or the specified options are not available for that type of object.


    .. versionchanged:: 0.4.0

        Replaced `only_methods`, `skip_methods`, `skip_magicmethods` options with `methods`.
        Renamed `on_init` option to `lazy`.
        Added `aliases` option.
        Replaced `skip_subclasses` option with `subclasses`.
    """
    if not callable(aspects):
        if not hasattr(aspects, '__iter__'):
            raise ExpectedAdvice('%s must be an `Aspect` instance, a callable or an iterable of.' % aspects)
        for obj in aspects:
            if not callable(obj):
                raise ExpectedAdvice('%s must be an `Aspect` instance or a callable.' % obj)
    assert target, "Can't weave falsy value %r." % target
    if isinstance(target, (list, tuple)):
        return Rollback([
            weave(item, aspects, **options) for item in target
        ])
    elif isinstance(target, basestring):
        parts = target.split('.')
        for part in parts:
            _check_name(part)

        if len(parts) == 1:
            __import__(part)
            return weave_module(sys.modules[part], aspects, **options)

        for pos in reversed(range(1, len(parts))):
            owner, name = '.'.join(parts[:pos]), '.'.join(parts[pos:])
            try:
                __import__(owner)
                owner = sys.modules[owner]
            except ImportError:
                continue
            else:
                break
        else:
            raise ImportError("Could not import %r. Last try was for %s" % (target, owner))

        if '.' in name:
            path, name = name.rsplit('.', 1)
            path = deque(path.split('.'))
            while path:
                owner = getattr(owner, path.popleft())

        logdebug(" ~ patching %s from %s ...", name, owner)
        obj = getattr(owner, name)

        if isinstance(obj, (type, ClassType)):
            logdebug("   .. as a class %r.", obj)
            return weave_class(
                obj, aspects,
                owner=owner, name=name, **options
            )
        elif callable(obj):  # or isinstance(obj, FunctionType) ??
            logdebug("   .. as a callable %r.", obj)
            return weave_module_function(owner, obj, aspects, force_name=name, **options)
        else:
            return weave(obj, aspects, **options)
    name = getattr(target, '__name__', None)
    logdebug("weave (target=%s, aspects=%s, name=%s, **options=%s)", target, aspects, name, options)
    if name and getattr(__builtin__, name, None) is target:
        return weave_module_function(__builtin__, target, aspects, **options)
    elif PY3 and ismethod(target):
        inst = target.__self__
        name = target.__name__
        logdebug(" ~ patching %r (%s) as instance method.", target, name)
        assert not options, "keyword arguments are not supported when weaving instance methods."
        func = getattr(inst, name)
        setattr(inst, name, _checked_apply(aspects, func).__get__(inst, type(inst)))
        return Rollback(lambda: delattr(inst, name))
    elif PY3 and isfunction(target):
        owner = __import__(target.__module__)
        path = deque(target.__qualname__.split('.')[:-1])
        while path:
            owner = getattr(owner, path.popleft())
        name = target.__name__
        logdebug(" ~ patching %r (%s) as a property.", target, name)
        func = owner.__dict__[name]
        return patch_module(owner, name, _checked_apply(aspects, func), func, **options)
    elif PY2 and isfunction(target):
        return weave_module_function(__import__(target.__module__), target, aspects, **options)
    elif PY2 and ismethod(target):
        if target.im_self:
            inst = target.im_self
            name = target.__name__
            logdebug(" ~ patching %r (%s) as instance method.", target, name)
            assert not options, "keyword arguments are not supported when weaving instance methods."
            func = getattr(inst, name)
            setattr(inst, name, _checked_apply(aspects, func).__get__(inst, type(inst)))
            return Rollback(lambda: delattr(inst, name))
        else:
            klass = target.im_class
            name = target.__name__
            return weave(klass, aspects, methods='%s$' % name, **options)
    elif isclass(target):
        return weave_class(target, aspects, **options)
    elif ismodule(target):
        return weave_module(target, aspects, **options)
    elif type(target).__module__ not in ('builtins', '__builtin__'):
        return weave_instance(target, aspects, **options)
    else:
        raise UnsupportedType("Can't weave object %s of type %s" % (target, type(target)))


def _rewrap_method(func, klass, aspect):
    if isinstance(func, staticmethod):
        if hasattr(func, '__func__'):
            return staticmethod(_checked_apply(aspect, func.__func__))
        else:
            return staticmethod(_checked_apply(aspect, func.__get__(None, klass)))
    elif isinstance(func, classmethod):
        if hasattr(func, '__func__'):
            return classmethod(_checked_apply(aspect, func.__func__))
        else:
            return classmethod(_checked_apply(aspect, func.__get__(None, klass).im_func))
    else:
        return _checked_apply(aspect, func)


def weave_instance(instance, aspect, methods=NORMAL_METHODS, lazy=False, **options):
    """
    Low-level weaver for instances.

    .. warning:: You should not use this directly.

    :returns: An :obj:`aspectlib.Entanglement` object.
    """
    entanglement = Rollback()
    method_matches = make_method_matcher(methods)
    logdebug("weave_instance (module=%r, aspect=%s, methods=%s, lazy=%s, **options=%s)",
             instance, aspect, methods, lazy, options)
    fixup = lambda func: func.__get__(instance, type(instance))
    fixed_aspect = aspect + [fixup] if isinstance(aspect, (list, tuple)) else [aspect, fixup]

    for attr in dir(instance):
        func = getattr(instance, attr)
        if method_matches(attr):
            if ismethod(func):
                logger.info("%s %s %s", attr, func, type(func))
                if hasattr(func, '__func__'):
                    realfunc = func.__func__
                else:
                    realfunc = func.im_func
                entanglement.merge(
                    patch_module(instance, attr, _checked_apply(fixed_aspect, realfunc, module=None), **options)
                )
    return entanglement

def weave_module(module, aspect, methods=NORMAL_METHODS, lazy=False, **options):
    """
    Low-level weaver for "whole module weaving".

    .. warning:: You should not use this directly.

    :returns: An :obj:`aspectlib.Entanglement` object.
    """
    entanglement = Rollback()
    method_matches = make_method_matcher(methods)
    logdebug("weave_module (module=%r, aspect=%s, methods=%s, lazy=%s, **options=%s)",
             module, aspect, methods, lazy, options)

    for attr in dir(module):
        func = getattr(module, attr)
        if method_matches(attr):
            if isroutine(func):
                entanglement.merge(weave_module_function(module, func, aspect, force_name=attr, **options))
            elif isclass(func):
                entanglement.merge(
                    weave_class(func, aspect, owner=module, name=attr, methods=methods, lazy=lazy, **options),
                    #  it's not consistent with the other ways of weaving a class (it's never weaved as a routine).
                    #  therefore it's disabled until it's considered useful.
                    #weave_module_function(module, getattr(module, attr), aspect, force_name=attr, **options),
                )
    return entanglement


def weave_class(klass, aspect, methods=NORMAL_METHODS, subclasses=True, lazy=False,
                owner=None, name=None, aliases=True):
    """
    Low-level weaver for classes.

    .. warning:: You should not use this directly.
    """

    assert isclass(klass), "Can't weave %r. Must be a class." % klass
    entanglement = Rollback()
    method_matches = make_method_matcher(methods)

    if subclasses and hasattr(klass, '__subclasses__'):
        for sub_class in klass.__subclasses__():
            if not issubclass(sub_class, Fabric):
                entanglement.merge(weave_class(sub_class, aspect, methods=methods, subclasses=subclasses, lazy=lazy))
    logdebug("weave_class (klass=%r, methods=%s, subclasses=%s, lazy=%s, owner=%s, name=%s, aliases=%s)",
          klass, methods, subclasses, lazy, owner, name, aliases)
    if lazy:
        def __init__(self, *args, **kwargs):
            super(SubClass, self).__init__(*args, **kwargs)
            for attr in dir(self):
                func = getattr(self, attr, None)
                if method_matches(attr) and attr not in wrappers and isroutine(func):
                    setattr(self, attr, _checked_apply(aspect, force_bind(func)).__get__(self, SubClass))

        wrappers = {
            '__init__': _checked_apply(aspect, __init__) if method_matches('__init__') else __init__
        }
        for attr, func in klass.__dict__.items():
            if method_matches(attr):
                if ismethoddescriptor(func):
                    wrappers[attr] = _rewrap_method(func, klass, aspect)

        logdebug(" * creating subclass with attributes %r", wrappers)
        name = name or klass.__name__
        SubClass = type(name, (klass, Fabric), wrappers)
        SubClass.__module__ = klass.__module__
        module = owner or __import__(klass.__module__)
        entanglement.merge(patch_module(module, name, SubClass, original=klass, aliases=aliases))
    else:
        original = {}
        for attr, func in klass.__dict__.items():
            if method_matches(attr):
                if isroutine(func):
                    logdebug(" ~ patching attributes %r (original: %r).", attr, func)
                    setattr(klass, attr, _rewrap_method(func, klass, aspect))
                else:
                    continue
                original[attr] = func

        entanglement.merge(lambda: deque((
            setattr(klass, attr, func) for attr, func in original.items()
        ), maxlen=0))

    return entanglement


def patch_module(module, name, replacement, original=UNSPECIFIED, aliases=True, location=None):
    """
    Low-level attribute patcher.

    :param module module: Object to patch.
    :param str name: Attribute to patch
    :param replacement: The replacement value.
    :param original: The original value (in case the object beeing patched uses descriptors or is plain weird).
    :param bool aliases: If ``True`` patch all the attributes that have the same original value.

    :returns: An :obj:`aspectlib.Entanglement` object.
    """
    rollback = Rollback()
    seen = False
    original = getattr(module, name) if original is UNSPECIFIED else original
    location = module.__name__ if hasattr(module, '__name__') else type(module).__module__
    try:
        replacement.__module__ = location
    except (TypeError, AttributeError):
        pass
    for alias in dir(module):
        if hasattr(module, alias):
            obj = getattr(module, alias)
            if obj is original:
                if aliases or alias == name:
                    logdebug(" ~ saving %s on %s.%s ...", replacement, location, alias)
                    setattr(module, alias, replacement)
                    rollback.merge(lambda alias=alias: setattr(module, alias, original))
                if alias == name:
                    seen = True
            elif alias == name:
                if ismethod(obj):
                    logdebug(" ~ saving %s on %s.%s ...", replacement, location, alias)
                    setattr(module, alias, replacement)
                    rollback.merge(lambda alias=alias: setattr(module, alias, original))
                else:
                    raise AssertionError("%s.%s = %s is not %s." % (location, alias, obj, original))

    if not seen:
        warnings.warn('Setting %s.%s to %s. There was no previous definition, probably patching the wrong module.' % (
            location, name, replacement
        ))
        logdebug(" ~ saving %s on %s.%s ...", replacement, location, name)
        setattr(module, name, replacement)
        rollback.merge(lambda: setattr(module, name, original))
    return rollback


def weave_module_function(module, target, aspect, force_name=None, **options):
    """
    Low-level weaver for one function from a specified module.

    .. warning:: You should not use this directly.

    :returns: An :obj:`aspectlib.Entanglement` object.
    """
    logdebug("weave_module_function (module=%s, target=%s, aspect=%s, force_name=%s, **options=%s",
          module, target, aspect, force_name, options)
    name = force_name or target.__name__
    return patch_module(module, name, _checked_apply(aspect, target, module=module), original=target, **options)
