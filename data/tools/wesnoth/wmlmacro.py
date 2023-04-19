import itertools
import os
import re
import shlex
import sys
from .wmltools3 import CrossRef, Reference
from .wmliterator3 import WmlIterator

from pprint import PrettyPrinter
pp = PrettyPrinter(indent=4)

# Interface between macro definitions and various
# Wesnoth tools.
# By Leonardo Julca, 2023

# Default value for AST.replace()
NO_ARGS = ({}, None)

_args3 = ("A", "B", "C")
_args4 = ("A", "B", "C", "D")
GlobalWMLMacros = {
    # GlobalWMLMacros: dict<str, ReferenceLike>
    # ReferenceLike: dict<str, {args: list<str>, body: str}
    "LEFT_BRACE": [{"args": [], "body": "{"}],
    "RIGHT_BRACE": [{"args": [], "body": "}"}],
    "ON_DIFFICULTY": [{"args": _args3, "body":"{A}"}, {"args": _args3, "body":"{B}"}, {"args": _args3, "body":"{C}"}],
    "ON_DIFFICULTY4": [{"args": _args4, "body":"{A}"}, {"args": _args4, "body":"{B}"}, {"args": _args4, "body":"{C}"}, {"args": _args4, "body":"{D}"}],
}

# Universe - convenient singleton for which
# `x in Universe` is always True
# Passing it to a filter is equivalent to not filtering.
class UniversalSet:
    def __contains__():
        return True

Universe = UniversalSet()

# memoize - Memoizes a binary function with support for
# a non-hashable as second argument.
def memoize(f):
    memo = {}
    def wrapper(i, j):
        if i not in memo or memo[i][0] != j:
            memo[i] = (j, f(i, j))
        return memo[i][1]
    return wrapper

def extend_no_override(target, source):
    for key, value in source.items():
        if key in target:
            continue
        target[key] = value

# LiteralNode - fragment without own expansion semantics.
# It may be subordinated to a MacroCallNode as an argument.
#
# Properties
#  is_root - always false, used to inspect AST parse status.
#  parent - ExpandableNode or AST
#  value - the literal content of the node.
#  children - always None, used to inspect AST parse status.
class LiteralNode:
    def __init__(self, parent, value):
        self.is_root = False
        self.parent = parent
        self.value = value
        self.children = None

    def __repr__(self):
        return "LiteralNode(\"%s\")" % self.value

    def __str__(self):
        return self.value

    def get_root(self):
        parent = self.parent
        while parent.parent is not None:
            parent = parent.parent
        return parent

    def replace(self, args_set=NO_ARGS, macro_defs=None):
        return self.value

# ExpandableNode - fragment with own expansion semantics.
# It may be a parameter inside a macro definition, or a
# macro call. Discriminating between them depends on
# context information.
#
# Properties
#  is_root - always false, used to inspect AST parse status.
#  parent - ExpandableNode or AST
#  name - the name of the parameter or macro call.
#  children - a list of any macro parameters, may be empty but not None.
#  _search - index plus 1 of the last parsed closing brace for a children.

class ExpandableNode:
    def __init__(self, parent, name, start, search):
        self.is_root = False
        self.parent = parent
        self.name = name
        self.children = []
        self._search = search

    def __repr__(self):
        return "ExpandableNode([*%d children])" % len(self.children)

    def __str__(self):
        return self.replace()

    def get_root(self):
        parent = self.parent
        while not parent.is_root:
            parent = parent.parent
        return parent

    def replace(self, args_set=NO_ARGS, macro_defs=None):
        if self.name in args_set[0]:
            sub = args_set[0][self.name]
            # print("Subbed parameter %s -> %s" % (self.name, sub))
            return sub

        if macro_defs is not None:
            # TODO: Generalize macro evaluation
            assert self.name in macro_defs, ("Macro %s unknown in %s." % (self, self.get_root()))
            macro_args = macro_defs[self.name]["args"]
            result = macro_defs[self.name]["body"]
            if len(self.children) >= 3 and (macro_args is _args3 or macro_args is _args4):
                result = re.sub(r'{A}', str(self.children[0]), result)
                result = re.sub(r'{B}', str(self.children[1]), result)
                result = re.sub(r'{C}', str(self.children[2]), result)
                if len(self.children) >= 4 and macro_args == _args4:
                    result = re.sub(r'{D}', str(self.children[3]), result)
            else:
                print("Failed to parse macro call for %s. Children:" % self.name)
                raise Exception("Bad macro %s" % self.name)

            # print("Subbed macro %s -> %s" % (self, result))
            return result

        out = ["{" + self.name]
        is_first = True
        for child in self.children:
            if not is_first:
                # Whitespace between two LiteralNodes
                out.append(" ")
            out.append(child.replace(args_set, macro_defs))
            is_first = False
        return " ".join(out) + "}"

