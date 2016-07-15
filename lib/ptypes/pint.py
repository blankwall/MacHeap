"""Primitive integral types.

A pint.integer_t is an atomic type that is used to describe integer types within
a complex data structure. They contain only one attribute which is the length.
The methods they expose are related to setting or getting the integer value.
This module includes functions for transforming the integer type to an
endian-ness that is different than the platform that the python interpreter is
built for.

At the time of importing this module, the default byteorder is that of the one
specifed by the python interpreter. Within this module, there are 3 methods that
are responsible for adjusting the endianness. They are as follows:

    setbyteorder(order) -- Set the byte-order for all the types in this module
                           globally. This function will modify the byteorder of
                           any type at the time a subtype is made to inherit
                           from it.

    bigendian(type) -- Return the provided pint.integer_t with the byteorder set
                       to bigendian.

    littleendian(type) -- Return the provided pint.integer_t with the byteorder
                          set to littleendian.

The base type within this module that all integral types are based on is labelled
integer_t. This base type includes methods for performing a few operations upon
the integer_t. The interface is as follows:

    class interface(pint.integer_t):
        length = number-of-bytes
        def int(self):
            '''Return the integer_t as an integer'''
        def set(self, integer):
            '''Set the integer_t to the value ``integer``'''
        def flip(self):
            '''Return the integer_t with the alternate byteorder'''

There are two basic integer_t's that each type in this module is based on. They
are the pint.uint_t, and pint.sint_t types. pint.sint_t is a signed integer with
the high-bit representing signedness and pint.uint_t is an unsigned integer. Each
subtype defined in this module is based on one of these two types.

The default types that are provided by this module are as follows:

    pint.uint8_t,pint.uint16_t,pint.uint32_t,pint.uint64_t -- Unsigned integers
    pint.sint8_t,pint.sint16_t,pint.sint32_t,pint.sint64_t -- Signed integers

Each default type is also defined within a ptype.definition that can be used to
locate a type given a particular size. The two definitions are pint.uinteger,
and pint.sinteger. These types are also aliased to pint.uint and pint.sint.

    # find a pint.uint_t that is 2 bytes in length
    type = pint.uinteger.get(2)

    # find a pint.sint_t that is 1 byte in length
    type = pint.sinteger.get(1)

Also included in this module is an enumeration type called `pint.enum`. In some
cases a developer might describe a complex data structure as having an integer
with a named identifier. The `pint.enum` type can be used to represent these
types of definitions. This enumeration type has the following interface:

    class type(pint.enum, integral-subtype):
        _values_ = [
            ('name1', 0xvalue1),
            ('name2', 0xvalue2),
        ]

        @classmethod
        def names(cls):
            '''Return the names of each enumeration.'''
        @classmethod
        def enumerations(cls):
            '''Return the values of each enumeration.'''
        @classmethod
        def byValue(cls, value):
            '''Return the enumeration name based on the ``value``.'''
        @classmethod
        def byName(cls, name):
            '''Return the enumeration value based on the ``name``.'''

Example usage:
    # change the endianness to little-endian globally
    from ptypes import pint
    pint.setbyteorder(pint.littleendian)

    # define an integral type of 3 bytes in length
    class type(pint.uint_t):
        length = 3

    # define a signed integral type of 8 bytes in length
    class type(pint.sint_t):
        length = 8

    # define a little-endian dword type using the decorative form
    @pint.bigendian
    class type(pint.uint32_t):
        pass

    # transform a type to bigendian form after defining
    type = pint.bigendian(type)

    # instantiate and load a 16-bit signed word in little-endian
    type = pint.littleendian(pint.uint16_t)
    instance = type()
    instance.load()

    # change the value of instance
    instance.set(57005)

    # output the value of instance as a numerical value
    print instance.int()

    # return instance in it's alternative byteorder
    flipped = instance.flip()

Example usage of pint.enum:
    # define an enumeration for a uint32_t
    from ptypes import pint
    class enumeration(pint.enum, pint.uint32_t):
        _values_ = [
            ('name1', 0x00000000),
            ('name2', 0x00000001),
            ('name3', 0x00000002),
            ...
        ]

    # instantiate and load an enumeration
    instance = enumeration()
    instance.load()

    # assign the instance by an enumeration name
    instance.set('name1') 

    # return the instance as a name or an integer in string form
    print instance.str()
"""
import six
from . import ptype,bitmap,config,error,utils
Config = config.defaults
Log = Config.log.getChild(__name__[len(__package__)+1:])

