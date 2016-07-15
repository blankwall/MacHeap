"""Primitive string types.

A pstr.type is an atomic type that is used to describe string types within a
data structure. They are treated internally as atomic types, but expose an
interface that allows one to modify each of it's particular characters.

The base type is named pstr.string and is sized according to the `.length`
property. An implied char_t type is assigned to the `._object_` property and is
used to determine what the size of each glyph in the string is. The dynamically
sized string types have no length due to them being terminated according to a
specific character terminator. Generally, string types have the following
interface:

    class interface(pstr.string):
        length = length-of-string
        def set(self, string):
            '''Set the string to the value of ``string``.'''
        def get(self):
            '''Return the value of ``self``'''
        def str(self):
            '''Return the string as a python str type.'''
        def insert(self, index, character):
            '''Insert the specified ``character`` at ``index`` of the pstr.string.'''
        def append(self, character):
            '''Append the ``character`` to the pstr.string'''
        def extend(self, iterable):
            '''Append each character in ``iterable`` to the pstr.string'''
        def __getitem__(self, index):
            '''Return the glyph at the specified ``index``'''
        def __getslice__(self, slice):
            '''Return the glyphs at the specified ``slice``'''
        def __len__(self):
            '''Return the number of characters within the string.'''

There are a few types that this module provides:

char_t -- a single character
wchar_t -- a single wide-character
string -- an ascii string of /self.length/ characters in length
wstring -- a wide-character string of /self.length/ characters in length
szstring -- a zero-terminated ascii string
szwstring -- a zero-terminated wide-character string
unicode -- an alias to wstring
szunicode -- an alias to szwstring

Example usage:
    # define a type
    from ptypes import pstr
    class type(pstr.string):
        length = 0x20

    # instantiate and load a type
    instance = type()
    instance.load()

    # fetch a specific character
    print instance[1]

    # re-assign a new string
    instance.set("new string contents")

    # return the length of the type
    print len(instance)

    # return the type in ascii
    value = instance.str()
"""

import __builtin__,sys,itertools,codecs
from . import ptype,parray,pint,dynamic,utils,error,pstruct,provider,config
Config = config.defaults
Log = Config.log.getChild(__name__[len(__package__)+1:])

class _char_t(pint.integer_t):
    encoding = codecs.lookup('ascii')

    def __init__(self, **attrs):
        super(_char_t,self).__init__(**attrs)

        # calculate the size of .length based on .encoding
        res = __builtin__.unicode('\x00', 'ascii').encode(self.encoding.name)
        self.length = len(res)

    def __setvalue__(self, value):
        '''Set the _char_t to the str ``value``.'''
        if isinstance(value, __builtin__.str):
            try: value = __builtin__.unicode(value, 'ascii')
            except UnicodeDecodeError: return super(pint.integer_t,self).__setvalue__(str(value))
        elif isinstance(value, __builtin__.unicode):
            value = value
        else:
            raise ValueError(self, '_char_t.set', 'User tried to set a value of an incorrect type : {:s}'.format(value.__class__))
        res = value.encode(self.encoding.name)
        return super(pint.integer_t,self).__setvalue__(res)

    def str(self):
        '''Try to decode the _char_t to a character.'''
        data = self.serialize()
        try:
            res = data.decode(self.encoding.name)
        except UnicodeDecodeError, e:
            raise UnicodeDecodeError(e.encoding, e.object, e.start, e.end, 'Unable to decode string {!r} to requested encoding : {:s}'.format(data, self.encoding.name))
        return res

    def __getvalue__(self):
        '''Decode the _char_t to a character replacing any invalid characters if they don't decode.'''
        data = self.serialize()
        try:
            res = data.decode(self.encoding.name)
        except UnicodeDecodeError:
            Log.warn('{:s}.get : {:s} : Unable to decode to {:s}. Replacing invalid characters. : {!r}'.format(self.classname(), self.instance(), self.encoding.name, data))
            res = data.decode(self.encoding.name, 'replace')
        return res

    def summary(self, **options):
        return repr(self.serialize())

    @classmethod
    def typename(cls):
        return '{:s}<{:s}>'.format(cls.__name__, cls.encoding.name)

class char_t(_char_t):
    '''Single character type'''

    def str(self):
        '''Return the character instance as a str type.'''
        return str(super(char_t, self).str())

    @classmethod
    def typename(cls):
        return cls.__name__

uchar_t = char_t    # yeah, secretly there's no difference..

class wchar_t(_char_t):
    '''Single wide-character type'''

    # try and figure out what type
    if Config.integer.order == config.byteorder.littleendian:
        encoding = codecs.lookup('utf-16-le')
    elif Config.integer.order == config.byteorder.bigendian:
        encoding = codecs.lookup('utf-16-be')
    else:
        raise SystemError('wchar_t', 'Unable to determine default encoding type based on platform byteorder : {!r}'.format(Config.integer.order))

