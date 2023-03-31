import os
from .wmltools3 import CrossRef, Reference
from .wmliterator3 import WmlIterator

# Interface between macro definitions and various
# Wesnoth tools.
# By Leonardo Julca, 2023


# Universe - convenient singleton for which
# `x in Universe` is always True
# Passing it to a filter is equivalent to not filtering.
class UniversalSet:
    def __contains__():
        return True

Universe = UniversalSet()

# LiteralNode - fragment without own expansion semantics.
# It may be subordinated to a MacroCallNode as an argument.
#
# Properties
#  is_root - always false, used to inspect AST parse status.
#  parent - ExpandableNode or AST
#  value - the literal content of the node.
class LiteralNode:
    def __init__(self, parent, value):
        self.is_root = False
        self.parent = parent
        self.value = value

    def __str__(self):
        return self.value

    def replace(self, args_set, xrefs):
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

    def __str__(self):
        return self.replace({}, None)

    def replace(self, args_set, xrefs=None):
        # TODO: This may be a macro we need to evaluate.
        # TODO: It's even possible the definition is unknown. If we are in a single-file
        # analysis, raise an Exception to defer it to full add-on analysis.
        if self.name in args_set[0]:
            sub = args_set[0][self.name]
            # print("Subbed value %s -> %s" % (self.name, sub))
            return sub

        out = ["{" + self.name]
        for child in self.children:
            out.append(child.replace(args_set, xrefs))
        return " ".join(out) + "}"

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

    def replace(self, args_set, xrefs):
        # args_set: (dict<str, str>, Macro)
        # return: str
        out = []
        for child in self.children:
            out.append(child.replace(args_set, xrefs))
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
                    assert not type(ast.active_node) == str
                elif elem[0] == "{":
                    ast.fill_literals(input, start)
                    assert not type(ast.active_node) == str
                    macro_node = ExpandableNode(ast.active_node, elem[1:], start, end)  
                    ast.active_node.children.append(macro_node)
                    ast.active_node = macro_node
                    assert not type(ast.active_node) == str
                else:
                    pass
            ast.fill_literals(input, len(input))
        return ast

    @staticmethod
    def parse_sentence_with_ids(sentence, lone_ids, complex_ids):
        # Mutates lone_ids
        # Mutates complex_ids
        def on_macro(node):
            if len(node.children) == 0:
                # Either parameters or constant macros
                lone_ids[node.name] = True
            else:
                # Definitely macros
                complex_ids[node.name] = True

        return AST.parse(sentence, on_macro)

    @staticmethod
    def parse_macro_arg_with_ctx(arg, in_macro_xref, in_macro_relevant_parameters):
        # Mutates in_macro_relevant_parameters
        def on_macro(node):
            if len(node.children) == 0 and \
                (node.name in in_macro_xref.args or node.name in in_macro_xref.optional_args):
                in_macro_relevant_parameters[node.name] = True

        return AST.parse(arg, on_macro)

    @staticmethod
    def evaluate_many_on_one(ast, args_sets_in, xrefs):
        # ast: AST
        # return: list<(str, Macro|NoneType)>

        out = []
        for args_with_ctx in args_sets_in:
            sub = ast.replace(args_with_ctx, xrefs)
            out.append((sub, args_with_ctx[1]))

        return out

    @staticmethod
    def evaluate_many_on_many(parameters_asts, args_sets_in, xrefs):
        # - parameters_asts : dict<str, AST>
        # - args_sets_in    : list<(dict<str, str>, Macro|NoneType)>
        # - args_sets_out   : list<(dict<str, str>, Macro|NoneType)>
        args_sets_out = []
        for args_with_ctx in args_sets_in:
            assert(isinstance(args_with_ctx[0], dict))
            # assert(isinstance(args_with_ctx[1], Macro|NoneType))
            parameters_out = {}
            for parameter_name, ast in parameters_asts.items():
                parameters_out[parameter_name] = ast.replace(args_with_ctx, xrefs)

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

class ReferenceHelper:
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

                for parameter_name, called_arg in call_site[2].items():
                    if not parameter_name in xref.optional_args:
                        # Invalid parameter name.
                        # Let pertinent tools worry about it.
                        continue
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

    # get_replaceables - Generator function to iterate over variants with braces.
    # variants is an unsorted mutable list.
    @staticmethod
    def get_replaceables(variants):
        # Mutates variants
        index = 0
        while index < len(variants):
            next = variants[index]
            # next: (dictionary<str, str>, Macro)
            if next[1] is None:
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
        for args, macro in ReferenceHelper.get_replaceables(variants):
            # (args, macro): (dictionary<str, str>, Macro)
            assert(isinstance(macro, Macro))
            assert(os.path.isabs(macro.fileref))
            parent_xref = macro.get_ref(xrefs)

            # asts - dict<str, AST>
            # Dictionary for AST representations of each argument in args.
            asts = {}

            # parent_used_params - dict<str, True>
            # Dictionary listing parameters used by args.
            parent_used_params = {}

            for parameter_name, arg_value in args.items():
                if has_brace(arg_value):
                    # Fill-in parent_used_params
                    asts[parameter_name] = AST.parse_macro_arg_with_ctx(arg_value, parent_xref, parent_used_params)

            parent_args = []
            if len(parent_used_params) > 0:                
                #   parent_called_args: list<(dict, Macro)>
                parent_args = ReferenceHelper.get_arguments(parent_xref, xrefs, parent_used_params)

            if len(parent_args) == 0:
                # Unable to expand this argument further.
                # Clear macro context so that get_replaceables()
                # won't yield it anymore.
                variants.append((parent_args, None))
            else:
                #arg_substitution_sets: list<(dict, Macro)>
                arg_substitution_sets = AST.evaluate_many_on_many(asts, parent_args, xrefs)
                for alternative in arg_substitution_sets:
                    variants.append(alternative)


