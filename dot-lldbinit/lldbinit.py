if __name__ == '__main__':
    raise RuntimeError("Not intended to be run as a stand-alone application")

import sys,os,platform,traceback,logging
import types,itertools,operator,functools
import fnmatch,six,array,math,heapq
import commands,argparse,shlex
import lldb
import subprocess,re  
import pyparsing as pp

### default options
class Options(object):
    # which disassembly-flavor to use
    syntax = 'intel'

    # whether to display with a color-scheme
    color = False

    # FIXME: allow better customization
    here_rows = 4, 6
    hex_rows = 6
    rows = 6

    forward_disassembly = 4
    backward_disassembly =3

    # which characters are printable within the hextdump
    import string
    printable = set().union(string.printable).difference(string.whitespace).union(' ')

# in some instances i've seen the 'argv' variable not defined...
# wtf are you doing, lldb?
if not hasattr(sys, 'argv'): sys.argv = [__name__]

### grammar
class ExpressionGrammar:
    pp.ParserElement.enablePackrat()

    ## character sets
    cSymbolPrefix = pp.alphas + '_'
    cSymbolSuffix = cSymbolPrefix + pp.nums
    cNumbersDec = pp.nums
    cNumbersHex = pp.hexnums
    cNumbersBin = '01'
    cNumbersOct = '01234567'
    cModuleName = pp.alphas + '_' + pp.nums + '.'

    ## token types
    # symbols
    tModule = pp.Word(cModuleName)
    tModuleSeparator = pp.oneOf('! `')
    tSymbol = pp.Combine(pp.Word(cSymbolPrefix) + pp.Optional(pp.Word(cSymbolSuffix)))

    # integer types
    tInteger = pp.Word(pp.nums)
    tZero = pp.Literal('0')
    tBaseBinary = pp.Literal('y')
    tBaseHex = pp.Literal('x')
    tBaseOctal = pp.Literal('o')

    # grouping
    tBegin, tEnd = pp.Literal('('), pp.Literal(')')

    # operations
    tPlus = pp.Literal('+')
    tMinus = pp.Literal('-')
    tMultiply = pp.Literal('*')
    tDivide = pp.Literal('/')
    tXor = pp.Literal('^')
    tOr = pp.Literal('|')
    tAnd = pp.Literal('&')
    tNot = pp.Literal('!')
    tPower = pp.Literal('**')
    tSign = pp.oneOf('+ -')
    tInvert = pp.Literal('~')

    # cast keywords
    tCastByte = pp.Keyword('by')
    tCastWord = pp.Keyword('wo')
    tCastDword = pp.Keyword('dwo')
    tCastQword = pp.Keyword('qwo')
    tCastPointer = pp.Keyword('poi')
    tCastSByte = pp.Keyword('sby')
    tCastSWord = pp.Keyword('swo')
    tCastSDword = pp.Keyword('sdwo')
    tCastSQword = pp.Keyword('sqwo')

    ## Grammar
    kExpression = pp.Forward()

    kBegin, kEnd = pp.Suppress(tBegin), pp.Suppress(tEnd)
    kHex = pp.Suppress(tZero + tBaseHex) + pp.Word(cNumbersHex)
    kOct = pp.Suppress(tZero + tBaseOctal) + pp.Word(cNumbersOct)
    kBin = pp.Suppress(tZero + tBaseBinary) + pp.Word(cNumbersBin)
    kDec = tInteger
    kNumeric = kHex | kOct | kBin | kDec
    kNumeric.setName('kNumeric')

    kSymbolWithModule = tModule + pp.Suppress(tModuleSeparator) + tSymbol
    kSymbolWithoutModule = tSymbol
    kSymbol = pp.Group(kSymbolWithModule | kSymbolWithoutModule)
    kSymbol.setName('kSymbol')

    kKeyword = pp.Or([tCastByte,tCastWord,tCastDword,tCastQword,tCastPointer,tCastSByte,tCastSWord,tCastSDword,tCastSQword])
    kFunction = pp.Group(kKeyword + kBegin + kExpression + kEnd)
    kFunction.setName('kFunction')

    kRegisterNames = pp.Forward() # FIXME: this needs to be assigned
    kRegister = pp.Group(pp.Literal('$').suppress() + kRegisterNames)

    ## grammar reductions
    def numeric(base):
        class tokens(object):
            def __init__(self, tokens):
                self.value, = tokens
            def __repr__(self):
                return str(self.eval())
            def eval(self, **kwds):
                return int(self.value, self.base)
        tokens.base = base
        return tokens
    kHex.setParseAction(numeric(16))
    kOct.setParseAction(numeric(8))
    kBin.setParseAction(numeric(2))
    kDec.setParseAction(numeric(10))

    class symbol(object):
        def __init__(self, tokens):
            res = tokens[0]
            self.module, self.symbol = (res[0],res[1]) if len(res) > 1 else (None, res[0])
        def __repr__(self):
            return '!'.join((self.module, self.symbol)) if self.module else '!'+self.symbol
        def eval(self, **kwds):
            """
            modules -- dictionary of module name to SBModule
            current_module -- current frame's module
            """
            modules = kwds['modules']
            m = modules.get(self.module, kwds['current_module'])
            s = next(s for s in m.symbols if s.name == self.symbol)
            a = s.addr
            return a.load_addr
    kSymbol.setParseAction(symbol)

    class register(object):
        def __init__(self, tokens):
            res = tokens[0]
            self.register, = res
        def __repr__(self):
            return '%{:s}'.format(self.register)
        def eval(self, **kwds):
            """
            registers -- dictionary of the current frame's register state
            """
            registers = kwds['registers']
            return registers[self.register]
    kRegister.setParseAction(register)

    class function(object):
        def __init__(self, tokens):
            res = tokens[0]
            self.func, self.expr = res
        def __repr__(self):
            return '{:s}({!r})'.format(self.func, self.expr)
        def eval(self, **kwds): 
            """
            function -- dictionary of keyword to callable
            """
            lookup = kwds['functions']
            f = getattr(lookup, self.func)
            # f = lookup[self.func]
            res = self.expr.eval(**kwds)
            return f(res)
    kFunction.setParseAction(function)

    def operation(op):
        class tokens(object):
            def __init__(self, tokens):
                self.value = tokens[0]
            def __repr__(self):
                res = [repr(x) for x in self.value]
                return '{:s}({:s})'.format(self.op.__name__, ','.join(res))
            def eval(self, **kwds):
                return reduce(self.op, ((n if isinstance(n, six.integer_types) else n.eval(**kwds)) for n in self.value))
        tokens.op = op
        return tokens

    kOpPower, kOpMultiply, kOpDivide = map(pp.Suppress, (tPower, tMultiply, tDivide))
    kOpNot, kOpSign, kOpInvert = map(pp.Suppress, (tNot, tSign, tInvert))
    kOpXor, kOpOr, kOpAnd = map(pp.Suppress, (tXor, tOr, tAnd))
    kOpPlus, kOpMinus = map(pp.Suppress, (tPlus, tMinus))

    kOperand = kFunction | kRegister | kSymbol | kNumeric
    kExpression << pp.infixNotation(kOperand, [                     \
        (kOpInvert, 1, pp.opAssoc.RIGHT, operation(operator.inv)),  \
        (kOpSign, 1, pp.opAssoc.RIGHT, operation(operator.neg)),    \
        (kOpNot, 1, pp.opAssoc.RIGHT, operation(operator.not_)),    \
        (kOpPower, 2, pp.opAssoc.RIGHT, operation(operator.pow)),   \
        (kOpXor, 2, pp.opAssoc.LEFT, operation(operator.xor)),      \
        (kOpOr, 2, pp.opAssoc.LEFT, operation(operator.or_)),       \
        (kOpAnd, 2, pp.opAssoc.LEFT, operation(operator.and_)),     \
        (kOpMultiply, 2, pp.opAssoc.LEFT, operation(operator.mul)), \
        (kOpDivide, 2, pp.opAssoc.LEFT, operation(operator.div)),   \
        (kOpPlus, 2, pp.opAssoc.LEFT, operation(operator.add)),     \
        (kOpMinus, 2, pp.opAssoc.LEFT, operation(operator.sub)),    \
    ])