def setbyteorder(endianness):
    import __builtin__
    if endianness in (config.byteorder.bigendian,config.byteorder.littleendian):
        for k,v in globals().iteritems():
            if v is not integer_t and isinstance(v,__builtin__.type) and issubclass(v,integer_t) and getattr(v, 'byteorder', config.defaults.integer.order) != endianness:
                d = dict(v.__dict__)
                d['byteorder'] = endianness
                globals()[k] = __builtin__.type(v.__name__, v.__bases__, d)     # re-instantiate types
            continue
        return
    elif getattr(endianness, '__name__', '').startswith('big'):
        return setbyteorder(config.byteorder.bigendian)
    elif getattr(endianness, '__name__', '').startswith('little'):
        return setbyteorder(config.byteorder.littleendian)
    raise ValueError("Unknown integer endianness {!r}".format(endianness))

def bigendian(ptype):
    '''Will convert an integer_t to bigendian form'''
    if not issubclass(ptype, type):
        raise error.TypeError(ptype, 'bigendian')
    import __builtin__
    d = dict(ptype.__dict__)
    d['byteorder'] = config.byteorder.bigendian
    return __builtin__.type(ptype.__name__, ptype.__bases__, d)

def littleendian(ptype):
    '''Will convert an integer_t to littleendian form'''
    if not issubclass(ptype, type):
        raise error.TypeError(ptype, 'littleendian')
    import __builtin__
    d = dict(ptype.__dict__)
    d['byteorder'] = config.byteorder.littleendian
    return __builtin__.type(ptype.__name__, ptype.__bases__, d)

class integer_t(ptype.type):
    '''Provides basic integer-like support'''
    byteorder = config.defaults.integer.order

    def classname(self):
        typename = self.typename()
        if self.byteorder is config.byteorder.bigendian:
            return config.defaults.pint.bigendian_name.format(typename, **(utils.attributes(self) if config.defaults.display.mangle_with_attributes else {}))
        elif self.byteorder is config.byteorder.littleendian:
            return config.defaults.pint.littleendian_name.format(typename, **(utils.attributes(self) if config.defaults.display.mangle_with_attributes else {}))
        else:
            raise error.SyntaxError(self, 'integer_t.classname', message='Unknown integer endianness {!r}'.format(self.byteorder))
        return typename

    def __setvalue__(self, integer):
        if self.byteorder is config.byteorder.bigendian:
            transform = lambda x: reversed(x)
        elif self.byteorder is config.byteorder.littleendian:
            transform = lambda x: x
        else:
            raise error.SyntaxError(self, 'integer_t.set', message='Unknown integer endianness {!r}'.format(self.byteorder))

        mask = (1<<self.blocksize()*8) - 1
        integer &= mask
        bc = bitmap.new(integer, self.blocksize() * 8)
        res = []
        while bc[1] > 0:
            bc,x = bitmap.consume(bc,8)
            res.append(x)
        res = res + [0]*(self.blocksize() - len(res))   # FIXME: use padding
        self.value = str().join(transform(map(chr,res)))
        return self

    def __getvalue__(self):
        return self.int()

    def int(self):
        '''Convert integer type into a number'''
        if not self.initializedQ():
            raise error.InitializationError(self, 'num')

        if self.byteorder is config.byteorder.bigendian:
            return reduce(lambda x,y: x << 8 | ord(y), self.serialize(), 0)
        elif self.byteorder is config.byteorder.littleendian:
            return reduce(lambda x,y: x << 8 | ord(y), reversed(self.serialize()), 0)
        raise error.SyntaxError(self, 'integer_t.int', message='Unknown integer endianness {!r}'.format(self.byteorder))
    __int__ = num = number = int

    def summary(self, **options):
        res = self.int()
        return '{s}0x{n:0{l:d}x} ({s}{n:d})'.format(s='-' if res < 0 else '',n=abs(res),l=self.length*2)

    def flip(self):
        '''Returns an integer with the endianness flipped'''
        if self.byteorder is config.byteorder.bigendian:
            return self.cast(littleendian(self.__class__))
        elif self.byteorder is config.byteorder.littleendian:
            return self.cast(bigendian(self.__class__))
        raise error.UserError(self, 'integer_t.flip', message='Unexpected byte order {!r}'.format(self.byteorder))
