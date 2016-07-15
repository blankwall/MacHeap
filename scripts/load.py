import lldb,os

import ptypes,macheap
import ptypes.bitmap as bit
ptypes.setsource(ptypes.prov.lldb(lldb.process))

ll = lldb.debugger.HandleCommand

def malloc_his(addr):
	s = "malloc_history {0} {1}".format(lldb.process.id, hex(addr))
	print s
	os.system(s)

modules = lldb.target.get_modules_array()
s_malloc_zones, = (m.FindSymbol('malloc_zones') for m in lldb.target.get_modules_array() if m.FindSymbol('malloc_zones').name)
z = macheap.entry(offset=int(s_malloc_zones.addr)).l.d.l
tiny = "tiny_magazines"
small = "small_magazines"
a = z[0].zone()
t = a[tiny].d.l[1]
# b = t['mag_free_list'][2].d.l
# print b
# s = a[small].d.l[1]
# s = a[small].d.l[1]
# r = t['firstNode'].d
# rs = s['firstNode'].d
# cache =  t['mag_last_free'].d.l
# scache =  s['mag_last_free'].d.l
# free = t['mag_free_list']
# sfree = s['mag_free_list']
# r = rt
# m = t
# print scache
# fir = m['firstNode'].d.l
#b = z[1].d.l