### parser
class ExpressionParser(object):
    def __init__(self, target, grammar, **kwds):
        self.target = self.__initialize_lldb(target)
        self.modules = self.__get_modules(self.target)
        self.registers = Register(self.frame)
        self.grammar = self.__update_grammar(grammar)
        self.bits = target.GetAddressByteSize() * 8

    def parse(self, string):
        res, = self.grammar.kExpression.parseString(string)
        options = {}
        options['current_module'] = self.target.GetModuleAtIndex(0)
        options['modules'] = dict(self.modules)
        options['registers'] = self.registers
        # options['functions'] = dict(self.__dict__)
        options['functions'] = self
        return res.eval(**options)

    def read(self, address, size):
        err = lldb.SBError()
        err.Clear()
        data = self.process.ReadMemory(address, size, err)
        if err.Fail() or len(data) != size:
            raise ValueError('{:s}.{:s}.read : Unable to read 0x{:x} bytes from 0x{:x}'.format(__name__, self._class__.__name__, size, address))
        data = reversed(data) if sys.byteorder == 'little' else data[:]
        return reduce(lambda t,c: t << 8 | ord(c), data, 0)
    def by(self, address):
        return self.read(address, 1)
    def wo(self, address):
        return self.read(address, 2)
    def dwo(self, address):
        return self.read(address, 4)
    def qwo(self, address):
        return self.read(address, 8)
    def sby(self, address):
        high,res = 1<<8-1, self.by(address)
        return -(high*2-res) if res & high else (res & (high-1))
    def swo(self, address):
        high,res = 1<<16-1, self.wo(address)
        return -(high*2-res) if res & high else (res & (high-1))
    def sdwo(self, address):
        high,res = 1<<32-1, self.dwo(address)
        return -(high*2-res) if res & high else (res & (high-1))
    def sqwo(self, address):
        high,res = 1<<64-1, self.qwo(address)
        return -(high*2-res) if res & high else (res & (high-1))
    def poi(self, address):
        return self.read(address, self.bits / 8)

    def __initialize_lldb(self, target):
        self.process = target.GetProcess()
        self.thread = self.process.GetSelectedThread()
        self.frame = self.thread.GetSelectedFrame()
        self.module = self.frame.GetModule()
        return target

    def __get_modules(self, target):
        # res = { m.file.basename : m.GetObjectFileHeaderAddress().load_addr for m in target.modules }
        res = { m.file.basename : m for m in target.modules }
        return res

    def __update_grammar(self, grammar):
        registers = list(self.registers)
        grammar.kRegisterNames << pp.Or(map(pp.Literal, list(self.registers)))
        return grammar

    @staticmethod
    def semisplit(string):
        res, inside, backslash = '', '', False
        for n in string:
            if not backslash and n == '\\':
                backslash = True
            if backslash:
                backslash, res = False, res + n
                continue
            if inside and n == inside:
                inside, res = '', res + n
                continue
            if not inside and n in ('\"\''):
                inside, res = n, res + n
                continue
            if not inside and n == ';':
                if res: yield res
                res = ''
                continue
            res += n
        if res: yield res

### lldb command utilities
class Command(object):
    __alias__, cache = {}, {}
    __synchronicity__ = {}
    __typemap__ = [(types.TypeType, types.ObjectType), ((types.FunctionType,types.MethodType), types.FunctionType)]

    class __synchtype__(object): pass
    ASYNC = type('asynchronous', (__synchtype__,), {'value':'asyncronous'})
    SYNC = type('synchronous', (__synchtype__,), {'value':'synchronous'})
    CURRENT = type('current', (__synchtype__,), {'value':'current'})

    # this should only get written to once.
    # FIXME: use a descriptor to enforce it only getting assigned once.
    interpreter = None

    @classmethod
    def __type(cls, instance):
        res, = (new for t, new in cls.__typemap__ if isinstance(instance, t))
        return res
    @classmethod
    def __hash(cls, instance):
        if not instance.__name__:
            raise AssertionError("{:s}.{:s}.__hash : Unable to hash instance due to it being unnamed. : {!r}".format(__name__, cls.__name__, instance.__class__))
        t = cls.__type(instance)
        return '_{:d}_{:x}'.format(id(t), abs(hash(instance.__name__)))

    @classmethod
    def add(cls, name, callable, sync=None):
        if sync and not isinstance(sync, cls.__synchtype__):
            raise TypeError("{:s}.{:s}.add : Invalid synchronicity type specified. : {!r}".format(__name__, cls.__name__, sync))
        key = cls.__hash(callable)
        if key in cls.cache:
            cls.__unalias(key)
        cls.__alias__[name], cls.cache[key] = key, callable
        if sync: cls.__synchronicity__[key] = sync.value
        return key if cls.__add(key) else None

    @classmethod
    def __add_command(cls, key):
        path = (cls.__module__, cls.__name__, cls.frontend.__class__.__name__)
        t = cls.__type(cls.cache[key])
        if t == types.FunctionType:
            scr = functools.partial("command script add -f {:s}.{:s} {:s}".format, '.'.join(path), key)
        elif t == types.ObjectType and key in cls.__synchronicity__:
            scr = functools.partial("command script add -c {:s}.{:s} -s {:s} {:s}".format, '.'.join(path), key, cls.__synchronicity__[key])
        elif t == types.ObjectType and key not in cls.__synchronicity__:
            scr = functools.partial("command script add -c {:s}.{:s} {:s}".format, '.'.join(path), key)
        else:
            raise TypeError('{:s}.{:s} : Unable to generate command with unknown type. {!r}'.format(cls.__module__, cls.__name__, t))
        return scr

    @classmethod
    def __add(cls, key):
        addscr = cls.__add_command(key)
        aliases = ( k for k,v in cls.__alias__.iteritems() if v == key )

        error, result = {}, lldb.SBCommandReturnObject()
        for k in aliases:
            addcmd = addscr(k)
            result.Clear()
            res = cls.interpreter.HandleCommand(addcmd, result, False)
            # FIXME: handle the return value which could be one of lldb.eReturnStatus*
            if not result.Succeeded(): error[k] = res
        return error

    @classmethod
    def __unalias(cls, key):
        removescr = functools.partial("command script delete {:s}".format)
        error, result = {}, lldb.SBCommandReturnObject()

        # delete all the commands
        aliases = ( k for k,v in cls.__alias__.iteritems() if v == key )
        for k in aliases:
            removecmd = removescr(aliases)
            result.Clear()
            res = cls.interpreter.HandleCommand(removecmd, result, False)
            # FIXME: handle the return value which could be one of lldb.eReturnStatus*
            if not result.Succeeded(): error[k] = res

        # now remove all aliases and synchronicity options
        cls.__alias__ = {k : v for k,v in cls.__alias__.iteritems() if v != key and k not in error}
        if not error:
            cls.synchronicity = { k : v for k,v in cls.synchronicity.iteritems() if k != key }
        return error

    @classmethod
    def remove(cls, name):
        key = cls.__alias__[name]
        res = cls.cache[key]
        return None if cls.__remove(key) else res

    @classmethod
    def __remove(cls, key):
        # figure out what aliases we have to remove
        aliases = (k for k,v in cls.__alias__.iteritems() if v == key)
        removescr = functools.partial("command script delete {:s}".format)

        # delete all the commands
        error, result = {}, lldb.SBCommandReturnObject()
        for k in aliases:
            removecmd = removescr(k)
            result.Clear()
            res = cls.interpreter.HandleCommand(removecmd, result, False)
            # FIXME: handle the return value which could be one of lldb.eReturnStatus*
            if not result.Succeeded(): error[k] = res

        # update all the aliases and synchronicity options
        cls.__alias__ = {k : v for k, v in cls.__alias__.iteritems() if v != key and k not in error}
        if not error:
            cls.__synchronicity__ = {k : v for k, v in cls.__synchronicity__.iteritems() if k != key}

        # if there was an error, then don't delete our command because there's still
        # an alias pointing towards it
        if not error:
            cls.cache.pop(key)
        return error

    @classmethod
    def alias(cls, source, *targets):
        # figure out what the actual name is
        key = cls.__alias__[source]
        aliasdict = dict.fromkeys(targets, key)

        # build the add and remove commands
        addscr = cls.__add_command(key)
        removescr = functools.partial("command script delete {:s}".format)

        # remove it if it already exists
        error = {}
        for k,v in aliasdict.iteritems():
            if k in cls.__alias__:
                res = cls.unalias(k)
                if not res: error[k] = res
            continue
        if error:
            raise StandardError('{:s}.{:s} : Error trying to remove the following already defined aliases : {!r}'.format(cls.frontend.__module__, cls.__name__, tuple(error.keys())))
                
        # now we can add each command
        error, result = {}, lldb.SBCommandReturnObject()
        for k,v in aliasdict.iteritems():
            result.Clear()
            res = cls.interpreter.HandleCommand(addscr(k), result, False)
            # FIXME: handle the return value which could be one of lldb.eReturnStatus*
            if not result.Succeeded(): error[k] = res

        # and now we can update our alias dictionary with our changes
        cls.__alias__.update({k : v for k,v in aliasdict.iteritems() if k not in error})
        if error:
            logging.warn('{:s}.{:s} : Error trying to add the following commands : {!r}'.format(cls.frontend.__module__, cls.__name__, tuple(error.keys())))

        # finally done
        return False if error else True

    @classmethod
    def unalias(cls, name):
        key = cls.__alias__[name]

        # if there's only one alias left, then _really_ remove it.
        if sum(1 for v in cls.__alias__.values() if v == key) == 1:
            return cls.remove(name)

        # otherwise, we can just remove the command
        result, removescr = lldb.SBCommandReturnObject(), functools.partial("command script delete {:s}".format)
        result.Clear()
        res = cls.interpreter.HandleCommand(removescr(name), result, False)
        if not result.Succeeded():
            logging.warn('{:s}.{:s} : Error trying to remove the following alias : {!r}'.format(cls.frontend.__module__, cls.__name__, name))
            return False

        # now clear the alias
        cls.__alias__.pop(name)
        return True

    class frontend(object):
        def __getattr__(self, name):
            return Command.cache[name]
    frontend = frontend()

    # decorator utilities
    @classmethod
    def preload(cls, name, sync=None):
        if sync and not isinstance(sync, cls.__synchtype__):
            raise TypeError("{:s}.{:s}.preload : Invalid synchronicity type specified. : {!r}".format(__name__, cls.__name__, sync))
        def prepare(definition):
            key = cls.__hash(definition)
            cls.__alias__[name] = key
            cls.cache[key] = definition
            if sync: cls.__synchronicity__[key] = sync
            return definition
        return prepare
    @classmethod
    def load(cls, interpreter):
        cls.interpreter = interpreter

        error, result = {}, lldb.SBCommandReturnObject()
        for alias,key in cls.__alias__.iteritems():
            addscr = cls.__add_command(key)
            addcmd = addscr(alias)
            result.Clear()
            res = cls.interpreter.HandleCommand(addcmd, result, False)
            if not result.Succeeded(): error[alias] = res
        if error:
            logging.warn('{:s}.{:s} : Error trying to load the following commands : {!r}'.format(cls.frontend.__module__, cls.__name__, tuple(error.keys())))
            return False
        return True
    def __new__(cls, name, sync=None):
        return cls.preload(name, sync)

