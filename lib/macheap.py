# blankwall, hereby disclaims all copyright interest in the program Macheap (which deconstructs OSX heap) written by Tyler Bohan.
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with this program. If not, see https://www.gnu.org/licenses/.

import sys,math,logging,six
import functools,operator,itertools
import string
import ptypes
from ptypes import bitmap
from ptypes import *

# some specific configurations
ptypes.Config.pstruct.use_offset_on_duplicate = True
ptypes.Config.ptype.clone_name = '{}'
ptypes.Config.pint.littleendian_name = '{}'
ptypes.Config.pint.bigendian_name = 'be({})'
ptypes.Config.pbinary.littleendian_name = '{}'
ptypes.Config.pbinary.bigendian_name = 'be({})'
ptypes.setbyteorder(ptypes.config.byteorder.littleendian)

### definitions
__LP64__ = True     # some define
LARGEMEM = False    # based on some sysctl

LARGE_ENTRY_CACHE_SIZE = 16
PAGE_MAX_SHIFT = 12     # 14?
PAGE_MAX_SIZE = 1<<PAGE_MAX_SHIFT
CACHE_LINE = 32
TINY_MAX_MAGAZINES = 32
TINY_CACHE = True

SHIFT_TINY_QUANTUM = 4
SHIFT_SMALL_QUANTUM = SHIFT_TINY_QUANTUM+5

### atomic types
class unsigned(pint.uint32_t): pass
class integer(pint.sint32_t): pass
class unsigned_short(pint.uint16_t): pass
class unsigned_long(pint.uint.get(ptypes.Config.integer.size)): pass
class long(pint.sint.get(ptypes.Config.integer.size)): pass
class size_t(pint.uint.get(ptypes.Config.integer.size)): pass
class voidstar(dyn.pointer(ptype.undefined)): pass

class uintptr_t(ptype.pointer_t): pass
class funcptr_t(dyn.pointer(ptype.undefined)): pass
class os_lock_handoff_s(uintptr_t): pass
class os_lock_spin_s(uintptr_t): pass

## utility types
class fpointer_t(ptype.opointer_t):
    _path_ = ()
    @ptypes.utils.memoize('offset', self=lambda s:(s._path_,s._object_,s.QUANTUM)) 
    def _calculate_(self, offset):
        res = self.new(self._object_).a
        res = reduce(operator.__getitem__, self._path_, res)
        return offset - res.getoffset()
    def classname(self):
        return '{:s}({:s}{:s})'.format(self.typename(), self._object_.typename(), ', {!r}'.format(self._path_) if self._path_ else '')
def fpointer(type, fieldname):
    return dyn.clone(fpointer_t, _object_=type, _path_=tuple(fieldname) if hasattr(fieldname, '__iter__') else (fieldname,))

class _malloc_lock_s(pstruct.type):
    _fields_ = [
        (os_lock_spin_s, 'osl_type'),
        (os_lock_handoff_s, '_osl_handoff_opaque'),
    ]

class vm_offset_t(uintptr_t): pass
class vm_address_t(vm_offset_t): pass
class vm_size_t(uintptr_t): pass
class boolean_t(pint.uint32_t): pass
class mag_index_t(integer): pass
class msize_t(unsigned_short): pass

class vm_range_t(pstruct.type):
    _fields_ = [
        (vm_address_t, 'address'),
        (vm_size_t, 'size'),
    ]
    def summary(self, **options):
        return 'address=0x{:x} size=0x{:x}'.format(self['address'].int(), self['size'].int())

