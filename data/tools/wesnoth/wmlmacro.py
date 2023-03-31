from enum import Enum
from pprint import PrettyPrinter
import os
from .wmltools3 import CrossRef, Reference
import json

# Interface between macro definitions and various
# Wesnoth tools.

printer = PrettyPrinter(indent=4,depth=3)

class ContextLessSyntaxTypes(Enum):
    RAW_TEXT = 1
    SUBS_SIMPLE = 2
    SUBS_COMPLEX = 3

class ContextFullSyntaxTypes(Enum):
    RAW_TEXT = 1
    PARAMETER = 4 # contextless: 2
    MACRO_CALL = 6 # contextless: 2 or 3


def is_substitution(arg):
    return "}" in arg

def parse_sentence_for_ast_and_identifiers(sentence, lone_identifiers, complex_identifiers):
    assert sentence == "+{AMOUNT} exp"
    ast = []
    # lone_identifiers: {}
    # TODO: fill lone_identifiers, complex_identifiers
    ast.append((ContextLessSyntaxTypes.RAW_TEXT, "+"))
    ast.append((ContextLessSyntaxTypes.SUBS_SIMPLE, "AMOUNT"))
    ast.append((ContextLessSyntaxTypes.RAW_TEXT, " exp"))
    lone_identifiers["AMOUNT"] = True
    return ast

def parse_macro_called_arg_for_ast_and_parameters(arg, in_macro_xref, in_macro_relevant_parameters):
    assert arg == "{EXTRA_ABILITY}"
    ast = []
    # in_macro_relevant_parameters: {}
    # TODO: fill in_macro_relevant_parameters

    ast.append((ContextFullSyntaxTypes.RAW_TEXT, ""))
    ast.append((ContextFullSyntaxTypes.PARAMETER, "EXTRA_ABILITY"))
    ast.append((ContextFullSyntaxTypes.RAW_TEXT, ""))
    arg_name = arg[1:-1]
    if arg_name in in_macro_xref.args or arg_name in in_macro_xref.optional_args:
        in_macro_relevant_parameters[arg_name] = True
        
    return ast

# Note that ast may refer to unknown macros. In that case, bail out
# (raise Exception)
# TODO: Check whether we are substituting a parameter or a macro.

def evaluate_substitution_for_ast(ast, args_set):
    #TODO
    #ast: AST
    #args_set: (dict<str, str>, Macro)
    #return: (str, Macro)
    out = []
    for type, value in ast:
        if type == ContextFullSyntaxTypes.PARAMETER or type == ContextLessSyntaxTypes.SUBS_SIMPLE:
            printer.pprint("Evaluate substitution for type(%s=%d), value=%s" % (type.name, type.value, value))
            sub = args_set[0][value]
            printer.pprint("Subbed value %s -> %s" % (value, sub))
            out.append(sub)
        else:
            out.append(value)
    return ("".join(out), args_set[1])

def evaluate_multi_substitution_for_ast(ast, args_all):
    #ast: AST
    #return: list<(str, Macro)>

    out = []
    for args_with_ctx in args_all:
        sub = evaluate_substitution_for_ast(ast, args_with_ctx)[0]
        out.append((sub, args_with_ctx[1]))

    return out

def evaluate_multi_substitution_for_ast_parameters(parameters_asts, args_sets_in):
    # parameters_asts: dict<str, AST>
    #    args_sets_in: list<(dict<str, str>, Macro)>
    #   args_sets_out: list<(dict<str, str>, Macro)>

    args_sets_out = []
    for args_with_ctx in args_sets_in:
        assert(isinstance(args_with_ctx[0], type(dict)))
        assert(isinstance(args_with_ctx[1], Macro))
        parameters_out = {}
        for parameter_name, ast in parameter_asts.items():
            parameters_out[parameter_name] = evaluate_substitution_for_ast(ast, args_with_ctx)[0]

        args_sets_out.append((parameters_out, args_with_ctx[1]))

    return args_sets_out

class UniversalSet:
    def __contains__():
        return True

Universe = UniversalSet()

