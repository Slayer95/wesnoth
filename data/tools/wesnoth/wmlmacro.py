import os
from .wmltools3 import CrossRef, Reference
from .wmliterator3 import WmlIterator

# Interface between macro definitions and various
# Wesnoth tools.
# By Leonardo Julca, 2023

class MacroCallNode:
    def __init__(self, parent, name, start, search):
        self.parent = parent
        self.name = name
        self.start = start
        self.children = []
        self.is_root = False
        self._search = search

    # TODO: It's possible that self.name is a macro we need to evaluate,
    # TODO: It's even possible that macro is unknown. If we are in a single-file
    # analysis, raise an Exception to defer it to full add-on analysis.

    def __str__(self):
        out = ["{" + self.name]
        for child in self.children:
            out.append(str(child))
        return " ".join(out) + "}"

    def subs(self, args_set, xrefs):
        if self.name in args_set[0]:
            sub = args_set[0][self.name]
            #print("Subbed value %s -> %s" % (self.name, sub))
            return sub

        out = ["{" + self.name]
        for child in self.children:
            out.append(child.subs(args_set, xrefs))
        return " ".join(out) + "}"

class LiteralNode:
    def __init__(self, parent, value):
        self.parent = parent
        self.value = value
        self.is_root = False

    def __str__(self):
        return self.value

    def subs(self, args_set, xrefs):
        return self.value

class AST:
    def __init__(self):
        self.children = []
        self.active_node = self
        self.is_root = True
        self._search = 0

    def fill_literals(self, text, end):
        assert not type(self.active_node) == str
        start = self.active_node._search
        literal = text[start:end]
        if len(literal) > 0:
            assert not type(self.active_node) == str
            literal_node = LiteralNode(self.active_node, literal)
            self.active_node.children.append(literal_node)

    def __str__(self):
        out = []
        for child in self.children:
            out.append(str(child))
        return "".join(out)

    def subs(self, args_set, xrefs):
        out = []
        for child in self.children:
            out.append(child.subs(args_set, xrefs))
        return "".join(out)

def parse_macro_ast(input, on_macro = None):
    lines = input.split("\n")
    ast = AST()
    for state in WmlIterator(lines=lines):
        elements, _scopes = state.parseElements(state.text)
        for elem, start in elements:
            length = 1 if elem == "end of macro" else len(elem)
            end = start + length
            if elem == "end of macro":
                ast.fill_literals(input, start)
                if ast.active_node.is_root:
                    raise Exception("Unexpected closing brace in translatable string %s" % arg)
                if on_macro is not None:
                    on_macro(ast.active_node)
                ast.active_node = ast.active_node.parent
                ast.active_node._search = end
                assert not type(ast.active_node) == str
            elif elem[0] == "{":
                ast.fill_literals(input, start)
                assert not type(ast.active_node) == str
                macro_node = MacroCallNode(ast.active_node, elem[1:], start, end)  
                ast.active_node.children.append(macro_node)
                ast.active_node = macro_node
                assert not type(ast.active_node) == str
            else:
                pass
        ast.fill_literals(input, len(input))
    return ast

def is_substitution(arg):
    return "}" in arg

def parse_sentence_for_ast_and_identifiers(sentence, lone_identifiers, complex_identifiers):
    def on_macro(node):
        if len(node.children) == 0:
            lone_identifiers[node.name] = True
        else:
            complex_identifiers[node.name] = True

    ast = parse_macro_ast(sentence, on_macro)
    return ast

def parse_macro_called_arg_for_ast_and_parameters(arg, in_macro_xref, in_macro_relevant_parameters):
    def on_macro(node):
        if len(node.children) == 0 and \
            (node.name in in_macro_xref.args or node.name in in_macro_xref.optional_args):
            in_macro_relevant_parameters[node.name] = True

    ast = parse_macro_ast(arg, on_macro)
    return ast

def evaluate_substitution_for_ast(ast, args_set, xrefs):
    #ast: AST
    #args_set: (dict<str, str>, Macro)
    #return: (str, Macro)
    return (ast.subs(args_set, xrefs), args_set[1])