def __lldb_init_module(debugger, globals):
    interp = debugger.GetCommandInterpreter()
    res = Command.load(interp)
    if not res:
        logging.fatal("{:s} : Unable to define default commands".format(__name__))
    return

# lldb-stupidity helpers
class CaptureOutput(object):
    def __init__(self, result):
        self.result = result
        self.state = []
        self.error = []

    @classmethod
    def splitoutput(cls, append):
        leftover = ''
        while True:
            try:
                output = leftover + (yield)
            except GeneratorExit:
                append(leftover)
                break

            split = output.split('\n')
            res = iter(split)
            if len(split) > 1: map(append,itertools.islice(res, len(split)-1))
            leftover = next(res)
        return

    @classmethod
    def fileobj(cls, append):
        splitter = cls.splitoutput(append)
        splitter.next()
        fileobj = type(cls.__name__, (object,), {'write':splitter.send})
        return fileobj()

    def __enter__(self):
        self.state.append(sys.stdout), self.error.append(sys.stderr)
        sys.stdout = out = self.fileobj(self.result.AppendMessage)
        sys.stderr = err = self.fileobj(self.result.AppendWarning)
        return out,err

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.state.pop(-1)
        sys.stderr = self.error.pop(-1)

class DebuggerCommandOutput(object):
    CONTINUE = {False : lldb.eReturnStatusSuccessContinuingNoResult, True : lldb.eReturnStatusSuccessContinuingResult}
    FINISH   = {False : lldb.eReturnStatusSuccessFinishNoResult,     True : lldb.eReturnStatusSuccessFinishResult}

    def __init__(self, fn, continuing=False, result=False):
        state = self.CONTINUE if continuing else self.FINISH
        self.callable, self.success = fn, state[result]

    def __call__(self, context, command, result):
        result.Clear()
        try:
            # FIXME: if this happens, check your command's flags.
            if not context.IsValid():
                raise StandardError("{:s}.{:s} : Unable to dispatch to command due to the command's requested context being invalid. : {!r}".format(__name__, self.callable.__name__, context))

            with CaptureOutput(result) as (f,e):
                failed = self.callable(context, command)
        except:
            exc = traceback.format_exception(*sys.exc_info())
            map(result.AppendWarning, exc)
            failed = True
        result.SetStatus(lldb.eReturnStatusFailed if failed else self.success)

Flags = type('Flags', (object,), { n[len('eCommand'):] : getattr(lldb, n) for n in dir(lldb) if n.startswith('eCommand') })

class DebuggerCommand(object):
    # what context to pass to the command
    context = lldb.SBDebugger

    # whether the command continues or finishes
    continuing = False

    # whether the command has a result or not
    hasresult = False

    # the argument parser object
    help = None

    # default arguments to pass if none is specified
    default = None

    # lldb.eCommand* flags that describe requirements of the command
    flags = 0

    @classmethod
    def __convert__(cls, ctx, (debugger, context)):
        # for some reason if these aren't touched, they don't work.
        lldb.target,lldb.debugger,lldb.process,lldb.thread,lldb.frame

        # return the correct object given the requested context
        if ctx == None:
            return context.GetTarget()
        elif ctx == lldb.SBExecutionContext:
            return context
        elif ctx == lldb.SBDebugger:
            return debugger
        elif ctx == lldb.SBTarget:
            return context.GetTarget()
        elif ctx == lldb.SBCommandInterpreter:
            return debugger.GetCommandInterpreter()
        elif ctx == lldb.SBProcess:
            return context.GetProcess()
        elif ctx == lldb.SBThread:
            return context.GetThread()
        elif ctx == lldb.SBFrame:
            return context.GetFrame()
        elif ctx == lldb.SBBlock:
            frame = context.GetFrame()
            #return frame.GetFrameBlock()
            return frame.GetBlock()
        elif ctx == lldb.SBValueList:
            frame = context.GetFrame()
            return frame.GetRegisters()
        elif ctx == lldb.SBFunction:
            frame = context.GetFrame()
            return frame.GetFunction()
        elif ctx == lldb.SBModule:
            frame = context.GetFrame()
            return frame.GetModule()
        elif ctx == lldb.SBFileSpec:
            frame = context.GetFrame()
            module = frame.GetModule()
            return frame.GetFileSpec()
        raise NotImplementedError("{:s}.{:s}.__convert__ : unable to convert requested context to it's instance : {!r}".format(__name__, cls.__name__, ctx))

    @classmethod
    def __verify__(cls):
        if not isinstance(cls.continuing, bool):
            raise AssertionError("{:s}.{:s}.continuing is not of type bool : {!r}".format(__name__, cls.__name__, cls.continuing.__class__))
        if not isinstance(cls.hasresult, bool):
            raise AssertionError("{:s}.{:s}.hasresult is not of type bool : {!r}".format(__name__, cls.__name__, cls.hasresult.__class__))
        if cls.help and not isinstance(cls.help, argparse.ArgumentParser):
            raise AssertionError("{:s}.{:s}.help is not of type {:s} : {!r}".format(__name__, cls.__name__, argparse.ArgumentParser.__name__, cls.help.__class__))
        if not isinstance(cls.flags, six.integer_types):
            raise AssertionError("{:s}.{:s}.flags is not an integral : {!r}".format(__name__, cls.__name__, cls.flags))
        if cls.command is DebuggerCommand.command:
            raise AssertionError("{:s}.{:s}.command has not been overloaded : {!r}".format(__name__, cls.__name__, cls.command))
        return

    def __init__(self, debugger, namespace):
        # not sure what the point of these are..
        self.debugger, self.namespace = debugger, namespace

        # verify the class is defined properly, and create our wrapper
        self.__verify__()

        # setup a default help
        if self.help is None:
            self.__help = argparse.ArgumentParser(description=self.__doc__, add_help=False)
        else:
            self.__help = self.help
        if not self.__help.prog:
            self.__help.prog = self.__class__.__name__

        # decorate our method
        self.callable = DebuggerCommandOutput(self.command, self.continuing, self.hasresult)

    def get_flags(self):
        FLAG = {
            lldb.SBTarget    : Flags.RequiresTarget,
            lldb.SBProcess   : Flags.RequiresProcess,
            lldb.SBThread    : Flags.RequiresThread,
            lldb.SBValueList : Flags.RequiresRegContext | Flags.RequiresFrame,
            lldb.SBFrame     : Flags.RequiresFrame,
            lldb.SBBlock     : Flags.RequiresFrame,
            lldb.SBFunction  : Flags.RequiresFrame,
            lldb.SBModule    : Flags.RequiresFrame,
            lldb.SBFileSpec  : Flags.RequiresFrame,
        }
        return self.flags | FLAG[self.context]
    def get_long_help(self):
        return self.__help.format_help() if self.help else 'No help is available.'
    def get_short_help(self):
        return self.__help.format_usage() if self.help else 'No usage information is available.'
    def __call__(self, debugger, command, context, result):
        argv = shlex.split(command) if command else self.default

        if self.help:
            if argv is None:
                result.Clear()
                map(result.AppendMessage, self.__help.format_usage().split('\n'))
                return
            try: res = self.__help.parse_args(argv)
            except SystemExit: return
        else: res = argv

        setattr(self, 'result', result)
        ctx = self.__convert__(self.context, (debugger,context))
        try: return self.callable(ctx, res, result)
        finally: delattr(self, 'result')

    @staticmethod
    def command(context, arguments):
        raise NotImplementedError

