#bitmap = (integer, bits)
import __builtin__,sys,six

## start somewhere
def new(value, size):
    '''creates a new bitmap object. Bitmaps "grow" to the left.'''
    if size < 0:
        signmask = 2**(abs(size)-1)
        mask = 2**abs(size)-1
        return (value & mask, size)
    mask = 2**abs(size)-1
    return (value & mask, size)

zero = new(0,0)

def isinteger(v):
    '''Returns true if provided variable is of type int or long'''
    return isinstance(v, six.integer_types)

def isbitmap(v):
    '''Returns true if provided variable is a valid bitmap type (i really shouldn't be keeping track of these)'''
    return isinstance(v, tuple) and len(v) == 2  # and isinteger(v[0]) and isinteger(v[1])

def empty(bitmap):
    '''Returns true if specified bitmap has none of its bits set'''
    integer,size = bitmap
    return not(integer > 0)

import math # glad this is a builtin
def fit(integer):
    '''Returns the number of bits necessary to contain integer'''
    return __builtin__.int(math.log(integer,2))+1

    count = 0
    while integer >= 2:
        count += 1
        integer >>= 1
    return count + 1

def string(bitmap, **kwds):
    '''Returns bitmap as a formatted binary string starting with the least-significant-bits first'''
    reverse = kwds['reversed'] if 'reversed' in kwds else kwds.get('reverse', False)
    integer,size = bitmap
    size = abs(size)
    res = []
    for position in range(size):
        res = res + ['1' if integer&1 else '0']
        integer >>= 1
    return str().join(reversed(res) if reverse else res)

def hex(bitmap):
    '''Return bitmap as a hex string'''
    n,s = bitmap
    size = abs(s)
    length = __builtin__.int(math.ceil(size/4.0))
    if s < 0:
        max,sf = 2**size,2**(size-1)
        n = (n-max) if n&sf else n&(sf-1)
        return '{:s}{:#0{:d}x}'.format('-' if n < 0 else '+', abs(n)&(max-1), length+2)
    return '{:#0{:d}x}'.format(n&(2**size)-1, length+2)

def scan(bitmap, value=True, position=0):
    '''Searches through bitmap for specified /value/ and returns it's position'''
    integer,size = bitmap

    if position < 0 or position > abs(size):
        raise AssertionError("Invalid position : {:d}".format(position))

    size,bitmask = abs(size), 1 << position
    for i in range(size):
        if bool(integer & bitmask) == value or position >= size:
            return position
        bitmask <<= 1
        position += 1
    return position

def runscan(bitmap, value, length, position=0):
    '''Will return the position of a run fulfilling the paramters in /bitmap/'''

    if length >= 0 and position >= 0:
        for run_integer,run_length in run(bitmap, position=position):
            # snag a run that best fits user's reqs
            if bool(run_integer&1) == value and length <= run_length:
                return position
            position += run_length
    raise ValueError('Unable to find a {:s} bit run of {:d} in bitmap'.format(length, value))

def runlength(bitmap, value, position=0):
    '''Returns the count of bits, starting at /position/'''
    integer,size = bitmap
    if position < 0 or position > abs(size):
        raise AssertionError("Invalid position : {:d}".format(position))
    return scan(bitmap, not value, position) - position

def run(bitmap, position=0):
    '''Iterates through all the runs in a given bitmap'''
    integer,size = bitmap
    if position < 0 or position > abs(size):
        raise AssertionError("Invalid position : {:d}".format(position))

    value,size = integer & 1, abs(size)
    while size > 0:
        length = runlength( (integer,size), value, position)
        yield get(bitmap, position, length)
        size -= length
        position += length
        value = not value
    return

def set(bitmap, position, value=True, count=1):
    '''Store /value/ into /bitmap/ starting at /position/'''
    integer,size = bitmap

    if count < 0 or position < 0:
        raise AssertionError("Invalid count or position : {:d} : {:d}".format(count, position))
    if position + count > abs(size):
        raise AssertionError("Attempted to set bits outside bitmap : {:d} + {:d} > {:d}".format(position, count, size))

    mask,size = reduce(lambda r,v: 1<<v | r, range(position, position+count), 0), abs(size)
    if value:
        return (integer | mask, size)
    return (integer & ~mask, size)

