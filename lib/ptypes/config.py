import os,sys,math,six
__all__ = 'defaults,byteorder'.split(',')
class field:
    class descriptor(object):
        def __init__(self):
            self.__value__ = {}
        def __set__(self, instance, value):
            self.__value__[instance] = value
        def __get__(self, instance, type=None):
            return self.__value__.get(instance)
        def __delete__(self, instance):
            raise AttributeError

    class __enum_descriptor(descriptor):
        __option = set
        def option(self, name, doc=''):
            cls = type(self)
            res = type(name, cls, {'__doc__':doc})
            self.__option__.add(res)
            return res
        def __set__(self, instance, value):
            if value in self.__option__:
                return field.descriptor.__set__(self, instance, value)
            raise ValueError('{!r} is not a member of {!r}'.format(value, self.__option__))

    class __type_descriptor(descriptor):
        __type__ = type
        def __set__(self, instance, value):
            if (hasattr(self.__type__, '__iter__') and type(value) in self.__type__) or isinstance(value, self.__type__):
                return field.descriptor.__set__(self, instance, value)
            raise ValueError('{!r} is not an instance of {!r}'.format(value, self.__type__))

    class __set_descriptor(descriptor):
        set,get = None,None
        def __init__(self): pass
        def __set__(self, instance, value):
            return self.__getattribute__('set').im_func(value)
        def __get__(self, instance, type=None):
            return self.__getattribute__('get').im_func()

    class __bool_descriptor(descriptor):
        def __set__(self, instance, value):
            if not isinstance(value, bool):
                logging.warn("rvalue {!r} is not of boolean type. Coercing it into one : ({:s} != {:s})".format(value, type(value).__name__, bool.__name__))
            return field.descriptor.__set__(self, instance, bool(value))

    @classmethod
    def enum(cls, name, options=(), doc=''):
        base = cls.__enum_descriptor
        attrs = dict(base.__dict__)
        attrs['__option__'] = set(options)
        attrs['__doc__'] = doc
        return type(name, (base,), attrs)()
    @classmethod
    def option(cls, name, doc='', base=object):
        return type(name, (base,), {'__doc__':doc})
    @classmethod
    def type(cls, name, subtype, doc=''):
        base = cls.__type_descriptor
        attrs = dict(base.__dict__)
        attrs['__type__'] = subtype
        attrs['__doc__'] = doc
        return type(name, (base,), attrs)()
    @classmethod
    def set(cls, name, fetch, store, doc=''):
        base = cls.__set_descriptor
        attrs = dict(base.__dict__)
        attrs['__doc__'] = doc
        attrs['set'] = store
        attrs['get'] = fetch
        return type(name, (base,), attrs)()
    @classmethod
    def constant(cls, name, value, doc=''):
        base = cls.descriptor
        attrs = dict(base.__dict__)
        def raiseAttributeError(self, instance, value):
            raise AttributeError
        attrs['__set__'] = raiseAttributeError
        attrs['__doc__'] = doc
        return type(name, (base,), attrs)()
    @classmethod
    def bool(cls, name, doc=''):
        base = cls.__bool_descriptor
        attrs = dict(base.__dict__)
        attrs['__doc__'] = doc
        return type(name, (base,), attrs)()

def namespace(cls):
    # turn all instances of things into read-only attributes
    attrs,properties,subclass = {},{},{}
    for k,v in cls.__dict__.items():
        if hasattr(v, '__name__'):
            v.__name__ = '{}.{}'.format(cls.__name__,k)
        if k.startswith('_') or type(v) is property:
            attrs[k] = v
        elif not callable(v) or isinstance(v,type):
            properties[k] = v
        elif not hasattr(v, '__class__'):
            subclass[k] = namespace(v)
        else:
            attrs[k] = v
        continue

    def getprops(obj):
        result = []
        col1,col2 = 0,0
        for k,v in obj.items():
            col1 = max((col1,len(k)))
            if isinstance(v, type):
                val = '<>'
            elif hasattr(v, '__class__'):
                val = repr(v)
            else:
                raise ValueError(k)
            doc = v.__doc__.split('\n')[0] if v.__doc__ else None
            col2 = max((col2,len(val)))
            result.append((k, val, doc))
        return [('{name:{}} : {val:{}} # {doc}' if d else '{name:{}} : {val:{}}').format(col1,col2,name=k,val=v,doc=d) for k,v,d in result]

    def __repr__(self):
        props = getprops(properties)
        descr = ('{{{!s}}} # {}\n' if cls.__doc__ else '{{{!s}}}\n')
        subs = ['{{{}.{}}}\n...'.format(cls.__name__,k) for k in subclass.keys()]
        res = descr.format(cls.__name__,cls.__doc__) + '\n'.join(props)
        if subs:
            return res + '\n' + '\n'.join(subs) + '\n'
        return res + '\n'

    def __setattr__(self, name, value):
        if name in attrs.viewkeys():
            object.__setattr__(self, name, value)
            return
        raise AttributeError('Configuration \'{:s}\' does not have field named \'{:s}\''.format(cls.__name__,name))

    attrs['__repr__'] = __repr__
    attrs['__setattr__'] = __setattr__
    attrs.update((k,property(fget=lambda s,k=k:properties[k])) for k in properties.viewkeys())
    attrs.update((k,property(fget=lambda s,k=k:subclass[k])) for k in subclass.viewkeys())
    result = type(cls.__name__, cls.__bases__, attrs)
    return result()

