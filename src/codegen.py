# CODEGEN
from enum import Enum,unique
import re
import os
import util as u
from util import die


@unique
class Tok(Enum):
    # IMPORTANT: order determines precedence. Higher will be favored in match
    MACROHEAD = re.compile(r'%(\w+\??)')
    WHITESPACE= re.compile(r'(\s+)')
    COMMA     = re.compile(r',')
    COLON     = re.compile(r':')
    FLAG     = re.compile(r'-(\w+)')
    PERIOD     = re.compile(r'\.')
    EQ     = re.compile(r'=')
    SH_LBRACE     = re.compile(r'sh{')
    LPAREN    = re.compile(r'\(')
    RPAREN    = re.compile(r'\)')
    LBRACE    = re.compile(r'{')
    RBRACE    = re.compile(r'}')
    LBRACKET  = re.compile(r'\[')
    RBRACKET  = re.compile(r'\]')
    ESCQUOTE2    = re.compile(r'\\\"')
    ESCQUOTE1    = re.compile(r'\\\'')
    QUOTE2    = re.compile(r'\"')
    QUOTE1    = re.compile(r'\'')
    DOLLARESC = re.compile(r'\$\$')
    DOLLARVAR = re.compile(r'\$(\w+)')
    IDENTIFIER= re.compile(r'(\w+)')
    UNKNOWN   = re.compile(r'(.)')
    def __repr__(self):
        if self.name == "SH_LBRACE":
            return u.mk_green(self.name)
        if self.name == "MACROHEAD":
            return u.mk_purple(self.name)
        if self.name == "DOLLARVAR":
            return u.mk_yellow(self.name)
        if self.name == "WHITESPACE":
            return u.mk_gray("WS")
        return self.name

macro_argc = {
    'argc':0,
    'argv':0,
    'basepath':1,
    'blue':1,
    'cat':1,
    'cd':1,
    'die':1,
    'direxists?':1,
    'exists?':1,
    'exists?':1,
    'fsize':1,
    'fullpath':1,
    'green':1,
    'head':1,
    'ls':0,
    'mkdir':1,
    'mkdirp':1,
    'p':1,
    'parse':2,
    'parselines':2,
    'parselines1':2,
    'purple':1,
    'pwd':0,
    'red':1,
    'yellow':1,
}
def get_macro_argc(name):
    return macro_argc[name]

def has_special_args(name): # returns boolean
    return name in ['parse', 'parselines', 'parselines1']

class Token:
    def __init__(self,tok,data,verbatim):
        self.tok=tok
        self.data=data
        self.verbatim=verbatim
    def __repr__(self):
        return self.tok.__repr__()


# turns a string into a list of (Token,data)
# where data holds the first capturing group
def tokenize(s):
    if s == '': return []
    for i in list(Tok):
        name = i.name
        match = i.value.match(s)
        if match is None: continue
        remaining = s[match.end():]
        grps = match.groups()
        if len(grps) == 0:
            data = ''
        else:
            data = grps[0]
        return [Token(i,data,match.group())] + tokenize(remaining)
    print("Error: Can't tokenize. This should be impossible because UNKNOWN token should be registered")
    exit(1)

#def p(tokenlist):
#    print(' '.join([t.__repr__() for (t,data) in tokenlist]))


class AtomCompound:
    def __init__(self):
        self.data=[]
    def add(self,atom):
        #magenta("adding "+str(atom)+" to "+str(self.__class__))
        self.data.append(atom)
    def __repr__(self):
        return self.pretty()
    def __str__(self):
        return self.__repr__()
    def __bool__(self):  # important in macroize(). None == False and any atom == True
        return True
    # does not recurse. removes top level whitespace of an AtomCompound
    def rm_whitespace(self):
        self.data = list(filter(lambda a: not is_tok(a,Tok.WHITESPACE),self.data))
    def pretty(self,depth=0):
        colorer = u.mk_cyan
        name = self.__class__.__name__
        if isinstance(self,AtomMacro):
            colorer = u.mk_purple
            name = self.name
        contents = colorer('[') + ' '.join([x.pretty(depth+1) for x in self.data]) + colorer(']')
        return '\n' + '\t'*depth + colorer(name) + contents
    def __iter__(self):
        yield from self.data
    def __getitem__(self, key):
        return self.data[key]
    def __setitem__(self, key, value):
        self.data.__setitem__(key,value)
    def __delitem__(self, key):
        self.data.__delitem__(key)
    def __len__(self):
        return len(self.data)

# may want to give custom codegen bodies later
# wow super dumb python bug: never have __init__(self,data=[]) bc by putting '[]' in the argument only ONE copy exists of it for ALL instances of the class. This is very dumb but in python only one instance of each default variable exists and it gets reused.
class AtomMaster(AtomCompound):
    def gentext(self):
        return ''.join([x.gentext() for x in self])
class AtomSH(AtomCompound):
    def gentext(self):
        body = ''.join([x.gentext() for x in self]).replace('"','\\"').replace('\1CONSERVEDQUOTE\1','"') # escape any quotes inside
        return 'backend.sh("' + body + '",BACKEND_PIPE)'