class ptr_union(ptype.pointer_t):
    def classname(self):
        return '{:s}<{:s}>'.format(self.typename(), self._object_.typename() if isinstance(self._object_,type) else self._object_.__name__)

    def decode(self, object, **kwds):
        szone,pu = self.getparent(szone_t),object.get()
        cookie = szone['cookie'].li.int()

        t = bitmap.new(pu, object.size()*8)
        t = bitmap.rol(t, 4)
        ptr = bitmap.number(t) & ~0xf
        cs = ptr ^ cookie

        if bitmap.number(t)&0xf != self.generate_checksum(cs):
            logging.warn("{:s}.ptr_union.decode : Checksum doesn't match with cookie 0x{:x} : 0x{:x} != 0x{:x}".format(__name__, cookie, bitmap.number(t)&0xf, self.generate_checksum(cs)))

        res = object.copy().set(ptr)
        return super(ptr_union,self).decode(res, **kwds)

    def encode(self, object, **kwds):
        szone,pu = self.getparent(szone_t),object.get()
        cookie = szone['cookie'].li.int()

        csum = self.generate_checksum(pu^cookie)

        t = bitmap.new(pu, object.size()*8)
        t = bitmap.rol(t, 4)

        cs = bitmap.new(bitmap.number(t)|csum, bitmap.size(t))
        cs = bitmap.ror(cs, 4)

        logging.info("{:s}.ptr_union.encode : Encoded pointer 0x{:x} with 0x{:x} results in checksum 0x{:x} : {:s}".format(__name__, pu, cookie, csum, bitmap.hex(cs)))

        res = object.copy().set(bitmap.number(cs))
        return super(ptr_union,self).encode(res, **kwds)

    def generate_checksum(self, ptr):
        pu = bitmap.new(ptr, self.size()*8)
        res = reduce(bitmap.add, map(bitmap.number,bitmap.split(pu,8)), bitmap.new(0,8))
        return bitmap.number(res) & 0xf

    def get_checksum(self):
        '''Returns the encoded checksum for the ptr_union'''
        pu = self.int()
        t = bitmap.new(pu, self.size()*8)
        t = bitmap.rol(t, 4)
        return bitmap.number(t) & 0xf

    def get_pointer(self):
        '''Returns the encoded pointer'''
        res = bitmap.new(self.int(), self.size()*8)
        res = bitmap.rol(res, 4)
        res = bitmap.number(res) & ~0xf
        return res
        
    def summary(self):
        szone = self.getparent(szone_t)
        cookie = szone['cookie'].li.int()

        pointer,checksum = self.get_pointer(),self.get_checksum()
        real_checksum = self.generate_checksum(pointer^cookie)
        return '{:s} (pointer=0x{:x} checksum={:x})'.format(super(ptr_union,self).summary(), pointer, checksum) + (' invalid (should be 0x{:x})'.format(real_checksum) if real_checksum != checksum else '')

class list_t(pstruct.type):
    _path_ = ()
    _fields_ = [
        (lambda s: s._object_, 'previous'),
        (lambda s: s._object_, 'next'),
    ]
    def classname(self):
        object = self._object_
        if isinstance(object, ptype.pointer_t):
            res = object._object_
            return '{:s}<{:s}>'.format(super(list_t,self).classname(), res.typename())
        return super(list_t,self).classname()

    def summary(self):
        return '<->'.join(('previous:0x{:x}'.format(self['previous'].int()), 'next:0x{:x}'.format(self['next'].int())))

    def next(self):
        '''Follow the next pointer to the next header entry.'''
        if self['next'].int():
            return reduce(operator.__getitem__, self._path_, self['next'].d.l)
        raise ValueError("{:s} : Unable to navigate to next pointer : 0x{:x}".format(self['next'].int()))
    def previous(self):
        '''Follow the previous pointer to the previous header entry.'''
        if self['previous'].int():
            return reduce(operator.__getitem__, self._path_, self['previous'].d.l)
        raise ValueError("{:s} : Unable to navigate to previous pointer : 0x{:x}".format(self['previous'].int()))

    def _walk(self, direction):
        '''Yield all the elements in the specified direction.'''
        yield self
        res = direction(self)
        while res.int():
            res = res.d
            res = reduce(operator.__getitem__, self._path_, res.l)
            yield res
            res = direction(res)
        return

    # FIXME: make sure that these return each and every header
    def moonwalk(self):
        for n in self._walk(operator.itemgetter('previous')): yield n
    def walk(self):
        for n in self._walk(operator.itemgetter('next')): yield n

list_t._object_ = dyn.pointer(list_t)

class chunk(ptype.generic):
    def region(self):
        blocks = {SHIFT_TINY_QUANTUM : 64520, SHIFT_SMALL_QUANTUM : 16320}
        shift = int(math.log(self.QUANTUM)/math.log(2))

        num_blocks = blocks[shift]
        ceil_shift = int(math.ceil(math.log(num_blocks)/math.log(2)))
        align = 1 << ((ceil_shift+shift)-1)

        ptr = self.getoffset()
        return self.new(region_t, offset=ptr & ~align)

class free_chunk(pstruct.type, chunk):
    def _block(self):
        msize = self['size'].li.int() + 1
        bs = msize * self.QUANTUM
        sz = self['header'].li.size() + self['size'].size()*2
        return dyn.block(0 if sz > bs else bs - sz)

    def next(self):
        return self['header']['next'].d.l
    def previous(self):
        return self['header']['previous'].d.l

    def walk(self):
        for n in self['header'].walk():
            for p in self['header']._path_: n = n.p
            yield n
        return
    def moonwalk(self):
        for n in self['header'].moonwalk():
            for p in self['header']._path_: n = n.p
            yield n
        return

free_chunk._fields_ = [
        (dyn.clone(list_t, _object_=dyn.clone(ptr_union,_object_=free_chunk), _path_=('header',)), 'header'),
        (msize_t, 'size'),
        (lambda s: s._block(), 'block'),
        (msize_t, 'end_size'),
    ]