def configuration(cls):
    attrs,properties,subclass = dict(cls.__dict__),{},{}
    for k,v in attrs.items():
        if isinstance(v, field.descriptor):
            properties[k] = v
        elif not hasattr(v, '__class__'):
            subclass[k] = configuration(v)
        continue

    def getprops(obj,val):
        result = []
        col1,col2 = 0,0
        for k,v in obj.items():
            col1 = max((col1,len(k)))
            doc = v.__doc__.split('\n')[0] if v.__doc__ else None
            col2 = max((col2,len(repr(val[k]))))
            result.append((k, val[k], doc))
        return [(('{name:%d} = {val:<%d} # {doc}' if d else '{name:%d} = {val:<%d}')%(col1,col2)).format(name=k,val=v,doc=d) for k,v,d in result]

    def __repr__(self):
        descr = ('[{!s}] # {}\n' if cls.__doc__ else '[{!s}]\n')
        values = dict((k,getattr(self,k,None)) for k in properties.viewkeys())
        res = descr.format(cls.__name__,cls.__doc__.split('\n')[0] if cls.__doc__ else None) + '\n'.join(getprops(properties,values))
        subs = ['[{}.{}]\n...'.format(cls.__name__,k) for k in subclass.keys()]
        if subs:
            return res + '\n' + '\n'.join(subs) + '\n'
        return res + '\n'

    def __setattr__(self, name, value):
        if name in attrs.viewkeys():
            object.__setattr__(self, name, value)
            return
        raise AttributeError('Namespace \'{:s}\' does not have a field named \'{:s}\''.format(cls.__name__,name))

    attrs['__repr__'] = __repr__
    attrs['__setattr__'] = __setattr__
    attrs.update((k,property(fget=lambda s,k=k:subclass[k])) for k in subclass.viewkeys())
    result = type(cls.__name__, cls.__bases__, attrs)
    return result()

### constants that can be used as options
@namespace
class byteorder:
    '''Byte order constants'''
    bigendian = field.option('bigendian', 'Specify big-endian ordering')
    littleendian = field.option('littleendian', 'Specify little-endian ordering')

@namespace
class partial:
    fractional = field.option('fractional', 'Display the offset as a fraction of the full bit (0.0, 0.125, 0.25, ..., 0.875)')
    hex = field.option('hexadecimal', 'Display the partial-offset in hexadecimal (0.0, 0.2, 0.4, ..., 0.c, 0.e)')
    bit = field.option('bit', 'Display just the bit number (0.0, 0.1, 0.2, ..., 0.7)')

### new-config
import logging
@configuration
class defaults:
    log = field.type('default-logger', logging.Filterer, 'Default place to log progress')

    class integer:
        size = field.type('integersize', six.integer_types, 'The word-size of the architecture')
        order = field.enum('byteorder', (byteorder.bigendian,byteorder.littleendian), 'The endianness of integers/pointers')

    class ptype:
        clone_name = field.type('clone_name', basestring, 'This will only affect newly cloned types')
        noncontiguous = field.bool('noncontiguous', 'Disable optimization for loading ptype.container elements contiguously. Enabling this allows there to be \'holes\' within a list of elements in a container and disables an important optimization.')

    class pint:
        bigendian_name = field.type('bigendian_name', basestring, 'Modifies the name of any integers that are big-endian')
        littleendian_name = field.type('littleendian_name', basestring, 'Modifies the name of any integers that are little-endian')

    class parray:
        break_on_zero_sized_element = field.bool('break_on_zero_sized_element', 'Terminate an array if the size of one of it\'s elements is invalid instead of possibly looping indefinitely.')
        break_on_max_count = field.bool('break_on_max_count', 'If a dynamically created array is larger than max_count, then fail it\'s creation. If not, then issue a warning.')
        max_count = field.type('max_count', six.integer_types, 'If max_count is larger than 0, then notify via a warning or an exception based on the value of \'break_on_max_count\'')

    class pstruct:
        use_offset_on_duplicate = field.bool('use_offset_on_duplicate', 'If more than one field has the same name, then suffix the field by it\'s offset. Otherwise use the field\'s index.')

    class display:
        show_module_name = field.bool('show_module_name', 'include the full module name in the summary')
        show_parent_name = field.bool('show_parent_name', 'include the parent name in the summary')
        mangle_with_attributes = field.bool('mangle_with_attributes', 'when doing name-mangling, include all atomic attributes of a ptype as a formatstring keyword')

        class hexdump:
            '''Formatting for a hexdump'''
            width = field.type('width', six.integer_types)
            threshold = field.type('threshold', six.integer_types)

        class threshold:
            '''Width and Row thresholds for displaying summaries'''
            summary = field.type('summary_threshold', six.integer_types)
            summary_message = field.type('summary_threshold_message', basestring)
            details = field.type('details_threshold', six.integer_types)
            details_message = field.type('details_threshold_message', basestring)

    class pbinary:
        '''How to display attributes of an element containing binary fields which might not be byte-aligned'''
        offset = field.enum('offset', (partial.bit,partial.fractional,partial.hex), 'which format to display the sub-offset for binary types')

        bigendian_name = field.type('bigendian_name', basestring, 'format specifier defining an element that is read most-significant to least-significant')
        littleendian_name = field.type('littleendian_name', basestring, 'format specifier defining an element that is read least-significant to most-significant')

    def __getsource():
        global ptype
        return ptype.source
    def __setsource(value):
        global ptype
        if all(hasattr(value, method) for method in ('seek','store','consume')) or isinstance(value, provider.base):
            ptype.source = value
            return
        raise ValueError("Invalid source object")
    source = field.set('default-source', __getsource, __setsource, 'Default source to load/commit data from/to')