class string(ptype.type):
    '''String of characters'''
    length = 0
    _object_ = char_t
    initializedQ = lambda self: self.value is not None    # bool

    def __init__(self, **attrs):
        res = super(string,self).__init__(**attrs)

        # ensure that self._object_ is using a fixed-width encoding
        _object_ = self._object_

        # encode 3 types of strings and ensure that their lengths scale up with their string sizes
        res,single,double = ( __builtin__.unicode(n, 'ascii').encode(_object_.encoding.name) for n in ('\x00', 'A', 'AA') )
        if len(res) * 2 == len(single) * 2 == len(double):
            return
        raise ValueError(self.classname(), 'string.__init__', 'User tried to specify a variable-width character encoding : {:s}'.format(_object_.encoding.name))

    def at(self, offset, **kwds):
        ofs = offset - self.getoffset()
        return self[ ofs / self._object_().blocksize() ]

    def blocksize(self):
        return self._object_().blocksize() * self.length

    def __insert(self, index, string):
        l = self._object_().blocksize()
        offset = index * l
        self.value = self.value[:offset] + string[:l] + self.value[offset:]

    def __delete(self, index):
        l = self._object_().blocksize()
        offset = index * l
        self.value = self.value[:offset] + self.value[offset+l:]

    def __replace(self, index, string):
        l = self._object_().blocksize()
        offset = index * l
        self.value = self.value[:offset] + string[:l] + self.value[offset+l:]

    def __fetch(self, index):
        l = self._object_().blocksize()
        offset = index * l
        return self.value[offset:offset+l]

    def __len__(self):
        if not self.initializedQ():
            raise error.InitializationError(self, 'string.__len__')
        return len(self.value) / self._object_().blocksize()

    def __delitem__(self, index):
        '''Remove the character at the specified ``index``.'''
        if isinstance(index, slice):
            raise error.ImplementationError(self, 'string.__delitem__', message='slice support not implemented')
        self.__delete(index)

    def __getitem__(self, index):
        '''Return the character at the specified ``index``.'''
        res = self.cast(dynamic.array(self._object_, len(self)))

        # handle a slice of glyphs
        if isinstance(index, slice):
            result = [res.value[_] for _ in xrange(*index.indices(len(res)))]

            # ..and now turn the slice into an array
            type = ptype.clone(parray.type,length=len(result), _object_=self._object_)
            return self.new(type, offset=result[0].getoffset(), value=result)

        if index < -len(self) or index >= len(self):
            raise error.UserError(self, 'string.__getitem__', message='list index {:d} out of range'.format(index))

        # otherwise, returning a single element from the array should be good
        index %= len(self)
        return res[index]

    def __setitem__(self, index, value):
        '''Replace the character at ``index`` with the character ``value``'''

        # convert self into an array we can modify
        res = self.cast(dynamic.array(self._object_, len(self)))

        # handle a slice of glyphs
        if isinstance(index, slice):
            indices = xrange(*index.indices(len(res)))
            [ res[index].__setvalue__(glyph) for glyph,index in map(None,value,indices) ]

        # handle a single glyph
        else:
            res[index].__setvalue__(value)

        # now we can re-load ourselves from it
        return self.load(offset=0, source=provider.proxy(res))

    def insert(self, index, object):
        '''Insert the character ``object`` into the string at index ``index`` of the string.'''
        if not isinstance(object, self._object_):
            raise error.TypeError(self, 'string.insert', message='expected value of type {!r}. received {!r}'.format(self._object_,object.__class__))
        self.__insert(index, value.serialize())

    def append(self, object):
        '''Append the character ``object`` to the string.'''
        if not isinstance(object, self._object_):
            raise error.TypeError(self, 'string.append', message='expected value of type {!r}. received {!r}'.format(self._object_,object.__class__))
        self.value += object.serialize()

    def extend(self, iterable):
        '''Extend the string ``self`` with the characters provided by ``iterable``.'''
        for x in iterable:
            self.append(x)
        return

    def __setvalue__(self, value):
        '''Replaces the contents of ``self`` with the string ``value``.'''
        size,glyphs = self.blocksize(),[x for x in value]
        t = dynamic.array(self._object_, len(glyphs))
        result = t(blocksize=lambda:size)
        for element,glyph in zip(result.alloc(), value):
            element.__setvalue__(glyph)
        if len(value) > self.blocksize() / self._object_().a.size():
            Log.warn('{:s}.set : {:s} : User attempted to set a value larger than the specified type. String was truncated to {:d} characters. : {:d} > {:d}'.format(self.classname(), self.instance(), size / result._object_().a.size(), len(value), self.blocksize() / self._object_().a.size()))
        return self.load(offset=0, source=provider.proxy(result))

    def str(self):
        '''Decode the string into the specified encoding type.'''
        t = dynamic.array(self._object_, len(self))
        data = self.cast(t).serialize()
        try:
            res = data.decode(t._object_.encoding.name)
        except UnicodeDecodeError, e:
            raise UnicodeDecodeError(e.encoding, e.object, e.start, e.end, 'Unable to decode string {!r} to requested encoding : {:s}'.format(data, t._object_.encoding.name))
        return utils.strdup(res)

    def __getvalue__(self):
        '''Try and decode the string into the specified encoding type.'''
        t = dynamic.array(self._object_, len(self))
        data = self.cast(t).serialize()
        try:
            res = data.decode(t._object_.encoding.name)
        except UnicodeDecodeError:
            Log.warn('{:s}.str : {:s} : Unable to decode to {:s}. Defaulting to unencoded string.'.format(self.classname(), self.instance(), self._object_.typename()))
            res = data.decode(t._object_.encoding.name, 'ignore')
        return utils.strdup(res)

    def load(self, **attrs):
        with utils.assign(self, **attrs):
            sz = self._object_().blocksize()
            self.source.seek(self.getoffset())
            block = self.source.consume( self.blocksize() )
            result = self.__deserialize_block__(block)
        return result

    def __deserialize_block__(self, block):
        if len(block) != self.blocksize():
            raise error.LoadError(self, len(block))
        self.value = block
        return self

    def serialize(self):
        if self.initializedQ():
            return str(self.value)
        raise error.InitializationError(self, 'string.serialize')

    def summary(self, **options):
        try:
            result = repr(self.str())
        except UnicodeDecodeError:
            Log.debug('{:s}.summary : {:s} : Unable to decode unicode string. Rendering as hexdump instead.'.format(self.classname(),self.instance()))
            return super(string,self).summary(**options)
        return result

    def repr(self, **options):
        return self.details(**options)

    def classname(self):
        return '{:s}<{:s}>'.format(super(string,self).classname(), self._object_.typename())