class free_list_t(parray.type):
    _object_ = dyn.pointer(free_chunk)

    def quantum(self, max=None):
        '''Return the number of quanta that is taken up by the free-list'''
        szone, shift = self.getparent(szone_t), int(math.log(self.QUANTUM)/math.log(2))
        # FIXME: check that this is correct for small quanta
        # 63 * TINY_QUANTUM = 1008, 254 * SMALL_QUANTUM = large_threshold
        maxlookup = { SHIFT_TINY_QUANTUM : 63, SHIFT_SMALL_QUANTUM : szone['large_threshold'].int() >> SHIFT_SMALL_QUANTUM }
        max = maxlookup[shift] if max is None else max
        return sum(((i+1) * len(list(e.d.l.walk()))) for i,e in self.enumerate() if i < max)

    def dump(self):
        res = []
        for index, entry in self.enumerate():
            msize = index + 1
            entry = entry.d
            try: entry = entry.l
            except ptypes.error.LoadError:
                res.append('[{:d}] ?0x{:x}'.format(msize, entry.getoffset()))
                continue
            res.append("[{:d}] {:s}".format(msize, " <--> ".join('0x{:x}'.format(n.getoffset()) for n in entry.walk())))
        return '\n'.join(res)

    def enumerate(self):
        for i,val in enumerate(self):
            if val.int(): yield i,val
        return

    def slot(self, size):
        shift = int(math.log(self.QUANTUM) / math.log(2))
        msize = (size + self.QUANTUM - 1) >> shift
        return self[msize]

### region
class tiny_header_inuse_pair_t(pstruct.type):
    class __uint32_t(pint.uint32_t):
        def bitmap(self):
            return bitmap.new(self.int(), self.size()*8)
        def summary(self):
            res = self.bitmap()
            align = ' ' if self.name() == 'inuse' else ''
            return align+'0x{:0{:d}x} bitmap:{:s}'.format(self.int(), self.size()*2, bitmap.string(res))

    _fields_ = [
        (__uint32_t, 'header'),
        (__uint32_t, 'inuse'),
    ]

    def header(self): return self['header'].bitmap()
    def inuse(self): return self['inuse'].bitmap()

class tiny_meta_data(parray.type):
    _object_ = tiny_header_inuse_pair_t

    def classname(self):
        return '{:s}[{:d}]'.format(super(tiny_meta_data,self).classname(), len(self))

    def __item_aggregate(self, field):
        res = (n[field] for n in self)
        res = map(operator.methodcaller('bitmap'), res)
        return reduce(bitmap.insert, res, bitmap.zero)
    def header(self): return self.__item_aggregate('header')
    def inuse(self): return self.__item_aggregate('inuse')

    def __check_header(self, index):
        header = self.header()
        headerQ = bitmap.int(bitmap.get(header, index, 1))
        if headerQ == 0:
            raise ValueError('index {:d} is not a header'.format(index))
        return index

    def freeQ(self, index):
        '''Returns whether the chunk at the specified index is free'''
        index = self.__check_header(index)
        inuse = self.inuse()
        freeQ = bitmap.int(bitmap.get(inuse, index, 1))
        return bool(freeQ == 0)
    def busyQ(self, index):
        return not self.freeQ(index)
    def msizeQ(self, index):
        index = self.__check_header(index)
        res = self.header()
        return bitmap.runlength(res, 0, index+1) + 1

    def enumerate(self):
        index, res = 0, self.header()
        while bitmap.size(res) > 1:
            # check to see if the msize moves us to a header bit that's unset
            if bitmap.int(bitmap.get(res, 0, 1))  == 0:
                fixup = bitmap.runlength(res, 0, 0)
                logging.warn('Index {:d} of header is not set. Possibly corrupt? Forced to consume {:d} bits.'.format(index, fixup))
                res, _ = bitmap.consume(res, fixup)
                if bitmap.size(res) == 0: break

            # search for how long this run is
            msize = bitmap.runlength(res, 0, 1) + 1
            yield index, msize

            # consume msize bits
            index += msize
            res, _ = bitmap.consume(res, msize)
        return

    def used(self):
        m, res = self.getparent(magazine_t), self.header()
        index = m['mag_bytes_free_at_start'].int() / self.QUANTUM
        sentinel = (m['num_bytes_in_magazine'].int() - m['mag_bytes_free_at_end'].int()) / self.QUANTUM
        while index <= sentinel:
            # check to see if the msize moves us to a header bit that's unset
            if bitmap.int(bitmap.get(res, 0, 1))  == 0:
                fixup = bitmap.runlength(res, 0, 0)
                logging.warn('Index {:d} of header is not set. Possibly corrupt? Forced to consume {:d} bits.'.format(index, fixup))
                res, _ = bitmap.consume(res, fixup)
                if bitmap.size(res) == 0: break

            # search for how long this run is
            msize = bitmap.runlength(res, 0, 1) + 1
            yield index, msize

            # consume msize bits
            index += msize
            res, _ = bitmap.consume(res, msize)
        return

    def busyfree(self):
        inuse = self.inuse()
        for index, msize in self.used():
            res = bitmap.get(inuse, index, 1)
            yield index, msize, bool(bitmap.int(res))
        return
    def free(self):
        for index, msize, busy in self.busyfree():
            if not busy: yield index, msize
        return
    def busy(self):
        for index, msize, busy in self.busyfree():
            if busy: yield index, msize
        return

    def get(self, index):
        return (index / 32, index % 32)

    # FIXME
    def summary(self):
        m, r = self.getparent(magazine_t), self.getparent(region_t)

        end = m['num_bytes_in_magazine'].int() - m['mag_bytes_free_at_end'].int()
        start = m['mag_bytes_free_at_start'].int()
        used = (end - start)

        busyc,freec = 0,0
        least,most = 0,0
        units = 0
        for index, msize, busy in self.busyfree():
            if busy: busyc += 1
            else: freec += 1
            least, most = min((msize, least or msize)), max((msize, most))
            units += msize
        return 'units={:d}(+{:d}) total={:d} free={:d} busy={:d} smallest={:d}(+{:d}) largest={:d}(+{:d})'.format(units, used, freec+busyc, freec, busyc, least, least*self.QUANTUM, most, most*self.QUANTUM)

