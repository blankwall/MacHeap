"""Binary-type primitives and containers.

Some parts of a complex data structure are described at a granularity that is
smaller than the atomic "byte" provided by an architecture. This module provides
binary primitives to assist with those types of definitions. Within this module
are 3 basic types. The atomic type that specifies an atomic range of bits. The
array type, which allows one to describe a contiguous list of binary types. And
a structure type, which allows one to describe a container of bits keyed by an
identifier. Each binary type is internally stored as a bitmap. A bitmap is simply
a tuple of (integer-value,number-of-bits). This tuple is abstracted away from the
user, but in some case may be useful to know about.

Each binary type has the same methods as defined by the core ptype module. However,
due to binary types being of different size primitive than the byte type..some of
the methods contain variations that are used to describe the dimensions of a type
by the number of bits. The basic interface for these is:

    class interface(pbinary.type):
        def bitmap(self):
            '''Return ``self`` as a bitmap type'''
        def bits(self):
            '''Return the number of bits. Parallel to .size()'''
        def blockbits(self):
            '''Return the expected number of bits. Parallel to .blocksize()'''
        def setposition(self, position):
            '''Move the binary type to the specified (offset, bit-offset)'''
        def getposition(self):
            '''Return the position of ``self`` as (offset, bit-offset)'''

        .suboffset -- bit offset of ptype

Due to the dimensions of data-structures being along a byte-granularity instead
of a bit-granularity, this module provides an intermediary type that is responsible
for containing any kind of pbinary type. This type is abstracted away from the
user and is created internally when inserting a pbinary type into a regular
byte-granularity ptype. The type is named pbinary.partial, and exposes the
following interface:

    class interface(pbinary.partial):
        byteorder = byte-order-of-type
        _object_ = pbinary-type-that-is-contained

        .object = Returns the pbinary-type that pbinary.partial wraps

Within this module, are two internal types similar to the two types defined within
ptype. These are the .type and .container types. pbinary.type is used to describe
a contiguous range of bits, and pbinary.container is used to describe a container
of pbinary types. When defining a pbinary structure, one can specify either
another pbinary.container or an integer. If an integer is specified, this will
describe the number of bits that the type will represent. These types can be used
in the following two interfaces.

    class interface(pbinary.array):
        _object_ = type
        length = number-of-elements

    class interface(pbinary.struct):
        _fields_ = [
            (type1, 'name1'),
            (integer1, 'name2'),
        ]

Similar to parray, there are types that provided support for sentinel-terminated
and block-sized arrays. These are listed as:

    pbinary.terminatedarray -- .isTerminator(self, value) specifies the sentinel value.
    pbinary.blockarray -- .blockbits(self) returns the number of bits to terminate at.

Another type included by this module is named pbinary.flags. This type is defined
like a pbinary.struct definition, only when it's display..any of it's single bit
fields are displayed when they're True.

Example usage:
# set the byteorder to bigendian
    from ptypes import pbinary,config
    pbinary.setbyteorder(pbinary.config.byteorder.bigendian)

# define an 32-element array of 4-bit sized elements
    class type(pbinary.array):
        _object_ = 4
        length = 32

# define a 2-byte structure
    class type(pbinary.struct):
        _fields_ = [
            (4, 'field1'),
            (2, 'field2'),
            (6, 'field3'),
            (4, 'field4'),
        ]

# define a 16-bit blockarray
    class type(pbinary.blockarray):
        _object_ = 2
        def blockbits(self):
            return 16

# define an array that's terminated when 3 bits are set to 1.
    class type(pbinary.terminatedarray):
        _object_ = 3
        def isTerminator(self, value):
            return value == 7

# define a pbinary flag type
    class type(pbinary.flags):
        _fields_ = [
            (1, 'flag1'),
            (1, 'flag2'),
            (6, 'padding'),
        ]

# instantiate and load a type
    instance = pbinary.new(type)
    instance.load()
"""

import types,inspect,itertools,operator,six
import ptype,utils,bitmap,config,error
Config = config.defaults
Log = Config.log.getChild(__name__[len(__package__)+1:])
__all__ = 'setbyteorder,istype,iscontainer,new,bigendian,littleendian,align,type,container,array,struct,terminatedarray,blockarray,partial'.split(',')

def setbyteorder(endianness):
    '''Sets the _global_ byte order for any pbinary.type.

    ``endianness`` can be either pbinary.bigendian or pbinary.littleendian
    '''
    global partial
    if endianness in (config.byteorder.bigendian,config.byteorder.littleendian):
        result = partial.byteorder
        partial.byteorder = config.byteorder.bigendian if endianness is config.byteorder.bigendian else config.byteorder.littleendian
        return result
    elif getattr(endianness, '__name__', '').startswith('big'):
        return setbyteorder(config.byteorder.bigendian)
    elif getattr(endianness, '__name__', '').startswith('little'):
        return setbyteorder(config.byteorder.littleendian)
    raise ValueError("Unknown integer endianness {!r}".format(endianness))

# instance tests
@utils.memoize('t')
def istype(t):
    return t.__class__ is t.__class__.__class__ and not ptype.isresolveable(t) and (isinstance(t, types.ClassType) or hasattr(object, '__bases__')) and issubclass(t, type)

@utils.memoize('t')
def iscontainer(t):
    return istype(t) and issubclass(t, container)

def force(t, self, chain=None):
    """Resolve type ``t`` into a pbinary.type for the provided object ``self``"""
    if chain is None:
        chain = []
    chain.append(t)

    # conversions
    if bitmap.isinteger(t):
        return ptype.clone(type, value=(0,t))
    if bitmap.isbitmap(t):
        return ptype.clone(type, value=t)

    # passthrough
    if istype(t) or isinstance(t, type):
        return t

    # functions
    if isinstance(t, types.FunctionType):
        return force(t(self), self, chain)
    if isinstance(t, types.MethodType):
        return force(t(), self, chain)

    if inspect.isgenerator(t):
        return force(next(t), self, chain)

    path = ','.join(self.backtrace())
    raise error.TypeError(self, 'force<pbinary>', message='chain={!r} : refusing request to resolve {!r} to a type that does not inherit from pbinary.type : {:s}'.format(chain, t, path))

