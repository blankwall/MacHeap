"""
Various providers that a ptype can be sourced from.

Each ptype instance can read and write it's data to particular provider type. A
provider type is responsible for keeping track of the current offset into some
byte-seekable data source and exposing a few general methods for reading and
writing to the source.

The interface for a provider must look like the following:

    class interface(object):
        def seek(self, offset): return last-offset-before
        def consume(self, amount): return string-containing-data
        def store(self, stringdata): return number-of-bytes-written

It is up to the implementor to maintain the current offset, and update them when
the .store or .consume methods are called.

Example usage:
# define a type
    type = ...

# set global source
    import ptypes
    ptypes.setsource( ptypes.provider.name(...) )

    instance = type()
    print( repr(instance) )

# set instance's source during construction
    import ptypes.provider
    instance = type(source=ptypes.provider.name(...))
    print( repr(instance) )

# set instance's source after construction
    import ptypes.provider
    instance = type()
    ...
    instance.source = ptypes.provider.name(...)
    instance.load()
    print( repr(instance) )

# set instance's source during load
    instance = type()
    instance.load(source=ptypes.provider.name(...))
    print( repr(instance) )

# set instances's source during commit
    instance = type()
    instance.commit(source=ptypes.provider.name(...))
    print( repr(instance) )
"""

import __builtin__,array,exceptions,sys,itertools,operator
from . import config,utils,error
Config = config.defaults
Log = Config.log.getChild(__name__[len(__package__)+1:])

class base(object):
    '''Base provider class. Intended to be used as a template for a provider implementation.'''
    def seek(self, offset):
        '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
        raise error.ImplementationError(self, 'seek', message='Developer forgot to overload this method')
    def consume(self, amount):
        '''Read some number of bytes from the current offset. If the first byte wasn't able to be consumed, raise an exception.'''
        raise error.ImplementationError(self, 'seek', message='Developer forgot to overload this method')
    def store(self, data):
        '''Write some number of bytes to the current offset. If nothing was able to be written, raise an exception.'''
        raise error.ImplementationError(self, 'seek', message='Developer forgot to overload this method')

class empty(base):
    '''Empty provider. Returns only zeroes.'''
    offset = 0
    def seek(self, offset):
        '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
        offset=0
        return 0
    def consume(self, amount):
        '''Consume ``amount`` bytes from the given provider.'''
        return '\x00'*amount
    def store(self, data):
        '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
        Log.info('{:s}.store : Tried to write 0x{:x} bytes to a read-only medium.'.format(type(self).__name__, len(data)))
        return len(data)

## core providers
class string(base):
    '''Basic writeable string provider.'''
    offset = int
    data = str     # this is backed by an array.array type

    @property
    def value(self): return self.data.tostring()
    @value.setter
    def value(self, value): self.data = value

    def __init__(self, string=''):
        self.data = array.array('c', string)
    def seek(self, offset):
        '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
        res,self.offset = self.offset,offset
        return res

    @utils.mapexception(any=error.ProviderError,ignored=(error.ConsumeError,error.UserError))
    def consume(self, amount):
        '''Consume ``amount`` bytes from the given provider.'''
        if amount < 0:
            raise error.UserError(self, 'consume', message='tried to consume a negative number of bytes. {:d}:+{:s} from {:s}'.format(self.offset,amount,self))
        if amount == 0: return ''
        if self.offset >= len(self.data):
            raise error.ConsumeError(self,self.offset,amount)

        minimum = min((self.offset+amount, len(self.data)))
        res = self.data[self.offset : minimum].tostring()
        if res == '' and amount > 0:
            raise error.ConsumeError(self,self.offset,amount,len(res))
        if len(res) == amount:
            self.offset += amount
        return str(res)

    @utils.mapexception(any=error.ProviderError,ignored=(error.StoreError,))
    def store(self, data):
        '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
        try:
            left, right = self.offset, self.offset + len(data)
            self.data[left:right] = array.array('c',data)
            self.offset = right
            return len(data)
        except Exception,e:
            raise error.StoreError(self,self.offset,len(data),exception=e)
        raise error.ProviderError

    @utils.mapexception(any=error.ProviderError)
    def size(self):
        return len(self.data)

class proxy(base):
    """Provider that will read or write it's data to/from the specified ptype.

    If autoload or autocommit is specified during construction, the object will sync the proxy with it's source before performing any operations requested of the proxied-type.
    """
    def __init__(self, source, **kwds):
        """Instantiate the provider using ``source`` as it's backing ptype.

        autocommit -- A dict that will be passed to the source type's .commit method when data is stored to the provider.
        autoload -- A dict that will be passed to the source type's .load method when data is read from the provider.
        """

        self.type = source
        self.offset = 0

        valid = ('autocommit', 'autoload')
        res = set(kwds.iterkeys()).difference(valid)
        if res.difference(valid):
            raise error.UserError(self, '__init__', message='Invalid keyword(s) specified. Expected ({!r}) : {!r}'.format(valid, tuple(res)))

        self.autoload = kwds.get('autoload', None)
        self.autocommit = kwds.get('autocommit', None)

    def seek(self, offset):
        '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
        res,self.offset = self.offset,offset
        return res

    @utils.mapexception(any=error.ProviderError, ignored=(error.ConsumeError,))
    def consume(self, amount):
        '''Consume ``amount`` bytes from the given provider.'''
        left,right = self.offset,self.offset+amount

        buf = self.type.serialize() if self.autoload is None else self.type.load(**self.autoload).serialize()
#        if self.autoload is not None:
#            Log.debug('{:s}.consume : Autoloading : {:s} : {!r}'.format(type(self).__name__, self.type.instance(), self.type.source))

        if amount >= 0 and left >= 0 and right <= len(buf):
            result = buf[left:right]
            self.offset += amount
            return result

        raise error.ConsumeError(self, left, amount, amount=right-len(buf))

    @utils.mapexception(any=error.ProviderError, ignored=(error.StoreError,))
    def store(self, data):
        '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
        left,right = self.offset, self.offset+len(data)

        # if trying to store within the bounds of self.type..
        if left >= 0 and right <= self.type.blocksize():
            from . import ptype,pbinary
            if isinstance(self.type, pbinary.partial):
                self.__write_partial(self.type, self.offset, data)

            elif isinstance(self.type, ptype.type):
                self.__write_object(self.type, self.offset, data)

            elif isinstance(self.type, ptype.container):
                self.__write_range(self.type, self.offset, data)

            else:
                raise NotImplementedError(self.type.__class__)

            self.offset += len(data)
            self.type if self.autocommit is None else self.type.commit(**self.autocommit)