class Macro:
    def __init__(self, name, fileref, line):
        self.name = name
        self.fileref = fileref
        self.line = line

    def __iter__(self):
        yield self.name
        yield self.fileref
        yield self.line

    def __str__(self):
        return "%s@%s:%d" % tuple(self)

    def __eq__(self, other):
        return tuple(self) == tuple(other)

    def __hash__(self):
        assert not os.path.isabs(self.fileref)
        return hash(tuple(self))

    def to_abs(self, root_path):
        return Macro(self.name, os.path.join(root_path, self.fileref), self.line)

    def to_rel(self, root_path):
        return Macro(self.name, os.path.relpath(root_path, self.fileref), self.line)

    def get_ref(self, xrefs):
        assert isinstance(xrefs, CrossRef)
        if not self.name in xrefs.xref:
            printer.pprint("Macro %s not found" % (self.name))
            return None

        for xref in xrefs.xref[self.name]:
            if xref.filename != self.fileref or xref.lineno != self.line:
                printer.pprint("Excluded %s@%s#%d" % (self.name, xref.filename, xref.lineno))
                printer.pprint("Expected %s" % self)
                continue

            assert isinstance(xref, Reference)
            return xref 

        return None

class CrossRefHelper:
    @staticmethod
    def get_macro_at(xrefs, fileref, lineno):
        assert(isinstance(xrefs, CrossRef))
        for macro_name in xrefs.xref.keys():
            for xref in xrefs.xref[macro_name]:
                if xref.filename != fileref:
                    continue
                if xref.lineno < lineno and lineno < xref.lineno_end:
                    return Macro(macro_name, xref.filename, xref.lineno)

        return None

class ReferenceHelper:
    @staticmethod
    def get_macro_called_args(xref, xrefs, filter_parameters = Universe):
        assert(isinstance(xref, Reference))
        assert(isinstance(xrefs, CrossRef))
        called_args_variants = []
        for xref_file_name, references in xref.references.items():
            assert(type(xref_file_name) == str)
            for call_site in references:
                assert(type(call_site) == tuple)
                assert(type(call_site[0]) == int)
                # call_site[0] == lineno
                # call_site[1] == string[]
                # call_site[2] == dictionary
                parent_macro = CrossRefHelper.get_macro_at(xrefs, xref_file_name, call_site[0]) # Macro|None
                called_args = {}
                for i, called_arg in enumerate(call_site[1]):
                    parameter_name = xref.args[i]
                    assert(type(parameter_name) == str)
                    assert(type(called_arg) == str)
                    if parameter_name in filter_parameters:
                        called_args[parameter_name] = called_arg
                    else:
                        called_args[parameter_name] = ""

                for parameter_name, called_arg in call_site[2].items():
                    assert(type(parameter_name) == str)
                    assert(type(called_arg) == str)
                    if parameter_name in filter_parameters:
                        called_args[parameter_name] = called_arg
                    else:
                        called_args[parameter_name] = ""

                called_args_variants.append((called_args, parent_macro))

        # list<(dictionary<str, str>, Macro|None)>
        return called_args_variants

    @staticmethod
    def get_next_substitution(called_args_variants):
        variant = 0
        while variant < len(called_args_variants):
            next = called_args_variants[variant]
            if next[1] is None:
                variant += 1
                continue

            for arg_name, arg_value in next[0].items():
                if is_substitution(arg_value):
                    printer.pprint("Variant %d: %s=%s" % (variant, arg_name, arg_value))
                    break
            else:
                variant += 1
                continue

            if variant+1 != len(called_args_variants):
                assert(variant+1 < len(called_args_variants))
                called_args_variants[variant] = called_args_variants.pop()
                
            yield next

    @staticmethod
    def resolve_called_args_substitutions(called_args_variants, xrefs):
        assert(isinstance(xrefs, CrossRef))
        for next_substitution in ReferenceHelper.get_next_substitution(called_args_variants):
            # (dictionary<str, str>, Macro)
            assert(isinstance(next_substitution[1], Macro))
            print("[%s] - would substitute %s" % (str(next_substitution[1]), json.dumps(next_substitution[0])))
            parent_xref = next_substitution[1].get_ref(xrefs)
            print("parent_xref")
            printer.pprint(parent_xref)

            parent_relevant_parameters = {}
            asts = {}

            for parameter_name, arg_value in next_substitution[0].items():
                if is_substitution(arg_value):
                    asts[parameter_name] = parse_macro_called_arg_for_ast_and_parameters(arg_value, parent_xref, parent_relevant_parameters)

            parent_called_args = []
            if len(parent_relevant_parameters) > 0:                
                parent_called_args = ReferenceHelper.get_macro_called_args(parent_xref, xrefs, parent_relevant_parameters)
                print("parent_called_args")
                printer.pprint(parent_called_args)

            #arg_substitution_sets: list<dict, Macro>
            #   parent_called_args: list<dict, Macro>
            arg_substitution_sets = evaluate_multi_substitution_for_ast_parameters(asts, parent_called_args)
            for alternative in arg_substitution_sets:
                called_args_variants.append(alternative)