class AST:
    def __init__(self):
        self.children = []
        self.active_node = self
        self.parent = None
        self.is_root = True
        self._search = 0

    def fill_literals(self, text, end):
        assert not type(self.active_node) == str
        start = self.active_node._search
        source = text[start:end]
        if len(source) == 0:
            return

        if self.active_node.is_root:
            # Preserve whitespace
            literal_node = LiteralNode(self.active_node, source)
            self.active_node.children.append(literal_node)
        else:
            # Ignore whitespace
            # TODO: Ensure compliance with preprocessor rules.
            try:
                for literal in shlex.split(source, posix=False):
                    assert not type(self.active_node) == str
                    literal_node = LiteralNode(self.active_node, literal)
                    self.active_node.children.append(literal_node)
            except Exception as ex:
                print("Bad string: %s" % source)
                # Recover
                literal_node = LiteralNode(self.active_node, source)
                self.active_node.children.append(literal_node)

    def __repr__(self):
        return "AST([*%d children])" % len(self.children)

    def __str__(self):
        return self.replace()

    def get_root(self):
        return self

    def replace(self, args_set=NO_ARGS, macro_defs=None):
        # args_set: (dict<str, str>, Macro)
        # return: str
        out = []
        for child in self.children:
            out.append(child.replace(args_set, macro_defs))
        return "".join(out)

    @staticmethod
    def parse(input, on_macro = None):
        lines = input.split("\n")
        ast = AST()
        for state in WmlIterator(lines=lines):
            elements, _scopes = state.parseElements(state.text)
            for elem, start in elements:
                length = 1 if elem == "end of macro" else len(elem)
                end = start + length
                if elem == "end of macro" and ast.active_node.is_root:
                    continue
                if elem == "end of macro":
                    ast.fill_literals(input, start)
                    if on_macro is not None:
                        on_macro(ast.active_node)
                    ast.active_node = ast.active_node.parent
                    ast.active_node._search = end
                elif elem[0] == "{":
                    assert len(elem) > 1
                    ast.fill_literals(input, start)
                    assert not type(ast.active_node) == str
                    macro_node = ExpandableNode(ast.active_node, elem[1:], start, end)  
                    ast.active_node.children.append(macro_node)
                    ast.active_node = macro_node
                else:
                    pass
            ast.fill_literals(input, len(input))

        # print("AST parsed %s <-> %s" % (input, ast))
        return ast

    @staticmethod
    def parse_sentence_and_ids(sentence, lone_ids, complex_ids):
        # Mutates lone_ids
        # Mutates complex_ids
        def on_macro(node):
            if len(node.children) == 0:
                # Either parameters or constant macros
                lone_ids.add(node.name)
            else:
                # Definitely macros
                complex_ids.add(node.name)

        return AST.parse(sentence, on_macro)

    @staticmethod
    def parse_with_ctx(arg, in_macro_xref, used_parameters=set(), used_macros=set()):
        # Mutates used_parameters
        # Mutates used_macros
        def on_macro(node):
            if len(node.children) == 0 and \
                (node.name in in_macro_xref.args or node.name in in_macro_xref.optional_args):
                used_parameters.add(node.name)
            else:
                used_macros.add(node.name)

        return AST.parse(arg, on_macro)

    @staticmethod
    def evaluate_many_on_one(ast, args_sets_in):
        # ast: AST
        # return: list<(str, Macro|NoneType)>

        out = []
        for args_with_ctx in args_sets_in:
            sub = ast.replace(args_with_ctx)
            out.append((sub, args_with_ctx[1]))

        return out

    @staticmethod
    def evaluate_many_on_many(parameters_asts, args_sets_in):
        # - parameters_asts : dict<str, AST>
        # - args_sets_in    : list<(dict<str, str>, Macro|NoneType)>
        # - args_sets_out   : list<(dict<str, str>, Macro|NoneType)>

        args_sets_out = []
        for args_with_ctx in args_sets_in:
            assert(isinstance(args_with_ctx[0], dict))
            # assert(isinstance(args_with_ctx[1], Macro|NoneType))
            parameters_out = {}
            for parameter_name, ast in parameters_asts.items():
                parameters_out[parameter_name] = ast.replace(args_with_ctx)

            args_sets_out.append((parameters_out, args_with_ctx[1]))

        return args_sets_out


