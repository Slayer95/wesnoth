import re
import pywmlx.state.machine
from pywmlx.state.state import State
import pywmlx.nodemanip
import pywmlx.tracing
from pywmlx.wmlerr import wmlerr



class WmlIdleState:
    def __init__(self):
        self.regex = None
        self.iffail = None

    def run(self, xline, lineno, match):
        _nextstate = 'wml_define'
        if pywmlx.state.machine._pending_wmlstring is not None:
            pywmlx.state.machine._pending_wmlstring.store()
            pywmlx.state.machine._pending_wmlstring = None
        m = re.match(r'\s*$', xline)
        if m:
            xline = None
            _nextstate = 'wml_idle'
        return (xline, _nextstate) # 'wml_define'



# In fact, Wesnoth's engine expands macros in the preprocessor step.
# Therefore, the input below ran through wmlxgettext should output
#
# msgid "Hello, world."
# msgstr ""
#
# # define GREET MODE WHOM
# [{MODE}]
#     {MODE} = _ "Hello, {WHOM}."
# [/{MODE}]
# # enddef
#
# {GREET message world}
#
# To accomplish that through all macro calls and subcalls, we identify
# three types of macro calls according to their context.
# A. Inside translatable strings.
# B. Inside macro definitions, but not inside a string.
# C. Every other macro call (top level).
#
# The simplest case is that macro type A is called directly by
# a single macro type C. In that case, we:
# 1. Identify the parameter index "n" in the definition of macro C,
#    associated with the call of macro A.
# 2. Substitute the nth parameter of macro C into the string containing
#    macro call A.
#
# There are several factors that complicate it:
# 1. There may be one or more macros of type B. We need to track their
#    parameters as well.
# 2. There may be more than one macro of type C. Each of them represents
#    a new string in the output.
# 3. It's possible the parameters of macro(s) type B and C aren't a 1:1
#    match.
# 4. Since Wesnoth 1.13.7, named optional macro parameters are available.
#    through the directive #arg
# 5. Macros may be deleted with #undef and later redefined.
#
# For example, let
#
# # define MOODY_GREET MODE QUALIFIER WHOM
#   {GREET {MODE} (very {QUALIFIER} {WHOM})}
# # enddef
#
# {MOODY_GREET message good world}
# {MOODY_GREET message bad world}
#
# We know that GREET's relevant parameter is the second, and it's affected by
# the second and third parameters of MOODY_GREET. Fortunately, MOODY_GREET has
# a finite universe of possible parameters, so we iterate through all of them
# in a cartesian product fashion, and we get
#
# msgid "Hello, very good world."
# msgstr ""
#
# msgid "Hello, very bad world."
# msgstr ""
#
# Note that $substitutions are bad practice for localizable strings,
# as the translator will only be able to relocate the variable, and not
# act according to their possible values. Many languages have lots of
# conditional declensions, which warrant exhausting all combinations.
# Those *are* provided by macros.
#
#
# New strategy:
# 1. Identify all strings which require preprocessing, and their textdomain.
# 2. Identify type-C macros that contain such strings in their expansions.
# 3. Identify files with such type-C macros, and with the same textdomain.
# 4. Use wmlparser3.py to preprocess those files.
#    Parser()
#    import wesnoth.wmlparser3.Parser as Parser
#    p = Parser()
#    p.preprocess(defines: string[])
#
# 6. Run those files through pywmlx extractor.
#
# Preprocessor output is awful
# New new strategy:
# 1. Identify all strings which require preprocessing, as well as their
#    associated textdomain, reference (file name, line number), and
#    parent macro definition.
#
# 2. Copy cfg files with candidate strings to a temp dir.
# 3. Use wesnoth.wmltools3 to parse macro definitions and callsites on the temp dir.
#    If any of the macros from (1) is non-local, fall back to 4. Otherwise, go to 5.
# 4. Use wesnoth.wmltools3 to parse macro definitions and callsites on the entire addon.
#    Considerations
#    4.1 Note whether there's an #undef in the same file (i.e whether 
#        the macro is local or global).
#    4.2. Note whether the macro contains quote marks or WML (error out if so.)
#    4.3. Note whether the macro contains conditional directives and which.
# 
# 5. Recursively identify all macro callsites with expansions that include
#    strings in (1).
# 6. Propagate macro parameters and evaluate the strings in (1).
#
class WmlDefineState:
    def __init__(self):
        self.regex = re.compile('\s*#(define[ |\t][^\n]+|enddef|\s+wmlxgettext:\s+)', re.I)
        self.iffail = 'wml_checkdom'

    def run(self, xline, lineno, match):
        directive = match.group(1).upper()

        if directive.startswith('DEFINE '):
            # define
            
            xline = None
            pywmlx.state.machine._pending_wmacroname = directive[7:].split(" ", 1)[0]
            pywmlx.state.machine._pending_wmacroline = lineno
        elif directive == 'ENDDEF':
            # enddef
            xline = None
            if pywmlx.state.machine._pending_wmacroname is not None:
                pywmlx.state.machine._pending_wmacroname = None
                pywmlx.state.machine._pending_wmacroline = None

            else:
                err_message = ("found an #enddef, but no macro definition " +
                               "is pending. Perhaps you forgot to put a " +
                               "#define somewhere?")
                finfo = pywmlx.nodemanip.fileref + ":" + str(lineno)
                wmlerr(finfo, err_message)
        else:
            # wmlxgettext: {WML CODE}
            xline = xline [ match.end(): ]
        return (xline, 'wml_idle')