def get(bitmap, position, count):
    '''Fetch /count/ number of bits from /bitmap/ starting at /position/'''
    integer,size = bitmap

    if count < 0 or position < 0:
        raise AssertionError("Invalid count or position : {:d} : {:d}".format(count, position))
    if position + count > abs(size):
        raise AssertionError("Attempted to fetch bits outside bitmap : {:d} + {:d} > {:d}".format(position, count, size))

    mask,size = reduce(lambda r,v: 1<<v | r, range(position, position+count), 0), abs(size)
    return ((integer & mask) >> position, count)

def add(bitmap, integer):
    '''Adds an integer to the specified bitmap whilst preserving signedness'''
    n,sz = bitmap
    if sz < 0:
        pass        # XXX: we trust that python handles signedness properly via &
    mask = (1<<abs(sz))-1
    return (integer+n) & mask,sz
def sub(bitmap, integer):
    '''Subtracts an integer to the specified bitmap whilst preserving signedness'''
    n,sz = bitmap
    if sz < 0:
        pass        # XXX: we trust that python handles signedness properly via &
    mask = (1<<abs(sz))-1
    return (n-integer) & mask,sz

def mul(bitmap, integer):
    n,size = bitmap
    max = 2**abs(size)
    if size < 0:
        sf = 2**(abs(size)-1)
        n = (n-max) if n&sf else n&(sf-1)
    return (n*integer)&(max-1),size
def div(bitmap, integer):
    n,size = bitmap
    max = 2**abs(size)
    if size < 0:
        sf = 2**(abs(size)-1)
        n = (n-max) if n&sf else n&(sf-1)
    return __builtin__.int(float(n)/integer)&(max-1),size
def mod(bitmap, integer):
    n,size = bitmap
    max = 2**abs(size)
    if size < 0:
        sf = 2**(abs(size)-1)
        n = (n-max) if n&sf else n&(sf-1)
    return (n%integer) & (max-1),size

def grow(bitmap, count):
    '''Grow bitmap by some specified number of bits

    This treats the bitmap as a set of bits and thus ignores the signed bit.
    '''
    if count < 0:
        return shrink(bitmap, -count)
    integer,size = bitmap
    return (integer << count, size + (count*(1,-1)[size<0]))

def shrink(bitmap, count):
    '''Shrink a bitmap by some specified size

    This treats the bitmap as a set of bits and thus ignores the signed bit.
    '''
    if count < 0:
        return grow(bitmap, -count)
    integer,size = bitmap
    return (integer >> count, size - (count*(1,-1)[size<0]))

## for treating a bitmap like an integer stream
def push(bitmap, operand):
    '''Append bitmap data to the end of the current bitmap

    This treats the bitmap as a set of bits and thus ignores the signed bit.
    '''
    (result, rbits) = bitmap
    (number, nbits) = operand

    rmask = 2**abs(rbits) - 1
    nmask = 2**abs(nbits) - 1

    res = result & rmask
    res <<= abs(nbits)
    res |= number & nmask
    return (res, (rbits - abs(nbits)) if rbits < 0 else (rbits+abs(nbits)))

def insert(bitmap, operand):
    '''Insert bitmap data at the beginning of the bitmap

    This treats the bitmap as a set of bits and thus ignores the signed bit.
    '''
    (result, rbits) = bitmap
    (number, nbits) = operand
    rmask = 2**rbits - 1
    nmask = 2**nbits - 1

    res = number & nmask
    res <<= rbits
    res |= result & rmask
    return (res, nbits+rbits)

def consume(bitmap, bits):
    '''Consume some number of bits off of the end of a bitmap

    If bitmap is signed, then return a signed integer.
    '''
    if bits < 0:
        raise AssertionError('Invalid bit count < 0 : {:d}'.format(bits))

    integersize,integermask = bits,2**bits
    bitmapinteger,bitmapsize = bitmap

    if integersize > abs(bitmapsize):
        integersize = abs(bitmapsize)

    res = bitmapinteger&(integermask-1)
    if bitmapsize < 0:
        signmask = integermask>>1
        if res & signmask:
            res = (res & (signmask-1)) - (integermask>>1)
        else:
            res = res & (signmask-1)
        bitmap = (bitmapinteger>>integersize,(bitmapsize+integersize))
    else:
        bitmap = (bitmapinteger>>integersize,(bitmapsize-integersize))
    return bitmap,res