def evaluate_multi_substitution_for_ast(ast, args_all, xrefs):
    #ast: AST
    #return: list<(str, Macro)>

    out = []
    for args_with_ctx in args_all:
        sub = evaluate_substitution_for_ast(ast, args_with_ctx, xrefs)[0]
        out.append((sub, args_with_ctx[1]))

    return out

def evaluate_multi_substitution_for_ast_parameters(parameters_asts, args_sets_in, xrefs):
    # parameters_asts: dict<str, AST>
    #    args_sets_in: list<(dict<str, str>, Macro)>
    #   args_sets_out: list<(dict<str, str>, Macro)>
    args_sets_out = []
    for args_with_ctx in args_sets_in:
        assert(isinstance(args_with_ctx[0], dict))
        #assert(isinstance(args_with_ctx[1], Macro|NoneType))
        parameters_out = {}
        for parameter_name, ast in parameters_asts.items():
            parameters_out[parameter_name] = evaluate_substitution_for_ast(ast, args_with_ctx, xrefs)[0]

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

    def __repr__(self):
        return "Macro(\"%s\", \"%s\", %d)" % tuple(self)

    def __str__(self):
        return "%s@%s:%d" % tuple(self)

    def __eq__(self, other):
        return tuple(self) == tuple(other)

    def __getitem__(self, key):
        return tuple(self)[key]

    def __hash__(self):
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
                #print("Excluded %s@%s#%d" % (self.name, xref.filename, xref.lineno))
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
                    if i >= len(xref.args):
                        # Macro called with too many args: ignore it.
                        continue
                    parameter_name = xref.args[i]
                    assert(type(parameter_name) == str)
                    assert(type(called_arg) == str)
                    if parameter_name in filter_parameters:
                        called_args[parameter_name] = called_arg
                    else:
                        called_args[parameter_name] = "_ignored_"

                for parameter_name, called_arg in call_site[2].items():
                    assert(type(parameter_name) == str)
                    assert(type(called_arg) == str)
                    if parameter_name in filter_parameters:
                        called_args[parameter_name] = called_arg
                    else:
                        called_args[parameter_name] = "_ignored_"

                for parameter_name, default_value in xref.optional_args.items():
                    if not parameter_name in called_args:
                        called_args[parameter_name] = default_value

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
                    break
            else:
                variant += 1
                continue

            if variant+1 != len(called_args_variants):
                assert variant+1 < len(called_args_variants)
                called_args_variants[variant] = called_args_variants.pop()
            else:
                called_args_variants.pop()
                
            yield next

    @staticmethod
    def resolve_called_args_substitutions(called_args_variants, xrefs):
        assert(isinstance(xrefs, CrossRef))
        for next_substitution in ReferenceHelper.get_next_substitution(called_args_variants):
            # (dictionary<str, str>, Macro)
            assert(isinstance(next_substitution[1], Macro))
            parent_xref = next_substitution[1].get_ref(xrefs)

            parent_relevant_parameters = {}
            asts = {}

            for parameter_name, arg_value in next_substitution[0].items():
                if is_substitution(arg_value):
                    asts[parameter_name] = parse_macro_called_arg_for_ast_and_parameters(arg_value, parent_xref, parent_relevant_parameters)

            parent_called_args = []
            if len(parent_relevant_parameters) > 0:                
                #   parent_called_args: list<(dict, Macro)>
                parent_called_args = ReferenceHelper.get_macro_called_args(parent_xref, xrefs, parent_relevant_parameters)

            if len(parent_called_args) == 0:
                called_args_variants.append((parent_called_args, None))
                print("Arguments unknown for %s" % next_substitution[1])
            #elif len(parent_called_args) == 1:
            else:
                #arg_substitution_sets: list<(dict, Macro)>
                arg_substitution_sets = evaluate_multi_substitution_for_ast_parameters(asts, parent_called_args, xrefs)
                for alternative in arg_substitution_sets:
                    called_args_variants.append(alternative)