import ptype # recursive

### defaults
# logging
defaults.log = log = logging.getLogger('ptypes')
log.setLevel(logging.root.level)
log.propagate = 1
res = logging.StreamHandler(None)
res.setFormatter(logging.Formatter("[%(created).3f] <%(process)x.%(thread)x> [%(levelname)s:%(name)s] %(message)s", None))
log.addHandler(res)
del(res,log)

# general integers
defaults.integer.size = long(math.log((sys.maxsize+1)*2,2)/8)
defaults.integer.order = byteorder.littleendian if sys.byteorder == 'little' else byteorder.bigendian if sys.byteorder == 'big' else None

# display
defaults.display.show_module_name = False
defaults.display.show_parent_name = False
defaults.display.hexdump.width = 16
defaults.display.hexdump.threshold = 8
defaults.display.threshold.summary = 80
defaults.display.threshold.details = 8
defaults.display.threshold.summary_message = ' ..skipped ~{leftover} bytes.. '
defaults.display.threshold.details_message = ' ..skipped {leftover} rows, {skipped} bytes.. '
defaults.display.mangle_with_attributes = False

# array types
defaults.parray.break_on_zero_sized_element = True
defaults.parray.break_on_max_count = False
defaults.parray.max_count = sys.maxint

# structures
defaults.pstruct.use_offset_on_duplicate = True

# root types
defaults.ptype.noncontiguous = False
#defaults.ptype.clone_name = 'clone({})'
#defaults.pint.bigendian_name = 'bigendian({})'
#defaults.pint.littleendian_name = 'littleendian({})'
defaults.ptype.clone_name = 'c({})'

# integer types
defaults.pint.bigendian_name = 'be({})' if sys.byteorder.startswith('little') else '{}'
defaults.pint.littleendian_name = 'le({})' if sys.byteorder.startswith('big') else '{}'

# pbinary types
defaults.pbinary.offset = partial.hex
defaults.pbinary.bigendian_name = 'pb({})'
defaults.pbinary.littleendian_name = 'pble({})'

if __name__ == '__main__':
    @namespace
    class consts:
        bigendian = field.option('bigendian', 'Big-endian integers')
        littleendian = field.option('littleendian', 'Little-endian integers')
        size = 20
        whatever = object()
        class huh:
            what = 5
            default = 10
            blah = object()
            class more:
                whee = object()

        class blah:
            pass

    import logging
    @configuration
    class config(object):
        byteorder = field.enum('byteorder', (byteorder.bigendian,byteorder.littleendian), 'The endianness of integers/pointers')
        integersize = field.type('integersize', six.integer_types, 'The word-size of the architecture')

        class display:
            summary = field.type('single-line', six.integer_types)
            details = field.type('multi-line', six.integer_types)
            show_module = field.bool('show-module-name')

        def __getlogger():
            return logging.root
        def __setlogger(value):
            logging.root = value
        logger = field.set('default-logger', __getlogger, __setlogger, 'Default place to log progress')
        #logger = field.type('default-logger', logging.Filterer, 'Default place to log progress')

        def __getsource():
            return ptype.source
        def __setsource(value):
            if not isinstance(value, provider.base):
                raise ValueError("Invalid source object")
            ptype.source = value
        source = field.set('default-source', __getsource, __setsource, 'Default source to load/commit data from/to')

    #ptypes.config.logger = logging.root
    print repr(consts)
    print repr(config)