def has_brace(arg):
    return "}" in arg

# Macro - wrapper around a 3-tuple, which identifies a
# macro definition.
# Elements (name, file reference, line number)
class Macro:
    def __init__(self, name, fileref, line):
        self.name = name
        self.fileref = fileref
        self.line = line

    def __iter__(self):
        yield self.name
        yield self.fileref
        yield self.line

    def __repr__(self):
        return "Macro(\"%s\", \"%s\", %d)" % tuple(self)

    def __str__(self):
        return "%s@%s:%d" % tuple(self)

    def __eq__(self, other):
        return tuple(self) == tuple(other)

    def __getitem__(self, key):
        return tuple(self)[key]

    def __hash__(self):
        # Only use macros with relative file references
        # as dictionary keys to avoid mismatches.
        # Those are built from Macro(PoCommentedString.macro)
        # Note that CrossRef contains absolute references.
        assert not os.path.isabs(self.fileref)
        return hash(tuple(self))

    def to_abs(self, root_path):
        return Macro(self.name, os.path.normpath(os.path.join(root_path, self.fileref)), self.line)

    def to_rel(self, root_path):
        return Macro(self.name, os.path.relpath(root_path, self.fileref), self.line)

    def get_ref(self, xrefs):
        assert isinstance(xrefs, CrossRef)
        if not self.name in xrefs.xref:
            print("Macro %s not found" % self)
            return None

        for xref in xrefs.xref[self.name]:
            if xref.filename != self.fileref or xref.lineno != self.line:
                # print("Excluded %s@%s#%d" % (self.name, xref.filename, xref.lineno))
                continue

            assert isinstance(xref, Reference)
            return xref 

        return None