type = integer_t

class sint_t(integer_t):
    '''Provides signed integer support'''
    def int(self):
        if not self.initializedQ():
            raise error.InitializationError(self, 'num')
        signmask = int(2**(8*self.blocksize()-1))
        num = super([_ for _ in self.__class__.__mro__ if _.__name__ == 'sint_t'][0],self).int()
        res = num&(signmask-1)
        if num&signmask:
            return (signmask-res)*-1
        return res & (signmask-1)

    def __setvalue__(self, integer):
        signmask = int(2**(8*self.blocksize()))
        res = integer & (signmask-1)
        if integer < 0:
            res |= signmask
        return super([_ for _ in self.__class__.__mro__ if _.__name__ == 'sint_t'][0], self).__setvalue__(res)

class uinteger(ptype.definition): attribute,cache = 'length',{}
class sinteger(ptype.definition): attribute,cache = 'length',{}
uint,sint,integer = uinteger,sinteger,sinteger

@uint.define
class uint_t(integer_t): length = 0
@uint.define
class uint8_t(uint_t): length = 1
@uint.define
class uint16_t(uint_t): length = 2
@uint.define
class uint32_t(uint_t): length = 4
@uint.define
class uint64_t(uint_t): length = 8

@sint.define
class int_t(sint_t): length = 0
@sint.define
class sint8_t(int_t): length = 1
@sint.define
class sint16_t(int_t): length = 2
@sint.define
class sint32_t(int_t): length = 4
@sint.define
class sint64_t(int_t): length = 8

int8_t,int16_t,int32_t,int64_t = sint8_t,sint16_t,sint32_t,sint64_t