class small_meta_data(parray.type):
    class _object_(msize_t):
        # FIXME: small_free_no_lock
        def msizeQ(self):
            return self.int() & 0x7fff
        def freeQ(self):
            return bool(self.int() & 0x8000)
        def busyQ(self):
            return not self.freeQ()
        isfree = property(fget=freeQ)
        isbusy = property(fget=busyQ)
        def summary(self):
            index, msize = int(self.__name__),self.msizeQ()
            p = self.getparent(region_t)['blocks'][index]
            return 'blockindex={:d} msize={:d} address=0x{:x}:+0x{size:x}({size:d})'.format(index, msize, p.getoffset(), size=msize*self.QUANTUM) + (' isfree' if self.freeQ() else '')

    def freeQ(self, index):
        return self[index].freeQ()
    def busyQ(self, index):
        return self[index].busyQ()
    def msizeQ(self, index):
        return self[index].msizeQ()

    def get(self, index):
        return self[index]

    def used(self):
        m = self.getparent(magazine_t)
        sentinel = (m['num_bytes_in_magazine'].int() - m['mag_bytes_free_at_end'].int()) / self.QUANTUM

        index, msize = m['mag_bytes_free_at_start'].int() / self.QUANTUM, 0
        while index + msize <= sentinel:
            msize = self[index].msizeQ()
            yield index, msize
            index += msize
        return
    def enumerate(self):
        index = 0
        while index < len(self):
            msize = self[index].msizeQ()
            yield index, msize
            index += msize
        return

    def busyfree(self):
        for index, msize in self.used():
            yield index, msize, self[index].busyQ()
        return

    def free(self):
        for index, msize, busy in self.busyfree():
            if not busy: yield index, msize
        return
    def busy(self):
        for index, msize, busy in self.busyfree():
            if busy: yield index, msize
        return

    def summary(self):
        m, r = self.getparent(magazine_t), self.getparent(region_t)

        end = m['num_bytes_in_magazine'].int() - m['mag_bytes_free_at_end'].int()
        start = m['mag_bytes_free_at_start'].int()
        used = (end - start)

        busyc,freec = 0,0
        least,most = 0,0
        units = 0
        for index,msize in self.used():
            if self[index].freeQ(): freec += 1
            else: busyc += 1
            least,most = min((msize, least or msize)), max((msize, most))
            units += msize
        # FIXME: calculate fragmentation and average size
        return 'units={:d}(+{:d}) total={:d} free={:d} busy={:d} smallest={:d}(+{:d}) largest={:d}(+{:d})'.format(units, used, freec+busyc, freec, busyc, least, least*self.QUANTUM, most, most*self.QUANTUM)

class region_trailer_t(pstruct.type):
    def iterate(self):
        yield n
        for n in self['entry'].walk():
            yield n
        return

#    def region(self):
#        blocks = {SHIFT_TINY_QUANTUM : 64520, SHIFT_SMALL_QUANTUM : 16320}
#        shift = int(math.log(self.QUANTUM)/math.log(2))
#        ptr = self.getoffset() - (blocks[shift]*self.QUANTUM)
#        return self.new(region_t, offset=ptr)

    _fields_ = [
        (lambda s: dyn.clone(list_t,_object_=fpointer(region_t,'trailer')), 'entry'),
        (boolean_t, 'recirc_suitable'),
        (integer, 'pinned_to_depot'),
        (unsigned, 'bytes_used'),
        (mag_index_t, 'mag_index'),
    ]

    def summary(self):
        recirc,pinned,used,mag = (self[n].int() for n in ('recirc_suitable','pinned_to_depot','bytes_used','mag_index'))
        return 'entry={{{:s}}} recirc_suitable={:d} pinned_to_depot={:d} bytes_used={:x}({:d}) mag_index={:d}'.format(self['entry'].summary(), recirc, pinned, used, used, mag)