def shift(bitmap, bits):
    '''Shift some number of bits off of the front of a bitmap

    If bitmap is signed, then return a signed integer.
    '''
    if bits < 0:
        raise AssertionError('Invalid bit count < 0 : {:d}'.format(bits))
    integersize,integermask = bits,2**bits

    bitmapinteger,bitmapsize = bitmap
    if bits > abs(bitmapsize):
        bits = abs(bitmapsize)

    shifty = abs(bitmapsize) - bits
    mask = (integermask-1)<<shifty

    if bitmapsize < 0:
        signmask = integermask>>1
        res = (bitmapinteger & mask)>>shifty
        if res & signmask:
            res = (res & (signmask-1)) - (integermask>>1)
        else:
            res = res & (signmask-1)
        bitmap = (bitmapinteger&~mask, -shifty)
    else:
        res = (bitmapinteger & mask)>>shifty
        bitmap = (bitmapinteger&~mask, shifty)
    return bitmap,res

class consumer(object):
    '''Given an iterable of an ascii string, provide an interface that supplies bits'''
    def __init__(self, iterable=()):
        self.source = iter(iterable)
        self.cache = new(0, 0)

    def insert(self, bitmap):
        self.cache = insert(self.cache, bitmap)
        return self

    def push(self, bitmap):
        self.cache = push(self.cache, bitmap)
        return self

    def read(self, bytes):
        '''Reads the specified number of bytes from iterable'''
        if bytes < 0:
            raise AssertionError('Invalid byte count < 0 : {:d}'.format(bytes))
        result,count = 0,0
        while bytes > 0:
            result *= 256
            result += ord(next(self.source))
            bytes,count = bytes-1,count+1
        self.cache = push(self.cache, new(result, count*8))
        return count

    def consume(self, bits):
        '''Returns some number of bits as an integer'''
        if bits > self.cache[1]:
            count = bits - self.cache[1]
            bs = (count+7)/8
            self.read(bs)
            return self.consume(bits)
        self.cache,result = shift(self.cache, bits)
        return result

    def __repr__(self):
        return ' '.join([str(self.__class__), self.cache.__repr__(), string(self.cache)])

def repr(object):
    integer,size = object
    return "<type 'bitmap'> (0x{:x}, {:d})".format(hex(object),size)

def data(bitmap, reversed=False):
    '''Convert a bitmap to a string left-aligned to 8-bits. Defaults to big-endian.'''
    fn = consume if reversed else shift
    integer,size = bitmap

    # XXX: this is just like splitter...

    l = size % 8
    if l > 0:
        bitmap = insert(bitmap,(0,8-l)) if reversed else push(bitmap,(0,8-l))

    res = []
    while bitmap[1] != 0:
        bitmap,b = fn(bitmap, 8)
        res.append(b)
    return str().join(map(chr,res))

def size(bitmap):
    '''Return the size of the bitmap, ignoring signedness'''
    v,s = bitmap
    return abs(s)
def signed(bitmap):
    '''Returns true if bitmap is signed'''
    integer,size = bitmap
    return size < 0
def cast_signed(bitmap):
    '''Casts a bitmap to a signed integer'''
    integer,size = bitmap
    return (integer,-abs(size))
def cast_unsigned(bitmap):
    '''Casts a bitmap to a unsigned integer'''
    integer,size = bitmap
    return (integer,abs(size))
def value(bitmap):
    '''Return the integral part of a bitmap, handling signedness if necessary'''
    v,s = bitmap
    if s < 0:
        signmask = 2**(abs(s)-1)
        res = v & (signmask-1)
        if v&signmask:
            return (signmask-res)*-1
        return res & (signmask-1)
    return v
int = num = number = value

def weight(bitmap):
    v,s = bitmap
    res,mask = 0, 2**s - 1
    while v > 0:
        res,v = res+1, v & (v - 1)
    return res

def count(bitmap, value=False):
    '''Returns the number of bits that are set to value and returns the count'''
    _,s = bitmap
    res = weight(bitmap)
    return res if value else (s-res)

def splitter(bitmap, maxsize):
    '''Split bitmap into multiple of maxsize bits starting from the low bit.'''

    sf,maxsize = -1 if maxsize < 0 else +1, abs(maxsize)
    while True:
        v,s = bitmap
        if s < maxsize:
            break
        bitmap,v = consume(bitmap,maxsize)
        yield (v,maxsize*sf)

    if s > 0:
        yield (v,s*sf)
    return