class enum(integer_t):
    '''
    An integer_t for managing constants used when you define your integer.
    i.e. class myinteger(pint.enum, pint.uint32_t): pass

    Settable properties:
        _values_:array( tuple( name, value ), ... )<w>
            This contains which enumerations are defined.
    '''
    _values_ = []

    def __init__(self, *args, **kwds):
        super(enum, self).__init__(*args, **kwds)

        # invert ._values_ if they're defined backwards
        if len(self._values_):
            name, value = self._values_[0]
            if isinstance(value, basestring):
                Log.warning("pint.enum : {:s} : {:s}._values_ is defined backwards. Inverting it's values.".format(self.classname(), self.typename()))
                self._values_ = [(k,v) for v,k in self._values_]

        # verify the types are correct for ._values_
        if any(not isinstance(k, basestring) or not isinstance(v, six.integer_types) for k,v in self._values_):
            raise TypeError(self, 'enum.__init__', "{:s}._values_ is of an incorrect format. Should be [({:s}, {:s}), ...]".format(self.classname(), basestring, int))

        # FIXME: fix constants within ._values_ by checking to see if they're out of bounds of our type
        return

    @classmethod
    def byValue(cls, value):
        '''Lookup the string in an enumeration by it's first-defined value'''
        for k,v in cls._values_:
            if v == value:
                return k
        raise KeyError(cls, 'enum.byValue', value)

    @classmethod
    def byName(cls, name):
        '''Lookup the value in an enumeration by it's first-defined name'''
        for k,v in cls._values_:
            if k == name:
                return v
        raise KeyError(cls, 'enum.byName', name)

    def __getattr__(self, name):
        try:
            # if getattr fails, then assume the user wants the value of
            #     a particular enum value
            return self.byName(name)

        except KeyError:
            pass
        raise AttributeError(enum, self, name)

    def str(self):
        '''Return value as a string'''
        res = self.int()
        number = ('0x{:x}'.format(abs(res)) if res >= 0 else '-0x{:x}'.format(abs(res)))
        try:
            value = self.byValue(res) + '({:s})'.format(number)
        except KeyError:
            value = number
        return value

    def summary(self, **options):
        return self.str()

    def __setvalue__(self, value):
        if isinstance(value, basestring):
            value = self.byName(value)
        return super(enum,self).__setvalue__(value)

    def __getitem__(self, name):
        '''If a key is specified, then return True if the enumeration actually matches the specified constant'''
        res = self.byName(name)
        return res == self.int()

    ## XXX: not sure what to name these 2 methods, but i've needed them on numerous occasions
    ##      for readability purposes
    @classmethod
    def names(cls):
        '''Return all the names that have been defined'''
        return [k for k,v in cls._values_]

    @classmethod
    def enumerations(cls):
        '''Return all values that have been defined in this'''
        return [v for k,v in cls._values_]