class AtomQuote(AtomCompound):
    def __init__(self,tok):
        super().__init__()
        self.tok = tok #to keep track of ' vs "
    def gentext(self):
        return self.tok.verbatim + ''.join([x.gentext() for x in self]) + self.tok.verbatim

class AtomParens(AtomCompound):
    def gentext(self):
        return '('+''.join([x.gentext() for x in self]) + ')'

class AtomMacro(AtomCompound):
    def __init__(self,name,argc):
        super().__init__()
        self.name=name
        self.argc=argc
    def __repr__(self):
        return super().__repr__() + u.mk_red('(name='+self.name+', argc='+str(self.argc) + ')')
    def gentext(self):
        return build_call(self.name,self.data)


def assertInst(child,parent):
    if not isinstance(child,parent):
        die(str(child) + " is not an instance of " + str(parent))

class AtomTok: # not a subclass bc we don't want it to inherit add()
    def __init__(self,token):
        self.tok = token.tok
        self.data = token.data
        self.verbatim = token.verbatim
    def __repr__(self):
        return self.pretty()
    def __str__(self):
        return self.__repr__()
    def __bool__(self):
        return True
    def pretty(self,depth=0):
        if self.tok == Tok.MACROHEAD:
            return u.mk_purple(self.data)
        if self.tok == Tok.DOLLARVAR:
            return u.mk_yellow(self.data)
        if self.tok == Tok.WHITESPACE:
            return u.mk_gray('WS')
        return self.tok.name
    def gentext(self):
        return self.verbatim

class AtomDollar(AtomTok):
    def __init__(self,tok,mode):
        super().__init__(tok)
        self.mode=mode
    def gentext(self): #for dollar this is only called when NOT part of a special macro construct like idx_casts (int $1, int $3) etc
        if self.mode == 'global':
            return 'os.environ('+self.data+')'
        elif self.mode == 'interp':
            return "\"+str(locals()[\"{}\"])+\"".format(self.data).replace('"','\1CONSERVEDQUOTE\1')
        else:
            die("unrecognized mode:{}".format(self.mode))

# turn a token list into a MASTER atom containing all other atoms
def atomize1(tokenlist):
    in_sh = False
    curr_quote = None #None, Tok.QUOTE1 or Tok.QUOTE2
    brace_depth = 0
    atoms = [AtomMaster()]
    for token in tokenlist:
        t = token.tok #the Tok
        if t == Tok.DOLLARVAR and in_sh:
            as_tok = AtomDollar(token,'interp')
        elif t == Tok.DOLLARVAR and not in_sh:
            as_tok = AtomDollar(token,'global')
        else:
            as_tok = AtomTok(token)
        # IF IN QUOTE ATOM, then everything is a plain token other than the exit quote token
        if curr_quote: #highest precedence -- special rules when inside quotes
            # EXIT QUOTE ATOM?
            if t == curr_quote: #close quotation
                curr_quote = None
                assertInst(atoms[-1],AtomQuote)
                atoms[-2].add(atoms.pop())  #pop last atom onto end of second to last atom's data
            # STAY IN QUOTE ATOM
            else:
                atoms[-1].add(as_tok)
        # ENTER QUOTE ATOM?
        elif t == Tok.QUOTE1 or t == Tok.QUOTE2:
            curr_quote = t
            atoms.append(AtomQuote(token))    #start a new quote atom
        # IF IN SH, then we don't care about anything but { } counting. we leave the SH atom data as a flattened token list
        elif in_sh:
            if t == Tok.SH_LBRACE: die("SH_LBRACE inside of an sh{}")
            elif t == Tok.LBRACE:
                brace_depth += 1
            elif t == Tok.RBRACE:
                brace_depth -= 1
                # LEAVE SH
                if brace_depth == 0:
                    in_sh = False
                    assertInst(atoms[-1],AtomSH)
                    atoms[-2].add(atoms.pop())
            #STAY IN SH
            else:
                atoms[-1].add(as_tok)
        # ENTER SH?
        elif t == Tok.SH_LBRACE:
            brace_depth = 1
            in_sh = True
            atoms.append(AtomSH())
        # PARENS
        elif t == Tok.LPAREN:
            atoms.append(AtomParens())
        elif t == Tok.RPAREN:
            assertInst(atoms[-1],AtomParens)
            atoms[-2].add(atoms.pop())
        else:
            atoms[-1].add(as_tok)
    if len(atoms) != 1: die("There should only be the MASTER left in the 'atoms' list! Actual contents:"+str(atoms))
    return atoms.pop()



is_tok = lambda atom,tok: isinstance(atom,AtomTok) and atom.tok == tok

