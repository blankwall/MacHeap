from . import ptype,parray,pstruct,pbinary,pint,pfloat,pstr
from . import config,utils,dynamic,provider
dyn = dynamic
prov = provider
Config = config.defaults

__all__ = 'ptype','parray','pstruct','pbinary','pint','pfloat','pstr','dynamic','dyn','prov'

## globally changing the ptype provider
def setsource(prov):
    '''Sets the default ptype provider to the one specified'''
    prov.seek,prov.consume,prov.store
    ptype.source = prov

## globally changing the byte order
def setbyteorder(endianness):
    '''
    _Globally_ sets the integer byte order to the endianness specified.
    Can be either config.byteorder.bigendian or config.byteorder.littleendian
    '''
    [ module.setbyteorder(endianness) for module in (ptype,pint,pfloat,pbinary) ]

## some things people people might find useful
#from ptype import debug,debugrecurse
from ptype import istype,iscontainer,undefined

from provider import file,memory
from utils import hexdump

if __name__ == '__main__':
    import __init__ as ptypes
    class a(ptypes.ptype.type):
        length = 4

    data = '\x41\x41\x41\x41'

    import ctypes
    b = ctypes.cast(ctypes.pointer(ctypes.c_buffer(data,4)), ctypes.c_void_p)

    ptypes.setsource(ptypes.prov.memory())
    print 'ptype-static-memory', type(ptypes.ptype.source) == ptypes.prov.memory
    print 'ptype-instance-memory', type(ptypes.ptype.type().source) == ptypes.prov.memory
    c = a(offset=b.value).l
    print 'type-instance-memory', c.serialize() == data

    ptypes.setsource(ptypes.prov.empty())
    print 'ptype-static-empty', type(ptypes.ptype.source) == ptypes.prov.empty
    print 'ptype-instance-empty', type(ptypes.ptype.type().source) == ptypes.prov.empty
    c = a(offset=b.value).l
    print 'type-instance-empty', c.serialize() == '\x00\x00\x00\x00'
    ptypes.setsource(ptypes.prov.memory())