type = string

class szstring(string):
    '''Standard null-terminated string'''
    _object_ = char_t
    length = None
    def isTerminator(self, value):
        return value.int() == 0

    def __setvalue__(self, value):
        """Set the null-terminated string to ``value``.

        Resizes the string according to the length of ``value``.
        """

        # FIXME: If .isTerminator() is altered for any reason, this won't work.
        if not value.endswith('\x00'.encode(self._object_.encoding.name)):
            value += '\x00'.encode(self._object_.encoding.name)

        t = dynamic.array(self._object_, len(value))
        result = t()
        for glyph,element in zip(value, result.alloc()):
            element.__setvalue__(glyph)
        return self.load(offset=0, source=provider.proxy(result))

    def __deserialize_block__(self, block):
        return self.__deserialize_stream__(iter(block))

    def load(self, **attrs):
        with utils.assign(self, **attrs):
            self.source.seek(self.getoffset())
            producer = (self.source.consume(1) for _ in itertools.count())
            result = self.__deserialize_stream__(producer)
        return result

    def __deserialize_stream__(self, stream):
        ofs = self.getoffset()
        obj = self.new(self._object_, offset=ofs)
        size = obj.blocksize()

        getchar = lambda: ''.join(itertools.islice(stream,size))

        self.value = ''
        while True:
            obj.setoffset(ofs)
            obj.__deserialize_block__(getchar())
            self.value += obj.serialize()
            if self.isTerminator(obj):
                break
            ofs += size
        return self

    def blocksize(self):
        return self.size() if self.initializedQ() else self.load().size()

class wstring(string):
    '''String of wide-characters'''
    _object_ = wchar_t

class szwstring(szstring):
    '''Standard null-terminated string of wide-characters'''
    _object_ = wchar_t

## aliases that should probably be improved
unicode=wstring
szunicode=szwstring