# tiny_region  = 0x100000
# small_region = 0x800000
class region_t(pstruct.type):
    def __blocks(self):
        shift = int(math.log(self.QUANTUM)/math.log(2))

        blocks = {SHIFT_TINY_QUANTUM : 64520, SHIFT_SMALL_QUANTUM : 16320}
        t = dyn.block(self.QUANTUM)
        return dyn.array(t, blocks[shift])

    def __meta(self):
        roundup = lambda n,s: (n+(s-1)) & ~(s-1)

        shift = int(math.log(self.QUANTUM)/math.log(2))
        blocks = self['blocks'].length

        # figure out the number of blocks we can fit in a tiny_meta_data._object_
        t,_ = tiny_meta_data._object_._fields_[0]
        res = t().a.size() * 8

        meta = {
            SHIFT_TINY_QUANTUM : dyn.clone(tiny_meta_data, length=roundup(blocks, res) / res),
            SHIFT_SMALL_QUANTUM : dyn.clone(small_meta_data, length=blocks)
        }
        return meta[shift]
        
    _fields_ = [
        (__blocks, 'blocks'),
        (region_trailer_t, 'trailer'),
        (__meta, 'metadata'),
        (dyn.align(1<<12), 'pad'),
    ]

    def properties(self):
        res = super(region_t,self).properties()
        shift = int(math.log(self.QUANTUM)/math.log(2))

        type = {SHIFT_TINY_QUANTUM : 'tiny', SHIFT_SMALL_QUANTUM : 'small'}
        res['region_size'] = type[shift]
        return res

    def msizeQ(self, index):
        return self['metadata'].msizeQ(index)
    def freeQ(self, index):
        return self['metadata'].freeQ(index)
    def busyQ(self, index):
        return self['metadata'].busyQ(index)
    def blockQ(self, index):
        msize = self['metadata'].msizeQ(index)
        return self['blocks'][index : index + msize]

    def blocks(self):
        for index, msize in self['metadata'].enumerate():
            yield self['blocks'][index : index + msize]
        return

    def free(self):
        for index, msize in self['metadata'].used():
            yield self['blocks'][index : index + msize]
        return

    def free(self):
        for index, msize in self['metadata'].free():
            yield self['blocks'][index : index + msize]
        return

    def busy(self):
        for index, msize in self['metadata'].busy():
            yield self['blocks'][index : index + msize]
        return

    def bitmap(self):
        res = bitmap.zero
        for index, msize, busy in self['metadata'].busyfree():
            val = bitmap.new((2**msize - 1) if busy else 0, msize)
            res = bitmap.insert(res, val)
        return res

class region_hash_generation_t(pstruct.type):
    def iterate(self):
        start = self
        yield self
        while self['nextgen'].int() != start:
            self = self['nextgen'].d.l
            yield self
        return

    class _hashed_regions(parray.type):
        _object_ = dyn.pointer(region_t)

        def enumerate(self):
            for i,n in enumerate(self):
                if n.int(): yield i,n
            return
        def iterate(self):
            for _, n in self.enumerate(): yield n

# FIXME: figure out 'hashed_regions' and whether it's really a pointer to an array of them
region_hash_generation_t._fields_ = [
    (size_t, 'num_regions_allocated'),
    (size_t, 'num_regions_allocated_shift'),
    (lambda s: dyn.pointer(dyn.clone(s._hashed_regions,length=s['num_regions_allocated'].li.int())), 'hashed_regions'),
    (dyn.pointer(region_hash_generation_t), 'nextgen'),
]

### large region
class large_entry_t(pstruct.type):
    _fields_ = [
        (dyn.pointer(lambda s: dyn.block(s.getparent(large_entry_t)['size'].li.int())), 'address'),
        (vm_size_t, 'size'),
        (boolean_t, 'did_madvise_reusable'),
        (dyn.block(4), 'padding(did_madvise_reusable)'),
    ]

    def valid(self):
        return bool(self['address'].int())

    def summary(self, **options):
        return 'address=0x{:x} size=0x{:x} did_madvise_reusable={:s}'.format(self['address'].int(), self['size'].int(), 'true' if self['did_madvise_reusable'].li.int() else 'false')

### major structures
class malloc_introspection_t(pstruct.type):
    _fields_ = [
        (funcptr_t, 'enumerator'),
        (funcptr_t, 'good_size'),
        (funcptr_t, 'check'),
        (funcptr_t, 'print'),
        (funcptr_t, 'log'),
        (funcptr_t, 'force_lock'),
        (funcptr_t, 'force_unlock'),
        (funcptr_t, 'statistics'),
        (funcptr_t, 'zone_locked'),
    ]
class zone_type(ptype.definition):
    attribute, cache = 'version', {}

    class unknown(ptype.block): pass
    