class WmlCheckdomState:
    def __init__(self):
        self.regex = re.compile(r'\s*#textdomain\s+(\S+)', re.I)
        self.iffail = 'wml_checkpo'

    def run(self, xline, lineno, match):
        pywmlx.state.machine._currentdomain = match.group(1)
        xline = None
        return (xline, 'wml_idle')



class WmlCheckpoState:
    def __init__(self):
        rx = r'\s*#\s*(wmlxgettext|po-override|po):\s+(.+)'
        self.regex = re.compile(rx, re.I)
        self.iffail = 'wml_comment'

    def run(self, xline, lineno, match):
        if match.group(1) == 'wmlxgettext':
            xline = match.group(2)
        # on  #po: addedinfo
        elif match.group(1) == "po":
            xline = None
            if pywmlx.state.machine._pending_addedinfo is None:
                pywmlx.state.machine._pending_addedinfo = [ match.group(2) ]
            else:
                pywmlx.state.machine._pending_addedinfo.append(match.group(2))
        # on -- #po-override: overrideinfo
        elif pywmlx.state.machine._pending_overrideinfo is None:
            pywmlx.state.machine._pending_overrideinfo = [ match.group(2) ]
            xline = None
        else:
            pywmlx.state.machine._pending_overrideinfo.append(match.group(2))
            xline = None
        return (xline, 'wml_idle')



class WmlCommentState:
    def __init__(self):
        self.regex = re.compile(r'\s*#.+')
        self.iffail = 'wml_str02'

    def run(self, xline, lineno, match):
        xline = None
        return (xline, 'wml_idle')