# adds in macros
def macroize(base_atom):
    #if isinstance(base_atom,

    #helper fn to tell if an AtomTok is a macro and shd be converted to an AtomMacro
    curr_macro = None
    for i,atom in enumerate(base_atom):
        # end macro creation if all args filled
        if curr_macro and len(curr_macro.data) == curr_macro.argc:
            curr_macro = None

        # Recursively macroize all parens you come across regardless of if currently building a macro
        # very importantly this CANNOT be "elif"
        if isinstance(atom,AtomParens):
            macroize(atom)

        # always ignore whitespace
        if is_tok(atom,Tok.WHITESPACE):
            continue

        # handle adding arguments to curr macro (parens, sh, quotes, or macros with argc=0)
        elif curr_macro and (isinstance(atom,AtomParens) or isinstance(atom,AtomSH) or isinstance(atom,AtomQuote)):
            curr_macro.add(atom)
            del base_atom[i]
        elif curr_macro and is_tok(atom,Tok.MACROHEAD) and get_macro_argc(atom.data) == 0:
            curr_macro.add(AtomMacro(atom.data,0))
            del base_atom[i]
        elif curr_macro and is_tok(atom,Tok.MACROHEAD) and get_macro_argc(atom.data) != 0:
            die("You must parenthesize macros of argc>0 when using them as arguments to other macros.")
        elif curr_macro and is_tok(atom,Tok.IDENTIFIER):
            curr_macro.add(atom)
            del base_atom[i]

        # enter new macro creation
        elif not curr_macro and is_tok(atom,Tok.MACROHEAD):
            name = atom.data
            base_atom[i] = AtomMacro(name,get_macro_argc(name))    # overwrite the AtomTok with a new MacroAtom
            curr_macro = base_atom[i]   #save a ref to the new MacroAtom

    if curr_macro and len(curr_macro.data) == curr_macro.argc:
        curr_macro = None
    if curr_macro:
        die("Macro did not receive enough args:"+str(curr_macro))




# returns the string for a call to a macro
# takes macro fn name (without the m_ prefix)
# also takes 'args', a list of arguments. any that are not 'str' will have .gentext() called on them.
def build_call(fname,args):
    fname = fname.replace('?','_qmark')
    if has_special_args(fname):
        args = build_special_args(fname,args) #e.g. (int $1, int $2) in parse
    def text_if_needed(x):
        return x if isinstance(x,str) else x.gentext()
    return 'backend.m_'+fname+'('+','.join([text_if_needed(x) for x in args])+')'

def build_special_args(fname,args):
    if fname in ['parse','parselines','parselines1']:
        idx_casts_tkns = args[1] # idx_casts_tkns = [ID DOLLAR COMMA ID DOLLAR COMMA ID DOLLAR COMMA ID DOLLAR COMMA]
        idx_casts_tkns.rm_whitespace()
        if len(idx_casts_tkns)%3 != 2:
            die("build_special_args() failed. Len of (int $1, int $2, ...) mod 3 should be 2 always (eg ID DOLLAR COMMA ID DOLLAR). Offending token list:{}".format(idx_casts_tkns))
        atomiter = iter(idx_casts_tkns)
        result = []
        while True:
            try:
                id = next(atomiter)
                dollar = next(atomiter)
                if not is_tok(id,Tok.IDENTIFIER): die("build_special_args() for parse/parselines/parselines1 failed. first item of every three in (int $1, int $2,...) should be an IDENTIFIER. (note: 3rd item=comma)")
                if not isinstance(dollar,AtomDollar): die("build_special_args() for parse/parselines/parselines1 failed. second item of every three in (int $1, int $2,...) should be an AtomDollar. (note: 3rd item=comma)")
                try:
                    idx = int(dollar.data)
                except:
                    die("unable to cast idx in parse/parlines/etc's format string. failed on:int({})".format(dollar.data))
                try: #this try-except is not necessary, tho its good bc it replaces a runtime error with a compiletime error even tho .__name__ shows up later which undoes this work.
                    cast = eval(id.data)
                except:
                    die("unable to eval identifier.data in parse/parlines/etc's format string. The program attempts to do eval('int') to yield the int() function to use as a caster. Failed on:eval({})".format(id.data))
                result.append((idx,cast.__name__))
                next(atomiter) # consume the comma
            except StopIteration:
                break
        args[1] = str(result)
        return args
    die('Failed to match on fname={} in build_call_special_args()'.format(fname))




def parse(line,debug=False):
    if debug:
        u.red("========================="*3)
        u.red("=Input=")
        print(line)
    tkns = tokenize(line)
    if debug:
        u.red("=Tokens=")
        print(tkns)
    a = atomize1(tkns)
    if debug:
        u.red("=Atoms=")
        print(a)
    macroize(a)
    if debug:
        u.red("=Atoms Post Macroization=")
        print(a)
    out = a.gentext()
    if debug:
        u.blue(out)
    return out


#parse("fname,linect = %parse sh{wc -l $file} (str $1, int $2)")
#parse("z = %parselines1  x (str $1, int $2)")
#parse("sh{echo \"hi \"$there\" you're the \"$one}")
#parse("if %exists? filename:")
#parse("vi_list = %parselines1 (%cat file) (int $1, int $2)")