class malloc_zone_t(pstruct.type):
    _fields_ = [
        (voidstar, 'reserved1'),
        (voidstar, 'reserved2'),
        (funcptr_t, 'size'),
        (funcptr_t, 'malloc'),
        (funcptr_t, 'calloc'),
        (funcptr_t, 'valloc'),
        (funcptr_t, 'free'),
        (funcptr_t, 'realloc'),
        (funcptr_t, 'destroy'),
        (dyn.pointer(pstr.szstring), 'zone_name'),

        (funcptr_t, 'batch_malloc'),
        (funcptr_t, 'batch_free'),

        (dyn.pointer(malloc_introspection_t), 'introspect'),
        (unsigned, 'version'),
        (dyn.block(4), 'padding(version)'),

        (funcptr_t, 'memalign'),
        (funcptr_t, 'free_definite_size'),
        (funcptr_t, 'pressure_relief'),
    ]

    def version(self):
        return self['version'].int()

    def zone_name(self):
        return self['zone_name'].d.l.str() if self['zone_name'].int() else None

    def summary(self, **optoins):
        name, version = self.zone_name(), self.version()
        return 'name={!r} version={:d} reserved1=0x{:x} reserved2=0x{:x} ...'.format(name, version, self['reserved1'].int(), self['reserved2'].int())

class zone_t(pstruct.type):
    _fields_ = [
        (malloc_zone_t, 'basic_zone'),
        (lambda s: dyn.block(PAGE_MAX_SIZE-s['basic_zone'].li.size()), 'pad'),
        (lambda s: zone_type.get(s['basic_zone'].li['version'].int()), 'complex_zone'),
    ]

    def basic(self): return self['basic_zone']
    def zone(self): return self['complex_zone']
    def version(self): return self.basic().version()
    def zone_name(self): return self.basic().zone_name()

class magazine_t(pstruct.type):
    class _mag_bitmap(parray.type):
        class _object_(unsigned):
            def bitmap(self):
                return bitmap.new(self.int(), self.size()*8)
            def summary(self):
                res = self.bitmap()
                return '0x{:0{:d}x} bitmap:{:s}'.format(self.int(), self.size()*2, bitmap.string(res))
        length = 256 / (_object_().a.size()*8)

        def bitmap(self):
            res = map(operator.methodcaller('bitmap'), self)
            return reduce(bitmap.insert, res, bitmap.zero)

        def get(self, index):
            res, = (n for i,n in enumerate(self.iterate()) if i == index)
            return int(res)

        def iterate(self):
            res = self.bitmap()
            while bitmap.size(res) > 0:
                res, val = bitmap.consume(res, 1)
                yield val
            return

        def enumerate(self):
            fl = self.getparent(magazine_t)['mag_free_list']
            for i,ok in enumerate(self.iterate()):
                if not ok: continue
                yield i, fl[i]
            return

        def summary(self):
            mapper = ['.', 'X']
            return str().join(map(mapper.__getitem__, self.iterate()))
        def repr(self): return self.summary()

    class _mag_free_list(free_list_t):
        length = 256

    class _mag_last_free(ptype.opointer_t):
        def _calculate_(self, offset):
            return offset & ~(self.QUANTUM-1)

        def match(self, size):
            '''Returns true if this 'mag_last_free' entry matches the specified size'''
            shift = int(math.log(self.QUANTUM)/math.log(2))
            res = (size + self.QUANTUM - 1) >> shift
            return res == self.msize()

        def _object_(self):
            msize = self.msize()
            shift = int(math.log(self.QUANTUM) / math.log(2))
            return dyn.block(msize << shift)

        def msize(self):
            return self.int() & (self.QUANTUM-1)

        def pointer(self):
            return self._calculate_(self.int())

        def summary(self):
            return '*0x{:x} msize={:d}(+{:d})'.format(self.pointer(), self.msize(), self.msize() * self.QUANTUM)
        def details(self):
            res = super(self.__class__, self).summary()
            p, msize = self.pointer(), self.msize()
            return '{:s} -> 0x{:x}:+{:d} (msize={:d})'.format(res, p, msize*self.QUANTUM, msize)
        def repr(self): return self.details()

    _fields_ = [
        (_malloc_lock_s, 'magazine_lock'),
        (boolean_t, 'alloc_underway'),
        (dyn.block(4), 'padding(alloc_underway)'),

        (_mag_last_free, 'mag_last_free'),
        (dyn.pointer(region_t), 'mag_last_free_rgn'),

        (_mag_free_list, 'mag_free_list'),   # FIXME: make this an explicit type
        (_mag_bitmap, 'mag_bitmap'),

        (size_t, 'mag_bytes_free_at_end'),
        (size_t, 'mag_bytes_free_at_start'),
        (dyn.pointer(region_t), 'mag_last_region'),

        (size_t, 'mag_num_objects'),
        (size_t, 'mag_num_bytes_in_objects'),
        (size_t, 'num_bytes_in_magazine'),

        (unsigned, 'recirculation_entries'),
        (dyn.block(4), 'padding(recirculation_entries)'),
        (fpointer(region_t, 'trailer'), 'firstNode'),
        (fpointer(region_t, 'trailer'), 'lastNode'),

        (lambda s: dyn.array(uintptr_t, 50 - CACHE_LINE/uintptr_t().a.size()), 'pad'),
    ]

    def properties(self):
        res = super(self.__class__,self).properties()
        shift = int(math.log(self.QUANTUM)/math.log(2))

        type = {SHIFT_TINY_QUANTUM : 'tiny', SHIFT_SMALL_QUANTUM : 'small'}
        res['magazine_size'] = type[shift]
        return res

    def slot(self, size):
        return self['mag_free_list'].slot(size)

    def dump(self):
        return self['mag_free_list'].dump()
    get_free_slot = freeslot = slot