if __name__ == '__main__':
    import ptype,parray
    import pstruct,parray,pint,provider

    import config,logging
    config.defaults.log.setLevel(logging.DEBUG)

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
    import ptypes
    from ptypes import *
    import provider,utils,struct
    string1 = '\x0a\xbc\xde\xf0'
    string2 = '\xf0\xde\xbc\x0a'

    @TestCase
    def test_int_bigendian_uint32_load():
        a = pint.bigendian(pint.uint32_t)(source=provider.string(string1))
        a = a.l
        if a.int() == 0x0abcdef0 and a.serialize() == string1:
            raise Success
        print b, repr(b.serialize())

    @TestCase
    def test_int_bigendian_uint32_set():
        a = pint.bigendian(pint.uint32_t)(source=provider.string(string1)).l
        a.set(0x0abcdef0)
        if a.int() == 0x0abcdef0 and a.serialize() == string1:
            raise Success
        print b, repr(b.serialize())

    @TestCase
    def test_int_littleendian_load():
        b = pint.littleendian(pint.uint32_t)(source=provider.string(string2)).l
        if b.int() == 0x0abcdef0 and b.serialize() == string2:
            raise Success
        print b, repr(b.serialize())

    @TestCase
    def test_int_littleendian_set():
        b = pint.littleendian(pint.uint32_t)(source=provider.string(string2)).l
        b.set(0x0abcdef0)
        if b.int() == 0x0abcdef0 and b.serialize() == string2:
            raise Success
        print b, repr(b.serialize())

    @TestCase
    def test_int_revert_bigendian_uint32_load():
        pint.setbyteorder(config.byteorder.bigendian)
        a = pint.uint32_t(source=provider.string(string1)).l
        if a.int() == 0x0abcdef0 and a.serialize() == string1:
            raise Success
        print a, repr(a.serialize())

    @TestCase
    def test_int_revert_littleendian_uint32_load():
        pint.setbyteorder(config.byteorder.littleendian)
        a = pint.uint32_t(source=provider.string(string2)).l
        if a.int() == 0x0abcdef0 and a.serialize() == string2:
            raise Success
        print a, repr(a.serialize())

    @TestCase
    def test_int_littleendian_int32_signed_load():
        pint.setbyteorder(config.byteorder.littleendian)
        s = '\xff\xff\xff\xff'
        a = pint.int32_t(source=provider.string(s)).l
        b, = struct.unpack('l',s)
        if a.int() == b and a.serialize() == s:
            raise Success
        print b,a, repr(a.serialize())

    @TestCase
    def test_int_littleendian_int32_unsigned_load():
        pint.setbyteorder(config.byteorder.littleendian)
        s = '\x00\x00\x00\x80'
        a = pint.int32_t(source=provider.string(s)).l
        b, = struct.unpack('l',s)
        if a.int() == b and a.serialize() == s:
            raise Success
        print b,a, repr(a.serialize())

    @TestCase
    def test_int_littleendian_int32_unsigned_highedge_load():
        pint.setbyteorder(config.byteorder.littleendian)
        s = '\xff\xff\xff\x7f'
        a = pint.int32_t(source=provider.string(s)).l
        b, = struct.unpack('l',s)
        if a.int() == b and a.serialize() == s:
            raise Success
        print b,a, repr(a.serialize())

    @TestCase
    def test_int_littleendian_int32_unsigned_lowedge_load():
        pint.setbyteorder(config.byteorder.littleendian)
        s = '\x00\x00\x00\x00'
        a = pint.int32_t(source=provider.string(s)).l
        b, = struct.unpack('l',s)
        if a.int() == b and a.serialize() == s:
            raise Success
        print b,a, repr(a.serialize())

    @TestCase
    def test_enum_set_integer():
        class e(pint.enum, pint.uint32_t):
            _values_ = [
                ('aa', 0xaaaaaaaa),
                ('bb', 0xbbbbbbbb),
                ('cc', 0xcccccccc),
            ]

        a = e().set(0xaaaaaaaa)
        if a['aa']: raise Success

    @TestCase
    def test_enum_set_name():
        class e(pint.enum, pint.uint32_t):
            _values_ = [
                ('aa', 0xaaaaaaaa),
                ('bb', 0xbbbbbbbb),
                ('cc', 0xcccccccc),
            ]

        a = e().set('aa')
        if a['aa']: raise Success

    @TestCase
    def test_enum_unknown_name():
        class e(pint.enum, pint.uint32_t):
            _values_ = [
                ('aa', 0xaaaaaaaa),
                ('bb', 0xbbbbbbbb),
                ('cc', 0xcccccccc),
            ]
        a = e().a
        if not a['aa'] and not a['bb'] and not a['cc']:
            raise Success

    @TestCase
    def test_enum_check_attributes():
        class e(pint.enum, pint.uint32_t):
            _values_ = [
                ('aa', 0xaaaaaaaa),
                ('bb', 0xbbbbbbbb),
                ('cc', 0xcccccccc),
            ]
        a = e()
        if a.aa == 0xaaaaaaaa and a.bb == 0xbbbbbbbb and a.cc == 0xcccccccc:
            raise Success

    @TestCase
    def test_enum_check_output_name():
        class e(pint.enum, pint.uint32_t):
            _values_ = [
                ('aa', 0xaaaaaaaa),
                ('bb', 0xbbbbbbbb),
                ('cc', 0xcccccccc),
            ]
        a = e().set('cc')
        if a.str().startswith('cc') and a.str().endswith('(0x%08x)'%a.int()):
            raise Success

    @TestCase
    def test_enum_check_output_number():
        class e(pint.enum, pint.uint32_t):
            _values_ = [
                ('aa', 0xaaaaaaaa),
                ('bb', 0xbbbbbbbb),
                ('cc', 0xcccccccc),
            ]
        a = e().set(0xdddddddd)
        if a.str() == '0x%08x'%a.int():
            raise Success

#    @TestCase
#    def Test11():
#        raise NotImplementedError

if __name__ == '__main__':
    results = []
    for t in TestCaseList:
        results.append( t() )