class type(ptype.generic):
    """An atomic component of any binary array or structure.

    This type is used internally to represent an element of any binary container.
    """
    value,position = None,(0,0)
    def setoffset(self, value, **_):
        _,suboffset = self.getposition()
        return self.setposition((value,suboffset))
    def getoffset(self):
        offset,_ = self.getposition()
        return offset
    def setposition(self, (offset,suboffset), recurse=False):
        result = self.getposition()
        ofs,bofs = (offset + (suboffset // 8), suboffset % 8)
        super(type,self).setposition((ofs,bofs), recurse=recurse)
        return result

    @property
    def suboffset(self):
        _,suboffset = self.getposition()
        return suboffset
    @suboffset.setter
    def suboffset(self, value):
        offset,_ = self.getposition()
        self.setposition((offset,value))
    bofs = boffset = suboffset

    initializedQ = lambda s: s.value is not None

    def int(self):
        return bitmap.value(self.value)
    num = int
    def bits(self):
        return bitmap.size(self.value)
    def blockbits(self):
        return self.bits()
    def __getvalue__(self):
        return self.value
    def __setvalue__(self, value):
        if bitmap.isbitmap(value):
            self.value = value
            return self
        if not isinstance(value, six.integer_types):
            raise error.UserError(self, 'type.__setvalue__', message='tried to call .__setvalue__ with an unknown type {:s}'.format(value.__class__))
        _,size = self.value or (0,0)
        self.value = value,size
        return self
    def bitmap(self):
        return tuple(self.value)
    def update(self, value):
        if not bitmap.isbitmap(value):
            raise error.UserError(self, 'type.update', message='tried to call .update with an unknown type {:s}'.format(value.__class__))
        self.value = value
        return self

    def copy(self, **attrs):
        result = self.new(self.__class__, position=self.getposition())
        if hasattr(self, '__name__'): attrs.setdefault('__name__', self.__name__)
        result.__update__(attrs)
        return result

    def __eq__(self, other):
        if isinstance(other, type):
            return (self.initializedQ(),self.bitmap()) == (other.initializedQ(),other.bitmap())
        return False

    def __deserialize_consumer__(self, consumer):
        try:
            self.__setvalue__(consumer.consume(self.blockbits()))
        except StopIteration, error:
            raise error
        return self

    def new(self, pbinarytype, **attrs):
        res = force(pbinarytype, self)
        return super(type,self).new(res, **attrs)

    def summary(self, **options):
        res = _,size = self.bitmap()
        return '({:s}, {:d})'.format(bitmap.hex(res), size)

    def details(self, **options):
        return bitmap.string(self.bitmap())

    def contains(self, offset):
        nmin = self.getoffset()
        nmax = nmin+self.blocksize()
        return (offset >= nmin) and (offset < nmax)

    # default methods
    def size(self):
        return (self.bits()+7)/8
    def blocksize(self):
        return (self.blockbits()+7)/8

    def alloc(self, **attrs):
        '''will initialize a pbinary.type with zeroes'''
        try:
            with utils.assign(self, **attrs):
                result = self.__deserialize_consumer__(bitmap.consumer(itertools.repeat('\x00')))
        except StopIteration, error:
            raise error.LoadError(self, exception=error)
        return result

    def properties(self):
        result = super(type, self).properties()
        if self.initializedQ() and bitmap.signed(self.bitmap()):
            result['signed'] = True
        return result

    def repr(self, **options):
        return self.details(**options) if self.initializedQ() else '???'

    #def __getstate__(self):
    #    return super(type,self).__getstate__(),self.value,self.position,

    #def __setstate__(self, state):
    #    state,self.value,self.position, = state
    #    super(type,self).__setstate__(state)

class container(type):
    '''contains a list of variable-bit integers'''
    # positioning
    def getposition(self, index=None):
        if index is None:
            return super(container,self).getposition()
        return self.value[index].getposition()

    def setposition(self, (offset,suboffset), recurse=False):
        result = self.getposition()
        ofs,bofs = (offset + (suboffset // 8), suboffset % 8)
        super(container,self).setposition((ofs,bofs))

        if recurse and self.value is not None:
            for n in self.value:
                n.setposition((ofs,bofs), recurse=recurse)
                bofs += n.bits() if n.initializedQ() else n.blockbits()
            pass
        return result

    def copy(self, **attrs):
        """Performs a deep-copy of self repopulating the new instance if self is initialized
        """
        # create an instance of self and update with requested attributes
        result = super(container,self).copy(**attrs)
        result.value = map(operator.methodcaller('copy', **attrs),self.value)
        return result

    def initializedQ(self):
        return self.value is not None and all(x is not None and isinstance(x,type) and x.initializedQ() for x in self.value)

    ### standard stuff
    def int(self):
        return bitmap.value(self.bitmap())
    num = int
    def bitmap(self):
        if self.value is None:
            raise error.InitializationError(self, 'container.bitmap')
        return reduce(bitmap.push, map(operator.methodcaller('bitmap'),self.value), bitmap.new(0,0))
    def bits(self):
        return sum(n.bits() for n in self.value or [])
    def blockbits(self):
        if self.value is None:
            raise error.InitializationError(self, 'container.blockbits')
        return sum(n.blockbits() for n in self.value)
    def blocksize(self):
        return (self.blockbits()+7) // 8

    def __getvalue__(self):
        return tuple(self.value)
    def __setvalue__(self, value):
        if not isinstance(value, six.integer_types):
            raise error.UserError(self, 'container.set', message='tried to call .set with an unknown type {:s}'.format(value.__class__))
        _,size = self.bitmap()
        result = value,size
        for element in self.value:
            result,number = bitmap.shift(result, element.bits())
            element.__setvalue__(number)
        return self

    def update(self, value):
        if bitmap.size(value) != self.blockbits():
            raise error.UserError(self, 'container.update', message='not allowed to change size of container')
        return self.__setvalue__(bitmap.value(value))

    # loading
    def __deserialize_consumer__(self, consumer, generator):
        '''initialize container object with bitmap /consumer/ using the type produced by /generator/'''
        if self.value is None:
            raise error.SyntaxError(self, 'container.__deserialize_consumer__', message='caller is responsible for pre-allocating the elements in self.value')

        position = self.getposition()
        for n in generator:
            self.append(n)
            n.setposition(position)
            n.__deserialize_consumer__(consumer)

            size = n.blockbits()
            offset,suboffset = position
            suboffset += size
            offset,suboffset = (offset + suboffset/8, suboffset % 8)
            position = (offset, suboffset)
        return self

    def serialize(self):
        Log.warn('container.serialize : {:s} : Returning a potentially unaligned binary structure as a string'.format(self.classname()))
        return bitmap.data(self.bitmap())

    def load(self, **attrs):
        raise error.UserError(self, 'container.load', "Not allowed to load from a binary-type. traverse to a partial, and then call .load")

    def commit(self, **attrs):
        raise error.UserError(self, 'container.commit', "Not allowed to commit from a binary-type")

    def alloc(self, **attrs):
        try:
            with utils.assign(self, **attrs):
                result = self.__deserialize_consumer__(bitmap.consumer(itertools.repeat('\x00')))
        except StopIteration, error:
            raise error.LoadError(self, exception=error)
        return result

    def append(self, object):
        '''Add an element to a pbinary.container. Return it's index.'''
        current,size = len(self.value),0 if self.value is None else self.bits()

        offset,suboffset = self.getposition()
        res = (offset+size//8,suboffset+size%8)

        object.parent,object.source = self,None
        if object.getposition() != res:
            object.setposition(res, recurse=True)

        if self.value is None: self.value = []
        self.value.append(object)
        return current

    def cast(self, container, **attrs):
        if not iscontainer(container):
            raise error.UserError(self, 'container.cast', message='unable to cast to type not of a pbinary.container ({:s})'.format(container.typename()))

        source = bitmap.consumer()
        source.push( self.bitmap() )

        target = self.new(container, __name__=self.name(), position=self.getposition(), **attrs)
        target.value = []
        try:
            target.__deserialize_consumer__(source)
        except StopIteration:
            Log.warn('container.cast : {:s} : Incomplete cast to {:s}. Target has been left partially initialized.'.format(self.classname(), target.typename()))
        return target

    # method overloads
    def __iter__(self):
        if self.value is None:
            raise error.InitializationError(self, 'container.__iter__')

        for res in self.value:
            yield res
        return

    def __getitem__(self, index):
        res = self.value[index]
        return res if isinstance(res,container) else res.int()

    def __setitem__(self, index, value):
        # if it's a pbinary element
        if isinstance(value,type):
            res = self.value[index].getposition()
            if value.getposition() != res:
                value.setposition(res, recurse=True)
            value.parent,value.source = self,None
            self.value[index] = value
            return value

        # if element it's being assigned to is a container
        res = self.value[index]
        if not isinstance(res, type):
            raise error.AssertionError(self, 'container.__setitem__', message='Unknown {:s} at index {:d} while trying to assign to it'.format(res.__class__, index))

        # if value is a bitmap
        if bitmap.isbitmap(value):
            size = res.blockbits()
            res.update(value)
            if bitmap.size(value) != size:
                self.setposition(self.getposition(), recurse=True)
            return value

        if not isinstance(value, six.integer_types):
            raise error.UserError(self, 'container.__setitem__', message='tried to assign to index {:d} with an unknown type {:s}'.format(index,value.__class__))

        # update a pbinary.type with the provided value clamped
        return res.__setvalue__(value & ((2**res.bits())-1))

### generics
class _array_generic(container):
    length = 0
    def __len__(self):
        if not self.initialized:
            return self.length
        return len(self.value)

    def __iter__(self):
        for res in super(_array_generic,self).__iter__():
            yield res if isinstance(res,container) else res.int()
        return

    def __getitem__(self, index):
        if isinstance(index, slice):
            result = [ self.value[ self.__getindex__(idx) ] for idx in xrange(*index.indices(len(self))) ]
            t = ptype.clone(array, length=len(result), _object_=self._object_)
            return self.new(t, offset=result[0].getoffset(), value=result)
        return super(_array_generic, self).__getitem__(index)

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            val = itertools.repeat(value) if (isinstance(value, (six.integer_types, type)) or bitmap.isbitmap(value)) else iter(value)
            for idx in xrange(*slice(index.start or 0, index.stop, index.step or 1).indices(index.stop)):
                super(_array_generic, self).__setitem__(idx, next(val))
            return

        value = super(_array_generic, self).__setitem__(index, value)
        if isinstance(value, type):
            value.__name__ = str(index)
        return

    def summary(self, **options):
        return self.__summary_initialized() if self.initializedQ() else self.__summary_uninitialized()

    def details(self, **options):
        # FIXME: make this display the array in a multiline format
        return self.summary(**options)

    def repr(self, **options):
        return self.__summary_initialized() if self.initializedQ() else self.__summary_uninitialized()

    def __getobject_name(self):
        if bitmap.isbitmap(self._object_):
            res = self._object_
            return ('signed<{:d}>' if bitmap.signed(res) else 'unsigned<{:d}>').format(bitmap.size(res))
        elif istype(self._object_):
            return self._object_.typename()
        elif isinstance(self._object_, six.integer_types):
            return ('signed<{:d}>' if self._object_ < 0 else 'unsigned<{:d}>').format(abs(self._object_))
        return self._object_.__name__

    def __summary_uninitialized(self):
        name = self.__getobject_name()
        try:count = len(self)
        except (TypeError): count = None
        return '{:s}[{:s}] ???'.format(name, repr(count) if count is None else str(count))

    def __summary_initialized(self):
        name,value = self.__getobject_name(),self.bitmap()
        try:count = len(self)
        except (TypeError): count = None
        return '{:s}[{:s}] {:s}'.format(name, repr(count) if count is None else str(count), bitmap.hex(value) if bitmap.size(value) > 0 else '...')

    def __getindex__(self, index):
        return self.__getindex__(int(index)) if isinstance(index, basestring) else index

class _struct_generic(container):
    def __init__(self, *args, **kwds):
        super(_struct_generic,self).__init__(*args, **kwds)
        self.__fastindex = {}

    def getposition(self, name=None):
        if name is None:
            return super(_struct_generic,self).getposition()
        index = self.__getindex__(name)
        return super(_struct_generic,self).getposition(index)

    def append(self, object):
        """Add an element to a pbinary.struct. Return it's index."""
        current = super(_struct_generic,self).append(object)
        self.__fastindex[object.name().lower()] = current
        return current

    def alias(self, alias, target):
        """Add an alias from /alias/ to the field /target/"""
        res = self.__getindex__(target)
        self.__fastindex[alias.lower()] = res
    def unalias(self, alias):
        """Remove the alias /alias/ as long as it's not defined in self._fields_"""
        if any(alias.lower() == name.lower() for _,name in self._fields_):
            raise error.UserError(self, '_struct_generic.__contains__', message='Not allowed to remove {:s} from aliases'.format(alias.lower()))
        del self.__fastindex[alias.lower()]

    def __getindex__(self, name):
        if not isinstance(name, basestring):
            raise error.UserError(self, '_struct_generic.__getindex__', message='Element names must be of a str type.')
        try:
            return self.__fastindex[name.lower()]
        except KeyError:
            for i,(_,n) in enumerate(self._fields_):
                if n.lower() == name.lower():
                    return self.__fastindex.setdefault(name.lower(), i)
                continue
        raise KeyError(name)

    def details(self, **options):
        return self.__details_initialized(**options) if self.initializedQ() else self.__details_uninitialized(**options)

    def repr(self, **options):
        return self.__details_initialized(**options) if self.initializedQ() else self.__details_uninitialized(**options)

    def __details_initialized(self):
        result = []
        for (t,name),value in map(None,self._fields_,self.value):
            if value is None:
                if istype(t):
                    typename = t.typename()
                elif bitmap.isbitmap(t):
                    typename = 'signed<{:s}>'.format(bitmap.size(t)) if bitmap.signed(t) else 'unsigned<{:s}>'.format(bitmap.size(t))
                elif isinstance(t, six.integer_types):
                    typename = 'signed<{:d}>'.format(t) if t<0 else 'unsigned<{:d}>'.format(t)
                else:
                    typename = 'unknown<{!r}>'.format(t)

                i = utils.repr_class(typename)
                _hex,_precision = Config.pbinary.offset == config.partial.hex, 3 if Config.pbinary.offset == config.partial.fractional else 0
                result.append('[{:s}] {:s} {:s} ???'.format(utils.repr_position(self.getposition(name), hex=_hex, precision=_precision),i,name,v))
                continue

            _,s = b = value.bitmap()
            i = utils.repr_instance(value.classname(),value.name())
            v = '({:s},{:d})'.format(bitmap.hex(b), s)
            _hex,_precision = Config.pbinary.offset == config.partial.hex, 3 if Config.pbinary.offset == config.partial.fractional else 0
            result.append('[{:s}] {:s} {:s}'.format(utils.repr_position(self.getposition(value.__name__ or name), hex=_hex, precision=_precision),i,value.summary()))
        return '\n'.join(result)

    def __details_uninitialized(self):
        result = []
        for t,name in self._fields_:
            if istype(t):
                s,typename = self.new(t).blockbits(), t.typename()
            elif bitmap.isbitmap(t):
                s,typename = bitmap.size(s),'signed' if bitmap.signed(t) else 'unsigned'
            elif isinstance(t, six.integer_types):
                s,typename = abs(t),'signed' if t<0 else 'unsigned'
            else:
                s,typename = 0,'unknown'

            i = utils.repr_class(typename)
            _hex,_precision = Config.pbinary.offset == config.partial.hex, 3 if Config.pbinary.offset == config.partial.fractional else 0
            result.append('[{:s}] {:s} {:s}{{{:d}}} ???'.format(utils.repr_position(self.getposition(), hex=_hex, precision=_precision),i,name,s))
        return '\n'.join(result)

    # iterator methods
    def iterkeys(self):
        for _,name in self._fields_: yield name

    def itervalues(self):
        for res in self.value:
            yield res if isinstance(res,container) else res.int()
        return

    def iteritems(self):
        for k,v in itertools.izip(self.iterkeys(), self.itervalues()):
            yield k,v
        return

    # list methods
    def keys(self):
        '''return the name of each field'''
        return [ name for _,name in self._fields_ ]

    def values(self):
        '''return all the integer values of each field'''
        return [ res if isinstance(res,container) else res.int() for res in self.value ]

    def items(self):
        return [(k,v) for (_,k),v in zip(self._fields_, self.values())]

    # method overloads
    def __contains__(self, name):
        if not isinstance(name, basestring):
            raise error.UserError(self, '_struct_generic.__contains__', message='Element names must be of a str type.')
        return name in self.__fastindex

    def __iter__(self):
        if self.value is None:
            raise error.InitializationError(self, '_struct_generic.__iter__')

        for k in self.iterkeys():
            yield k
        return

    def __getitem__(self, name):
        index = self.__getindex__(name)
        return super(_struct_generic, self).__getitem__(index)

    def __setitem__(self, name, value):
        index = self.__getindex__(name)
        value = super(_struct_generic, self).__setitem__(index, value)
        if isinstance(value, type):
            value.__name__ = name
        return value

    #def __getstate__(self):
    #    return super(_struct_generic,self).__getstate__(),self.__fastindex

    #def __setstate__(self, state):
    #    state,self.__fastindex, = state
    #    super(_struct_generic,self).__setstate__(state)

class array(_array_generic):
    length = 0

    def copy(self, **attrs):
        """Performs a deep-copy of self repopulating the new instance if self is initialized"""
        result = super(array,self).copy(**attrs)
        result._object_ = self._object_
        result.length = self.length
        return result

    def alloc(self, *fields, **attrs):
        result = super(array,self).alloc(**attrs)
        if len(fields) > 0 and isinstance(fields[0], tuple):
            for k,v in fields:
                idx = result.__getindex__(k)
                #if any((istype(v),isinstance(v,type),ptype.isresolveable(v))):
                if istype(v) or ptype.isresolveable(v):
                    result.value[idx] = result.new(v, __name__=k).alloc(**attrs)
                elif isinstance(v,type):
                    result.value[idx] = result.new(v, __name__=k)
                elif isbitmap(v):
                    result.value[idx] = result.new(type, __name__=k).__setvalue__(v)
                else:
                    result.value[idx].__setvalue__(v)
                continue
            return result
        for idx,v in enumerate(fields):
            #if any((istype(v),isinstance(v,type),ptype.isresolveable(v))):
            if istype(v) or ptype.isresolveable(v) or isinstance(v,type):
                result.value[idx] = result.new(v, __name__=str(idx))
            elif bitmap.isbitmap(v):
                result.value[idx] = result.new(type, __name__=str(idx)).__setvalue__(v)
            else:
                result.value[idx].__setvalue__(v)
            continue
        return result

    def __setvalue__(self, value):
        if self.initializedQ():
            iterable = iter(value) if isinstance(value,(tuple,list)) and len(value) > 0 and isinstance(value[0], tuple) else iter(enumerate(value))
            for idx,val in enumerate(value):
                if istype(val) or ptype.isresolveable(val) or isinstance(val,type):
                    self.value[idx] = result.new(val, __name__=str(idx))
                else:
                    self[idx] = val
                continue
            self.setposition(self.getposition(), recurse=True)
            return self

        self.value = result = []
        for idx,val in enumerate(value):
            if istype(val) or ptype.isresolveable(val):
                res = self.new(val, __name__=str(idx)).a
            elif isinstance(val,type):
                res = self.new(val, __name__=str(idx))
            else:
                res = self.new(self._object_,__name__=str(idx)).a.__setvalue__(val)
            self.value.append(res)
        self.length = len(self.value)
        return self

    def __deserialize_consumer__(self, consumer):
        position = self.getposition()
        obj = self._object_
        self.value = []
        generator = (self.new(obj,__name__=str(index),position=position) for index in xrange(self.length))
        return super(array,self).__deserialize_consumer__(consumer, generator)

    def blockbits(self):
        if self.initializedQ():
            return super(array,self).blockbits()

        res = self._object_
        if isinstance(res, six.integer_types):
            size = res
        elif bitmap.isbitmap(res):
            size = bitmap.size(res)
        elif istype(res):
            size = self.new(res).blockbits()
        else:
            raise error.InitializationError(self, 'array.blockbits')
        return size * len(self)

    #def __getstate__(self):
    #    return super(array,self).__getstate__(),self._object_,self.length

    #def __setstate__(self, state):
    #    state,self._object_,self.length, = state
    #    super(array,self).__setstate__(state)

class struct(_struct_generic):
    _fields_ = None

    def copy(self, **attrs):
        result = super(struct,self).copy(**attrs)
        result._fields_ = self._fields_[:]
        return result

    def alloc(self, __attrs__={}, **fields):
        attrs = __attrs__
        result = super(struct,self).alloc(**attrs)
        if fields:
            for idx,(t,n) in enumerate(self._fields_):
                if n not in fields:
                    if ptype.isresolveable(t): result.value[idx] = result.new(t, __name__=n).alloc(**attrs)
                    continue
                v = fields[n]
                #if any((istype(v),isinstance(v,type),ptype.isresolveable(v))):
                if istype(v) or ptype.isresolveable(v):
                    result.value[idx] = result.new(v, __name__=n).alloc(**attrs)
                elif isinstance(v,type):
                    result.value[idx] = result.new(v, __name__=n)
                elif bitmap.isbitmap(v):
                    result.value[idx] = result.new(type, __name__=n).__setvalue__(v)
                else:
                    result.value[idx].__setvalue__(v)
                continue
            self.setposition(self.getposition(), recurse=True)
        return result

    def __deserialize_consumer__(self, consumer):
        self.value = []
        position = self.getposition()
        generator = (self.new(t,__name__=name,position=position) for t,name in self._fields_)
        return super(struct,self).__deserialize_consumer__(consumer, generator)

    def blockbits(self):
        if self.initializedQ():
            return super(struct,self).blockbits()
        return sum((t if isinstance(t,six.integer_types) else bitmap.size(t) if bitmap.isbitmap(t) else self.new(t).blockbits()) for t,_ in self._fields_)

    def __and__(self, field):
        '''Returns the specified /field/'''
        return self[field]

    def __setvalue__(self, value=(), **individual):
        result = self

        def assign((index, value)):
            if istype(value) or ptype.isresolveable(value):
                k = result.value[index].__name__
                result.value[index] = result.new(value, __name__=k).a
            elif isinstance(value,type):
                k = result.value[index].__name__
                result.value[index] = result.new(value, __name__=k)
            else:
                result.value[index].__setvalue__(value)
            return

        if result.initializedQ():
            if value:
                if len(result._fields_) != len(value):
                    raise error.UserError(result, 'struct.set', message='iterable value to assign with is not of the same length as struct')
                map(assign, enumerate(value))
            map(assign, ((self.__getindex__(k),v) for k,v in individual.iteritems()) )
            result.setposition(result.getposition(), recurse=True)
            return result
        return result.a.__setvalue__(value, **individual)

    #def __getstate__(self):
    #    return super(struct,self).__getstate__(),self._fields_,

    #def __setstate__(self, state):
    #    state,self._fields_, = state
    #    super(struct,self).__setstate__(state)

class terminatedarray(_array_generic):
    length = None

    def alloc(self, *fields, **attrs):
        if 'length' in attrs:
            return super(terminatedarray, self).alloc(*fields, **attrs)

        # a terminatedarray will always have at least 1 element if it's
        #   initialized
        attrs.setdefault('length',1)
        return super(terminatedarray, self).alloc(*fields, **attrs)

    def __deserialize_consumer__(self, consumer):
        self.value = []
        obj = self._object_
        forever = itertools.count() if self.length is None else xrange(self.length)
        position = self.getposition()

        def generator():
            for index in forever:
                n = self.new(obj, __name__=str(index), position=position)
                yield n
                if self.isTerminator(n):
                    break
                continue
            return

        p = generator()
        try:
            return super(terminatedarray,self).__deserialize_consumer__(consumer, p)

        # terminated arrays can also stop when out-of-data
        except StopIteration,e:
            n = self.value[-1]
            path = ' ->\n\t'.join(self.backtrace())
            Log.info("terminatedarray : {:s} : Terminated at {:s}<{:x}:+??>\n\t{:s}".format(self.instance(), n.typename(), n.getoffset(), path))

        return self

    def isTerminator(self, v):
        '''Intended to be overloaded. Should return True if value ``v`` represents the end of the array.'''
        raise error.ImplementationError(self, 'terminatedarray.isTerminator')

    def blockbits(self):
        if self.initializedQ():
            return super(terminatedarray,self).blockbits()
        return 0 if self.length is None else self.new(self._object_).blockbits() * len(self)

class blockarray(terminatedarray):
    length = None
    def isTerminator(self, value):
        return False

    def __deserialize_consumer__(self, consumer):
        obj,position = self._object_,self.getposition()
        total = self.blocksize()*8
        if total != self.blockbits():
            total = self.blockbits()
        value = self.value = []
        forever = itertools.count() if self.length is None else xrange(self.length)
        generator = (self.new(obj,__name__=str(index),position=position) for index in forever)

        # fork the consumer
        consumer = bitmap.consumer().push( (consumer.consume(total),total) )

        try:
            while total > 0:
                n = next(generator)
                n.setposition(position)
                value.append(n)

                n.__deserialize_consumer__(consumer)    #
                if self.isTerminator(n):
                    break

                size = n.blockbits()
                total -= size

                (offset,suboffset) = position
                suboffset += size
                offset,suboffset = (offset + suboffset/8, suboffset % 8)
                position = (offset,suboffset)

            if total < 0:
                Log.info('blockarray.__deserialize_consumer__ : {:s} : Read {:d} extra bits'.format(self.instance(), -total))

        except StopIteration,e:
            # FIXME: fix this error: total bits, bits left, byte offset: bit offset
            Log.warn('blockarray.__deserialize_consumer__ : {:s} : Incomplete read at {!r} while consuming {:d} bits'.format(self.instance(), position, n.blockbits()))
        return self

class partial(ptype.container):
    value = None
    _object_ = None
    byteorder = Config.integer.order
    initializedQ = lambda s:isinstance(s.value,list) and len(s.value) > 0
    __pb_attribute = None

    def __pb_object(self, **attrs):
        ofs = self.getoffset()
        obj = force(self._object_, self)
        updateattrs = {}
        map(updateattrs.update, (self.attributes, attrs))
        list(itertools.starmap(updateattrs.__setitem__, (('position',(ofs,0)), ('parent',self))))
        if hasattr(self.blocksize, 'im_func') and self.blocksize.im_func is not partial.blocksize.im_func:
            updateattrs.setdefault('blockbits', self.blockbits)
        return obj(**updateattrs)

    def __update__(self, attrs={}, **moreattrs):
        res = dict(attrs)
        res.update(moreattrs)

        localk,pbk = set(),set()
        for k in res.keys():
            fn = localk.add if hasattr(self, k) else pbk.add
            fn(k)

        locald = {k : res[k] for k in localk}
        pbd = {k : res[k] for k in pbk}
        if 'recurse' in res:
            locald['recurse'] = pbd['recurse'] = res['recurse']

        super(partial,self).__update__(locald)
        if self.initializedQ(): self.object.__update__(pbd)
        return self

    def copy(self, **attrs):
        result = super(ptype.container,self).copy(**attrs)
        result._object_ = self._object_
        result.byteorder = self.byteorder
        return result

    @property
    def object(self):
        if not self.initializedQ():
            return None
        res, = self.value
        return res
    o = object

    def serialize(self):
        if not self.initializedQ():
            raise error.InitializationError(self, 'partial.serialize')

        res, = self.value
        bmp = res.bitmap()

        if self.byteorder is config.byteorder.bigendian:
            return bitmap.data(bmp)
        if self.byteorder is not config.byteorder.littleendian:
            raise error.AssertionError(self, 'partial.serialize', message='byteorder {:s} is invalid'.format(self.byteorder))
        return str().join(reversed(bitmap.data(bmp)))

    def __deserialize_block__(self, block):
        self.value = res = [self.__pb_object()]
        data = iter(block) if self.byteorder is config.byteorder.bigendian else reversed(block)
        res = res[0].__deserialize_consumer__(bitmap.consumer(data))
        return self

    def load(self, **attrs):
        try:
            self.value = [self.__pb_object()]
            result = self.__load_bigendian(**attrs) if self.byteorder is config.byteorder.bigendian else self.__load_littleendian(**attrs)
            result.setoffset(result.getoffset())
            return result

        except StopIteration, e:
            raise error.LoadError(self, exception=e)

    def __load_bigendian(self, **attrs):
        # big-endian. stream-based
        if self.byteorder is not config.byteorder.bigendian:
            raise error.AssertionError(self, 'partial.load', message='byteorder {:s} is invalid'.format(self.byteorder))

        with utils.assign(self, **attrs):
            o = self.getoffset()
            self.source.seek(o)
            bc = bitmap.consumer( self.source.consume(1) for x in itertools.count() )
            self.object.__deserialize_consumer__(bc)
        return self

    def __load_littleendian(self, **attrs):
        # little-endian. block-based
        if self.byteorder is not config.byteorder.littleendian:
            raise error.AssertionError(self, 'partial.load', message='byteorder {:s} is invalid'.format(self.byteorder))

        with utils.assign(self, **attrs):
            o,s = self.getoffset(),self.blocksize()
            self.source.seek(o)
            block = str().join(reversed(self.source.consume(s)))
            bc = bitmap.consumer(x for x in block)
            self.object.__deserialize_consumer__(bc)
        return self

    def commit(self, **attrs):
        try:
            with utils.assign(self, **attrs):
                self.source.seek( self.getoffset() )
                data = self.serialize()
                self.source.store(data)
            return self

        except (StopIteration,error.ProviderError), e:
            raise error.CommitError(self, exception=e)

    def alloc(self, **attrs):
        try:
            self.value = [self.__pb_object()]
            with utils.assign(self, **attrs):
                result = self.object.__deserialize_consumer__(bitmap.consumer(itertools.repeat('\x00')))
            return self
        except (StopIteration,error.ProviderError), e:
            raise error.LoadError(self, exception=e)

    def bits(self):
        return self.size()*8
    def blockbits(self):
        return self.blocksize()*8

    def size(self):
        v = self.value[0] if self.initializedQ() else self.__pb_object()
        s = v.bits()
        res = (s) if (s&7) == 0x0 else ((s+8)&~7)
        return res / 8
    def blocksize(self):
        v = self.value[0] if self.initializedQ() else self.__pb_object()
        s = v.blockbits()
        res = (s) if (s&7) == 0x0 else ((s+8)&~7)
        return res / 8

    def properties(self):
        result = super(partial,self).properties()
        if self.initialized:
            res, = self.value
            if res.bits() != self.blockbits():
                result['unaligned'] = True
            result['bits'] = res.bits()
        result['partial'] = True

        # endianness
        if self.byteorder is config.byteorder.bigendian:
            result['byteorder'] = 'bigendian'
        else:
            if self.byteorder is not config.byteorder.littleendian:
                raise error.AssertionError(self, 'partial.properties', message='byteorder {:s} is invalid'.format(self.byteorder))
            result['byteorder'] = 'littleendian'
        return result

    ### passthrough
    def __len__(self):
        res, = self.value
        return len(res)
    def __getitem__(self, name):
        res, = self.value
        return res[name]
    def __setitem__(self, name, value):
        res, = self.value
        res[name] = value
    def __iter__(self):
        for res in self.value[0]: yield res

    def __getattr__(self, name):
        if name in ('__module__','__name__'):
            raise AttributeError(name)
        if not self.initializedQ():
            raise error.InitializationError(self, 'partial.__getattr__')
        res, = self.value
        return getattr(res, name)

    def classname(self):
        fmt = {
            config.byteorder.littleendian : Config.pbinary.littleendian_name,
            config.byteorder.bigendian : Config.pbinary.bigendian_name,
        }
        if self.initializedQ():
            res, = self.value
            cn = res.classname()
        else:
            cn = self._object_.typename() if istype(self._object_) else self._object_.__name__
        return fmt[self.byteorder].format(cn, **(utils.attributes(self) if Config.display.mangle_with_attributes else {}))

    def contains(self, offset):
        """True if the specified ``offset`` is contained within"""
        nmin = self.getoffset()
        nmax = nmin+self.blocksize()
        return (offset >= nmin) and (offset < nmax)

    def summary(self, **options):
        return '???' if not self.initializedQ() else self.value[0].summary(**options)

    def details(self, **options):
        return '???' if not self.initializedQ() else self.value[0].details(**options)

    def repr(self, **options):
        return '???' if not self.initializedQ() else self.value[0].repr(**options)

    def __getvalue__(self):
        res, = self.value
        return res.get()

    def __setvalue__(self, *args, **kwds):
        res, = self.value
        return res.set(*args, **kwds)

    #def __getstate__(self):
    #    return super(partial,self).__getstate__(),self._object_,self.position,self.byteorder,

    #def __setstate__(self, state):
    #    state,self._object_,self.position,self.byteorder, = state
    #    super(type,self).__setstate__(state)

    def setoffset(self, offset, recurse=False):
        return self.setposition((offset,), recurse=recurse)

    def setposition(self, (offset,), recurse=False):
        if self.initializedQ():
            res, = self.value
            res.setposition((offset,0), recurse=recurse)
        return super(partial,self).setposition((offset,), recurse=False)

class flags(struct):
    '''represents bit flags that can be toggled'''
    def summary(self, **options):
        return self.__summary_initialized() if self.initializedQ() else self.__summary_uninitialized()

    def __summary_initialized(self):
        flags = []
        for (t,name),value in map(None,self._fields_,self.value):
            if value is None:
                flags.append( (name,value) )
                continue
            flags.append( (name,value.int()) )

        x = _,s = self.bitmap()
        return '({:s}, {:d}) {:s}'.format(bitmap.hex(x), s, ','.join(''.join((n, '?' if v is None else '={:d}'.format(v) if v > 1 else '')) for n,v in flags if v is None or v > 0))

    def __summary_uninitialized(self):
        return '(flags) {:s}'.format(','.join("{:s}?".format(name) for t,name in self._fields_))

    def __and__(self, field):
        '''Returns if the specified /field/ is set'''
        return bool(self[field] > 0)

## binary type conversion/generation
def new(pb, **attrs):
    '''Create a new instance of /pb/ applying the attributes specified by /attrs/'''
    # create a partial type
    if istype(pb):
        Log.debug("new : {:s} : Instantiating type as partial".format(pb.typename()))
        t = ptype.clone(partial, _object_=pb)
        return t(**attrs)

    # create a partial type with the specified instance
    if isinstance(pb, type):
        attrs.setdefault('value', pb)
        attrs.setdefault('offset', pb.getposition()[0])
        t = ptype.clone(partial, _object_=pb.__class__)
        return t(**attrs)

    return pb(**attrs)

def bigendian(p, **attrs):
    '''Force binary type /p/ to be ordered in the bigendian integer format'''
    attrs.setdefault('byteorder', config.byteorder.bigendian)
    attrs.setdefault('__name__', p._object_.__name__ if issubclass(p,partial) else p.__name__)

    if not issubclass(p, partial):
        Log.debug("bigendian : {:s} : Promoting type to partial".format(p.typename()))
        p = ptype.clone(partial, _object_=p, **attrs)
    else:
        p.__update__(attrs)
    return p

def littleendian(p, **attrs):
    '''Force binary type /p/ to be ordered in the littleendian integer format'''
    attrs.setdefault('byteorder', config.byteorder.littleendian)
    attrs.setdefault('__name__', p._object_.__name__ if issubclass(p,partial) else p.__name__)

    if not issubclass(p, partial):
        Log.debug("littleendian : {:s} : Promoting type to partial".format(p.typename()))
        p = ptype.clone(partial, _object_=p, **attrs)
    else:
        p.__update__(attrs)
    return p

def align(bits):
    '''Returns a type that will align fields to the specified bit size'''
    def align(self):
        b = self.bits()
        r = b % bits
        if r == 0:
            return 0
        return bits - r
    return align

if __name__ == '__main__':
    import provider
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
            import traceback
            traceback.print_exc()
            return False
        TestCaseList.append(harness)
        return fn

##########################
if __name__ == '__main__':
    import ptypes,pbinary

    TESTDATA = 'ABCDIEAHFLSDFDLKADSJFLASKDJFALKDSFJ'

    def fn(self):
        return self['size']

    class RECT(pbinary.struct):
        _fields_ = [
            (4, 'size'),
            (fn, 'value1'),
            (fn, 'value2'),
            (fn, 'value3'),
        ]

    class nibble(pbinary.struct):
        _fields_ = [
            (4, 'value')
        ]

    class byte(pbinary.struct):
        _fields_ = [
            (8, 'value')
        ]

    class word(pbinary.struct):
        _fields_ = [
            (8, 'high'),
            (8, 'low'),
        ]

    class dword(pbinary.struct):
        _fields_ = [
            (16, 'high'),
            (16, 'low')
        ]

    @TestCase
    def test_pbinary_struct_load_be_global_1():
        pbinary.setbyteorder(config.byteorder.bigendian)
        x = pbinary.new(RECT,source=provider.string('\x4a\xbc\xde\xf0'))
        x = x.l

        if (x['size'],x['value1'],x['value2'],x['value3']) == (4,0xa,0xb,0xc):
            raise Success
        raise Failure

    @TestCase
    def test_pbinary_struct_dynamic_load_2():
        ### inline bitcontainer pbinary.structures
        class blah(pbinary.struct):
            _fields_ = [
                (4, 'header'),
                (RECT, 'rectangle'),
                (lambda self: self['rectangle']['size'], 'heh')
            ]

        s = '\x44\xab\xcd\xef\x00'

        a = pbinary.new(blah,source=provider.string(s)).l

        b = a['rectangle']

        if a['header'] == 4 and (b['size'],b['value1'],b['value2'],b['value3']) == (4,0xa,0xb,0xc):
            raise Success

    @TestCase
    def test_pbinary_struct_be_3():
        #### test for integer endianness
        class blah(pbinary.struct):
            _fields_ = [
                (10, 'type'),
                (6, 'size')
            ]

        # 0000 0001 1011 1111
        data = '\x01\xbf'
        res = pbinary.new(blah,source=provider.string(data)).l

        if res['type'] == 6 and res['size'] == 0x3f:
            raise Success

    @TestCase
    def test_pbinary_struct_le_4():
        class blah(pbinary.struct):
            _fields_ = [
                (10, 'type'),
                (6, 'size')
            ]

        # 1011 1111 0000 0001
        data = '\xbf\x01'
        a = blah
        res = pbinary.littleendian(blah)
        b = res
        res = res()

        data = itertools.islice(data, res.a.size())
        res.source = provider.string(''.join(data))
        res.l

        if res['type'] == 6 and res['size'] == 0x3f:
            raise Success

    @TestCase
    def test_pbinary_struct_be_5():
        class blah(pbinary.struct):
            _fields_ = [
                (4, 'heh'),
                (4, 'blah1'),
                (4, 'blah2'),
                (4, 'blah3'),
                (4, 'blah4'),
                (8, 'blah5'),
                (4, 'blah6')
            ]

        data = '\xaa\xbb\xcc\xdd\x11\x11'

        res = pbinary.new(blah,source=provider.string(data)).l

        if res.values() == [0xa,0xa,0xb,0xb,0xc,0xcd, 0xd]:
            raise Success

    @TestCase
    def test_pbinary_struct_le_6():
        class blah(pbinary.struct):
            _fields_ = [
                (4, 'heh'),
                (4, 'blah1'),
                (4, 'blah2'),
                (4, 'blah3'),
                (4, 'blah4'),
                (8, 'blah5'),
                (4, 'blah6')
            ]
        data = '\xdd\xcc\xbb\xaa\x11\x11'
        res = blah
        res = pbinary.littleendian(res)
        res = res(source=provider.string(data))
        res = res.l

        if res.values() == [0xa, 0xa, 0xb, 0xb, 0xc, 0xcd, 0xd]:
            raise Success

    @TestCase
    def test_pbinary_struct_unaligned_7():
        x = pbinary.new(RECT,source=provider.string('hello world')).l
        if x['size'] == 6 and x.size() == (4 + 6*3 + 7)/8:
            raise Success
        return

    @TestCase
    def test_pbinary_array_int_load_8():
        class blah(pbinary.array):
            _object_ = bitmap.new(0, 3)
            length = 3

        s = '\xaa\xbb\xcc'

        x = pbinary.new(blah,source=provider.string(s)).l
        if list(x.object) == [5, 2, 5]:
            raise Success

    @TestCase
    def test_pbinary_struct_bitoffsets_9():
        # print out bit offsets for a pbinary.struct

        class halfnibble(pbinary.struct): _fields_ = [(2, 'value')]
        class tribble(pbinary.struct): _fields_ = [(3, 'value')]
        class nibble(pbinary.struct): _fields_ = [(4, 'value')]

        class byte(pbinary.array):
            _object_ = halfnibble
            length = 4

        class largearray(pbinary.array):
            _object_ = byte
            length = 16

        res = reduce(lambda x,y: x<<1 | [0,1][int(y)], ('11001100'), 0)

        x = pbinary.new(largearray,source=provider.string(chr(res)*63)).l
        if x[5].int() == res:
            raise Success

    @TestCase
    def test_pbinary_struct_load_10():
        self = pbinary.new(dword,source=provider.string('\xde\xad\xde\xaf')).l
        if self['high'] == 0xdead and self['low'] == 0xdeaf:
            raise Success

    @TestCase
    def test_pbinary_struct_recurse_11():
        ## a struct containing a struct
        class blah(pbinary.struct):
            _fields_ = [
                (word, 'higher'),
                (word, 'lower'),
            ]
        self = pbinary.new(blah,source=provider.string('\xde\xad\xde\xaf')).l
        if self['higher']['high'] == 0xde and self['higher']['low'] == 0xad and self['lower']['high'] == 0xde and self['lower']['low'] == 0xaf:
            raise Success

    @TestCase
    def test_pbinary_struct_dynamic_12():
        ## a struct containing functions
        class blah(pbinary.struct):
            _fields_ = [
                (lambda s: word, 'higher'),
                (lambda s: 8, 'lower')
            ]

        self = pbinary.new(blah,source=provider.string('\xde\xad\x80')).l
        if self['higher']['high'] == 0xde and self['higher']['low'] == 0xad and self['lower'] == 0x80:
            raise Success

    @TestCase
    def test_pbinary_array_int_load_13():
        ## an array containing a bit size
        class blah(pbinary.array):
            _object_ = 4
            length = 8

        data = '\xab\xcd\xef\x12'
        self = pbinary.new(blah,source=provider.string(data)).l

        if list(self.object) == [0xa,0xb,0xc,0xd,0xe,0xf,0x1,0x2]:
            raise Success

    @TestCase
    def test_pbinary_array_struct_load_14():
        ## an array containing a pbinary
        class blah(pbinary.array):
            _object_ = byte
            length = 4

        data = '\xab\xcd\xef\x12'
        self = pbinary.new(blah,source=provider.string(data)).l

        l = [ x['value'] for x in self.value[0] ]
        if [0xab,0xcd,0xef,0x12] == l:
            raise Success

    @TestCase
    def test_pbinary_array_dynamic_15():
        class blah(pbinary.array):
            _object_ = lambda s: byte
            length = 4

        data = '\xab\xcd\xef\x12'
        self = pbinary.new(blah,source=provider.string(data)).l

        l = [ x['value'] for x in self.value[0] ]
        if [0xab,0xcd,0xef,0x12] == l:
            raise Success

    @TestCase
    def test_pbinary_struct_struct_load_16():
        class blah(pbinary.struct):
            _fields_ = [
                (byte, 'first'),
                (byte, 'second'),
                (byte, 'third'),
                (byte, 'fourth'),
            ]

        self = pbinary.new(blah)

        import provider
        self.source = provider.string(TESTDATA)
        self.load()

        l = [ v['value'] for v in self.values() ]

        if l == [ ord(TESTDATA[i]) for i,x in enumerate(l) ]:
            raise Success

    @TestCase
    def test_pbinary_struct_struct_load_17():
        class blah(pbinary.struct):
            _fields_ = [
                (4, 'heh'),
                (dword, 'dw'),
                (4, 'hehhh')
            ]

        import provider
        self = pbinary.new(blah)
        self.source = provider.string(TESTDATA)
        self.load()
        if self['heh'] == 4 and self['dw']['high'] == 0x1424 and self['dw']['low'] == 0x3444 and self['hehhh'] == 9:
            raise Success

    @TestCase
    def test_pbinary_struct_dynamic_load_18():
        class RECT(pbinary.struct):
            _fields_ = [
                (5, 'Nbits'),
                (lambda self: self['Nbits'], 'Xmin'),
                (lambda self: self['Nbits'], 'Xmax'),
                (lambda self: self['Nbits'], 'Ymin'),
                (lambda self: self['Nbits'], 'Ymax')
            ]

        n = int('1110001110001110', 2)
        b = bitmap.new(n,16)

        a = bitmap.new(0,0)
        a = bitmap.push(a, (4, 5))
        a = bitmap.push(a, (0xd, 4))
        a = bitmap.push(a, (0xe, 4))
        a = bitmap.push(a, (0xa, 4))
        a = bitmap.push(a, (0xd, 4))

        s = bitmap.data(a)

        i = iter(s)
        z = pbinary.new(RECT,source=provider.string(s)).l

        if z['Nbits'] == 4 and z['Xmin'] == 0xd and z['Xmax'] == 0xe and z['Ymin'] == 0xa and z['Ymax'] == 0xd:
            raise Success

    @TestCase
    def test_pbinary_terminatedarray_19():
        class myarray(pbinary.terminatedarray):
            _object_ = 4

            def isTerminator(self, v):
                if v.int() == 0:
                    return True
                return False

        z = pbinary.new(myarray,source=provider.string('\x44\x43\x42\x41\x3f\x0f\xee\xde')).l
        if z.serialize() == 'DCBA?\x00':
            raise Success

    @TestCase
    def test_pbinary_struct_aggregatenum_20():
        class mystruct(pbinary.struct):
            _fields_ = [
                (4, 'high'),
                (4, 'low'),
                (4, 'lower'),
                (4, 'hell'),
            ]

        z = pbinary.new(mystruct,source=provider.string('\x41\x40')).l
        if z.int() == 0x4140:
            raise Success

    @TestCase
    def test_pbinary_partial_hierarchy_21():
        class mychild1(pbinary.struct):
            _fields_ = [(4, 'len')]
        class mychild2(pbinary.struct):
            _fields_ = [(4, 'len')]

        class myparent(pbinary.struct):
            _fields_ = [(mychild1, 'a'), (mychild2, 'b')]

        from ptypes import provider
        z = pbinary.new(myparent)
        z.source = provider.string('A'*5000)
        z.l

        a,b = z['a'],z['b']
        if (a.parent is b.parent) and (a.parent is z.object):
            raise Success
        raise Failure

    @TestCase
    def test_pstruct_partial_load_22():
        import pstruct,pint

        correct='\x44\x11\x08\x00\x00\x00'
        class RECORDHEADER(pbinary.struct):
            _fields_ = [ (10, 't'), (6, 'l') ]

        class broken(pstruct.type):
            _fields_ = [(pbinary.littleendian(RECORDHEADER), 'h'), (pint.uint32_t, 'v')]

        z = broken(source=provider.string(correct))
        z = z.l
        a = z['h']

        if a['t'] == 69 and a['l'] == 4:
            raise Success
        raise Failure

    @TestCase
    def test_pstruct_partial_le_set_23():
        import pstruct,pint

        correct='\x44\x11\x08\x00\x00\x00'
        class RECORDHEADER(pbinary.struct):
            _fields_ = [ (10, 't'), (6, 'l') ]

        class broken(pstruct.type):
            _fields_ = [(pbinary.littleendian(RECORDHEADER), 'h'), (pint.littleendian(pint.uint32_t), 'v')]

        z = broken().alloc()
        z['v'].set(8)

        z['h']['l'] = 4
        z['h']['t'] = 0x45

        if z.serialize() == correct:
            raise Success
        raise Failure

    @TestCase
    def test_pbinary_struct_partial_load_24():
        correct = '\x0f\x00'
        class header(pbinary.struct):
            _fields_ = [
                (12, 'instance'),
                (4, 'version'),
            ]

        z = pbinary.littleendian(header)(source=provider.string(correct)).l

        if z.serialize() != correct:
            raise Failure
        if z['version'] == 15 and z['instance'] == 0:
            raise Success
        raise Failure

    @TestCase
    def test_pbinary_align_load_25():
        class blah(pbinary.struct):
            _fields_ = [
                (4, 'a'),
                (pbinary.align(8), 'b'),
                (4, 'c')
            ]

        x = pbinary.new(blah,source=provider.string('\xde\xad')).l
        if x['a'] == 13 and x['b'] == 14 and x['c'] == 10:
            raise Success
        raise Failure

    import struct
    class blah(pbinary.struct):
        _fields_ = [
            (-16, 'a'),
        ]

    @TestCase
    def test_pbinary_struct_signed_load_26():
        s = '\xff\xff'
        a = pbinary.new(blah,source=provider.string(s)).l
        b, = struct.unpack('>h',s)
        if a['a'] == b:
            raise Success

    @TestCase
    def test_pbinary_struct_signed_load_27():
        s = '\x80\x00'
        a = pbinary.new(blah,source=provider.string(s)).l
        b, = struct.unpack('>h',s)
        if a['a'] == b:
            raise Success

    @TestCase
    def test_pbinary_struct_signed_load_28():
        s = '\x7f\xff'
        a = pbinary.new(blah,source=provider.string(s)).l
        b, = struct.unpack('>h',s)
        if a['a'] == b:
            raise Success

    @TestCase
    def test_pbinary_struct_signed_load_29():
        s = '\x00\x00'
        a = pbinary.new(blah,source=provider.string(s)).l
        b, = struct.unpack('>h',s)
        if a['a'] == b:
            raise Success

    @TestCase
    def test_pbinary_struct_load_le_conf_30():
        class blah2(pbinary.struct):
            _fields_ = [
                (4, 'a0'),
                (1, 'a1'),
                (1, 'a2'),
                (1, 'a3'),
                (1, 'a4'),
                (8, 'b'),
                (8, 'c'),
                (8, 'd'),
            ]

        s = '\x00\x00\x00\x04'
        a = pbinary.littleendian(blah2)(source=provider.string(s)).l
        if a['a2'] == 1:
            raise Success

    @TestCase
    def test_pbinary_struct_load_31():
        s = '\x04\x00'
        class fuq(pbinary.struct):
            _fields_ = [
                (4, 'zero'),
                (1, 'a'),
                (1, 'b'),
                (1, 'c'),
                (1, 'd'),
                (8, 'padding'),
            ]

        a = pbinary.new(fuq,source=provider.string(s)).l
        if a['b'] == 1:
            raise Success

    @TestCase
    def test_pbinary_struct_load_global_le_32():
        s = '\x00\x04'
        pbinary.setbyteorder(config.byteorder.littleendian)
        class fuq(pbinary.struct):
            _fields_ = [
                (4, 'zero'),
                (1, 'a'),
                (1, 'b'),
                (1, 'c'),
                (1, 'd'),
                (8, 'padding'),
            ]

        a = pbinary.new(fuq,source=provider.string(s)).l
        if a['b'] == 1:
            raise Success

    @TestCase
    def test_pbinary_array_load_iter_33():
        class test(pbinary.array):
            _object_ = 1
            length = 16

        src = provider.string('\xaa'*2)
        x = pbinary.new(test,source=src).l
        if tuple(x.object) == (1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0):
            raise Success

    @TestCase
    def test_pbinary_array_set_34():
        class test(pbinary.array):
            _object_ = 1
            length = 16

        a = '\xaa'*2
        b = pbinary.new(test).a

        for i,x in enumerate((1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0)):
            b[i] = x

        if b.serialize() == a:
            raise Success

    @TestCase
    def test_pbinary_struct_load_be_conv_35():
        class test(pbinary.struct):
            _fields_ = [(8,'i'),(8,'v')]

        test = pbinary.bigendian(test)
        a = '\x00\x0f'
        b = test(source=provider.string(a)).l
        if b.serialize() == a:
            raise Success

    @TestCase
    def test_pbinary_terminatedarray_multiple_load_36():
        pbinary.setbyteorder(config.byteorder.bigendian)

        # terminated-array
        class part(pbinary.struct):
            _fields_ = [(4,'a'),(4,'b')]

        class encompassing(pbinary.terminatedarray):
            _object_ = part
            def isTerminator(self, value):
                return value['a'] == value['b'] and value['a'] == 0xf

        class complete(pbinary.terminatedarray):
            _object_ = encompassing
            def isTerminator(self, value):
                v = value[0]
                return v['a'] == v['b'] and v['a'] == 0x0

        string = 'ABCD\xffEFGH\xffIJKL\xffMNOP\xffQRST\xffUVWX\xffYZ..\xff\x00!!!!!!!!\xffuhhh'
        a = pbinary.new(complete,source=ptypes.prov.string(string))
        a = a.l
        if len(a) == 8 and a.object[-1][0].bitmap() == (0,8):
            raise Success

    @TestCase
    def test_pbinary_array_load_global_be_37():
        pbinary.setbyteorder(config.byteorder.bigendian)

        string = "ABCDEFGHIJKL"
        src = provider.string(string)
        class st(pbinary.struct):
            _fields_ = [(4,'nib1'),(4,'nib2'),(4,'nib3')]

        class argh(pbinary.array):
            length = 8
            _object_ = st

        a = pbinary.new(argh,source=src)
        a = a.l
        if len(a.object) == 8 and a[-1].bitmap() == (0xb4c,12):
            raise Success

    @TestCase
    def test_pbinary_array_load_global_be_38():
        pbinary.setbyteorder(config.byteorder.littleendian)

        string = "ABCDEFGHIJKL"
        src = provider.string(string)
        class st(pbinary.struct):
            _fields_ = [(4,'nib1'),(4,'nib2'),(4,'nib3')]

        class argh(pbinary.array):
            length = 8
            _object_ = st

        a = pbinary.new(argh,source=src)
        a = a.l
        if len(a.object) == 8 and a.object[-1].bitmap() == (0x241,12):
            raise Success

    @TestCase
    def test_pbinary_blockarray_load_global_be_39():
        pbinary.setbyteorder(config.byteorder.bigendian)

        class st(pbinary.struct):
            _fields_ = [
                (word, 'mz'),
                (word, 'l'),
                (dword, 'ptr'),
            ]

        class argh(pbinary.blockarray):
            _object_ = st
            def blockbits(self):
                return 32*8

        data = ''.join(map(chr, (x for x in range(48,48+75))))
        src = provider.string(data)
        a = pbinary.new(argh, source=src)
        a = a.l
        if len(a) == 32/8 and a.size() == 32 and a.serialize() == data[:a.size()]:
            raise Success

    @TestCase
    def test_pbinary_array_blockarray_load_global_be_40():
        pbinary.setbyteorder(config.byteorder.bigendian)

        class argh(pbinary.blockarray):
            _object_ = 32

            def blockbits(self):
                return 32*4

        class ack(pbinary.array):
            _object_ = argh
            length = 4

        data = ''.join((''.join(chr(x)*4 for x in range(48,48+75)) for _ in range(500)))
        src = provider.string(data)
        a = pbinary.new(ack, source=src)
        a = a.l
        if a[0].bits() == 128 and len(a[0]) == 4 and a.blockbits() == 4*32*4 and a[0][-1] == 0x33333333:
            raise Success

    @TestCase
    def test_pbinary_struct_load_signed_global_be_41():
        pbinary.setbyteorder(config.byteorder.bigendian)

        class argh(pbinary.struct):
            _fields_ = [
                (-8, 'a'),
                (+8, 'b'),
                (-8, 'c'),
                (-8, 'd'),
            ]

        data = '\xff\xff\x7f\x80'
        a = pbinary.new(argh, source=provider.string(data))
        a = a.l
        if a.values() == [-1,255,127,-128]:
            raise Success

    @TestCase
    def test_pbinary_array_load_global_be_42():
        pbinary.setbyteorder(config.byteorder.bigendian)

        class argh(pbinary.array):
            _object_ = -8
            length = 4

        data = '\xff\x01\x7f\x80'
        a = pbinary.new(argh, source=provider.string(data))
        a = a.l
        if list(a.object) == [-1,1,127,-128]:
            raise Success

    @TestCase
    def test_pbinary_struct_samesize_casting_43():
        from ptypes import pbinary,prov
        class p1(pbinary.struct):
            _fields_ = [(2,'a'),(2,'b'),(4,'c')]
        class p2(pbinary.struct):
            _fields_ = [(4,'a'),(2,'b'),(2,'c')]

        data = '\x5f'
        a = pbinary.new(p1, source=prov.string(data))
        a = a.l
        b = a.cast(p2)
        c = a.object
        d = a.object.cast(p2)
        if b['a'] == d['a'] and b['b'] == d['b'] and b['c'] == d['c']:
            raise Success

    @TestCase
    def test_pbinary_struct_casting_incomplete_44():
        from ptypes import pbinary,prov
        class p1(pbinary.struct):
            _fields_ = [(2,'a'),(2,'b')]
        class p2(pbinary.struct):
            _fields_ = [(4,'a'),(2,'b')]
        data = '\x5f'
        a = pbinary.new(p1, source=prov.string(data))
        a = a.l
        b = a.object.cast(p2)
        x,_ = a.bitmap()
        if b['a'] == x:
            raise Success

    @TestCase
    def test_pbinary_flags_load_45():
        from ptypes import pbinary,prov
        class p(pbinary.flags):
            _fields_ = [
                (1,'set0'),
                (1,'notset1'),
                (1,'set1'),
                (1,'notset2'),
                (1,'set2'),
            ]

        data = '\xa8'
        a = pbinary.new(pbinary.bigendian(p, source=prov.string(data)))
        a = a.l
        if 'notset' not in a.summary() and all(('set%d'%x) in a.summary() for x in range(3)):
            raise Success

    @TestCase
    def test_pbinary_partial_terminatedarray_dynamic_load_46():
        class vle(pbinary.terminatedarray):
            class _continue_(pbinary.struct):
                _fields_ = [(1, 'continue'), (7, 'value')]
            class _sentinel_(pbinary.struct):
                _fields_ = [(0, 'continue'), (8, 'value')]

            def _object_(self):
                if len(self.value) < 4:
                    return self._continue_
                return self._sentinel_

            length = 5
            def isTerminator(self, value):
                if value['continue'] == 0:
                    return True
                return False

        source = '\x80\x80\x80\x80\xff'
        a = pbinary.new(vle, source=ptypes.provider.string(source))
        a = a.load()

        if a.serialize() == '\x80\x80\x80\x80\xff':
            raise Success
        for x in a:
            print x
        print repr(a.serialize())

    @TestCase
    def test_pbinary_pstruct_set_num_47():
        class structure(pbinary.struct):
            _fields_ = [
                (4, 'a'),(4,'b')
            ]
        x = structure()
        res = x.set(a=4,b=8)
        if res.int() == 0x48:
            raise Success

    def test_pbinary_parray_set_tuple_48():
        class array(pbinary.array):
            _object_ = 16
            length = 0
        x = array(length=4).set((0,0xabcd),(3,0xdcba))
        if x[0].int() == 0xabcd and x[-1].int()==0xdcba:
            raise Success

    def test_pbinary_parray_set_iterable_49():
        class array(pbinary.array):
            _object_ = 16
            length = 0
        x = array(length=4).set(0xabcd,0xdcba)
        if x[0].int() == 0xabcd and x[1].int()==0xdcba:
            raise Success

    @TestCase
    def test_pbinary_pstruct_set_container_50():
        class array(pbinary.array):
            _object_ = 16
            length = 0
        class structure(pbinary.struct):
            _fields_ = [
                (array, 'a'),(4,'b')
            ]

        x = array(length=2).set([0xdead,0xdead])
        res = structure().set(a=x, b=3)
        if res['a'].int() == 0xdeaddead:
            raise Success

    @TestCase
    def test_pbinary_parray_set_container_51():
        class array(pbinary.array):
            _object_ = 16
            length = 0
        class structure(pbinary.struct):
            _fields_ = [
                (8, 'a'),(8,'b')
            ]

        x = array(length=2).set((1,structure().set(a=0x41,b=0x42)))
        if x[1].int() == 0x4142:
            raise Success

    @TestCase
    def test_pbinary_parray_getslice_atomic_52():
        class array(pbinary.array):
            _object_ = 8
        data = 'hola mundo'
        x = array(length=len(data)).set(map(ord,data))
        if all(a == ord(b) for a,b in zip(x[2:8],data[2:8])):
            raise Success

    @TestCase
    def test_pbinary_parray_getslice_array_53():
        from ptypes import bitmap
        class array(pbinary.array):
            class _object_(pbinary.array):
                length = 2
                _object_ = 4
        data = 0x1122334455abcdef
        result = map(bitmap.value, bitmap.split(bitmap.new(data,64), 4))
        result = zip(*((iter(result),)*2))
        x = array().set(result)
        if all(a[0] == b[0] and a[1] == b[1] for a,b in zip(x[2:8],result[2:8])):
            raise Success

    @TestCase
    def test_pbinary_parray_getslice_struct_54():
        from ptypes import bitmap
        class array(pbinary.array):
            class _object_(pbinary.struct):
                _fields_ = [(4,'a'),(4,'b')]
            length = 4

        data = 0x1122334455abcdef
        result = map(bitmap.value, bitmap.split(bitmap.new(data,64), 4))
        result = zip(*((iter(result),)*2))
        x = array().set(result)
        if all(a['a'] == b[0] and a['b'] == b[1] for a,b in zip(x[2:8],result[2:8])):
            raise Success

    @TestCase
    def test_pbinary_parray_setslice_atomic_55():
        class array(pbinary.array):
            _object_ = length = 8
        x = array().a
        x[2:6] = map(ord,'hola')
        if ''.join(map(chr,x)) == '\x00\x00hola\x00\x00':
            raise Success

    @TestCase
    def test_pbinary_parray_setslice_array_56():
        class array(pbinary.array):
            class _object_(pbinary.array):
                _object_ = 8
                length = 4
            length = 4
        x = array().a
        v1 = array._object_().set((0x41,0x41,0x41,0x41))
        v2 = array._object_().set((0x42,0x42,0x42,0x42))
        x[1:3] = [v1,v2]
        if x[0].bitmap() == (0,32) and x[1].bitmap() == (0x41414141,32) and x[2].bitmap() == (0x42424242,32) and x[3].bitmap() == (0,32):
            raise Success

    @TestCase
    def test_pbinary_parray_setslice_struct_57():
        class array(pbinary.array):
            class _object_(pbinary.struct):
                _fields_ = [(8,'a'),(8,'b')]
        x = array(length=4).a
        value = array._object_().set(a=0x41, b=0x42)
        x[1:3] = value
        if x[0].bitmap() == (0,16) and x[1].bitmap() == (0x4142,16) and x[2].bitmap() == (0x4142,16) and x[3].bitmap() == (0,16):
            raise Success

if __name__ == '__main__':
    results = []
    for t in TestCaseList:
        results.append( t() )