#            if self.autocommit is not None:
#                Log.debug('{:s}.store : Autocommitting : {:s} : {!r}'.format(type(self).__name__, self.type.instance(), self.type.source))
            return len(data)

        # otherwise, check if nothing is being written
        if left == right:
            return len(data)

        raise error.StoreError(self, left, len(data), 0)

    @classmethod
    def __write_partial(cls, object, offset, data):
        left,right = offset, offset+len(data)
        size,value = object.blocksize(),object.serialize()
        padding = utils.padding.fill(size - min(size,len(data)), object.padding)
        object.load(offset=0, source=string(value[:left] + data + padding + value[right:]))
        return len(data)+len(padding)

    @classmethod
    def __write_object(cls, object, offset, data):
        left,right = offset, offset+len(data)
        res = object.blocksize()
        padding = utils.padding.fill(res - min(res,len(data)), object.padding)
        object.value = object.value[:left] + data + padding + object.value[right:]
        return res

    @classmethod
    def __write_range(cls, object, offset, data):
        result,left,right = 0, offset, offset+len(data)
        sl = list(cls.collect(object, left, right))

        # fix beginning element
        n = sl.pop(0)
        source,bs,l = n.serialize(),n.blocksize(),left-n.getoffset()
        s = bs-l
        _ = source[:l] + data[:s] + source[l+s:]
        n.load(offset=0, source=string(_))
        data = data[s:]
        result += s    # sum the blocksize

        # fix elements in the middle
        while len(sl) > 1:
            n = sl.pop(0)
            source,bs = n.serialize(),n.blocksize()
            _ = data[:bs] + source[len(data[:bs]):]
            n.load(offset=0, source=string(_))
            data = data[bs:]
            result += bs    # sum the blocksize

        # fix last element
        if len(sl) > 0:
            n = sl.pop(0)
            source,bs = n.serialize(),n.blocksize()
            _ = data[:bs] + source[len(data[:bs]):]
            padding = utils.padding.fill(bs - min(bs,len(_)), n.padding)
            n.load(offset=0, source=string(_ + padding))
            data = data[bs:]
            result += len(data[:bs])    # sum the final blocksize

        # check to see if there's any data left
        if len(data) > 0:
            Log.warn("{:s} : __write_range : {:d} bytes left-over from trying to write to {:d} bytes.".format(cls.__name__, len(data), result))

        # return the aggregated total
        return result

    @classmethod
    def collect(cls, object, left, right):
        '''an iterator that returns all the leaf nodes of ``object`` from field offset ``left`` to ``right``.'''
        # figure out which objects to start and stop at
        lobj = object.field(left, recurse=True) if left >= 0 else None
        robj = object.field(right, recurse=True) if right < object.blocksize() else None

        # return all leaf objects with a .value that's not a pbinary
        from . import ptype,pbinary
        leaves = object.traverse(lambda s: s.value, filter=lambda s: isinstance(s, ptype.type) or isinstance(s, pbinary.partial))

        # consume everything up to lobj
        list(itertools.takewhile(lambda n: n is not lobj, leaves))

        # now yield all elements from left..right
        if lobj is not None: yield lobj
        for res in itertools.takewhile(lambda n: n is not robj, leaves):
            yield res
        if robj is not None: yield robj

    def __repr__(self):
        return '{:s} -> {:s}'.format(super(proxy, self).__repr__(), self.type.instance())

import random as _random
class random(base):
    """Provider that returns random data when read from."""

    offset = 0
    @utils.mapexception(any=error.ProviderError)
    def seek(self, offset):
        '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
        res,self.offset = self.offset,offset
        _random.seed(self.offset)   # lol
        return res

    @utils.mapexception(any=error.ProviderError)
    def consume(self, amount):
        '''Consume ``amount`` bytes from the given provider.'''
        return str().join(chr(_random.randint(0,255)) for x in xrange(amount))

    @utils.mapexception(any=error.ProviderError)
    def store(self, data):
        '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
        Log.info('{:s}.store : Tried to write 0x{:x} bytes to a read-only medium.'.format(type(self).__name__, len(data)))
        return len(data)

## useful providers
class stream(base):
    """Provider that caches data read from a file stream in order to provide random-access reading.

    When reading from a particular offset, this provider will load only as much data as needed into it's cache in order to satify the user's request.
    """
    data = data_ofs = None
    iterator = None
    eof = False

    offset = None

    def __init__(self, source, offset=0):
        self.source = source
        self.data = array.array('c')
        self.data_ofs = self.offset = offset

    def seek(self, offset):
        '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
        res,self.offset = self.offset,offset
        return res
    def _read(self, amount):
        return self.source.read(amount)
    def _write(self, data):
        return self.source.write(data)

    def __getattr__(self, name):
        return getattr(self.source, name)

    ###
    def preread(self, amount):
        '''Preload some bytes from the stream and append it to the cache.'''
        if self.eof:
            raise EOFError

        data = self._read(amount)
        self.data.extend( array.array('c', data) )
        if len(data) < amount:    # XXX: this really can't be the only way(?) that an instance
                                  #      of something ~fileobj.read (...) can return for a 
            self.eof = True
        return data

    @utils.mapexception(any=error.ProviderError)
    def remove(self, amount):
        '''Removes some number of bytes from the beginning of the cache.'''
        assert amount < len(self.data)
        result = self.data[:amount]
        del(self.data[:amount])
        self.data_ofs += amount
        return result

    ###
    @utils.mapexception(any=error.ProviderError, ignored=(error.ConsumeError,))
    def consume(self, amount):
        '''Consume ``amount`` bytes from the given provider.'''
        o = self.offset - self.data_ofs
        if o < 0:
            raise ValueError('{:s}.consume : Unable to seek to offset {:x} ({:x},+{:x})'.format(type(self).__name__, self.offset, self.data_ofs, len(self.data)))

        # select the requested data
        if (self.eof) or (o + amount <= len(self.data)):
            result = self.data[o:o+amount].tostring()
            self.offset += amount
            return result

        # preread enough bytes so that stuff works
        elif len(self.data) == 0 or o <= len(self.data):
            n = amount - (len(self.data) - o)
            self.preread(n)
            return self.consume(amount)

        # preread up to the offset
        if o + amount > len(self.data):
            self.preread(o - len(self.data))
            return self.consume(amount)

        raise error.ConsumeError(self, self.offset,amount)

    if False:
        def store(self, data):
            '''updates data at an offset in the stream's cache.'''
            # FIXME: this logic _apparently_ hasn't been thought out at all..check notes
            o = self.offset - self.data_ofs
            if o>=0 and o<=len(self.data):
                self.data[o:o+len(data)] = array.array('c', data)
                if o+len(data) >= len(self.data):
                    self.eof = False
                self._write(data)
                return len(data)
            raise ValueError("{:s}.store : Unable to store {:x} bytes outside of provider's cache size ({:x},+{:x})".format(type(self), len(data), self.data_ofs, len(self.data)))

    @utils.mapexception(any=error.ProviderError)
    def store(self, data):
        '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
        return self._write(data)

    def __repr__(self):
        return '{:s}[eof={!r} base=0x{:x} length=+{:x}] ofs=0x{:x}'.format(type(self), self.eof, self.data_ofs, len(self.data), self.offset)

    def __getitem__(self, i):
        return self.data[i-self.data_ofs]

    def __getslice__(self, i, j):
        return self.data[i-self.data_ofs:j-self.data_ofs].tostring()

    def hexdump(self, **kwds):
        return utils.hexdump(self.data.tostring(), offset=self.data_ofs, **kwds)