### generalized lldb object tools
class Module(object):
    separator = '`' if platform.system() == 'Darwin' else '!'
    @classmethod
    def list(cls, target, string, all=True, ignorecase=True):
        results = ((i,m) for i,m in enumerate(target.modules) if fnmatch.fnmatch(m.file.basename.lower() if ignorecase else m.file.basename, string.lower() if ignorecase else string))
        for i,m in results:
            if not all and not cls.mappedQ(m):
                continue
            yield '[{:d}] {:s}'.format(i, cls.repr(m))
        return

    @classmethod
    def mappedQ(cls, m):
        res = cls.address(m)
        return res not in (0,lldb.LLDB_INVALID_ADDRESS)

    @classmethod
    def address(cls, m):
        res = m.GetObjectFileHeaderAddress()
        return res.file_addr if res.load_addr == lldb.LLDB_INVALID_ADDRESS else res.load_addr

    @classmethod
    def filesize(cls, m):
        return sum(s.file_size for s in m.sections if s.name != '__PAGEZERO')

    @classmethod
    def loadsize(cls, m):
        return sum(s.size for s in m.sections if s.name != '__PAGEZERO')

    @classmethod
    def repr(cls, m):
        addr,size = cls.address(m),cls.loadsize(m)
        start = '0x{:x}'.format(addr) if cls.mappedQ(m) else '{unmapped}'
        return '{name:s} {triple:s} {fullname:s} {address:s}:+0x{size:x} num_sections={sections:d} num_symbols={symbols:d}'.format(address=start, size=size, name=m.file.basename, triple=m.triple, fullname=m.file.fullpath, symbols=len(m.symbols), sections=len(m.sections))

class Section(object):
    SUMMARY_SIZE = 0x10

    @classmethod
    def repr(cls, s):
        e = lldb.SBError()
        try:
            section_data = s.GetSectionData()
            data = repr(section_data.ReadRawData(e, 0, cls.SUMMARY_SIZE))
            if e.Fail(): raise Exception
        except:
            data = '???'
        return '[0x{address:x}] {name:!r} 0x{offset:x}:+0x{size:x}{:s}'.format(name=s.name, offset=s.file_offset, size=s.size, address=s.file_addr, data=(' '+data if data else ''))

class Symbol(object):
    @classmethod
    def list(cls, target, string, all=False, ignorecase=True):
        fullmatch,modulematch,symmatch = None,None,None
        if Module.separator in string:
            modulematch,symmatch = string.split(Module.separator, 1)
        else:
            fullmatch,symmatch = string,string

        total = 0
        for m in target.modules:
            if not all and not Module.mappedQ(m): continue
            if modulematch and not fnmatch.fnmatch(m.file.basename.lower() if ignorecase else m.file.basename, modulematch.lower() if ignorecase else modulematch):
                continue

            prefix = m.file.basename + Module.separator

            # check matches
            res = set()
            if fullmatch:
                res.update(s for s in m.symbols if fnmatch.fnmatch((prefix+s.name).lower() if ignorecase else (prefix+s.name), fullmatch.lower() if ignorecase else fullmatch))
            if symmatch:
                res.update(s for s in m.symbols if fnmatch.fnmatch(s.name.lower() if ignorecase else s.name, symmatch.lower() if ignorecase else symmatch))
            if not res: continue

            # start yielding our results
            for i,s in enumerate(res):
                yield '[{:d}] {:s}'.format(total+i, prefix+cls.repr(s))
            total += i + 1
        return

    @classmethod
    def address(cls, s):
        return s.addr.file_addr if s.addr.load_addr == lldb.LLDB_INVALID_ADDRESS else s.addr.load_addr

    @classmethod
    def size(cls, s):
        addr = cls.address(s)
        end = s.end_addr.file_addr if s.end_addr.load_addr == lldb.LLDB_INVALID_ADDRESS else s.end_addr.load_addr
        return end-addr

    @classmethod
    def repr(cls, s):
        TYPE_PREFIX = 'eTypeClass'
        start = cls.address(s)
        end = start + cls.size(s)

        types = {getattr(lldb,n) : n[len(TYPE_PREFIX):] for n in dir(lldb) if n.startswith(TYPE_PREFIX)}
        attributes = (n for n in ('external','synthetic') if getattr(s,n))
        if s.type in (lldb.eTypeClassFunction,):
            attributes = itertools.chain(attributes, ('instructions={:d}'.format(len(s.instructions))))
        attributes=filter(None,attributes)
        return '{name:s}{opt_mangled:s} type={type:s} 0x{addr:x}{opt_size:s}'.format(name=s.name, type=types.get(s.type,str(s.type)), opt_mangled=(' ('+s.mangled+')') if s.mangled else '', addr=start, opt_size=':+0x{:x}'.format(end-start) if end > start else '') + ((' ' + ' '.join(attributes)) if attributes else '')

class Frame(object):
    @classmethod
    def registers(cls, frame):
        pc,fp,sp = frame.pc,frame.GetFP(),frame.sp
        regs = frame.registers
        raise NotImplementedError
    @classmethod
    def flags(cls, frame):
        regs = frame.registers
        raise NotImplementedError
    @classmethod
    def args(cls, frame):
        #lldb.LLDB_REGNUM_GENERIC_ARG1
        #lldb.LLDB_REGNUM_GENERIC_ARG2
        avars = frame.args
        raise NotImplementedError
    @classmethod
    def vars(cls, frame):
        lvars,svars = frame.locals,frame.statics
        raise NotImplementedError

class Register(object):
    groups = "General Purpose Registers", "Floating Point Registers"
    # "General Purpose Registers"
    # "Floating Point Registers"
    # "Exception State Registers"
    def __init__(self, frame):
        self.cache, self.frame = {}, frame
        map(self.cache.update, (self.__fetch(n) for n in self.groups))

        # processor-specific aliases
        # FIXME: would be nice to generalize this with some architecture-specific class
