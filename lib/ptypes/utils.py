import sys,itertools,_random,math,_weakref,array,logging
import functools,random

## string formatting
def strdup(string, terminator='\x00'):
    """Will return a copy of ``string`` with the provided ``terminated`` characters trimmed"""
    count = len(list(itertools.takewhile(lambda n: n not in terminator, string)))
    return string[:count]

def indent(string, tabsize=4, char=' ', newline='\n'):
    """Indent each line of ``string`` with the specified tabsize"""
    indent = char*tabsize
    strings = [(indent + x) for x in string.split(newline)]
    return newline.join(strings)

## temporary attribute assignments for a context
class assign(object):
    """Will temporarily assign the provided attributes to the specified to all code within it's scope"""
    def __init__(self, *objects, **attrs):
        self.objects = objects
        self.attributes = attrs

    def __enter__(self):
        objects,attrs = self.objects,self.attributes
        self.states = tuple( dict((k,getattr(o,k)) for k in attrs.keys()) for o in objects)
        [o.__update__(attrs) for o in objects]
        return objects

    def __exit__(self, exc_type, exc_value, traceback):
        [o.__update__(a) for o,a in zip(self.objects,self.states)]
        return

## ptype padding types
class padding:
    """Used for providing padding."""
    class source:
        @classmethod
        def repeat(cls,value):
            return itertools.cycle(iter(value))

        @classmethod
        def source(cls,iterable):
            return (x for x in iter(iterable))

        @classmethod
        def file(cls,file):
            return itertools.imap(file.read, itertools.repeat(1))
            #return (file.read(1) for x in itertools.count())

        @classmethod
        def prng(cls,seed=None):
            random.seed(seed)
            return itertools.imap(chr, itertools.starmap(random.randint, itertools.repeat((0,0xff))))
            #return (chr(random.randint(0,0xff)) for x in itertools.count())

        @classmethod
        def zero(cls):
            return cls.repeat('\x00')

    @classmethod
    def fill(cls, amount, source):
        """Returns a bytearray of ``amount`` elements, from the specified ``source``"""
        return str().join(itertools.islice(source, amount))

## exception remapping
def mapexception(map={}, any=None, ignored=()):
    """Decorator for a function that maps exceptions from one type into another.

    /map/ is a dictionary describing how to map exceptions.
        Each tuple can be one of the following formats and will map any instance of Source to Destination
            (Source, Destination)
            ((Source1,Source2...), Destination)
    /any/ describes the exception to raise if any exception is raised.
        use None to pass the original exception through
    /ignored/ will allow exceptions of these types to fall through

    """
    assert type(map) is dict, 'exception /map/ expected to be of a dictionary type'
    assert hasattr(ignored, '__contains__'), '/ignored/ is expected to be a list of exceptions'
    if any is not None:
        assert issubclass(any,BaseException), '/any/ expected to be a solitary exception'

    def decorator(fn):
        def decorated(*args, **kwds):
            try:
                return fn(*args, **kwds)
            except:
                t,v,_ = sys.exc_info()

            for src,dst in map.iteritems():
                if t is src or (hasattr(src,'__contains__') and t in src):
                    raise dst(t, *v)
                continue
            raise v if t in ignored or any is None else any(t, *v)

        functools.update_wrapper(decorated, fn)
        return decorated
    return decorator

## naming representations of a type or instance
def repr_class(name):
    #return "<class '{:s}'>".format(name)
    return "<class {:s}>".format(name)
def repr_instance(classname, name):
    return "<instance {:s} '{:s}'>".format(classname, name)
def repr_position(pos, hex=True, precision=0):
    if len(pos) == 1:
        ofs, = pos
        return '{:x}'.format(ofs)
    ofs,bofs = pos
    if precision > 0 or hex:
        partial = bofs / 8.0
        if hex:
            return '{:x}.{:x}'.format(ofs,math.trunc(partial*0x10))
        fraction = ':0{:d}d'.format(precision)
        res = '{:x}.{'+fraction+'}'
        return res.format(ofs,math.trunc(partial * 10**precision))
    return '{:x}.{:x}'.format(ofs,bofs)