class magazine_array(parray.type):
    _object_ = magazine_t

    def core(self, _os_cpu_number=None):
        # FIXME: core is determined by the result of the following:
        #        sidt (ptr); (uint32_t)(*ptr) & 0x1f
        core = (0 if _os_cpu_number is None else _os_cpu_number) & 0x1f
        index = core & (TINY_MAX_MAGAZINES-1)
        return self[index]

class large_entry_array(parray.type):
    _object_ = large_entry_t

    def details(self):
        res = ((n['address'].int(),n['size'].int()) for n in self)
        return ', '.join('0x{:x}:+0x{:x}'.format(a,s) for a,s in res)

    def repr(self): return self.details()

@zone_type.define
class szone_t(pstruct.type):
    version = 8
    class _debug_flags(pbinary.flags):
        _fields_ = [
            (1, 'CHECK_REGION'),
            (1, 'DISABLE_ASLR'),
            (23, 'RESERVED'),
            (1, 'ABORT_ON_CORRUPTION'),
            (1, 'PURGEABLE'),
            (1, 'ABORT_ON_ERROR'),
            (1, 'DO_SCRIBBLE'),
            (1, 'DONT_PROTECT_POSTLUDE'),
            (1, 'DONT_PROTECT_PRELUDE'),
            (1, 'ADD_GUARD_PAGES'),
        ]
    class _region_ptr_array(parray.type):
        _object_ = dyn.pointer(region_t)

        def enumerate(self):
            for i,n in enumerate(self):
                if n.int(): yield i,n
            return
        def iterate(self):
            for _, n in self.enumerate(): yield n

    class _large_entries(ptype.pointer_t):
        _object_ = large_entry_array
        def summary(self):
            res = self.d.l
            return 'length={:d} total=0x{:x}'.format(len(res), sum(x['size'].int() for x in res))

    class _large_entry_cache(parray.type):
        _object_ = large_entry_t
        def enumerate(self):
            for i,n in enumerate(self):
                if n.valid(): yield i, n.d.l
            return
        def iterate(self):
            for _, n in self.enumerate(): yield n

    def mag(self, key):
        """Return the correct magazine based on the type of mag:
            int -> allocation size
            str -> 't' for tiny, 's' for small, 'l' for large
        """

        if isinstance(key, six.integer_types):
            field = ('large_entries',)
            fields = (('tiny_magazines',63*self['tiny_magazines'].QUANTUM), ('small_magazines', self['large_threshold'].li.int()))
            for f,sz in fields:
                if key < sz:
                    field = f
                    break
                continue

        elif isinstance(key, basestring):
            lookup = {'t':'tiny_magazines', 's':'small_magazines', 'l':'large_entries'}
            field = lookup[key]

        else:
            raise TypeError(key)

        return self[field].d.l