class iterable(stream):
    '''Provider that caches data read from a generator/iterable in order to provide random-access reading.'''
    def _read(self, amount):
        return str().join(itertools.islice(self.source, amount))

    def _write(self, data):
        Log.info('iter._write : Tried to write 0x{:x} bytes to an iterator'.format(len(data)))
        return len(data)

class filebase(base):
    '''Basic fileobj provider. Intended to be inherited from.'''
    file = None
    def __init__(self, fileobj):
        self.file = fileobj

    @utils.mapexception(any=error.ProviderError)
    def seek(self, offset):
        '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
        res = self.file.tell()
        self.file.seek(offset)
        return res

    @utils.mapexception(any=error.ProviderError, ignored=(error.ConsumeError,))
    def consume(self, amount):
        '''Consume ``amount`` bytes from the given provider.'''
        offset = self.file.tell()
        if amount < 0:
            raise error.UserError(self, 'consume', message='Tried to consume a negative number of bytes. {:d}:+{:s} from {:s}'.format(offset,amount,self))
        Log.debug('{:s}.consume : Attempting to consume {:x}:+{:x}'.format(type(self).__name__, offset, amount))

        result = ''
        try:
            result = self.file.read(amount)
        except OverflowError, e:
            self.file.seek(offset)
            raise error.ConsumeError(self,offset,amount, len(result), exception=e)

        if result == '' and amount > 0:
            raise error.ConsumeError(self,offset,amount, len(result))

        if len(result) != amount:
            self.file.seek(offset)
        return result

    @utils.mapexception(any=error.ProviderError, ignored=(error.StoreError,))
    def store(self, data):
        '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
        offset = self.file.tell()
        try:
            return self.file.write(data)
        except Exception, e:
            self.file.seek(offset)
        raise error.StoreError(self, offset, len(data), exception=e)

    @utils.mapexception(any=error.ProviderError)
    def close(self):
        return self.file.close()

    @utils.mapexception(any=error.ProviderError)
    def size(self):
        old = self.file.tell()
        self.file.seek(0, 2)
        result = self.file.tell()
        self.file.seek(old, 0)
        return result

    def __repr__(self):
        return '{:s} -> {!r}'.format(super(filebase, self).__repr__(), self.file)

    def __del__(self):
        try: self.close()
        except: pass
        return

## optional providers
import os
class posixfile(filebase):
    '''Basic posix file provider.'''
    def __init__(self, *args, **kwds):
        res = self.open(*args, **kwds)
        super(posixfile,self).__init__(res)

    @utils.mapexception(any=error.ProviderError)
    def open(self, filename, mode='rw', perms=0644):
        mode = str().join(sorted(set(x.lower() for x in mode)))
        flags = (os.O_SHLOCK|os.O_FSYNC) if 'posix' in sys.modules else 0

        # this is always assumed
        if mode.startswith('b'):
            mode = mode[1:]

        # setup access
        flags = 0
        if 'r' in mode:
            flags |= os.O_RDONLY
        if 'w' in mode:
            flags |= os.O_WRONLY

        if (flags & os.O_RDONLY) and (flags & os.O_WRONLY):
            flags ^= os.O_RDONLY|os.O_WRONLY
            flags |= os.O_RDWR

        access = 'read/write' if (flags&os.O_RDWR) else 'write' if (flags&os.O_WRONLY) else 'read-only' if flags & os.O_RDONLY else 'unknown'

        if os.access(filename,6):
            Log.info("{:s}({!r}, {!r}) : Opening file for {:s}".format(type(self).__name__, filename, mode, access))
        else:
            flags |= os.O_CREAT|os.O_TRUNC
            Log.info("{:s}({!r}, {!r}) : Creating new file for {:s}".format(type(self).__name__, filename, mode, access))

        # mode defaults to rw-rw-r--
        self.fd = os.open(filename, flags, perms)
        return os.fdopen(self.fd)

    @utils.mapexception(any=error.ProviderError)
    def close(self):
        os.close(self.fd)
        return super(posixfile,self).close()

class file(filebase):
    '''Basic file provider.'''
    def __init__(self, *args, **kwds):
        res = self.open(*args, **kwds)
        return super(file,self).__init__(res)

    @utils.mapexception(any=error.ProviderError)
    def open(self, filename, mode='rw'):
        usermode = list(x.lower() for x in mode)

        # this is always assumed
        if 'b' in usermode:
            usermode.remove('b')

        if '+' in usermode:
            access = 'r+b'
        elif 'r' in usermode and 'w' in usermode:
            access = 'r+b'
        elif 'w' in usermode:
            access = 'wb'
        elif 'r' in usermode:
            access = 'rb'

        straccess = 'read/write' if access =='r+b' else 'write' if access == 'wb' else 'read-only' if access == 'rb' else 'unknown'

        if os.access(filename,0):
            if 'wb' in access:
                Log.warn("{:s}({!r}, {!r}) : Truncating file by user-request.".format(type(self).__name__, filename, access))
            Log.info("{:s}({!r}, {!r}) : Opening file for {:s}".format(type(self).__name__, filename, access, straccess))

        else:  # file not found
            if 'r+' in access:
                Log.warn("{:s}({!r}, {!r}) : File not found. Modifying access to write-only.".format(type(self).__name__, filename, access))
                access = 'wb'
            Log.warn("{:s}({!r}, {!r}) : Creating new file for {:s}".format(type(self).__name__, filename, access, straccess))

        return __builtin__.open(filename, access, 0)