def split(bitmap, maxsize):
    '''Returns a list of bitmaps resulting from the bitmap divided by maxsize bits.'''
    return [x for x in splitter(bitmap,maxsize)][::-1]

def join(iterable):
    '''Join a list of bitmaps into a single one'''
    return reduce(push, iterable, (0,0))

import itertools
def groupby(sequence, count):
    '''Group sequence by number of elements'''
    data = enumerate(sequence)
    key = lambda (index,value): index/count
    for _,res in itertools.groupby(data, key):
        yield [v for _,v in res]
    return

# jspelman. he's everywhere.
ror = lambda (v,b),shift=1: ((((v&2**shift-1) << b-shift) | (v>>shift)) & 2**b-1, b)
rol = lambda (v,b),shift=1: (((v << shift) | ((v & ((2**b-1) ^ (2**(b-shift)-1))) >> (b-shift))) & 2**b-1, b)

def reverse(bitmap):
    '''Flip the bit order of the bitmap'''
    res,(_,sz) = (0,0),bitmap
    while size(res) < sz:
        bitmap,value = consume(bitmap, 1)
        res = push(res, (value,1))
    return res

def iterate(bitmap):
    '''Iterate through the bitmap returning True or False for each bit'''
    while size(bitmap) > 0:
        bitmap,value = shift(bitmap, 1)
        yield bool(value)
    return

def riterate(bitmap):
    '''Reverse iterate through the bitmap returning True or False for each bit'''
    while size(bitmap) > 0:
        bitmap,value = consume(bitmap, 1)
        yield bool(value)
    return

if False:
    # are bits clear
    # are bits set
    # check bit
    # clear all bits
    # clear bits
    # find clear bits
    # find clear bits and set
    # find clear runs
    # find first run clear
    # find last backward run clear
    # find longest run clear
    # find next forward run clear
    # find set bits
    # find set bits and clear
    # number of clear bits, number of set bits
    # set all bits, set bits
    pass

if __name__ == '__main__':
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
    import bitmap

    ### set
    @TestCase
    def set_bitmap_signed():
        result = bitmap.new(0, -32)
        freeslot = 0
        count = 3
        result = bitmap.set(result, freeslot, 1, count)
        if bitmap.value(result) == 7:
            raise Success