#        self.cache['pc'] = self.cache['rip'] if 'rip' in self.cache else self.cache['eip']
#        self.cache['sp'] = self.cache['rsp'] if 'rsp' in self.cache else self.cache['esp']
#        self.cache['fp'] = self.cache['rbp'] if 'rbp' in self.cache else self.cache['rbp']

    def __fetch(self, name):
        frame_regs = self.frame.GetRegisters()
        regs = next((rlist for rlist in frame_regs if rlist.GetName() == name), [])
        res = {}
        for r in regs:
            k, v = r.GetName(), r.GetValue()
            if v is None: continue
            if '.' in v:
                res[k] = float(v)
            elif v.startswith('0x'):
                res[k] = int(v, 0x10)
            else:
                raise AssertionError("Unexpected value for register {!r}.{:s} : {!r}".format(name, k, v))
            continue
        self.cache.update(res)
        return res

    def general(self): return self.__fetch("General Purpose Registers")
    def floating(self): return self.__fetch("Floating Point Registers")
    def exception(self): return self.__fetch("Exception State Registers")
    def __iter__(self): return self.cache.iterkeys()
    def __getitem__(self, name): return self.cache[name]

class Target(object):
    @staticmethod
    def evaluate(target, string):
        parser = ExpressionParser(target, ExpressionGrammar)
        return parser.parse(string) 

    @classmethod
    def disassemble(cls, target, address, count, flavor=None):
        flavor = Options.syntax if flavor is None else flavor
        addr = lldb.SBAddress(address, target)
        return target.ReadInstructions(addr, count, flavor)
    @classmethod
    def disassemble_up(cls, target, address, count, flavor=None):
        flavor = Options.syntax if flavor is None else flavor
        #frame = target.GetProcess().GetSelectedThread().GetSelectedFrame()
        # FIXME: no way to disassemble upwards if lldb can't determine the function

    @classmethod
    def read(cls, target, address, count):
        process = target.GetProcess()

        err = lldb.SBError()
        err.Clear()
        data = process.ReadMemory(address, count, err)
        if err.Fail() or len(data) != count:
            raise ValueError("{:s}.{:s}.read : Unable to read 0x{:x} bytes from 0x{:x}".format(__name__, cls.__name__, count, address))
        return data

    ## dumping
    @classmethod
    def _gfilter(cls, iterable, itemsize):
        if itemsize < 8:
            for n in iterable: yield n
            return
        while True:
            nl,nh = next(iterable),next(iterable)
            yield (nh << (8*itemsize/2)) | nl
        return

    @classmethod
    def _hex_generator(cls, iterable, itemsize):
        maxlength = math.ceil(math.log(2**(itemsize*8)) / math.log(0x10))
        while True:
            n = next(iterable)
            yield '{:0{:d}x}'.format(n, int(maxlength))
        return

    @classmethod
    def _bin_generator(cls, iterable, itemsize):
        # FIXME: this might not be tested properly
        maxlength = math.ceil(math.log(2**(itemsize*8)) / math.log(2))
        while True:
            n = next(iterable)
            yield '{:0{:d}x}'.format(n, int(maxlength))
        return

    @classmethod
    def _int_generator(cls, iterable, itemsize):
        maxlength = math.ceil(math.log(2**(itemsize*8)) / math.log(10))
        while True:
            n = next(iterable)
            yield '{:{:d}d}'.format(n, int(maxlength))
        return

    @classmethod
    def _float_generator(cls, iterable, itemsize):
        maxlength = 16
        while True:
            n = next(iterable)
            yield '{:{:d}f}'.format(n, int(maxlength))
        return

    @classmethod
    def _dump(cls, data, kind=1):
        lookup = {1:'B', 2:'H', 4:'I', 8:'L'}
        itemtype = lookup.get(kind, kind)
        return array.array(itemtype, data)

    ## specific dumping formats
    @classmethod
    def _hexdump(cls, data, kind):
        res = array.array(kind, data)
        if res.typecode == 'L' and res.itemsize == 4:
            res,sz = cls._gfilter(iter(res),8),8
        else:
            res,sz = res,res.itemsize
        return sz, cls._hex_generator(iter(res), sz)
    @classmethod
    def _itemdump(cls, data, kind):
        res = array.array(kind, data)
        if res.typecode == 'L' and res.itemsize == 4:
            res,sz = cls._gfilter(iter(res),8),8
        else:
            res,sz = res,res.itemsize
        if res.typecode in ('f','d'):
            return res.itemsize, cls._float_generator(iter(res), sz)
        return sz, cls._int_generator(iter(res), sz)
    @classmethod
    def _bindump(cls, data, kind):
        res = array.array(kind, data)
        if res.typecode == 'L' and res.itemsize == 4:
            res,sz = cls._gfilter(iter(res),8),8
        else:
            res,sz = res,res.itemsize
        return sz, cls._bin_generator(iter(res), sz*8)
    @classmethod
    def _chardump(cls, data, width):
        printable = set(sorted(Options.printable))
        printable = ''.join((ch if ch in printable else '.') for ch in map(chr,xrange(0,256)))
        res = array.array('c', data.translate(printable))
        return width, itertools.imap(''.join, itertools.izip_longest(*(iter(res),)*width, fillvalue=''))

    @classmethod
    def _row(cls, width, columns):
        result = []
        for itemsize,column in columns:
            data = (c for i,c in zip(xrange(0, width, itemsize),column))
            result.append(' '.join(data))
        return result

    @classmethod
    def _dump(cls, target, address, count, width, kind, content):
        data = cls.read(target, address, count)
        countup = int((count // width) * width)
        offset = ('{:0{:d}x}'.format(a, int(math.ceil(math.log(address+count)/math.log(0x10)))) for a in xrange(address, address+countup, width))
        cols = ((width, offset), content(data, kind), cls._chardump(data, width))
        maxcols = (0,) * len(cols)
        while True:
            row = cls._row(width, cols)
            if len(row[0].strip()) == 0: break
            maxcols = tuple(max((n,len(r))) for n,r in zip(maxcols,row))
            yield tuple('{:{:d}s}'.format(col, colsize) for col,colsize in zip(row,maxcols))
        return

    @classmethod
    def hexdump(cls, target, address, count, kind, width=16):
        return '\n'.join(map(' | '.join, cls._dump(target, address, count*width, width, kind, cls._hexdump)))

    @classmethod
    def itemdump(cls, target, address, count, kind, width=16):
        return '\n'.join(map(' | '.join, cls._dump(target, address, count*width, width, kind, cls._itemdump)))

    @classmethod
    def binarydump(cls, target, address, count, kind, width=16):
        return '\n'.join(map(' | '.join, cls._dump(target, address, count*width, width, kind, cls._bindump)))

class Breakpoint(object):
    cache = {}          # unique id number to breakpoint/watchpoint name
    __internal__ = {}     # breakpoint/watchpoint name to SBBreakpoint
    __address__ = []      # address to breakpoint/watchpoint name
    __expression__ = {}   # breakpoint/watchpoint name to address/expression
    __function__ = {}

    @classmethod
    def __unique(cls):
        return max(cls.cache.keys() or (0,))+1

    @classmethod
    def __hash(cls, instance):
        if isinstance(instance, lldb.SBBreakpoint):
            return '_{:s}_{:d}'.format(lldb.SBBreakpoint.__name__, instance.GetID())
        elif isinstance(instance, lldb.SBWatchpoint):
            return '_{:s}_{:d}'.format(lldb.SBWatchpoint.__name__, instance.GetID())
        raise TypeError("{:s}.{:s}.hash : Unable to hash instance due to invalid type. : {!r}".format(__name__, cls.__name__, instance.__class__))

    ## cache modification
    @classmethod
    def __add_cache(cls, bp):
        id, key = cls.__unique(), cls.__hash(bp)
        cls.__internal__[key] = bp
        cls.cache[id] = key
        return id
    @classmethod
    def __rm_cache(cls, id):
        key = cls.cache.pop(id)
        return cls.__internal__.pop(key)

    @classmethod
    def __lldb_locations(cls, bp):
        if isinstance(bp, lldb.SBWatchpoint):
            return [(bp.GetWatchAddress(),bp.GetWatchSize())]
        count = bp.GetNumLocations()
        #count = bp.GetNumResolvedLocations()
        res = [(bp.GetLocationAtIndex(idx),1) for idx in xrange(count)]
        return [(l.GetLoadAddress(),size) for l,size in res]
    @classmethod
    def __location(cls, bp):
        res = cls.__lldb_locations(bp)
        if len(res) > 1:
            raise StandardError("{:s}.{:s}.location : More than one location was returned for specified breakpoint. : {!r}".format(__name__, cls.__name__, res))
        return next(iter(res))

    ## address searching
    @classmethod
    def __chk_address(cls, bp):
        key = cls.__hash(bp)
        addr,_ = cls.__location(bp)
        res = addr,key
        return res in cls.__address__
    @classmethod
    def __add_address(cls, bp):
        key = cls.__hash(bp)
        addr,_ = cls.__location(bp)
        res = addr,key
        heapq.heappush(cls.__address__, res)
        return addr
    @classmethod
    def __rm_address(cls, bp):
        key = cls.__hash(bp)
        res = [(a,k) for a,k in cls.__address__ if k == key]
        cls.__address__[:] = [(a,k) for a,k in cls.__address__ if k != key]
        (addr, _), = res
        return addr

    ## simple lldb wrappers
    @classmethod
    def __set_enabled(cls, id, bool):
        bp = cls.get(id)
        res, _ = bp.IsEnabled(), bp.SetEnabled(bool)
        return res
    @classmethod
    def enable(cls, id): return cls.__set_enabled(id, True)
    @classmethod
    def disable(cls, id): return cls.__set_enabled(id, False)

    ## return the breakpoint object with the specified id
    @classmethod
    def get(cls, id):
        res = cls.cache[id]
        return cls.__internal__[res]

    @classmethod
    def enumerate(cls):
        for res in sorted(cls.cache.keys()):
            key = cls.cache[res]
            yield res, cls.__internal__[key]
        return

    ## O(log n) search through all breakpoints for the specified address
    # FIXME: initially this included the breakpoint size to find the breakpoint covered by a range,
    #        but now since sizes are excluded.. this can be done in O(1) time.
    @classmethod
    def search(cls, address):
        def recurse(result, address):
            if len(result) > 1:
                center = len(result)//2
                a,k = result[center]
                return recurse(result[:center], address) if address < a else recurse(result[center:], address)
            (a,k), = result
            if a == address:
                return k
            raise LookupError('{:s}.{:s}.search : Unable to find address 0x{:x} in breakpoint list.'.format(__name__, cls.__name__, address))
        return recurse(cls.__address__[:], address)

    @classmethod
    def add_execute(cls, target, address, enabled=True):
        if isinstance(address, basestring):
            addr, expr = Target.evaluate(target, address), address
        else:
            addr, expr = address, hex(address)
        
        bp = target.BreakpointCreateByAddress(addr)
        res = cls.__add_cache(bp)
        key = cls.cache[res]
        bp.AddName(key)

        cls.__add_address(bp)
        cls.__expression__[key] = expr
        cls.__set_enabled(res, enabled)
        cls.__function__[key] = None
        return res

    @classmethod
    def add_access(cls, target, address, size=1, perms='rw', enabled=True):
        if isinstance(address, basestring):
            addr, expr = Target.evaluate(target, address), address
        else:
            addr, expr = address, hex(address)

        err = lldb.SBCommandReturnObject()
        bp = target.WatchAddress(addr, size, 'r' in perms, 'w' in perms, err)
        if not err.Succeeded():
            raise ValueError("{:s}.{:s}.add_access : Unable to add watchpoint at address 0x{:x}. : {!r}".format(__name__, cls.__name__, addr, expr))
        res = cls.__add_cache(bp)
        key = cls.cache[res]
        bp.AddName(key)

        cls.__add_address(bp)
        cls.__expression__[key] = expr
        cls.__set_enabled(res, enabled)
        cls.__function__[key] = None
        return res

    @classmethod
    def flush_command(cls, target, id):
        debugger, path = target.GetDebugger(), (cls.__module__, cls.__name__, cls.frontend.__class__.__name__)
        key = cls.cache[id]
        com = cls.__function__[key]

        bptype = 'breakpoint' if isinstance(cls.get(id), lldb.SBBreakpoint) else 'watchpoint'

        addscript = functools.partial('{:s} command add {:s}'.format, bptype)
        addcallable = functools.partial('{:s} command add -F {:s}.{:s} {:s}'.format, bptype, '.'.join(path), key)
        if isinstance(com, list):
            commands = [addscript(key)] + com + ['DONE']
            return debugger.HandleCommand('\n'.join(commands))
        return debugger.HandleCommand(addcallable(key))

    @classmethod
    def rm_command(cls, target, id):
        debugger = target.GetDebugger()
        bp = cls.get(id)
        bptype = 'breakpoint' if isinstance(bp, lldb.SBBreakpoint) else 'watchpoint'
        return debugger.HandleCommand("{:s} command delete {:d}".format(bptype, bp.GetID()))

    @classmethod
    def add_command(cls, target, id, commands):
        key = cls.cache[id]
        cls.__function__[key] = [commands] if isinstance(commands, basestring) else commands[:]
        return cls.flush_command(target, id)

    @classmethod
    def add_callable(cls, target, id, callable):
        key = cls.cache[id]
        cls.__function__[key] = callable
        return cls.flush_command(target, id)

    @classmethod
    def remove(cls, target, id):
        key, bp = cls.cache[id], cls.get(id)
        if not isinstance(bp, (lldb.SBBreakpoint, lldb.SBWatchpoint)):
            raise TypeError("{:s}.{:s}.remove : Unable to remove unknown breakpoint type. : {!r}".format(__name__, cls.__name__, bp.__class__))
        cls.rm_command(target, id)
        cls.__rm_cache(id)
        cls.__rm_address(bp)
        cls.__expression__.pop(key)
        cls.__function__.pop(key)
        return target.BreakpointDelete(bp.GetID()) if isinstance(bp, lldb.SBBreakpoint) else target.DeleteWatchpoint(bp.GetID())

    @classmethod
    def repr(cls, id):
        key, bp = cls.cache[id], cls.get(id)
        addr, size = cls.__location(bp)
        expr = cls.__expression__.get(key, None)
        if isinstance(expr, list):
            expr = ' -- ' + ';'.join(expr)
        elif expr is None:
            expr = ''
        else:
            expr = ' -- ' + repr(expr)
        return '0x{:x}:+{:d} -- {{{:s}}}'.format(addr, size, 'enabled' if bp.IsEnabled() else 'disabled') + expr

    class frontend(object):
        def __getattr__(self, name):
            return Breakpoint.__function__[name]
    frontend = frontend()

### command definitions
@Command('lm')
class list_modules(DebuggerCommand):
    context = lldb.SBTarget

    help = argparse.ArgumentParser(prog='lm', description='list all modules that match the specified glob')
    help.add_argument('-I', action='store_false', dest='ignorecase', default=True, help='case-sensitive matching')
    help.add_argument('-a', action='store_true', dest='all', default=False, help='list all modules, included ones that are not loaded yet.')
    help.add_argument('glob', action='store', default='*', help='glob to match module names with')

    @staticmethod
    def command(target, args):
        for res in Module.list(target, args.glob, all=args.all, ignorecase=args.ignorecase):
            print res
        return

@Command('ls')
class list_symbols(DebuggerCommand):
    context = lldb.SBTarget

    help = argparse.ArgumentParser(prog='ls', description='list all symbols that match the specified glob against a module with it\'s symbols')
    help.add_argument('-I', action='store_false', dest='ignorecase', default=True, help='case-sensitive matching')
    help.add_argument('-a', action='store_true', dest='all', default=False, help='list all symbols, including ones that are from unloaded modules.')
    help.add_argument('glob', action='store', default='*', help='glob to match symbol names with')

    @staticmethod
    def command(target, args):
        for res in Symbol.list(target, args.glob, all=args.all, ignorecase=args.ignorecase):
            print res
        return

#@Command('gvars')
class list_globals(DebuggerCommand):
    context = lldb.SBProcess
    @staticmethod
    def command(target, args):
        raise NotImplementedError   # FIXME

#@Command('lvars')
class list_locals(DebuggerCommand):
    context = lldb.SBFrame
    @staticmethod
    def command(frame, args):
        frame.vars
        raise NotImplementedError   # FIXME

#@Command('avars')
class list_arguments(DebuggerCommand):
    context = lldb.SBFrame
    @staticmethod
    def command(frame, args):
        frame.args
        raise NotImplementedError   # FIXME

#@Command('ln')
class list_near(DebuggerCommand):
    context = lldb.SBTarget
    @staticmethod
    def command(target, args):
        # FIXME: search through all symbols for the specified address
        raise NotImplementedError

class show_regs(DebuggerCommand):
    flags, context = Flags.RequiresRegContext, lldb.SBFrame

    flagbits = [
        (1, ["CF", "NC"]),
        (2, ["PF", "NP"]),
        (4, ["AF", "NA"]),
        (8, ["ZF", "NZ"]),
        (16, ["SF", "NS"]),
        (32, ["TF", "NT"]),
        (64, ["IF", "NI"]),
        (128, ["DF", "ND"]),
        (256, ["OF", "NO"]),
        (512, ["IOPL", ""]),
        (1024, ["NT", ""]),
        (2048, ["", ""]),
        (4096, ["RF", ""]),
        (8192, ["VM", ""]),
    ]

    @staticmethod
    def regs32(regs):
        res = []
        res.append("[eax: 0x%08x] [ebx: 0x%08x] [ecx: 0x%08x] [edx: 0x%08x]"% (regs['eax'], regs['ebx'], regs['ecx'], regs['edx']))
        res.append("[esi: 0x%08x] [edi: 0x%08x] [esp: 0x%08x] [ebp: 0x%08x]"% (regs['esi'], regs['edi'], regs['esp'], regs['ebp']))
        return '\n'.join(res)

    @staticmethod
    def eflags(regs):
        fl, names = regs['eflags'], (3, 4, 8, 0, 7, 6)
        res = (v[1][0 if fl & v[0] else 1] for v in map(show_regs.flagbits.__getitem__, names))
        return '[eflags: %s]'% ' '.join(res)

    @staticmethod
    def regs64(regs):
        res = []
        res.append("[rax: 0x%016lx] [rbx: 0x%016lx] [rcx: 0x%016lx]"% (regs['rax'], regs['rbx'], regs['rcx']))
        res.append("[rdx: 0x%016lx] [rsi: 0x%016lx] [rdi: 0x%016lx]"% (regs['rdx'], regs['rsi'], regs['rdi']))
        res.append("[rsp: 0x%016lx] [rbp: 0x%016lx] [ pc: 0x%016lx]"% (regs['rsp'], regs['rbp'], regs['rip']))
        res.append("[ r8: 0x%016lx] [ r9: 0x%016lx] [r10: 0x%016lx]"% (regs['r8'],  regs['r9'],  regs['r10']))
        res.append("[r11: 0x%016lx] [r12: 0x%016lx] [r13: 0x%016lx]"% (regs['r11'], regs['r12'], regs['r13']))
        res.append("[r14: 0x%016lx] [r15: 0x%016lx] [efl: 0x%016lx]"  % (regs['r14'], regs['r15'], regs['rflags']))
        return '\n'.join(res)

    @staticmethod
    def rflags(regs):
        fl, names = regs['rflags'], (3, 4, 8, 0, 7, 6)
        res = (v[1][0 if fl & v[0] else 1] for v in map(show_regs.flagbits.__getitem__, names))
        return '[rflags: %08x %s]'% (((fl & 0xffffffff00000000) >> 32), ' '.join(res))

    @staticmethod
    def command(frame, args):
        target = frame.GetThread().GetProcess().GetTarget()
        bits = target.GetAddressByteSize() * 8
        res = Register(frame).general()

        print('-=[registers]=-')
        if bits == 32:
            print(show_regs.regs32(res))
            print(show_regs.eflags(res))
        elif bits == 64:
            print(show_regs.regs64(res))
            print(show_regs.rflags(res))
        else: raise NotImplementedError(bits)

class show_stack(DebuggerCommand):
    flags, context = Flags.RequiresRegContext, lldb.SBFrame
    @staticmethod
    def command(frame, args):
        t = frame.GetThread().GetProcess().GetTarget()
        bits = t.GetAddressByteSize() * 8
        res = Register(frame).general()
        print('-=[stack]=-')
        if bits == 32:
            print(Target.hexdump(t, res['esp'], Options.here_rows[0], 'I'))
        elif bits == 64:
            print(Target.hexdump(t, res['rsp'], Options.here_rows[0], 'L'))
        else: raise NotImplementedError(bits)

class show_code(DebuggerCommand):
    context = lldb.SBFrame
    @staticmethod
    def command(frame, args):
        t = frame.GetThread().GetProcess().GetTarget()
        regs = Register(frame)
        pc = regs['rip']    # FIXME: would be nice to properly determine the pc based on arch

        bcount = int(math.floor(float(Options.here_rows[1]) / 2))
        fcount = int(math.ceil(float(Options.here_rows[1]) / 2))

        backwards = Target.disassemble_up(t, pc, bcount)
        forwards = Target.disassemble(t, pc, fcount)

        print('-=[disassembly]=-')
        # FIXME: although it'd be proper to grab the address and disassemble it,
        #        lldb uses SBFrame.Disassemble to display the current pc
        #        and it includes no option to specify the assembler flavor.
        # lldb.debugger.GetCommandInterpreter().HandleCommand("disassemble  --start-address=$pc --count={:d} -F {:s}".format(Options.here_rows[1], Options.syntax), None)
        res = lldb.SBCommandReturnObject();
        lldb.debugger.GetCommandInterpreter().HandleCommand("disassemble -f -F {:s}".format(Options.syntax), res);
        # print res.GetOutput(); 
        x = res.GetOutput().split("\n")
        count = 0
        back = Options.backward_disassembly
        fwd = Options.forward_disassembly
        for i in x:
            if "->" in i:
                break
            count += 1

        for i in range(count-back, count+fwd):
            try:
                print x[i]
            except:
                continue

@Command('address')
class mem_prot(DebuggerCommand):
    flags, context = Flags.ProcessMustBeLaunched, lldb.SBProcess
    mem_map = {}

    @classmethod
    def query(cls, addr):
        for i in cls.mem_map:
            if addr in range(int(i[0], 16), int(i[1], 16)):
                return ((i[0], i[1]), cls.mem_map[i])

    @classmethod
    def load_map(cls, process):
        pid = process.GetProcessID();
        p = subprocess.Popen(['sudo','vmmap', str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        maps = out.split("\n")


        for i in maps:
            i = ' '.join(i.split())
            addrs = re.findall("[0-9a-fA-F]+-[0-9a-fA-F]+", i)
            prot = re.findall("[rwx-]+/[rwx-]+", i)
            if len(addrs) == 1 and len(prot) == 1:
                addrs = addrs[0].split("-")
                cls.mem_map[(addrs[0], addrs[1])] = prot[0]

    @classmethod
    def command(cls, process, args):
        if len(cls.mem_map) == 0:
            cls.load_map(process)

        print cls.query(int(args[0],16))

@Command('dsearch')
class dsearch(DebuggerCommand):
    context = lldb.SBFrame

    @classmethod
    def command(cls, frame, args):
        if len(args) < 3:
            return
        #FIXME
        # res = cls.result
        res = lldb.SBCommandReturnObject()
        tipe = args[0]
        if tipe == 's':
            Target.evaluate(target, args[1])
        else:
            expression = args[1]
        word = args[2]
        try:
            extra = ' '.join(args[3:])
        except IndexError:
            extra = ""  
        x = "disassemble " + tipe + " " + expression + " -F " + Options.syntax + " " + extra
        lldb.debugger.GetCommandInterpreter().HandleCommand(x , res);
        res = str(res).split("\n")[2:]
        for i in res:
            if  not re.search(r'\d', i) or word in i:
                print i

@Command('bdisas')
class bdisas(DebuggerCommand):
    # help = argparse.ArgumentParser(prog='bdisas', description='disassemble backwards from pc')
    # help.add_argument('address', action='store', type=int, nargs=1, default=None, help='address or expression to query')

    context = lldb.SBTarget

    @staticmethod
    def command(target, args):
        try:
            if len(args) == 1:
                distance = int(args[0])
            else:
                distance = Options.backward_disassembly
        except:
            distance = Options.backward_disassembly


        res = lldb.SBCommandReturnObject();
        lldb.debugger.GetCommandInterpreter().HandleCommand("disassemble -f -F {:s}".format(Options.syntax), res);
        x = res.GetOutput().split("\n")
        count = 0
        back =distance
        for i in x:
            if "->" in i:
                break
            count += 1

        for i in range(count-back, count+1):
            try:
                print x[i]
            except:
                continue



@Command('history')
class history(DebuggerCommand):
    #help = argparse.ArgumentParser(prog='history', description='malloc_history for an address')
    #help.add_argument('address', action='store', type=int, nargs=1, default=None, help='address or expression to query')

    context = lldb.SBTarget

    @staticmethod
    def command(target, args):
        if len(args) < 1:
            return
        process = lldb.debugger.GetSelectedTarget().GetProcess();
        pid = process.GetProcessID();
        address = Target.evaluate(target, args[0])
        os.system("malloc_history {0} {1}".format(pid, hex(address)))

@Command('p')
class p(DebuggerCommand):
    #help = argparse.ArgumentParser(prog='p', description='print using expression parser')
    #help.add_argument('expression', action='store', default='$sp', nargs='+',help='address expression')

    context = lldb.SBTarget

    @staticmethod
    def command(target, args):
        if len(args) < 1:
            return
        res = Target.evaluate(target, ''.join(args))
        # FIXME: display all possible output formats like in pcalc
        print '{:d} -- 0x{:x}'.format(res, res)

class hexdump(DebuggerCommand):
    context = lldb.SBTarget
    help = argparse.ArgumentParser(prog='hexdump', description='dump the data at the specifed address')
    help.add_argument('-c', '--count', dest='count', action='store', type=int, nargs=1, default=None, help='expression describing address')
    help.add_argument('expression', action='store', nargs='*', default=['$sp'], help='expression describing address')

    @classmethod
    def command(cls, target, args):
        count = Options.hex_rows if args.count is None else args.count[0]
        expr = Target.evaluate(target, ''.join(args.expression))
        print Target.hexdump(target, expr, count, cls.kind)

class itemdump(DebuggerCommand):
    context = lldb.SBTarget
    help = argparse.ArgumentParser(prog='itemdump', description='dump the data at the specifed address')
    help.add_argument('-c', '--count', dest='count', action='store', type=int, nargs=1, default=None, help='expression describing address')
    help.add_argument('expression', action='store', nargs='*', default=['$sp'], help='expression describing address')

    @classmethod
    def command(cls, target, args):
        count = Options.rows if args.count is None else args.count[0]
        expr = Target.evaluate(target, ''.join(args.expression))
        print Target.itemdump(target, expr, count, cls.kind)

class binarydump(DebuggerCommand):
    flags, context = Flags.ProcessMustBePaused, lldb.SBTarget

    help = argparse.ArgumentParser(prog='itemdump', description='dump the data at the specifed address')
    help.add_argument('-c', '--count', dest='count', action='store', type=int, nargs=1, default=None, help='expression describing address')
    help.add_argument('expression', action='store', nargs='*', default=['$sp'], help='expression describing address')

    @classmethod
    def command(cls, target, args):
        count = Options.rows if args.count is None else args.count[0]
        expr = Target.evaluate(target, ''.join(args.expression))
        print Target.binarydump(target, expr, count, cls.kind)

# FIXME: fix up the help documentation for each of these
@Command('db')
class dump_byte(hexdump):
    kind = 'B'

@Command('dw')
class dump_word(hexdump):
    kind = 'H'

@Command('dd')
class dump_dword(hexdump):
    kind = 'I'

@Command('dq')
class dump_qword(hexdump):
    kind = 'L'

@Command('df')
class dump_float(itemdump):
    kind = 'f'

@Command('dD')
class dump_double(itemdump):
    kind = 'd'

# FIXME: check that this actually works
@Command('dyb')
class dump_binary_byte(binarydump):
    kind = 'B'

@Command('dyw')
class dump_binary_word(binarydump):
    kind = 'H'

@Command('dyd')
class dump_binary_dword(binarydump):
    kind = 'I'

@Command('dyq')
class dump_binary_qword(binarydump):
    kind = 'L'

@Command('h')
class show(DebuggerCommand):
    flags = Flags.RequiresRegContext | Flags.RequiresFrame | Flags.RequiresTarget | Flags.RequiresProcess | Flags.RequiresThread
    context = lldb.SBFrame

    @staticmethod
    def command(frame, args):
        show_regs.command(frame, args)
        print('')
        show_stack.command(frame, args)
        print ""
        show_code.command(frame, args)

@Command('maps')
class show_maps(DebuggerCommand):
    ''' maps [pid]  - returns map of process address space '''
    context = lldb.SBProcess
    flags = Flags.ProcessMustBeLaunched | Flags.ProcessMustBePaused
    @staticmethod
    def command(process, args):
        process = lldb.debugger.GetSelectedTarget().GetProcess();
        pid = process.GetProcessID();
        p = subprocess.Popen(['sudo','vmmap', str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        print out

@Command('cwd')
class getcwd(DebuggerCommand):
    context = lldb.SBTarget
    flags = Flags.ProcessMustBeLaunched
    @staticmethod
    def command(target, _):
        li = target.GetLaunchInfo()
        print(li.GetWorkingDirectory())

@Command('ba')
class breakpoint_code(DebuggerCommand):
    help = argparse.ArgumentParser(prog='ba', description='set a breakpoint when the specified address is accessed')
    help.add_argument('-c', action='store', dest='commands', default=[], help='commands to execute')
    # FIXME: make this next argument positional
    help.add_argument('-t', action='store', dest='access', type=str, default='rw', help='break on r, w, or r/w access')
    help.add_argument('-s', action='store', dest='size', type=int, default=1, help='memory size')
    help.add_argument('expression', action='store', default='$sp', help='address expression')

    context = lldb.SBTarget
    @staticmethod
    def command(target, args):
        id = Breakpoint.add_access(target, ' '.join(args.expression), args.size, args.access)
        print "Successfully added watchpoint #{:d}".format(id)

@Command('bp')
class breakpoint_code(DebuggerCommand):
    help = argparse.ArgumentParser(prog='bp', description='set a breakpoint at the specified address')
    help.add_argument('-c', action='store', dest='commands', default=[], help='commands to execute')
    help.add_argument('expression', action='store', nargs='+', default='$pc', help='address expression')

    context = lldb.SBTarget
    @staticmethod
    def command(target, args):
        id = Breakpoint.add_execute(target, ' '.join(args.expression))
        # FIXME: add commands
        print "Successfully added breakpoint #{:d}".format(id)

@Command('bc')
class breakpoint_delete(DebuggerCommand):
    help = argparse.ArgumentParser(prog='bc', description='remove the specified breakpoints')
    help.add_argument('breakpoint', action='store', nargs='+', help='range or list of breakpoints')

    context = lldb.SBTarget
    @staticmethod
    def command(target, args):
        count = 0
        for i in args.breakpoint:
            i = int(i)
            print 'Removing #{:d} -- {:s}'.format(i, Breakpoint.repr(i))
            Breakpoint.remove(target, i)
            count += 1
        print "Successfully removed {:d} breakpoints.".format(count)

@Command('bl')
class breakpoint_list(DebuggerCommand):
    context = lldb.SBTarget
    @staticmethod
    def command(target, args):
        # FIXME: allow one to select which breakpoints to list
        for i, _ in Breakpoint.enumerate():
            print '[{:d}] {:s}'.format(i, Breakpoint.repr(i))
        return

@Command('be')
class breakpoint_enable(DebuggerCommand):
    help = argparse.ArgumentParser(prog='be', description='enable the specified breakpoint')
    help.add_argument('breakpoint', action='store', nargs='+', help='range or list of breakpoints')
    
    context = lldb.SBTarget
    @staticmethod
    def command(target, args):
        # FIXME: convert args.breakpoint from a range into a list
        for i in map(int, args.breakpoint):
            Breakpoint.enable(i)
            print '[{:d}] {:s}'.format(i, Breakpoint.repr(i))
        return

@Command('bd')
class breakpoint_disable(DebuggerCommand):
    help = argparse.ArgumentParser(prog='be', description='disable the specified breakpoint')
    help.add_argument('breakpoint', action='store', nargs='+', help='range or list of breakpoints')
    
    context = lldb.SBTarget
    @staticmethod
    def command(target, args):
        # FIXME: convert args.breakpoint from a range into a list
        for i in map(int, args.breakpoint):
            Breakpoint.disable(i)
            print '[{:d}] {:s}'.format(i, Breakpoint.repr(i))
        return
