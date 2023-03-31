macros = {
}
macro_calls = []

def ensure_macroinfo(name):
    if name in macros:
        return macros[name]

    macros[name] = {
        parameters: pywmlx.nodemanip.macrosignature[1:],

        # Where is it invoked and by whom.
        callers: [], # init
        callfiles: [],

        # Macros nested inside.
        callees: [],
        # [{
        #    name: string,
        #    inputs: [{
        #        type: 'parameter' | 'text' | 'call' | 'complex',
        #        key: number | string,
        #        value,
        #    }],
        #    length: number,
        #    is_complex: boolean,
        # }]
    }

    return macros[name]

def ref_callers():
    for name, definition in macros:
        for callee in definition.callees:
            # callee {
            #    name: string,
            #    inputs: [{
            #        type: 'parameter' | 'text' | 'call' | 'complex',
            #        key: number | string,
            #        value,
            #    }],
            #    length: number,
            #    is_complex: boolean,
            # }
            if callee.name in macros:
                rule = []

                for key, input in enumerate(callee.inputs):
                    if input[0:1] == '{' and input[-1:] == '}':
                        for j, parameter in enumerate(definition.indexed):
                            if input[1:-1] == parameter:
                                # i-th parameter of callee equals j-th parameter of caller
                                rule.append((i, j))
                                break
                            elif '{' + parameter + '}' in input:
                                complex[i] = True
                        else:
                            if input[1:-1] in definition.named:
                                rule.append((i, True)) # here lie dragons
                            else:
                                # i-th is constant or too complex
                                rule.append((i, None))

                for input in callee.inputs.named:
                    if input[0:1] == '{' and input[-1:] == '}':
                        for j, parameter in enumerate(definition.indexed):
                            if input[1:-1] == parameter:
                                # i-th parameter of callee equals j-th parameter of caller
                                rule.append((i, j))
                                break
                            elif '{' + parameter + '}' in input:
                                complex[i] = True
                        else:
                            if input[1:-1] in definition.named:
                                rule.append((i, True)) # here lie dragons
                            else:
                                # i-th is constant or too complex
                                rule.append((i, None))
                
                macros[callee.name].callers.append({
                    macro: name,
                    rule: rule,
                    complex: complex,
                })

            else:
                # Some macros might not have a known definition,
                # e.g. if they are imported from wesnoth/utils.cfg
                # We just ignore them, and focus on those macros that
                # are actually involved in our strings.
                pass


