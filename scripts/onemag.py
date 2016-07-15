import lldb
def cont1(a,b,c):
    """
    breakpoint set -s libsystem_malloc.dylib -a 0x262a
    breakpoint set -s libsystem_malloc.dylib -a 0x2a6a
    """
    lldb.debugger.HandleCommand("mem write $rbp-0x40 0x0")
    thread = a.GetThread()
    process = thread.GetProcess()
    process.Continue()
to = rule = cont1   # bad

def cont2(a,b,c):
    """
    breakpoint set -s libsystem_malloc.dylib -a 0xb95d
    breakpoint set -s libsystem_malloc.dylib -a 0xbd43
    """
    lldb.debugger.HandleCommand("mem write $rbp-0x38 0x0")
    thread = a.GetThread()
    process = thread.GetProcess()
    process.Continue()
them = all = cont2  # jokes
