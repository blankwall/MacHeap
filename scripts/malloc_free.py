import commands, os, sys
import operator,functools,itertools
import re
import lldb 
from glob import *
import lldb.macosx.heap as j
import math
import struct

'''
script 
'''

log = "mf.txt"
file(log, "w+").close()

def cont(frame):
    thread = frame.GetThread()
    process = thread.GetProcess()
    process.Continue()

def get_registers(frame, kind):
    registerSet = frame.GetRegisters() # Return type of SBValueList.
    for value in registerSet:
        if kind.lower() in value.GetName().lower():
            return value
    return None

def get_register(frame, need):
    regs = get_registers(frame, 'general purpose')
    for reg in regs:
        if reg.GetName() == need:
            return reg.GetValue()

def quant(clean):
    qu = ""
    if clean:
        qu += "SMALL [%d]" % int(math.trunc(math.ceil((float(clean)/512.0)))) if int(clean) > 1008 else "TINY [%d]" % int(math.trunc(math.ceil((float(clean)/16.0))))
    return qu

def read_rsp(frame, rsp):
    thread = frame.GetThread()
    process = thread.GetProcess()
    err = lldb.SBError()
    out = process.ReadMemory(int(rsp,16), 8, err)
    if err.Success():
        out, = struct.unpack("<Q", out)
        return out
    raise ValueError("fucked up at %s : %s"% (rsp, err.GetCString()))

def set_malloc_after():
    malloc_before = "breakpoint set -s libsystem_malloc.dylib -a 0x10E8"
    lldb.debugger.HandleCommand(malloc_before)
    index = lldb.target.GetNumBreakpoints()
    log_cmd = 'breakpoint command add %d -F malloc_free.malloc_after' % (index)
    lldb.debugger.HandleCommand(log_cmd)

def malloc_after(a, b, c):
    x = lldb.SBCommandReturnObject()
    x.Clear()
    rax, rsp = map(functools.partial(get_register, a), ("rax", "rsp"))
    j.malloc_info(lldb.debugger, rax, x, globals())
    clean = x.GetOutput() and x.GetOutput().split('(',2)[1].split(')',2)[0].translate(None,' ')
    info = "Malloc:[%x] -- %s - %s - %x" % (int(rax,16), clean, quant(clean), read_rsp(a, rsp))
    with file(log, "a") as x:
        print >>x, info
    cont(a)

def set_free():
    malloc_before = "breakpoint set -s libsystem_malloc.dylib -a 0x3e98"
    lldb.debugger.HandleCommand(malloc_before)
    index = lldb.target.GetNumBreakpoints()
    log_cmd = 'breakpoint command add %d -F malloc_free.free' % (index)
    lldb.debugger.HandleCommand(log_cmd)

def free(a, b, c):
    x = lldb.SBCommandReturnObject()
    x.Clear()
    rdi = get_register(a, "rdi")
    rsp = get_register(a, "rsp")
    j.malloc_info(lldb.debugger, rdi, x, globals())
    out = int(rdi, 16)
    clean = x.GetOutput() and x.GetOutput().split('(',2)[1].split(')',2)[0].translate(None,' ')
    qu = quant(clean)
    

    info = "Free:::[%x] -- %s - %s - %x" % (out, clean, qu, read_rsp(a,rsp))
    with file(log, "a") as x:
        print >>x, info
    cont(a)

def set():
    set_free()
    set_malloc_after()