## hexdumping capability
def printable(s):
    """Return a string of only printable characters"""
    return reduce(lambda t,c: t + (c if ord(c) >= 0x20 and ord(c) < 0x7f else '.'), iter(s), '')

def hexrow(value, offset=0, width=16, breaks=[8]):
    """Returns ``value as a formatted hexadecimal str"""
    value = str(value)[:width]
    extra = width - len(value)

    ## left
    left = '{:04x}'.format(offset)

    ## middle
    res = [ '{:02x}'.format(ord(x)) for x in value ]
    if len(value) < width:
        res += ['  ' for x in range(extra)]

    for x in breaks:
        if x < len(res):
            res[x] = ' '+res[x]
    middle = ' '.join(res)

    ## right
    right = printable(value) + ' '*extra

    return '  '.join((left, middle, right))

def hexdump(value, offset=0, width=16, rows=None, **kwds):
    """Returns ``value`` as a formatted hexdump

    If ``offset`` is specified, then the hexdump will start there.
    If ``rows`` or it's alias ``lines`` is specified, only that number of rows
    will be displayed.
    """

    rows = kwds.pop('rows', kwds.pop('lines', None))
    value = iter(value)

    getRow = lambda o: hexrow(data, offset=o, **kwds)

    res = []
    (ofs, data) = offset, str().join(itertools.islice(value, width))
    for i in (itertools.count(1) if rows is None else xrange(1, rows)):
        res.append( getRow(ofs) )
        ofs, data = (ofs + width, str().join(itertools.islice(value, width)))
        if len(data) < width:
            break
        continue

    if len(data) > 0:
        res.append( getRow(ofs) )
    return '\n'.join(res)

def emit_repr(data, width=0, message=' .. skipped {leftover} chars .. ', padding=' ', **formats):
    """Return a string replaced with ``message`` if larger than ``width``

    Message can contain the following format operands:
    width = width to be displayed
    charwidth = width of each character
    bytewidth = number of bytes that can fit within width
    length = number of bytes displayed
    leftover = approximate number of bytes skipped
    **format = extra format specifiers for message
    """
    size = len(data)
    charwidth = len(r'\xFF')
    bytewidth = width / charwidth
    leftover = size - bytewidth

    hexify = lambda s: ''.join('\\x{:02x}'.format(ord(x)) for x in iter(s))

    if width <= 0 or bytewidth >= len(data):
        return hexify(data)

    # FIXME: the skipped/leftover bytes are being calculated incorrectly..
    msg = message.format(size=size, charwidth=charwidth, width=width, leftover=leftover, **formats)

    # figure out how many bytes we can print
    bytefrac,bytewidth = math.modf((width - len(msg)) * 1.0 / charwidth)
    padlength = math.trunc(charwidth*bytefrac)

    msg = padding*math.trunc(padlength/2.0+0.5) + msg + padding*math.trunc(padlength/2)
    left,right = data[:math.trunc(bytewidth/2 + 0.5)], data[size-math.trunc(bytewidth/2):]
    return hexify(left) + msg + hexify(right)

def emit_hexrows(data, height, message, offset=0, width=16, **attrs):
    """Return a hexdump replaced with ``message`` if rows are larger than ``height``

    Message can contain the following format operands:
    leftover - number of hexdump rows skipped
    height - the height requested
    count - the total rows in the hexdump
    skipped - the total number of bytes skipped
    size - the total number of bytes
    """
    size = len(data)
    count = math.trunc(math.ceil(size*1.0/width))
    half = math.trunc(height/2.0)
    leftover = (count - half*2)
    skipped = leftover*width

    # display everything
    if height <= 0 or leftover <= 0:
        for o in xrange(0, size, width):
            # offset, width, attrs
            yield hexrow(data[o:o+width], offset+o, width, **attrs)
        return

    # display rows
    o1 = offset
    for o in xrange(0, half*width, width):
        yield hexrow(data[o:o+width], o+o1, **attrs)
    yield message.format(leftover=leftover, height=height, count=count, skipped=skipped, size=size)
    o2 = width*(count-half)
    for o in xrange(0, half*width, width):
        yield hexrow(data[o+o2:o+o2+width], o+o1+o2, **attrs)
    return