try:
    import tempfile
    class filecopy(filebase):
        """A provider that reads/writes from a temporary copy of the specified file.

        If the user wishes to save the file to another location, a .save method is provided.
        """
        def __init__(self, *args, **kwds):
            res = self.open(*args, **kwds)
            return super(filecopy,self).__init__(res)

        @utils.mapexception(any=error.ProviderError)
        def open(self, filename):
            '''Open the specified file as a temporary file.'''
            with open(filename, 'rb') as input:
                input.seek(0)
                output = tempfile.TemporaryFile(mode='w+b')
                for data in input:
                    output.write(data)
                output.seek(0)
            return output

        def save(self, filename):
            '''Copy the current temporary file to the specified ``filename``.'''
            ofs = self.file.tell()
            with __builtin__.file(filename, 'wb') as output:
                self.file.seek(0)
                for data in self.file:
                    output.write(data)
            self.file.seek(ofs)

except ImportError:
    Log.warning("__module__ : Unable to import the 'tempfile' module. Failed to load the `filecopy` provider.")

class memorybase(base):
    '''Base provider class for reading/writing with a memory-type backing. Intended to be inherited from.'''

try:
    import ctypes

    ## TODO: figure out an elegant way to catch exceptions we might cause
    ##       by dereferencing any of these pointers on both windows (veh) and posix (signals)

    class memory(memorybase):
        '''Basic in-process memory provider based on ctypes.'''
        address = 0
        def seek(self, offset):
            '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
            res,self.address = self.address,offset
            return res

        @utils.mapexception(any=error.ProviderError, ignored=(error.ConsumeError,))
        def consume(self, amount):
            '''Consume ``amount`` bytes from the given provider.'''
            if amount < 0:
                raise error.UserError(self, 'consume', message='tried to consume a negative number of bytes. {:d}:+{:s} from {:s}'.format(self.address,amount,self))
            res = memory._read(self.address, amount)
            if len(res) == 0 and amount > 0:
                raise error.ConsumeError(self,offset,amount,len(res))
            if len(res) == amount:
                self.address += amount
            return res

        @utils.mapexception(any=error.ProviderError, ignored=(error.StoreError,))
        def store(self, data):
            '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
            res = memory._write(self.address, data)
            if res != len(data):
                raise error.StoreError(self,self.address,len(data),written=res)
            self.address += len(data)
            return res

        @staticmethod
        def _read(address, length):
            blockpointer = ctypes.POINTER(ctypes.c_char*length)
            v = ctypes.c_void_p(address)
            p = ctypes.cast(v, blockpointer)
            return str().join(p.contents)

        @staticmethod
        def _write(address, value):
            blockpointer = ctypes.POINTER(ctypes.c_char*len(value))
            v = ctypes.c_void_p(address)
            p = ctypes.cast(v, blockpointer)
            for i,c in enumerate(value):
                p.contents[i] = c
            return i+1

except ImportError:
    Log.warning("__module__ : Unable to import the 'ctypes' module. Failed to load the `memory` provider.")

try:
    import ctypes
    try:
        k32 = ctypes.WinDLL('kernel32.dll')
    except Exception,m:
        raise OSError(m)

    class win32error:
        @staticmethod
        def getLastErrorTuple():
            errorCode = k32.GetLastError()
            p_string = ctypes.c_void_p(0)

            # FORMAT_MESSAGE_
            ALLOCATE_BUFFER = 0x100
            FROM_SYSTEM = 0x1000
            res = k32.FormatMessageA(
                ALLOCATE_BUFFER | FROM_SYSTEM, 0, errorCode,
                0, ctypes.pointer(p_string), 0, None
            )
            res = ctypes.cast(p_string, ctypes.c_char_p)
            errorString = str(res.value)
            res = k32.LocalFree(res)
            assert res == 0, "kernel32!LocalFree failed. Error 0x{:08x}.".format(k32.GetLastError())

            return (errorCode, errorString)

        @staticmethod
        def getLastErrorString():
            code, string = getLastErrorTuple()
            return string

    class WindowsProcessHandle(memorybase):
        '''Windows memory provider that will use a process handle in order to access memory.'''
        address = 0
        handle = None
        def __init__(self, handle):
            self.handle = handle

        def seek(self, offset):
            '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
            res,self.address = self.address,offset
            return res

        @utils.mapexception(any=error.ProviderError, ignored=(error.ConsumeError,))
        def consume(self, amount):
            '''Consume ``amount`` bytes from the given provider.'''
            if amount < 0:
                raise error.UserError(self, 'consume', message='tried to consume a negative number of bytes. {:d}:+{:s} from {:s}'.format(self.address,amount,self))

            NumberOfBytesRead = ctypes.c_int()
            res = ctypes.c_char*amount
            Buffer = res()

            # FIXME: instead of failing on an incomplete read, perform a partial read
            res = k32.ReadProcessMemory(self.handle, self.address, Buffer, amount, ctypes.byref(NumberOfBytesRead))
            if (res == 0) or (NumberOfBytesRead.value != amount):
                e = ValueError('Unable to read pid({:x})[{:08x}:{:08x}].'.format(self.handle, self.address, self.address+amount))
                raise error.ConsumeError(self, self.address,amount, NumberOfBytesRead.value)

            self.address += amount
            # XXX: test this shit out
            return str(Buffer.raw)

        @utils.mapexception(any=error.ProviderError, ignored=(error.StoreError,))
        def store(self, value):
            '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
            NumberOfBytesWritten = ctypes.c_int()

            res = ctypes.c_char*len(value)
            Buffer = res()
            Buffer.value = value

            res = k32.WriteProcessMemory(self.handle, self.address, Buffer, len(value), ctypes.byref(NumberOfBytesWritten))
            if (res == 0) or (NumberOfBytesWritten.value != len(value)):
                e = OSError('Unable to write to pid({:x})[{:08x}:{:08x}].'.format(self.id, self.address, self.address+len(value)))
                raise error.StoreError(self, self.address,len(value), written=NumberOfBytesWritten.value, exception=e)

            self.address += len(value)
            return NumberOfBytesWritten.value

    def WindowsProcessId(pid, **attributes):
        '''Return a provider that allows one to read/write from memory owned by the specified windows process ``pid``.'''
        handle = k32.OpenProcess(0x30, False, pid)
        return WindowsProcessHandle(handle)

    class WindowsFile(base):
        '''A provider that uses the Windows File API.'''
        offset = 0
        def __init__(self, filename, mode='rb'):
            self.offset = 0

            GENERIC_READ, GENERIC_WRITE = 0x40000000,0x80000000
            FILE_SHARE_READ,FILE_SHARE_WRITE = 1,2
            OPEN_EXISTING,OPEN_ALWAYS = 3,4
            FILE_ATTRIBUTE_NORMAL = 0x80
            INVALID_HANDLE_VALUE = -1