# On WML you can also have _ << translatable string >>, even if quite rare
# This is considered here as "WML string 02" since it is a rare case.
# However, for code safety, it is evaluated here before evaluating tags, and
# before string 1. Unlike all other strings, this will be evaluated ONLY if
# translatable, to avoid possible conflicts with WmlGoLuaState (and to prevent
# to make that state unreachable).
# In order to ensure that the order of sentences will be respected, the regexp
# does not match if " is found before _ <<
# In this way the WmlStr01 state (wich is placed after) can be reached and the
# sentence will not be lost.
# WARNING: This also means that it is impossible to capture any wmlinfo which
#          uses this kind of translatable string
#          example: name = _ <<Name>>
#          in that case the string "name" will be captured, but the wmlinfo
#          name = Name will be NOT added to automatic informations.
#          This solution is necessary, since extending the workaround
#          done for _ "standard translatable strings" to _ << wmlstr02 >>
#          can introduce serious bugs
class WmlStr02:
    def __init__(self):
        rx = r'[^"]*_\s*<<(?:(.*?)>>|(.*))'
        self.regex = re.compile(rx)
        self.iffail = 'wml_tag'

    def run(self, xline, lineno, match):
        # if will ever happen 'wmlstr02 assertion error' than you could
        # turn 'mydebug' to 'True' to inspect what exactly happened.
        # However this should be never necessary
        mydebug = False
        _nextstate = 'wml_idle'
        loc_translatable = True
        loc_multiline = False
        loc_string = None
        # match group(1) exists, so it is a single line string
        # (group(2) will not exist, than)
        if match.group(1) is not None:
            loc_multiline = False
            loc_string = match.group(1)
            xline = xline [ match.end(): ]
        # match.group(2) exists, so it is a multi-line string
        # (group(1) will not exist, than)
        elif match.group(2) is not None:
            loc_multiline = True
            loc_string = match.group(2)
            _nextstate = 'wml_str20'
            xline = None
        else:
            if mydebug:
                err_message = ("wmlstr02 assertion error (DEBUGGING)\n" +
                               'g1: ' + str(match.group(1)) + '\n' +
                               'g2: ' + str(match.group(2)) )
                finfo = pywmlx.nodemanip.fileref + ":" + str(lineno)
                wmlerr(finfo, err_message)
            else:
                wmlerr('wmlxgettext python sources',
                   'wmlstr02 assertion error\n'
                   'please report a bug if you encounter this error message')
        pywmlx.state.machine._pending_wmlstring = (
            pywmlx.state.machine.PendingWmlString(
                lineno, loc_string, loc_multiline, loc_translatable, israw=True
            )
        )
        return (xline, _nextstate)



class WmlTagState:
    def __init__(self):
        # this regexp is discussed in depth in Source Documentation, chapter 6
        rx = r'\s*(?:[^"]+\(\s*)?\[\s*([\/+-]?)\s*([A-Za-z0-9_]+)\s*\]'
        self.regex = re.compile(rx)
        self.iffail = 'wml_getinf'

    def run(self, xline, lineno, match):
        # xdebug = open('./debug.txt', 'a')
        # xdebug_str = None
        if match.group(1) == '/':
            closetag = '[/' + match.group(2) + ']'
            pywmlx.nodemanip.closenode(closetag,
                                       pywmlx.state.machine._dictionary,
                                       lineno)
            if closetag == '[/lua]':
                pywmlx.state.machine._pending_luafuncname = None
                pywmlx.state.machine._on_luatag = False
            # xdebug_str = closetag + ': ' + str(lineno)
        else:
            opentag = '[' + match.group(2) + ']'
            pywmlx.nodemanip.newnode(opentag)
            if(opentag == '[lua]'):
                pywmlx.state.machine._on_luatag = True
            # xdebug_str = opentag + ': ' + str(lineno)
        # print(xdebug_str, file=xdebug)
        # xdebug.close()
        pywmlx.state.machine._pending_addedinfo = None
        pywmlx.state.machine._pending_overrideinfo = None
        xline = xline [ match.end(): ]
        return (xline, 'wml_idle')



class WmlGetinfState:
    def __init__(self):
        rx = ( r'\s*(speaker|id|role|description|condition|type|race)' +
               r'\s*=\s*(.*)' )
        self.regex = re.compile(rx, re.I)
        self.iffail = 'wml_str01'
    def run(self, xline, lineno, match):
        _nextstate = 'wml_idle'
        if '"' in match.group(2):
            _nextstate = 'wml_str01'
            pywmlx.state.machine._pending_winfotype = match.group(1)
        else:
            loc_wmlinfo = match.group(1) + '=' + match.group(2)
            xline = None
            pywmlx.nodemanip.addWmlInfo(loc_wmlinfo)
        return (xline, _nextstate)



class WmlStr01:
    def __init__(self):
        rx = r'(?:[^"]*?)\s*(_?)\s*"((?:""|[^"])*)("?)'
        self.regex = re.compile(rx)
        self.iffail = 'wml_golua'

    def run(self, xline, lineno, match):
        _nextstate = 'wml_idle'
        loc_translatable = True
        if match.group(1) == "":
            loc_translatable = False
        loc_multiline = False
        if match.group(3) == "":
            xline = None
            loc_multiline = True
            _nextstate = 'wml_str10'
        else:
            xline = xline [ match.end(): ]
        pywmlx.state.machine._pending_wmlstring = (
            pywmlx.state.machine.PendingWmlString(
                lineno, match.group(2), loc_multiline, loc_translatable, israw=False
            )
        )
        return (xline, _nextstate)