def attributes(instance):
    """Return all constant attributes of an instance.

    This skips over things that require executing code such as properties.
    """
    i,t = ( set(dir(_)) for _ in (instance,instance.__class__))
    result = {}
    for k in i:
        v = getattr(instance.__class__, k, callable)
        if not (callable(v) or hasattr(v,'__delete__')):
            result[k] = getattr(instance, k)
        continue
    for k in i.difference(t):
        v = getattr(instance, k)
        if not callable(v):
            result[k] = getattr(instance, k)
        continue
    return result

def memoize(*kargs,**kattrs):
    '''Converts a function into a memoized callable
    kargs = a list of positional arguments to use as a key
    kattrs = a keyword-value pair describing attributes to use as a key

    if key='string', use kattrs[key].string as a key
    if key=callable(n)', pass kattrs[key] to callable, and use the returned value as key

    if no memoize arguments were provided, try keying the function's result by _all_ of it's arguments.
    '''
    F_VARARG = 0x4
    F_VARKWD = 0x8
    F_VARGEN = 0x20
    kargs = map(None,kargs)
    kattrs = tuple((o,a) for o,a in sorted(kattrs.items()))
    def prepare_callable(fn, kargs=kargs, kattrs=kattrs):
        if hasattr(fn,'im_func'):
            fn = fn.im_func
        assert isinstance(fn,memoize.__class__), 'Callable {!r} is not of a function type'.format(fn)
        functiontype = type(fn)
        cache = {}
        co = fn.func_code
        flags,varnames = co.co_flags,iter(co.co_varnames)
        assert (flags & F_VARGEN) == 0, 'Not able to memoize {!r} generator function'.format(fn)
        argnames = itertools.islice(varnames, co.co_argcount)
        c_positional = tuple(argnames)
        c_attribute = kattrs
        c_var = (next(varnames) if flags & F_VARARG else None, next(varnames) if flags & F_VARKWD else None)
        if not kargs and not kattrs:
            kargs[:] = itertools.chain(c_positional,filter(None,c_var))
        def key(*args, **kwds):
            res = iter(args)
            p = dict(zip(c_positional,res))
            p.update(kwds)
            a,k = c_var
            if a is not None: p[a] = tuple(res)
            if k is not None: p[k] = dict(kwds)
            k1 = (p.get(k, None) for k in kargs)
            k2 = ((n(p[o]) if callable(n) else getattr(p[o],n,None)) for o,n in c_attribute)
            return tuple(itertools.chain(k1, (None,), k2))
        def callee(*args, **kwds):
            res = key(*args, **kwds)
            return cache[res] if res in cache else cache.setdefault(res, fn(*args,**kwds))

        # set some utilies on the memoized function
        callee.memoize_key = lambda: key
        callee.memoize_key.__doc__ = """Generate a unique key based on the provided arguments"""
        callee.memoize_cache = lambda: cache
        callee.memoize_cache.__doc__ = """Return the current memoize cache"""
        callee.memoize_clear = lambda: cache.clear()
        callee.memoize_clear.__doc__ = """Empty the current memoize cache"""

        callee.func_name = fn.func_name
        callee.func_doc = fn.func_doc
        callee.callable = fn
        return callee if isinstance(callee,functiontype) else functiontype(callee)
    return prepare_callable(kargs.pop(0)) if not kattrs and len(kargs) == 1 and callable(kargs[0]) else prepare_callable

if __name__ == '__main__':
    # test cases are found at next instance of '__main__'
    import config,logging
    config.defaults.log = logging.RootLogger(logging.DEBUG)

    class Result(Exception): pass
    class Success(Result): pass
    class Failure(Result): pass

    TestCaseList = []
    def TestCase(fn):
        def harness(**kwds):
            name = fn.__name__
            try:
                res = fn(**kwds)
                raise Failure
            except Success,e:
                print '%s: %r'% (name,e)
                return True
            except Failure,e:
                print '%s: %r'% (name,e)
            except Exception,e:
                print '%s: %r : %r'% (name,Failure(), e)
            return False
        TestCaseList.append(harness)
        return fn