#            raise NotImplementedError("These are not the correct permissions")

            cmode = OPEN_EXISTING

            if 'w' in mode:
                smode = FILE_SHARE_READ|FILE_SHARE_WRITE
                amode = GENERIC_READ|GENERIC_WRITE
            else:
                smode = FILE_SHARE_READ
                amode = GENERIC_READ|GENERIC_WRITE

            result = k32.CreateFileA(
                filename, amode, smode, None, cmode,
                FILE_ATTRIBUTE_NORMAL, None
            )
            if result == INVALID_HANDLE_VALUE:
                raise OSError(win32error.getLastErrorTuple())
            self.handle = result

        @utils.mapexception(any=error.ProviderError)
        def seek(self, offset):
            '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
            distance,resultDistance = ctypes.c_longlong(offset),ctypes.c_longlong(offset)
            FILE_BEGIN = 0
            result = k32.SetFilePointerEx(
                self.handle, distance, ctypes.byref(resultDistance),
                FILE_BEGIN
            )
            if result == 0:
                raise OSError(win32error.getLastErrorTuple())
            res,self.offset = self.offset,resultDistance.value
            return res

        @utils.mapexception(any=error.ProviderError, ignored=(error.ConsumeError,))
        def consume(self, amount):
            '''Consume ``amount`` bytes from the given provider.'''
            resultBuffer = (ctypes.c_char*amount)()
            amount,resultAmount = ctypes.c_ulong(amount),ctypes.c_ulong(amount)
            result = k32.ReadFile(
                self.handle, ctypes.byref(resultBuffer),
                amount, ctypes.byref(resultAmount),
                None
            )
            if (result == 0) or (resultAmount.value == 0 and amount > 0):
                e = OSError(win32error.getLastErrorTuple())
                raise error.ConsumeError(self,self.offset,amount,resultAmount.value, exception=e)

            if resultAmount.value == amount:
                self.offset += resultAmount.value
            return str(resultBuffer.raw)

        @utils.mapexception(any=error.ProviderError, ignored=(error.StoreError,))
        def store(self, value):
            '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
            buffer = (c_char*len(value))(value)
            resultWritten = ctypes.c_ulong()
            result = k32.WriteFile(
                self.handle, buffer,
                len(value), ctypes.byref(resultWritten),
                None
            )
            if (result == 0) or (resultWritten.value != len(value)):
                e = OSError(win32error.getLastErrorTuple())
                raise error.StoreError(self, self.offset,len(value),resultWritten.value,exception=e)
            self.offset += resultWritten.value
            return resultWritten

        @utils.mapexception(any=error.ProviderError)
        def close(self):
            result = k32.CloseHandle(self.handle)
            if (result == 0):
                raise OSError(win32error.getLastErrorTuple())
            self.handle = None
            return result

    Log.info("__module__ : Successfully loaded the `WindowsProcessHandle`, `WindowsProcessId`, and `WindowsFile` providers.")
except ImportError:
    Log.warning("__module__ : Unable to import the 'ctypes' module. Failed to load the `WindowsProcessHandle`, `WindowsProcessId`, and `WindowsFile` providers.")

except OSError, m:
    Log.warning("__module__ : Unable to load 'kernel32.dll' ({:s}). Failed to load the `WindowsProcessHandle`, `WindowsProcessId`, and `WindowsFile` providers.".format(m))

try:
    import _idaapi
    class Ida(memorybase):
        '''A provider that uses IDA Pro's API for reading/writing to the database.'''
        offset = 0xffffffff

        def __init__(self):
            raise UserWarning("{:s}.{:s} is a static object and contains only staticmethods.".format(self.__module__,self.__class__.__name__))

        @classmethod
        def read(cls, offset, size, padding='\x00'):
            result = _idaapi.get_many_bytes(offset, size) or ''
            if len(result) == size:
                return result

            half = size // 2
            if half > 0:
                return str().join((cls.read(offset, half, padding=padding),cls.read(offset+half, half+size%2, padding=padding)))
            if _idaapi.isEnabled(offset):
                return '' if size == 0 else (padding*size) if (_idaapi.getFlags(offset) & _idaapi.FF_IVL) == 0 else _idaapi.get_many_bytes(offset, size)
            raise Exception(offset)

        @classmethod
        def within_segment(cls, offset):
            s = _idaapi.getseg(offset)
            return s is not None and s.startEA <= offset < s.endEA

        @classmethod
        def seek(cls, offset):
            '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
            res,cls.offset = cls.offset,offset
            return res

        @classmethod
        def consume(cls, amount):
            '''Consume ``amount`` bytes from the given provider.'''
            try:
                result = cls.read(cls.offset, amount)
            except Exception, (ofs,):
                raise error.ConsumeError(cls, ofs, amount, ofs-cls.offset)
            cls.offset += len(result)
            return result

        @classmethod
        def store(cls, data):
            '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
            #_idaapi.put_many_bytes(cls.offset, data)
            _idaapi.patch_many_bytes(cls.offset, data)
            cls.offset += len(data)
            return len(data)

    Log.warning("__module__ : Successfully loaded the `Ida` provider.")

except ImportError:
    Log.info("__module__ : Unable to import the '_idaapi' module (not running IDA?). Failed to load the `Ida` provider.")