#    @TestCase
    def set_bitmap_unsigned():
        x = bitmap.new(0xf000000000000000,64)
        #x = bitmap.set(x, 60, count=4)
        print bitmap.string(x)

        y,res = bitmap.shift(x, 4)
        print res,bitmap.string(y)

        x = bitmap.new(0,0)
        x = bitmap.push(x, (0x1,4) )
        x = bitmap.push(x, (0x2,4) )
        x = bitmap.push(x, (0x3,4) )
        x = bitmap.push(x, (0x4,4) )
        print x,bitmap.string(x)

        x = bitmap.new(0,0)
        x = bitmap.insert(x, (0x1,4) )
        x = bitmap.insert(x, (0x2,4) )
        x = bitmap.insert(x, (0x3,4) )
        x = bitmap.insert(x, (0x4,4) )
        print x,bitmap.string(x)

        x = bitmap.consumer('\x12\x34')
        print x.consume(4)
        print x.consume(4)
        print x.consume(4)
        print x.consume(4)

        x = bitmap.new(0, 4)
        for i in range(6):
            print x
            x = bitmap.add(x, 3)

        for i in range(6):
            print x
            x = bitmap.sub(x, 6)

        x = bitmap.new(4,4)
        print bitmap.string(bitmap.ror(bitmap.ror(bitmap.ror(x))))

    ### add
    @TestCase
    def signed_add_positive_wrap():
        x = (255, -8)
        res = bitmap.add(x, 1)
        if res == (0, -8) and bitmap.value(res) == 0:
            raise Success
    @TestCase
    def signed_add_positive_nowrap():
        x = (254, -8)
        res = bitmap.add(x, 1)
        if res == (255, -8) and bitmap.value(res) == -1:
            raise Success
    @TestCase
    def signed_add_negative_wrap():
        x = (254,-8)
        res = bitmap.add(x, 2)
        if res == (0,-8) and bitmap.value(res) == 0:
            raise Success
    @TestCase
    def signed_add_negative_nowrap():
        x = (250,-8)
        res = bitmap.add(x, 5)
        if res == (255,-8) and bitmap.value(res) == -1:
            raise Success

    ### sub
    @TestCase
    def signed_sub_positive_wrap():
        x = (5, -8)
        res = bitmap.sub(x, 10)
        if res == (251, -8) and bitmap.value(res) == -5:
            raise Success
    @TestCase
    def signed_sub_positive_nowrap():
        x = (10, -8)
        res = bitmap.sub(x, 5)
        if res == (5, -8) and bitmap.value(res) == 5:
            raise Success
    @TestCase
    def signed_sub_negative_nowrap():
        x = (156,-8)
        res = bitmap.sub(x, 10)
        if res == (146,-8) and bitmap.value(res) == -110:
            raise Success
    @TestCase
    def signed_sub_negative_wrap():
        x = (133,-8)
        res = bitmap.sub(x, 10)
        if res == (123,-8) and bitmap.value(res) == 123:
            raise Success

    ### grow
    @TestCase
    def grow_unsigned():
        x = (5, 4)
        res = bitmap.grow(x, 4)
        if res == (5*2**4,8) and bitmap.value(res) == 5*2**4:
            raise Success
    @TestCase
    def grow_signed():
        x = (15, -4)
        res = bitmap.grow(x, 4)
        if res == (15*2**4,-8) and bitmap.value(res) == -16:
            raise Success

    ### shrink
    @TestCase
    def shrink_unsigned():
        x = (0x50, 8)
        res = bitmap.shrink(x, 4)
        if res == (5,4) and bitmap.value(res) == 5:
            raise Success
    @TestCase
    def shrink_signed():
        x = (0xff, -8)
        res = bitmap.shrink(x, 4)
        if res == (15,-4) and bitmap.value(res) == -1:
            raise Success

    ### push
    @TestCase
    def push_bitmap_unsigned():
        x = (15,4)
        res = bitmap.push(x, (15,4))
        if res == (0xff,8) and bitmap.value(res) == 255:
            raise Success
    @TestCase
    def push_bitmap_signed():
        x = (15,-4)
        res = bitmap.push(x, (15,4))
        if res == (0xff,-8) and bitmap.value(res) == -1:
            raise Success

    ### consume
    @TestCase
    def consume_unsigned_bitmap_unsigned():
        x = (0x41424344,32)
        res,n = bitmap.consume(x, 8)
        if n == 0x44 and res == (0x414243,24):
            raise Success
    @TestCase
    def consume_signed_bitmap_unsigned():
        x = (0x414243ff,32)
        res,n = bitmap.consume(x, 8)
        if n == 0xff and res == (0x414243,24):
            raise Success
    @TestCase
    def consume_unsigned_bitmap_signed():
        x = (0x41424344,-32)
        res,n = bitmap.consume(x, 8)
        if n == 0x44 and res == (0x414243,-24):
            raise Success
    @TestCase
    def consume_signed_bitmap_signed():
        x = (0x414243ff,-32)
        res,n = bitmap.consume(x, 8)
        if n == -1 and res == (0x414243,-24):
            raise Success
    @TestCase
    def consume_zero_bitmap_unsigned():
        x = (0x41424344,32)
        res,n = bitmap.consume(x, 0)
        if n == 0 and res == x:
            raise Success
    @TestCase
    def consume_zero_bitmap_signed():
        x = (0x41424344,-32)
        res,n = bitmap.consume(x, 0)
        if n == 0 and res == x:
            raise Success
    @TestCase
    def consume_empty_bitmap():
        x = (0,0)
        res,n = bitmap.consume(x, 8)
        if n == 0 and res == x:
            raise Success

    ### shift
    @TestCase
    def shift_unsigned_bitmap_unsigned():
        x = (0x41424344,32)
        res,n = bitmap.shift(x, 8)
        if n == 0x41 and res == (0x424344,24):
            raise Success
    @TestCase
    def shift_signed_bitmap_unsigned():
        x = (0xff424344,32)
        res,n = bitmap.shift(x, 8)
        if n == 0xff and res == (0x424344,24):
            raise Success
    @TestCase
    def shift_unsigned_bitmap_signed():
        x = (0x41424344,-32)
        res,n = bitmap.shift(x, 8)
        if n == 0x41 and res == (0x424344,-24):
            raise Success
    @TestCase
    def shift_signed_bitmap_signed():
        x = (0xff424344,-32)
        res,n = bitmap.shift(x, 8)
        if n == -1 and res == (0x424344,-24):
            raise Success
    @TestCase
    def shift_zero_bitmap_unsigned():
        x = (0x41424344, 32)
        res,n = bitmap.shift(x, 0)
        if n == 0 and res == (0x41424344,32):
            raise Success
    @TestCase
    def shift_zero_bitmap_signed():
        x = (0x41424344, -32)
        res,n = bitmap.shift(x, 0)
        if n == 0 and res == (0x41424344,-32):
            raise Success
    @TestCase
    def shift_empty_bitmap():
        x = (0,0)
        res,n = bitmap.shift(x, 8)
        if n == 0 and res == (0,0):
            raise Success

    ### mul
    @TestCase
    def mul_unsigned_bitmap_unsigned():
        x = (0x40000000,32)
        res = bitmap.mul(x, 4)
        if res == (0,32) and bitmap.value(res) == 0:
            raise Success
    @TestCase
    def mul_unsigned_bitmap_signed():
        x = (0x40000000,32)
        res = bitmap.mul(x, -4)
        if res == (0,32) and bitmap.value(res) == 0:
            raise Success

    #signed_divide(4,4) == 0xc000000000000002L and signed_divide(4,-4) !=
    #signed_divide(-4,4)
    #signed_divide(0xffffffffffffa251, 0x00000000000000c1) == 0xffffffffffffff84
    #signed_divide(0xffffffffffff1634, 0x00000000000000ad) == 0xfffffffffffffea7
    #assert(signed_divide(0x0000000000000004, 0x0000000000000004) == 0x0000000000000001)
    #assert(signed_divide(0xffffffffffffa251, 0x00000000000000c1) == 0xffffffffffffff84)
    #assert(signed_divide(0xffffffffffff1634, 0x00000000000000ad) == 0xfffffffffffffea7)
    #assert(signed_divide(0x8888888800000000, 0x0000000400000000) == 0x0000000022222222)
    #assert(signed_divide(0x0000000000004000, 0x0000000000000004) == 0x0000000000001000)

    ### div
    @TestCase
    def div_unsigned_bitmap_unsigned():
        '''0x10000000 / 0x10 = 0x1000000'''

        x = (0x10000000,32)
        res = bitmap.div(x,0x10)
        if bitmap.value(res) == 0x1000000:
            raise Success
    @TestCase
    def div_unsigned_bitmap_signed():
        '''0x10 / -0x10 = -1'''
        x = (0x10,-32)
        res = bitmap.div(x,-0x10)
        if bitmap.value(res) == -1:
            raise Success
    @TestCase
    def div_signed_bitmap_signed_1():
        x = (0xffffffffffffa251,-64)
        res = bitmap.div(x, 0xc1)
        if bitmap.value(res) == -124:
            raise Success
    @TestCase
    def div_signed_bitmap_signed_2():
        x = (0xffffffffffff1634,-64)
        res = bitmap.div(x, 0xad)
        if bitmap.value(res) == -345:
            raise Success

    @TestCase
    def div_signed_bitmap_unsigned():
        '''-0x10/-0x10 = 1'''
        x = (0xfffffffffffffff0,-64)
        res = bitmap.div(x, -0x10)
        if bitmap.value(res) == 1:
            raise Success

    ### mod
    @TestCase
    def mod_unsigned_bitmap_unsigned():
        '''23983 % 5 == 3'''
        mask=2**64-1
        x = (23983&mask,64)
        res = bitmap.mod(x, 5)
        if bitmap.value(res) == 3:
            raise Success
    @TestCase
    def mod_unsigned_bitmap_signed():
        '''23983 % -5 == -2'''
        mask=2**64-1
        x = (23983&mask,-64)
        res = bitmap.mod(x, -5)
        if bitmap.signed(res) and bitmap.value(res) == -2:
            raise Success
    @TestCase
    def mod_signed_bitmap_unsigned():
        '''-23983 % -5 == 2'''
        mask=2**64-1
        x = (-23983&mask,64)
        res = bitmap.mod(x, -5)
        if bitmap.value(res) == 0xfffffffffffffffe:
            raise Success

    @TestCase
    def mod_signed_bitmap_signed():
        '''-23983 % -5 == -3'''
        mask=2**64-1
        x = (-23983&mask,-64)
        res = bitmap.mod(x, -5)
        if bitmap.signed(res) and bitmap.value(res) == -3:
            raise Success

if __name__ == '__main__':
    results = []
    for t in TestCaseList:
        results.append( t() )