if __name__ == '__main__':
    import utils

    @mapexception({Failure:Success})
    def blah_failure_to_success():
        raise Failure
    @mapexception(any=Success)
    def blah_success():
        raise OSError
    @mapexception({Failure:Failure})
    def blah_nomatch():
        raise OSError
    @mapexception()
    def blah_noexception():
        pass
    @mapexception({(OSError,StopIteration):Success})
    def blah_multiple_1():
        raise OSError
    @mapexception({(OSError,StopIteration):Success})
    def blah_multiple_2():
        raise StopIteration
    @mapexception(ignored=(OSError,))
    def blah_pass():
        raise OSError

    class blah(object):
        @mapexception({Failure:Success})
        def method(self):
            raise Failure

    @TestCase
    def test_mapexception_1():
        blah_failure_to_success()
    @TestCase
    def test_mapexception_2():
        blah_success()
    @TestCase
    def test_mapexception_3():
        try:
            blah_nomatch()
        except OSError:
            raise Success
    @TestCase
    def test_mapexception_4():
        try:
            blah_noexception()
        except:
            raise Failure
        raise Success
    @TestCase
    def test_mapexception_5():
        blah_multiple_1()
    @TestCase
    def test_mapexception_6():
        blah_multiple_2()
    @TestCase
    def test_mapexception_7():
        x = blah()
        x.method()
    @TestCase
    def test_mapexception_8():
        try:
            x = blah_pass()
        except OSError:
            raise Success

    @TestCase
    def test_memoize_fn_1():
        @utils.memoize('arg1','arg2')
        def blah(arg1,arg2,arg3,arg4):
            blah.counter += 1
            return arg1+arg2
        blah.counter = 0
        blah(15,20,0,0)
        blah(35,30,0,0)
        res = blah(15,20, 30,35)
        if res == 35 and blah.counter == 2:
            raise Success

    @TestCase
    def test_memoize_fn_2():
        @utils.memoize('arg1','arg2', arg3='attribute')
        def blah(arg1,arg2,arg3):
            blah.counter += 1
            return arg1+arg2
        class f(object): attribute=10
        class g(object): attribute=20
        blah.counter = 0
        blah(15,20,f)
        blah(15,20,g)
        res = blah(15,20,f)
        if res == 35 and blah.counter == 2:
            raise Success

    @TestCase
    def test_memoize_fn_3():
        x,y,z = 10,15,20
        @utils.memoize('arg1','arg2', kwds=lambda n: n['arg3'])
        def blah(arg1,arg2,**kwds):
            blah.counter += 1
            return arg1+arg2
        blah.counter = 0
        blah(15,20,arg3=10)
        blah(15,20,arg3=20)
        res = blah(15,20,arg3=10)
        if res == 35 and blah.counter == 2:
            raise Success

    @TestCase
    def test_memoize_im_1():
        class a(object):
            counter = 0
            @utils.memoize('self','arg')
            def blah(self, arg):
                a.counter += 1
                return arg * arg
        x = a()
        x.blah(10)
        x.blah(5)
        res = x.blah(10)
        if x.counter == 2 and res == 100:
            raise Success

    @TestCase
    def test_memoize_im_2():
        class a(object):
            def __init__(self): self.counter = 0
            @utils.memoize('self','arg', self='test')
            def blah(self, arg):
                self.counter += 1
                return arg * arg
            test = 100
        x,y = a(),a()
        x.blah(10)
        x.blah(5)
        y.blah(10)
        res = x.blah(10)
        if x.counter == 2 and y.counter == 1 and res == 100:
            raise Success

    @TestCase
    def test_memoize_im_3():
        class a(object):
            def __init__(self): self.counter = 0
            @utils.memoize('self','arg', self=lambda s: s.test)
            def blah(self, arg):
                self.counter += 1
                return arg * arg
            test = 100
        x,y = a(),a()
        x.blah(10)
        x.blah(5)
        y.blah(10)
        res = x.blah( 10)
        if x.counter == 2 and y.counter == 1 and res == 100:
            raise Success

if __name__ == '__main__':
    results = []
    for t in TestCaseList:
        results.append( t() )