try:
    import _PyDbgEng
    class PyDbgEng(memorybase):
        '''A provider that uses the PyDbgEng.pyd module to interact with the memory of the current debugged process.'''
        offset = 0
        def __init__(self, client=None):
            self.client = client

        @classmethod
        def connect(cls, remote):
            if remote is None:
                result = _PyDbgEng.Create()
            elif type(remote) is tuple:
                host,port = client
                result = _PyDbgEng.Connect('tcp:port={},server={}'.format(port,host))
            elif type(remote) is dict:
                result = _PyDbgEng.Connect('tcp:port={port},server={host}'.format(**client))
            elif isinstance(type(remote), basestring):
                result = _PyDbgEng.Connect(client)
            return cls(result)
        @classmethod
        def connectprocessserver(cls, remote):
            result = _PyDbgEng.ConnectProcessServer(remoteOptions=remote)
            return cls(result)
        def connectkernel(self, remote):
            if remote is None:
                result = _PyDbgEng.AttachKernel(flags=_PyDbgEng.ATTACH_LOCAL_KERNEL)
            else:
                result = _PyDbgEng.AttachKernel(flags=0, connectOptions=remote)
            return cls(result)

        def seek(self, offset):
            '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
            res,self.offset = self.offset,offset
            return res

        def consume(self, amount):
            '''Consume ``amount`` bytes from the given provider.'''
            try:
                result = self.client.DataSpaces.Virtual.Read(self.offset, amount)
            except RuntimeError, e:
                raise StopIteration('Unable to read 0x{:x} bytes from address 0x{:x}'.format(amount, self.offset))
            return str(result)

        def store(self, data):
            '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
            return self.client.DataSpaces.Virtual.Write(self.offset, data)

    Log.warning("__module__ : Successfully loaded the `PyDbgEng` provider.")
except ImportError:
    Log.info("__module__ : Unable to import the '_PyDbgEng' module. Failed to load the `PyDbgEng` provider.")

try:
    import pykd as _pykd
    class Pykd(memorybase):
        '''A provider that uses the Pykd library to interact with the memory of a debugged process.'''
        def __init__(self):
            self.addr = 0

        def seek(self, offset):
            '''Seek to the specified ``offset``. Returns the last offset before it was modified.'''
            # FIXME: check to see if we're at an invalid address
            res,self.addr = self.addr,offset
            return res

        def consume(self, amount):
            '''Consume ``amount`` bytes from the given provider.'''
            if amount == 0:
                return ''
            try:
                res = map(chr,_pykd.loadBytes(self.addr, amount))
            except:
                raise error.ConsumeError(self,self.addr,amount,0)
            self.addr += amount
            return str().join(res)

        def store(self, data):
            '''Store ``data`` at the current offset. Returns the number of bytes successfully written.'''
            raise error.StoreError(self, self.addr, len(data), message="Pykd doesn't allow you to write to memory.")
            res = len(data)
            self.addr += res
            return res

    Log.warning("__module__ : Successfully loaded the `Pykd` provider.")

except ImportError:
    Log.info("__module__ : Unable to import the 'pykd' module. Failed to load the `Pykd` provider.")

try:
    class lldb(base):
        module = __import__('lldb')
        def __init__(self, sbprocess=None):
            self.__process = sbprocess or self.module.process
            self.address = 0
        def seek(self, offset):
            res,self.address = self.address, offset
            return res
        def consume(self, amount):
            if amount < 0:
                raise error.ConsumeError(self, self.address, amount)
            process,err = self.__process, self.module.SBError()
            if amount > 0:
                data = process.ReadMemory(self.address, amount, err)
                if err.Fail() or len(data) != amount:
                    raise error.ConsumeError(self, self.address, amount)
                self.address += len(data)
                return bytes(data)
            return ''
        def store(self, data):
            process,err = self.__process, self.module.SBError()
            amount = process.WriteMemory(self.address, bytes(data), err)
            if err.Fail() or len(data) != amount:
                raise error.StoreError(self, self.address, len(data))
            self.address += amount
            return amount

    Log.warning("__module__ : Successfully loaded the `lldb` provider.")
except ImportError:
    Log.info("__module__ : Unable to import the 'lldb' module. Failed to load the `lldb` provider.")

try:
    class gdb(base):
        module = __import__('gdb')
        def __init__(self, inferior=None):
            self.__process = inferior or self.module.selected_inferior()
            self.address = 0
        def seek(self, offset):
            res,self.address = self.address, offset
            return res
        def consume(self, amount):
            process = self.__process
            try:
                data = process.read_memory(self.address, amount)
            except gdb.MemoryError:
                data = None
            if data is None or len(data) != amount:
                raise error.ConsumeError(self, self.address, amount)
            self.address += len(data)
            return bytes(data)
        def store(self, data):
            process = self.__process
            try:
                process.write_memory(self.address, bytes(data))
            except gdb.MemoryError:
                raise error.StoreError(self, self.address, len(data))
            self.address += len(data)
            return len(data)

    Log.warning("__module__ : Successfully loaded the `gdb` provider.")
except ImportError:
    Log.info("__module__ : Unable to import the 'gdb' module. Failed to load the `gdb` provider.")

class base64(string):
    '''A provider that accesses data in a Base64 encoded string.'''
    def __init__(self, base64string, begin='', end=''):
        result = map(operator.methodcaller('strip'),base64string.split('\n'))
        if begin and begin in base64string:
            res = [i for i,_ in enumerate(result) if _.startswith(begin)][0]
            result[:] = result[res+1:]
        if end and end in base64string:
            res = [i for i,_ in enumerate(result) if _.startswith(end)][0]
            result[:] = result[:res]
        result = str().join(result).translate(None, ' \t\n\r\v')
        super(base64,self).__init__(result.decode('base64'))

    @property
    def value(self):
        return self.data.tostring().encode('base64')

if __name__ == '__main__' and 0:
    import array
    import ptypes,ptypes.provider as provider
#    x = provider.WindowsFile('~/a.out')
#    raise NotImplementedError("Stop being lazy and finish WindowsFile")

    import array
    class fakefile(object):
        d = array.array('L', ((0xdead*x)&0xffffffff for x in range(0x1000)))
        d = array.array('c', d.tostring())
        o = 0
        def seek(self, ofs):
            self.o = ofs
        def read(self, amount):
            r = self.d[self.o:self.o+amount].tostring()
            self.o += amount
            return r

    import ptypes
    from ptypes import *
    strm = provider.stream(fakefile())
#    print repr(strm.fileobj.d)
#    print strm.buffer_data

#    print repr(fakefile().d[0:0x30].tostring())
    x = dynamic.array(pint.uint32_t, 3)(source=strm)
    x = x.l