if __name__ == '__main__':
    import provider
    import pstr

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

    @TestCase
    def test_str_char():
        x = pstr.char_t(source=provider.string('hello')).l
        if x.get() == 'h':
            raise Success

    @TestCase
    def test_str_wchar():
        x = pstr.wchar_t(source=provider.string('\x43\x00')).l
        if x.get() == '\x43':
            raise Success

    @TestCase
    def test_str_string():
        x = pstr.string()
        string = "helllo world ok, i'm hungry for some sushi\x00"
        x.length = len(string)/2
        x.source = provider.string(string)
        x.load()
        if x.str() == string[:len(string)/2]:
            raise Success

    @TestCase
    def test_str_wstring():
        x = pstr.wstring()
        oldstring = "ok, this is unicode"
        string = oldstring
        x.length = len(string)/2
        string = ''.join([c+'\x00' for c in string])
        x.source = provider.string(string)
        x.load()
        if x.str() == oldstring[:len(oldstring)/2]:
            raise Success

    @TestCase
    def test_str_szstring():
        string = 'null-terminated\x00ok'
        x = pstr.szstring(source=provider.string(string)).l
        if x.str() == 'null-terminated':
            raise Success

    @TestCase
    def test_str_array_szstring():
        import parray
        data = 'here\x00is\x00my\x00null-terminated\x00strings\x00eof\x00stop here okay plz'

        class stringarray(parray.terminated):
            _object_ = pstr.szstring

            def isTerminator(self, value):
                if value.str() == 'eof':
                    return True
                return False

        x = stringarray(source=provider.string(data)).l
        if x[3].str() == 'null-terminated':
            raise Success

    @TestCase
    def test_str_struct_szstring():
        import pstruct,pint,pstr
        class IMAGE_IMPORT_HINT(pstruct.type):
            _fields_ = [
                ( pint.uint16_t, 'Hint' ),
                ( pstr.szstring, 'String' )
            ]

        x = IMAGE_IMPORT_HINT(source=provider.string('AAHello world this is a zero0-terminated string\x00this didnt work')).l
        if x['String'].str() == 'Hello world this is a zero0-terminated string':
            raise Success

    @TestCase
    def test_str_szwstring():
        s = '_\x00c\x00t\x00y\x00p\x00e\x00s\x00.\x00p\x00y\x00d\x00\x00\x00'
        v = pstr.szwstring(source=provider.string(s)).l
        if v.str() == '_ctypes.pyd':
            raise Success

    @TestCase
    def test_str_szwstring_customchar():
        data = ' '.join(map(lambda x:x.strip(),'''
            00 57 00 65 00 6c 00 63 00 6f 00 6d 00 65 00 00
        '''.split('\n'))).strip()
        data = map(lambda x: chr(int(x,16)), data.split(' '))
        data = ''.join(data)

        import pstruct,pstr,provider,utils
        class wbechar_t(pstr.wchar_t):
            def set(self, value):
                self.value = '\x00' + value
                return self

            def get(self):
                return unicode(self.value, 'utf-16-be').encode('utf-8')

        class unicodestring(pstr.szwstring):
            _object_ = wbechar_t
            def str(self):
                s = __builtin__.unicode(self.value, 'utf-16-be').encode('utf-8')
                return utils.strdup(s)[:len(self)]

        class unicodespeech_packet(pstruct.type):
            _fields_ = [
                (unicodestring, 'msg'),
            ]

        a = unicodestring(source=provider.string(data)).l
        if a.l.str() == 'Welcome':
            raise Success
        raise Failure

    @TestCase
    def test_str_szstring_customterm():
        class fuq(pstr.szstring):
            def isTerminator(self, value):
                return value.int() == 0x3f

        s = provider.string('hello world\x3f..................')
        a = fuq(source=s)
        a = a.l
        if a.size() == 12:
            raise Success

    @TestCase
    def test_wstr_struct():
        import ptypes
        from ptypes import pint,dyn,pstr
        class record0085(pstruct.type):
            _fields_ = [
                (pint.uint16_t, 'unknown'),
                (pint.uint32_t, 'skipped'),
                (pint.uint16_t, 'sheetname_length'),
                (lambda s: dyn.clone(pstr.wstring, length=s['sheetname_length'].li.int()), 'sheetname'),
            ]
        s = ptypes.prov.string('85001400e511000000000600530068006500650074003100'.decode('hex')[4:])
        a = record0085(source=s)
        a=a.l
        if a['sheetname'].str() == 'Sheet1':
            raise Success

    @TestCase
    def test_str_szwstring_blockarray():
        import ptypes
        from ptypes import pstr,dyn
        data = '3d 00 3a 00 3a 00 3d 00 3a 00 3a 00 5c 00 00 00 65 00 2e 00 6c 00 6f 00 67 00 00 00 00 00 ab ab ab ab ab ab ab ab'.replace(' ','').decode('hex')
        source = ptypes.prov.string(data)
        t = dyn.blockarray(pstr.szwstring, 30)
        a = t(source=source).l
        if (a[0].str(),a[1].str(),a[2].str()) == ('=::=::\\','e.log','') and a[2].blocksize() == 2 and len(a) == 3:
            raise Success

if __name__ == '__main__':
    results = []
    for t in TestCaseList:
        results.append( t() )