class CrossRefHelper:
    @staticmethod
    # get_macro_at - Given a file reference and line number,
    # return the Macro that contains it, if any.
    def get_macro_at(xrefs, fileref, lineno):
        assert(isinstance(xrefs, CrossRef))
        for macro_name in xrefs.xref.keys():
            for xref in xrefs.xref[macro_name]:
                if xref.filename != fileref:
                    continue
                if xref.lineno < lineno and lineno < xref.lineno_end:
                    return Macro(macro_name, xref.filename, xref.lineno)

        return None

    # _get_valid_macros - Given a N-tuple of macro names,
    # return a M-tuple of macro names that can be embedded in translatable strings,
    # M <= N
    @staticmethod
    @memoize
    def _get_valid_macros(input, xrefs):
        macros = []
        for name in input:
            if name in GlobalWMLMacros:
                macros.append(name)
            elif name in xrefs.xref:
                if any(map(ReferenceHelper.is_embeddable_macro, xrefs.xref[name])):
                    macros.append(name)
                else:
                    print("Macro {%s} cannot be embedded in a translatable string (only simple single-line macros may.)")

        return tuple(macros)

    # get_valid_macros - Given an unsorted iterable of macro names,
    # return a tuple of macro names that can be embedded in translatable strings.
    @staticmethod
    def get_valid_macros(input, xrefs):
        return CrossRefHelper._get_valid_macros(tuple(input), xrefs)

    # _get_macro_variants - Returns a list of tuples
    # list<(Reference|ReferenceLike, True, None)>
    @staticmethod
    def get_macro_variants(macro_names, xrefs):
        assert isinstance(xrefs, CrossRef), ("xrefs is %s" % xrefs)
        assert(type(macro_names) == tuple)

        # - xref_matrix[i][j]: Reference
        # - i matches macro_names index
        # - j discriminates definitions
        xref_matrix = []
        for name in macro_names:
            if name in xrefs.xref:
                xref_matrix.append(xrefs.xref[name])
            else:
                xref_matrix.append(GlobalWMLMacros[name])

        # product(list<Reference>, list<Reference>, ...)
        # Cartesian product that returns an iterator (`variants_matrix`) of N-tuples (`variant`),
        # such that variant[i] is a picked Reference for macro_names[i],
        # and N=len(macro_names)
        variants_matrix = itertools.product(*xref_matrix)

        variants = []
        for variant in variants_matrix:
            defs = {macro_names[i]:ref for i, ref in enumerate(variant)}
            variants.append((defs, True, None))

        # list<(Reference|ReferenceLike, True|None, None)>
        return variants

    # get_macro_replaceables - Generator function to iterate over variants with braces.
    # variants is an unsorted mutable list.
    @staticmethod
    def get_macro_replaceables(input_sentence, variants):
        # Mutates variants
        index = 0
        while index < len(variants):
            next = variants[index]
            # next: (Reference|ReferenceLike, True|None, str)
            if next[1] is None:
                # Signals that this sentence cannot be expanded anymore.
                index += 1
                continue

            if not has_brace(next[2]):
                index += 1
                continue

            last = variants.pop()
            if index != len(variants):
                assert index < len(variants)
                variants[index] = last
            else:
                # variants[index] removed in pop()
                assert next == last
                
            yield next

    @staticmethod
    def deep_replace_macros(input_sentence, variants, xrefs):
        # variants: list<Reference|ReferenceLike, True|None, str|None>

        for i, variant in enumerate(variants):
            # Seed with input_sentence
            variants[i] = (variants[i][0], variants[i][1], input_sentence)

        for defs, sentinel, sentence in CrossRefHelper.get_macro_replaceables(input_sentence, variants):
            # (defs, sentinel, sentence): (Reference|ReferenceLike, True, str)
            assert(isinstance(defs, Reference) or type(defs) == dict)
            assert(sentinel is not None)

            ast = AST.parse(sentence)
            replaced_sentence = ast.replace(NO_ARGS, defs)

            used_macros = set()
            ast = AST.parse_sentence_and_ids(replaced_sentence, used_macros, used_macros)
            nested_variants = []
            if len(used_macros) > 0:
                nested_valid_macros = CrossRefHelper.get_valid_macros(used_macros, xrefs)
                nested_variants = CrossRefHelper.get_macro_variants(nested_valid_macros, xrefs)

            if len(nested_variants) == 0:
                # Set sentinel to None so that get_param_replaceables()
                # won't yield it anymore.
                variants.append(({}, None, replaced_sentence))
            else:
                for variant in nested_variants:
                    nested_sentence = ast.replace(NO_ARGS, variant[0])
                    variants.append((variant, True, nested_sentence))
        