#    print repr(x.l.serialize())

    print repr(pint.uint32_t(offset=0,source=strm).l.serialize() + \
     pint.uint32_t(offset=4,source=strm).l.serialize() + \
     pint.uint32_t(offset=8,source=strm).l.serialize() + \
     pint.uint32_t(offset=0xc,source=strm).l.serialize() + \
     pint.uint32_t(offset=0x10,source=strm).l.serialize() + \
     pint.uint32_t(offset=0x14,source=strm).l.serialize() + \
     pint.uint32_t(offset=0x18,source=strm).l.serialize() )

if __name__ == '__main__':
    # test cases are found at next instance of '__main__'
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
    import os,random
    from __builtin__ import *
    import provider
    import tempfile

    class temporaryname(object):
        def __enter__(self, *args):
            self.name = tempfile.mktemp()
            return self.name
        def __exit__(self, *args):
            try: os.unlink(self.name)
            except: pass
            del(self.name)

    class temporaryfile(object):
        def __enter__(self, *args):
            name = tempfile.mktemp()
            self.file = file(name, 'w+b')
            return self.file
        def __exit__(self, *args):
            self.file.close()
            filename = self.file.name
            del(self.file)
            os.unlink(filename)

    import time
    @TestCase
    def test_file_readonly():
        data = 'A'*512
        with temporaryname() as filename:
            f = open(filename, 'wb')
            f.write(data)
            f.seek(0)
            f.close()

            z = provider.file(filename, mode='r')
            a = z.consume(len(data))
            assert a == data

            try:
                z.store('nope')
            except:
                raise Success
            finally:
                z.close()
        raise Failure

    @TestCase
    def test_file_writeonly():
        data = 'A'*512
        with temporaryname() as filename:
            f = open(filename, 'wb')
            f.write(data)
            f.seek(0)
            f.close()

            z = provider.file(filename, mode='w')
            z.store(data)
            z.seek(0)
            try:
                a = z.consume(len(data))
                assert a == data
            except:
                raise Success
            finally:
                z.close()
        return

    @TestCase
    def test_file_readwrite():
        data = 'A'*512
        with temporaryname() as filename:
            f = open(filename, 'wb')
            f.write(data)
            f.seek(0)
            f.close()

            z = provider.file(filename, mode='rw')
            z.store(data)

            z.seek(0)
            a = z.consume(len(data))
            assert a == data

            z.close()
        raise Success

    @TestCase
    def test_filecopy_read():
        data = 'A'*512
        with temporaryname() as filename:
            f = open(filename, 'wb')
            f.write(data)
            f.seek(0)
            f.close()

            z = provider.filecopy(filename)
            if z.consume(len(data)) == data:
                raise Success
        return

    @TestCase
    def test_filecopy_write():
        data = 'A'*512
        with temporaryname() as filename:
            f = open(filename, 'wb')
            f.write(data)
            f.seek(0)
            f.close()

            z = provider.filecopy(filename)
            a = z.store('B' * len(data))

            z.seek(0)
            a = z.consume(len(data))
            if a.count('B') == len(data):
                raise Success
        return

    @TestCase
    def test_filecopy_readwrite():
        data = 'A'*512
        with temporaryname() as filename:
            f = open(filename, 'wb')
            f.write(data)
            f.seek(0)
            f.close()

            z = provider.filecopy(filename)
            z.seek(len(data))
            a = z.store('B' * len(data))

            z.seek(0)
            a = z.consume(len(data)*2)
            if a.count('A') == len(data) and a.count('B') == len(data):
                raise Success
        return

    try:
        import ctypes
        @TestCase
        def test_memory_read():
            data = 'A'*0x40
            buf = ctypes.c_buffer(data)
            ea = ctypes.addressof(buf)
            z = provider.memory()
            z.seek(ea)
            if z.consume(len(data)) == data:
                raise Success
            raise Failure

        @TestCase
        def test_memory_write():
            data = 'A'*0x40
            buf = ctypes.c_buffer(data)
            ea = ctypes.addressof(buf)
            z = provider.memory()
            z.seek(ea)
            z.store('B'*len(data))
            if buf.value == 'B'*len(data):
                raise Success
            raise Failure

        @TestCase
        def test_memory_readwrite():
            data = 'A'*0x40
            buf = ctypes.c_buffer(data)
            ea = ctypes.addressof(buf)
            z = provider.memory()
            z.seek(ea)
            z.store('B'*len(data))
            z.seek(ea)
            if z.consume(len(data)) == 'B'*len(data):
                raise Success

    except ImportError:
        Log.warning("__module__ : Skipping the `memory` provider tests.")
        pass

    @TestCase
    def test_random_read():
        z = provider.random()
        z.seek(0)
        a = z.consume(0x40)
        z.seek(0)
        if a == z.consume(0x40):
            raise Success

    @TestCase
    def test_random_write():
        raise Failure('Unable to write to provider.random()')

    @TestCase
    def test_random_readwrite():
        raise Failure('Unable to write to provider.random()')

    @TestCase
    def test_proxy_read_container():
        import ptypes
        from ptypes import parray,pint
        class t1(parray.type):
            _object_ = pint.uint8_t
            length = 0x10*4

        class t2(parray.type):
            _object_ = pint.uint32_t
            length = 0x10

        source = t1().set((0x41,)*4 + (0x42,)*4 + (0x43,)*(4*0xe))
        res = t2(source=provider.proxy(source)).l
        if res[0].int() == 0x41414141 and res[1].int() == 0x42424242 and res[2].int() == 0x43434343:
            raise Success
        raise Failure

    @TestCase
    def test_proxy_write_container():
        import ptypes
        from ptypes import parray,pint
        class t1(parray.type):
            _object_ = pint.uint8_t
            length = 0x10*4

        class t2(parray.type):
            _object_ = pint.uint32_t
            length = 0x10

        source = t1().set((0x41,)*4 + (0x42,)*4 + (0x43,)*(4*0xe))
        res = t2(source=provider.proxy(source)).l
        res[1].set(0x0d0e0a0d)
        res.commit()
        if ''.join(n.serialize() for n in source[0:0xc]) == 'AAAA\x0d\x0a\x0e\x0dCCCC':
            raise Success

    @TestCase
    def test_proxy_readwrite_container():
        import ptypes
        from ptypes import pint,parray,pbinary

        class t1(parray.type):
            length = 8
            class _object_(pbinary.struct):
                _fields_ = [(8,'a'),(8,'b'),(8,'c')]
            _object_ = pbinary.bigendian(_object_)

        class t2(parray.type):
            _object_ = pint.uint32_t
            length = 6

        source = t1(source=ptypes.prov.string('abcABCdefDEFghiGHIjlkJLK')).l
        res = t2(source=ptypes.prov.proxy(source)).l
        source[0].set((0x41,0x41,0x41))
        source.commit()
        res[1].set(0x42424242)
        res[1].commit()
        if source[0].serialize() == 'AAA' and source[1].serialize() == 'ABB' and source[2]['a'] == ord('B') and source[2]['b'] == ord('B'):
            raise Success

    try:
        import nt
        raise ImportError
        def stringalloc(string):
            v = ctypes.c_char*len(string)
            x = v(*string)
            return x,ctypes.addressof(x)

        def stringspin(q,string):
            _,x = stringalloc(string)
            q.put(x)
            while True:
                pass

        @TestCase
        def test_windows_remote_consume():
            import multiprocessing,os,ctypes
            q = multiprocessing.Queue()
            string = "hola mundo"

            p = multiprocessing.Process(target=stringspin, args=(q,string,))
            p.start()
            address = q.get()
            print hex(address)

            src = provider.WindowsProcessId(p.pid)
            src.seek(address)
            data = src.consume(len(string))
            p.terminate()
            if data == string:
                raise Success

        @TestCase
        def test_windows_remote_store():
            pass

    except ImportError:
        Log.warning("__module__ : Skipping the `WindowsProcessId` provider tests.")

    testcert="""
    -----BEGIN CERTIFICATE-----
    MIIC+TCCArigAwIBAgIJAOLOwubF5bg3MAkGByqGSM44BAMwNjELMAkGA1UEBhMC
    VVMxDjAMBgNVBAgMBVRleGFzMRcwFQYDVQQKDA50aHVua2Vyc0RPVG5ldDAeFw0x
    NDA5MTAxOTUyMDJaFw0xNDEwMTAxOTUyMDJaMDYxCzAJBgNVBAYTAlVTMQ4wDAYD
    VQQIDAVUZXhhczEXMBUGA1UECgwOdGh1bmtlcnNET1RuZXQwggG3MIIBLAYHKoZI
    zjgEATCCAR8CgYEA9i7VTIaia1b5UljGzdonzMayj6bKmmbXqrw7XQcxagwOiR/w
    HpJbD88h81VII4bQFcIKnlJ9jA8pisffLt9fG2L+9yHA8pB6C192INiloIePf1wK
    lePuWpkAOuZQdA97XIaEwZYXTCvkgozhgp/j9Agcef/IeWaga7CiOCinJw8CFQDp
    DJ0yhfywMk90ZaJVzpMld4FdHwKBgQCpxKWJbU7NUGWRBQY2TPzVuSwKpa+R1ezn
    yiggGHQxb9S6kBKkarsHrmUfcgmmHcsI5ntRYD7ZeRKUgTasQsA3I8NlhmetxdaT
    BKnSdZZAYvRdAxaxRKvMtSwSBGReflSedme0822z+/FNfJG9rMmiBaURNQIpIxb+
    /ecM9MP8fwOBhAACgYA3O9CNln3zUnW8SyUqFovp0AFBFixrZhxRbFsASjk1dDqr
    1GEhE9WGt6cRpLICMQZ80vsrWItc7PpV09OuivkL1oHRpwmeGUA43LV8Wp4FA64F
    EkhbOgBcKlA1aM06bOlJhU26iGuGB4ZTgfyuWtMWFf7LE4bykOa8NOl83yo3FqNQ
    ME4wHQYDVR0OBBYEFJLWL1FUKaTChKV0EgiYCwWzR3O9MB8GA1UdIwQYMBaAFJLW
    L1FUKaTChKV0EgiYCwWzR3O9MAwGA1UdEwQFMAMBAf8wCQYHKoZIzjgEAwMwADAt
    AhUAmftACaObx1+KUcHlzKw+iJI5CE4CFAQLG5nhjAlBzh3nNOMRIs4TDXOb
    -----END CERTIFICATE-----
    """

    @TestCase
    def test_base64_read():
        a = base64(testcert, '-----BEGIN', '-----END')
        a.seek(0)
        if a.consume(4) == '0\x82\x02\xf9':
            raise Success

    @TestCase
    def test_base64_write():
        a = base64(testcert, '-----BEGIN', '-----END')
        a.seek(0)
        a.store('XXXXXX')
        if a.value.startswith('XXXXXX'.encode('base64').strip()):
            raise Success