# well... the regex will always be true on this state, so iffail will never
# be executed
class WmlStr10:
    def __init__(self):
        self.regex = re.compile(r'((?:""|[^"])*)("?)')
        self.iffail = 'wml_str10'

    def run(self, xline, lineno, match):
        _nextstate = None
        pywmlx.state.machine._pending_wmlstring.addline( match.group(1) )
        if match.group(2) == "":
            _nextstate = 'wml_str10'
            xline = None
        else:
            _nextstate = 'wml_idle'
            xline = xline [ match.end(): ]
        return (xline, _nextstate)



class WmlStr20:
    def __init__(self):
        self.regex = None
        self.iffail = None

    def run(self, xline, lineno, match):
        realmatch = re.match(r'(.*?)>>', xline)
        _nextstate = 'wml_str20'
        if realmatch:
            pywmlx.state.machine._pending_wmlstring.addline(
                realmatch.group(1) )
            xline = xline [ realmatch.end(): ]
            _nextstate = 'wml_idle'
        else:
            pywmlx.state.machine._pending_wmlstring.addline(xline)
            xline = None
            _nextstate = 'wml_str20'
        return (xline, _nextstate)



# Only if the symbol '<<' is found inside a [lua] tag, then it means we are
# actually starting a lua code.
# It can happen that WML uses the '<<' symbol in a very different context
# wich has nothing to do with lua, so switching to the lua states in that
# case can lead to problems.
# This happened on the file data/gui/default/widget/toggle_button_orb.cfg
# on wesnoth 1.13.x, where there is this line inside the first [image] tag:
#
#     name = "('buttons/misc/orb{STATE}.png" + <<~RC(magenta>{icon})')>>
#
# In that case, after 'name' there is a WML string
# "('buttons/misc/orb{STATE}.png"
# And after that you find a concatenation with a literal string
# <<~RC(magenta>{icon})')>>
#
# That second string has nothing to do with lua, and, most importantly, if
# it is parsed with lua states, it returns an error... why?
# Simply because of the final ' symbol, wich is a valid symbol, in lua, for
# opening a new string; but, in that case, there is not an opening string,
# but a ' symbol that must be used literally.
#
# This is why we use a global var _on_luatag in state.py wich is usually False.
# it will be set to True only when opening a lua tag (see WmlTagState)
# it will be set to False again when the lua tag is closed (see WmlTagState)
class WmlGoluaState:
    def __init__(self):
        self.regex = re.compile(r'.*?<<\s*')
        self.iffail = 'wml_final'

    def run(self, xline, lineno, match):
        if pywmlx.state.machine._on_luatag:
            xline = xline [ match.end(): ]
            return (xline, 'lua_idle')
        else:
            return (xline, 'wml_final')



class WmlFinalState:
    def __init__(self):
        self.regex = None
        self.iffail = None

    def run(self, xline, lineno, match):
        xline = None
        if pywmlx.state.machine._pending_wmlstring is not None:
            pywmlx.state.machine._pending_wmlstring.store()
            pywmlx.state.machine._pending_wmlstring = None
        return (xline, 'wml_idle')



def setup_wmlstates():
    for statename, stateclass in [ ('wml_idle', WmlIdleState),
                                   ('wml_define', WmlDefineState),
                                   ('wml_checkdom', WmlCheckdomState),
                                   ('wml_checkpo', WmlCheckpoState),
                                   ('wml_comment', WmlCommentState),
                                   ('wml_str02', WmlStr02),
                                   ('wml_tag', WmlTagState),
                                   ('wml_getinf', WmlGetinfState),
                                   ('wml_str01', WmlStr01),
                                   ('wml_str10', WmlStr10),
                                   ('wml_str20', WmlStr20),
                                   ('wml_golua', WmlGoluaState),
                                   ('wml_final', WmlFinalState)]:
        st = stateclass()
        pywmlx.state.machine.addstate(statename,
            State(st.regex, st.run, st.iffail) )