class ReferenceHelper:
    @staticmethod
    def is_embeddable_macro(xref):
        return xref.lineno + 1 == xref.lineno_end and not "\"" in xref.body

    @staticmethod
    # get_arguments - Given a Reference for a macro definition,
    # return a list of call site representations.
    # Each call is a tuple (dictionary, Macro|None):
    # - dictionary contains passed and default arguments.
    # - second element is the macro containing that call, if any.
    #
    # filter_parameters is an optional bag to filter only relevant
    # parameters. Parameters not matched will be set to the string
    # `_ignored_`.
    def get_arguments(xref, xrefs, filter_parameters = Universe):
        assert(isinstance(xref, Reference))
        assert(isinstance(xrefs, CrossRef))
        variants = []
        for xref_file_name, references in xref.references.items():
            assert(type(xref_file_name) == str)
            for call_site in references:
                # call_site == (int, str[], dict<str, str>)
                # call_site == (lineno, args, optional_args)
                parent_macro = CrossRefHelper.get_macro_at(xrefs, xref_file_name, call_site[0]) # Macro|None
                called_args = {}
                if call_site[1] is not None:
                    for i, called_arg in enumerate(call_site[1]):
                        if i >= len(xref.args):
                            # Macro called with too many args.
                            # Let pertinent tools worry about it.
                            break
                        parameter_name = xref.args[i]
                        if parameter_name in filter_parameters:
                            called_args[parameter_name] = called_arg
                        else:
                            called_args[parameter_name] = "_ignored_"

                if call_site[2] is not None:
                    for parameter_name, called_arg in call_site[2].items():
                        if not parameter_name in xref.optional_args:
                            # Invalid parameter name.
                            # Let pertinent tools worry about it.
                            continue
                        if called_arg == "{ON_DIFFICULTYeasynormalhard}":
                            # wmltools3 whitespace bug
                            print("Workaround1 for wmltools3 whitespace bug")
                            called_arg = "{ON_DIFFICULTY easy normal hard}"
                        elif called_arg == "{ON_DIFFICULTYworldearthland}":
                            # wmltools3 whitespace bug
                            print("Workaround1 for wmltools3 whitespace bug")
                            called_arg = "{ON_DIFFICULTY world earth land}"
                        elif called_arg == r'{ON_DIFFICULTY"lots of laughs""laughing my ass off""rolling on the floor"}':
                            print("Workaround2 for wmltools3 whitespace bug")
                            called_arg = r'{ON_DIFFICULTY "lots of laughs" "laughing my ass off" "rolling on the floor"}'
                        elif called_arg == r'{ON_DIFFICULTY4" test prevOpt whitespace""test nextOpt whitespace ""test noneOpt whitespace"" test bothOpt whitespace "}':
                            print("Workaround3 for wmltools3 whitespace bug")
                            called_arg = r'{ON_DIFFICULTY4 " test prevOpt whitespace" "test nextOpt whitespace " "test noneOpt whitespace" " test bothOpt whitespace "}'
                        else:
                            # print("called_arg: %s" % called_arg)
                            pass

                        if parameter_name in filter_parameters:
                            called_args[parameter_name] = called_arg
                        else:
                            called_args[parameter_name] = "_ignored_"

                for parameter_name, default_value in xref.optional_args.items():
                    if parameter_name in filter_parameters and not parameter_name in called_args:
                        called_args[parameter_name] = default_value

                variants.append((called_args, parent_macro))

        # list<(dictionary<str, str>, Macro|None)>
        return variants

    # get_param_replaceables - Generator function to iterate over variants with braces.
    # variants is an unsorted mutable list.
    @staticmethod
    def get_param_replaceables(variants):
        # Mutates variants
        index = 0
        while index < len(variants):
            next = variants[index]
            # next: (dictionary<str, str>, Macro)
            if next[1] is None:
                # Signals that this sentence cannot be expanded anymore.
                index += 1
                continue

            if not any(has_brace(arg) for arg in next[0].values()):
                index += 1
                continue

            last = variants.pop()
            if index != len(variants):
                assert index < len(variants)
                variants[index] = last
            else:
                # variants[index] removed in pop()
                assert next == last
                
            yield next

    # deep_replace_arguments - Iterates over variants over and over.
    # Each turn, an expandable variant is processed and readded to the pool,
    # with an updated Macro context.
    # Ends when no more expandable variants are left.
    @staticmethod
    def deep_replace_arguments(variants, xrefs):
        # Mutates variants
        assert(isinstance(xrefs, CrossRef))
        for args, macro in ReferenceHelper.get_param_replaceables(variants):
            # (args, macro): (dictionary<str, str>, Macro)
            assert(isinstance(macro, Macro))
            assert(os.path.isabs(macro.fileref))
            xref = macro.get_ref(xrefs)

            # asts - dict<str, AST>
            # Dictionary for AST representations of each argument in args.
            asts = {}

            # Sets listing parameters and macros used by args.

            # used_params - set<str>
            used_params = set()
            for parameter_name, arg_value in args.items():
                if has_brace(arg_value):
                    # Fill-in used_params
                    asts[parameter_name] = AST.parse_with_ctx(arg_value, xref, used_params)
                else:
                    asts[parameter_name] = LiteralNode(None, arg_value)

            resolved_args = args
            if len(used_params) > 0:                
                # parent_args: list<(dict, Macro)>
                resolved_args = ReferenceHelper.get_arguments(xref, xrefs, used_params)
                for parent_args, parent_macro in resolved_args:
                    extend_no_override(parent_args, args)

            if len(parent_args) == 0:
                # Unable to expand this argument further.
                # Clear macro context so that get_param_replaceables()
                # won't yield it anymore.
                variants.append((args, None))
            else:
                #arg_substitution_sets: list<(dict, Macro)>
                for variant in AST.evaluate_many_on_many(asts, resolved_args):
                    variants.append(variant)