if __name__ == '__main__' and 0:
    import ptype,parray
    import pstruct,parray,pint,provider

    a = provider.virtual()
    a.available = [0,6]
    a.data = {0:'hello',6:'world'}
    print a.available
    print a.data

    @TestCase
    def test_first():
        if a._find(0) == 0:
            raise Success

    @TestCase
    def test_first_2():
        if a._find(3) == 0:
            raise Success

    @TestCase
    def test_first_3():
        if a._find(4) == 0:
            raise Success

    @TestCase
    def test_hole():
        if a._find(5) == -1:
            raise Success

    @TestCase
    def test_second():
        if a.available[a._find(6)] == 6:
            raise Success
    @TestCase
    def test_second_2():
        if a.available[a._find(9)] == 6:
            raise Success

    @TestCase
    def test_second_3():
        if a.available[a._find(10)] == 6:
            raise Success

    @TestCase
    def test_less():
        if a.find(-1) == -1:
            raise Success

    @TestCase
    def test_tail():
        if a.find(11) == -1:
            raise Success

    @TestCase
    def test_flatten():
        from array import array
        s = lambda x:array('c',x)
        a = provider.virtual()
        a.available = [0,5]
        a.data = {0:s('hello'),5:s('world')}
        a.flatten(0,5)
        if len(a.data[0]) == 10:
            raise Success

    @TestCase
    def test_consume():
        s = lambda x:array.array('c',x)

        global a
        a = provider.virtual()
        a.available = [0, 5, 10, 15, 20]
        a.data = {0:s('hello'),5:s('world'),10:s('55555'),15:s('66666'),20:s('77777')}
        a.seek(17)
        if a.consume(5) == '66677':
            raise Success

if __name__ == '__main__':
    results = []
    for t in TestCaseList:
        results.append( t() )