szone_t._fields_ = [
    (unsigned_long, 'cpu_id_key'),
    (szone_t._debug_flags, 'debug_flags'),
    (dyn.block(4), 'padding(debug_flags)'),
    (voidstar, 'log_address'),

    (dyn.block(0x68), 'reserved_1018'),

    (_malloc_lock_s, 'tiny_regions_lock'),
    (size_t, 'num_tiny_regions'),
    (size_t, 'num_tiny_regions_dealloc'),
    (lambda s: dyn.pointer(region_hash_generation_t, recurse={'QUANTUM':1<<SHIFT_TINY_QUANTUM}), 'tiny_region_generation'),
    (lambda s: dyn.array(dyn.clone(region_hash_generation_t, recurse={'QUANTUM':1<<SHIFT_TINY_QUANTUM}),2), 'trg'),
    (integer, 'num_tiny_magazines'),    # note: max of 0x1f
    (unsigned, 'num_tiny_magazines_mask'),
    (size_t, 'num_tiny_magazines_mask_shift'),
    (lambda s: dyn.opointer(dyn.clone(magazine_array,length=s['num_tiny_magazines'].li.int()+1), lambda _,o:o-magazine_t().a.size(), recurse={'QUANTUM':1<<SHIFT_TINY_QUANTUM}), 'tiny_magazines'),
    (uintptr_t, 'last_tiny_advise'),
    (dyn.block(0x78), 'reserved_1108'),

    (_malloc_lock_s, 'small_regions_lock'),
    (size_t, 'num_small_regions'),
    (size_t, 'num_small_regions_dealloc'),
    (lambda s: dyn.pointer(region_hash_generation_t, recurse={'QUANTUM':1<<SHIFT_SMALL_QUANTUM}), 'small_region_generation'),
    (lambda s: dyn.array(dyn.clone(region_hash_generation_t, recurse={'QUANTUM':1<<SHIFT_SMALL_QUANTUM}),2), 'srg'),
    (unsigned , 'num_small_slots'),
    (integer, 'num_small_magazines'),   # note: max of 0x1f
    (unsigned, 'num_small_magazines_mask'),
    (integer, 'num_small_magazines_mask_shift'),
    (lambda s: dyn.opointer(dyn.clone(magazine_array,length=s['num_small_magazines'].li.int()+1), lambda _,o:o-magazine_t().a.size(), recurse={'QUANTUM':1<<SHIFT_SMALL_QUANTUM} ), 'small_magazines'),
    (uintptr_t, 'last_small_advise'),
    (dyn.block(0x78), 'reserved_1208'),

    (_malloc_lock_s, 'large_szone_lock'),
    (unsigned, 'num_large_objects_in_use'),
    (unsigned, 'num_large_entries'),
    (lambda s: dyn.clone(s._large_entries, _object_=dyn.clone(s._large_entries._object_, length=s['num_large_entries'].li.int())), 'large_entries'),
    (size_t, 'num_bytes_in_large_objects'),
    (integer, 'large_entry_cache_newest'),
    (integer, 'large_entry_cache_oldest'),
    (dyn.clone(szone_t._large_entry_cache,length=16), 'large_entry_cache'),
#    (dyn.block(4), 'padding(large_entry_cache)'),
    (boolean_t, 'large_legacy_reset_mprotect'),
    (dyn.block(4), 'padding(large_legacy_reset_mprotect)'),
    (size_t, 'large_entry_cache_reserve_bytes'),
    (size_t, 'large_entry_cache_reserve_limit'),
    (size_t, 'large_entry_bytes'),

    (unsigned, 'is_largemem'),
    (unsigned, 'large_threshold'),
    (unsigned, 'vm_copy_threshold'),
    (dyn.block(4), 'padding(vm_copy_threshold)'),
    (uintptr_t, 'cookie'),
    (lambda s: dyn.clone(s._region_ptr_array, recurse={'QUANTUM':1<<SHIFT_TINY_QUANTUM}, length=64), 'initial_tiny_regions'),
    (lambda s: dyn.clone(s._region_ptr_array, recurse={'QUANTUM':1<<SHIFT_SMALL_QUANTUM}, length=64), 'initial_small_regions'),
    (dyn.pointer(szone_t), 'helper_zone'),
    (boolean_t, 'flotsam_enabled'),
]
    
class malloc_zones(parray.terminated):
    class _object_(dyn.pointer(zone_t)):
        def basic(self): return self.d.l.basic()
        def zone(self): return self.d.l.zone()
        def zone_name(self): return self.d.l.zone_name()
        def version(self): return self.d.l.version()
        def summary(self):
            res = self.d.l
            return '{:s} version={:d} complex_zone=0x{:x}'.format(res.zone_name(), res.version(), res['complex_zone'].getoffset())

    def isTerminator(self, value):
        return value.get() == 0

    def enumerate(self, version=8):
        for i,n in enumerate(self[:-1]):
            res = n.d.l
            if version is None or res.version() == version:
                yield i,res
            continue
        return
    def iterate(self, version=8):
        for _,n in self.enumerate(version): yield n

    def repr(self):
        return ', '.join('{:s}/{:d}'.format(res.zone_name(), res.version()) for res in self.iterate(None))

entry = dyn.pointer(malloc_zones)

if __name__ == '__main__':
    ab = szone_t()
    ab.alloc()
    print ab
    exit()

    import lldb
    import ptypes,macheap
    ptypes.setsource(lldbprocess(lldb.process))

    modules = lldb.target.get_modules_array()
    sym_malloc_zones, = (m.FindSymbol('malloc_zones') for m in lldb.target.get_modules_array() if m.FindSymbol('malloc_zones').name)
    z = macheap.entry(offset=int(sym_malloc_zones.addr))

if __name__ == '__main__':
    z = macheap.szone_t().a

    mag_get_thread_index = _os_cpu_number() & (TINY_MAX_MAGAZINES-1)
    szone_t.tiny_magazines[mag_thread_index]
