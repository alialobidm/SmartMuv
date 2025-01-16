from solidity_parser import parser as sol_parser # type: ignore

"""
An Abstract Syntax Tree (AST) is a hierarchical, tree-like representation of the structure of source code.
It breaks down the code into nested nodes, each representing a construct like expressions or statements,
abstracting away syntax details. ASTs are essential in compilers for syntax analysis, optimization, and code generation.

i.e 

Code 

function add(uint a, uint b) public pure returns (uint) {
    return a + b;
}


Generated AST can look similar to this 

FunctionDefinition
├── ParameterList (parameters)
│   ├── Parameter (a: uint)
│   └── Parameter (b: uint)
├── Block (function body)
│   └── ReturnStatement
│       └── BinaryOperation (a + b)
│           ├── Identifier (a)
│           └── Identifier (b)
└── ParameterList (return parameters)
    └── Parameter (returns uint)

Note : The original implementation and return results by sol_parser must be taken into account.

"""
def generate_ast(code):
    source_unit = sol_parser.parse(code)
    children = source_unit['children'] # type: ignore
    try:
        compiler_version = children[0]['value']
    except:
        compiler_version = ''
    return children, compiler_version

def check_ast_nodes(sub_nodes, definition, functions, variables, mappings):
    statements = sub_nodes['statements']
    for statement in statements:
        if statement == ';' or statement == None:
            continue
        if statement['type'] == 'ExpressionStatement':
            functions, variables, mappings = check_mapping(
                statement, definition, functions, variables, mappings)
        elif statement['type'] == 'IfStatement':
            functions, variables, mappings = check_if_stmt(
                statement, definition, functions, variables, mappings) # type: ignore
        elif statement['type'] == 'ForStatement':
            functions, variables, mappings = check_ast_nodes(
                statement['body'], definition, functions, variables, mappings)
    return functions, variables, mappings


def check_mapping(statement, definition, functions, variables, mappings):
    if statement['expression']['type'] == 'BinaryOperation':
        if '=' in statement['expression']['operator'] and statement['expression']['operator'] != '==':
            if statement['expression']['left']['type'] == 'IndexAccess':
                tmp = statement['expression']['left']
                while 'base' in tmp['base']:
                    tmp = tmp['base']
                #mappings contains mapping name and key type, extracting mapping names from the list
                mapp_names = [x[0] for x in mappings]
                if tmp['base']['name'] in mapp_names:
                    if definition not in functions:
                        functions.append(definition)
                tmp = statement['expression']['left']
                tmp_var_list = []
                while 'index' in tmp:
                    try:
                        tmp_var_list.append(tmp['index']['name'])
                    except:
                        a = tmp['index']['expression']['name']
                        b = tmp['index']['memberName']
                        tmp_var_list.append(a + '.' + b)
                    tmp = tmp['base']
                tmp_var_list.reverse()
                tmp_var_list.insert(0, definition['name'])
                if len(tmp_var_list) > 0:
                    variables.append(tmp_var_list)
    return functions, variables, mappings


def check_if_stmt(statement, definition, functions, variables, mappings):
    statements = statement['TrueBody']
    functions, variables, mappings = check_ast_nodes(
        statements, definition, functions, variables, mappings)
    statements = statement['FalseBody']

    if statements == None:
        return
    functions, variables, mappings = check_ast_nodes(
        statements, definition, functions, variables, mappings)
    return functions, variables, mappings


def parse_ast(children, cont_name):
    all_contracts_details = {}
    variables = []
    state_vars = []
    cont_names = []
    mappings = []
    cont_functions = {}
    for contract in children:
        if contract == None:
            continue
        if contract['type'] == "ContractDefinition":
            cont_names.append(contract['name'])
        else:
            continue
        functions = []
        func_names = []
        func_var = []
        parents = []
        all_functions = {}
        try:
            sub_nodes = contract['subNodes']
        except:
            sub_nodes = []
        for definition in sub_nodes:
            #print(definition['type'])
            if definition['type'] == 'StateVariableDeclaration':
                dec_vars = definition['variables']
                state_vars = state_vars + [var['name'] for var in dec_vars]
            try:
                if definition['type'] == 'StateVariableDeclaration':
                    if definition['variables'][0]['typeName']['type'] == 'Mapping':
                        key_type = definition['variables'][0]['typeName']['keyType']['name']
                        #print("key type", key_type)
                        mappings.append([definition['variables'][0]['name'], key_type])
                        #mappings.append(definition['variables'][0]['name'])
            except:
                pass
            if definition['type'] == "FunctionDefinition":
                all_functions[definition['name']] =  definition
                functions.append(definition)
            try:
                statements = definition['body']
                if statements != []:
                    functions, variables, mappings = check_ast_nodes(
                        statements, definition, functions, variables, mappings)
            except KeyError:
                continue
            except:
                pass      
        # replaces duplicate names of functions
        for func in functions:
            if func['name'] not in func_names:
                if func['name'] == None:
                    func['name'] = 'constructor'
                func_names.append(func['name'])
        # replaces duplicate func, var pairs
        for var in variables:
            if var not in func_var:
                func_var.append(var)
        if 'baseContracts' in contract:
            if contract['baseContracts'] != []:
                parents = contract['baseContracts']
                for base_contract in contract['baseContracts']:
                    tmp = base_contract['baseName']['namePath']
                    if tmp not in cont_names:
                        continue                
                    base_vars = all_contracts_details[tmp]['vars']
                    base_funcs = all_contracts_details[tmp]['fbody']
                    for func in base_funcs:
                        if func not in functions:
                            functions.append(func)
                        if func['name'] not in func_names:
                            if func['name'] == None:
                                func['name'] = 'constructor'
                            func_names.append(func['name'])
                    # func_names = func_names + [func['name'] for func in base_funcs ]
                    for var in base_vars:
                        if type(var) == list:
                            var_list = var
                            for v in var_list:
                                if v not in state_vars:
                                    state_vars.append(v)
                        else:
                            if var not in state_vars:
                                state_vars.append(var)
        state_vars = list(set(state_vars))
        func_names = list(set(func_names))
        all_contracts_details[contract['name']] = {
            'func': func_names, 'vars': state_vars, 'parents': parents, 'fbody': functions, 'maps': mappings}
        cont_functions[contract['name']] = all_functions
    return all_contracts_details, cont_functions


def find_diamond_for_class(tree, class_name):
    # A recursive function to get all base classes for a given class
    def all_bases(cls, accum=None):
        if accum is None:
            accum = {}
        bases = tree.get(cls, [])
        # print(cls, "->", bases)
        for base in bases:
            accum[base] = accum.get(base, 0) + 1
            all_bases(base, accum)
        return accum

    # Find if the specified class has any base classes included multiple times
    bases = all_bases(class_name)
    diamond_bases = {base: count for base, count in bases.items() if count > 1}
    return diamond_bases


def merge(sequences):
    """
    Merges multiple sequences into a single C3 linearization, as per the C3 algorithm.
    """
    result = []
    while True:
        non_empty_seqs = [seq for seq in sequences if seq]
        if not non_empty_seqs:
            return result
        for seq in non_empty_seqs:  # find merge candidates among seq heads
            candidate = seq[0]
            if not any(candidate in s[1:] for s in non_empty_seqs):
                break
        else:
            raise Exception("Inconsistent hierarchy")
        result.append(candidate)
        for seq in non_empty_seqs:  # remove candidate
            if seq[0] == candidate:
                del seq[0]

def c3_linearization(classname, tree):
    """
    Calculates the C3 linearization for a given class.
    """
    base_classes = tree.get(classname, [])
    sequences = [c3_linearization(base_class, tree) for base_class in base_classes] + [base_classes + [classname]]
    return merge(sequences)

def unroll_struct(struct, all_contract_dict):
    '''Takes in a struct data type, returns list of variables in the struct'''
    var_lst = []
    for var_struct in struct['members']:
        var_lst.append(format_variable(var_struct, all_contract_dict))
    return var_lst

def format_variable(var_struct, all_contracts_dict):
    '''Takes in a variable, returns the formatted variable according to it's type'''
    if var_struct['typeName']['type'] == 'ElementaryTypeName':
        var_dict = {}
        var_dict['type'] = var_struct['typeName']['type']
        var_dict['dataType'] = var_struct['typeName']['name']
        var_dict['name'] = var_struct['name']
        return var_dict
    elif var_struct['typeName']['type'] == 'UserDefinedTypeName':      
        # if userdefined variable is an enum, treat it as elementary type
        if "." in var_struct['typeName']['namePath']:
            var_struct['typeName']['namePath'] = var_struct['typeName']['namePath'].split(".")[-1]
        try:
            var_struct_data_type = all_contracts_dict[var_struct['typeName']['namePath']]['vars'][0]['dataType']
        except:
            var_struct_data_type = ''
        if var_struct_data_type == 'enum':
            var_dict = {}
            var_dict['type'] = 'ElementaryTypeName'
            var_dict['dataType'] = 'enum'
            var_dict['name'] = var_struct['name']
        else:
            var_dict = {}
            var_dict['type'] = var_struct['typeName']['type']
            var_dict['dataType'] = var_struct['typeName']['namePath']
            try:
                var_dict['typeVars'] = all_contracts_dict[var_struct['typeName']
                    ['namePath']]['vars']
            except:
                var_dict['typeVars'] = []
        var_dict['name'] = var_struct['name']
        return var_dict
    elif var_struct['typeName']['type'] == 'Mapping':
        var_dict = {}
        var_dict['type'] = var_struct['typeName']['type']
        var_dict['keyType'] = var_struct['typeName']['keyType']
        var_dict['valueType'] = var_struct['typeName']['valueType']
        var_dict['name'] = var_struct['name']
        return var_dict
    elif var_struct['typeName']['type'] == 'ArrayTypeName':
        print("var_struct -", var_struct)
        name_struct = var_struct['typeName']['baseTypeName']
        lens = []
        try:
            lens.append(var_struct['typeName']['length']['number'])
        except:
            try:
                lens.append(var_struct['typeName']['length']['name'])
            except:
                lens.append(var_struct['typeName']['length'])
        # iterate over all dimensions of array to get length of each dimension
        while not ('name' in name_struct or 'namePath' in name_struct):
            print("name_struct", name_struct)
            if 'length' in name_struct:
                try:
                    lens.append(name_struct['length']['number'])
                except:
                    try:
                        lens.append(name_struct['length']['name'])
                    except:
                        lens.append(name_struct['length'])
            name_struct = name_struct['baseTypeName']
        new_lens = []
        for i in range(1, len(lens)+1):
            new_lens.append(lens[-i])
        type_struct = name_struct['type']
        var_dict = {}
        if 'name' in name_struct:
            name_struct = name_struct['name']
            type_struct = 'ElementaryTypeName'
        else:
            name_struct = name_struct['namePath']
            type_struct = 'UserDefinedTypeName'

        var_dict['type'] = var_struct['typeName']['type']
        var_dict['dataTypeType'] = type_struct
        var_dict['dataTypeName'] = name_struct
        var_dict['length'] = new_lens
        var_dict['name'] = var_struct['name']
        var_dict['curr'] = -1
        if len(lens) > 1:
            var_dict['dimension'] = 'multi'
        else:
            var_dict['dimension'] = 'single'
        if None not in lens:
            var_dict['StorageType'] = 'static'
        else:
            var_dict['StorageType'] = 'dynamic'
        return var_dict


def variable_unrolling(subnodes, all_contracts_dict, all_vars):
    statevars = []
    for node in subnodes:
        if node['type'] == 'StateVariableDeclaration':
            vars = node['variables']
            for variable in vars:
                # grab the value if the value is assigned to a variable at compile time
                if 'isDeclaredConst' in variable:
                    if variable['isDeclaredConst'] == True:
                        try:
                            if 'value' in variable['expression']:
                                all_vars.append(
                                    [variable['name'], variable['typeName']['name'], variable['expression']['value']])
                            elif 'number' in variable['expression']:
                                all_vars.append(
                                    [variable['name'], variable['typeName']['name'], variable['expression']['number']])
                        except:
                            pass
                        continue
                if 'isDeclaredImmutable' in variable:
                    if variable['isDeclaredImmutable'] == True:
                        try:
                            if 'value' in variable['expression']:
                                all_vars.append(
                                    [variable['name'], variable['typeName']['name'], variable['expression']['value']])
                            elif 'number' in variable['expression']:
                                all_vars.append(
                                    [variable['name'], variable['typeName']['name'], variable['expression']['number']])
                        except:
                            pass
                        continue
                st_var = format_variable(variable, all_contracts_dict)
                if st_var != None:
                    statevars.append(st_var)
        elif node['type'] == 'StructDefinition':
            tmp = unroll_struct(node, all_contracts_dict)
            all_contracts_dict[node['name']] = {'vars': tmp}
        elif node['type'] == 'EnumDefinition':
            var_dict = {}
            var_dict['type'] = 'ElementaryTypeName'
            var_dict['dataType'] = 'enum'
            var_dict['name'] = node['name']
            all_contracts_dict[node['name']] = {'vars': [var_dict]}
    return statevars, all_contracts_dict, all_vars

def get_contract_details(children, contract_name):
    all_vars = []
    all_contracts_dict = {}
    inherit_tree = {}
    linearized_inherit_tree = {}
    # print("children", children)
    for contract in children:
        if contract == None:
            continue
        try:
            sub_nodes = contract['subNodes']
        except:
            sub_nodes = []
        if contract['type'] == 'PragmaDirective':
            continue
        if 'baseContracts' in contract:
            if contract['baseContracts'] != []:
                lst = contract['baseContracts']
                parent_list = []
                for basecontract in lst:
                    parent_list.append(basecontract['baseName']['namePath'])
                inherit_tree[contract['name']] = parent_list
                
    diamonds = find_diamond_for_class(inherit_tree, contract_name)
    if diamonds:
        print("************************************")
        print(f"Diamond inheritance detected for class {contract_name}: {diamonds}")
        print("************************************")
    else:
        print(f"No diamond inheritance detected for class {contract_name}.")
    for cont in inherit_tree:
        temp = c3_linearization(cont, inherit_tree)
        linearized_inherit_tree[cont] = temp[:-1]

    for contract in children:
        parent = []
        if contract == None:
            continue
        if 'subNodes' in contract: #contract definition
            sub_nodes = contract['subNodes']
        elif 'members' in contract: # struct definition
            if contract['type'] == 'EnumDefinition':
                var_dict = {}
                var_dict['type'] = 'ElementaryTypeName'
                var_dict['dataType'] = 'enum'
                var_dict['name'] = contract['name']
                all_contracts_dict[contract['name']] = {'vars': [var_dict]}                            
            else:
                tmp = unroll_struct(contract, all_contracts_dict)
                all_contracts_dict[contract['name']] = {'vars': tmp}
            continue
        else: # unknown case
            sub_nodes = []
        if contract['type'] == 'PragmaDirective':
            continue
        state_vars, all_contracts_dict, all_vars = variable_unrolling(
            sub_nodes, all_contracts_dict, all_vars)
        if 'baseContracts' in contract:
            if contract['baseContracts'] != []:
                    lst = linearized_inherit_tree[contract['name']]
                    parent_vars = []
                    for parent_cont_name in lst:
                        if len(all_contracts_dict) != 0:
                            b_statevars = all_contracts_dict[parent_cont_name]['vars']
                            for var in b_statevars:
                                if type(var) == list:
                                    for va in var:
                                        if va not in parent_vars:
                                            parent_vars.append(va)
                                else:
                                    if var not in parent_vars:
                                        parent_vars.append(var)
                    state_vars = parent_vars + state_vars
                    parent = lst

            #     lst = contract['baseContracts']
            #     tmpls = []
            #     for basecontract in lst:
            #         tmp = basecontract['baseName']['namePath']
            #         if len(all_contracts_dict) != 0:
            #             b_statevars = all_contracts_dict[tmp]['vars']
            #             for var in b_statevars:
            #                 if type(var) == list:
            #                     for va in var:
            #                         if va not in tmpls:
            #                             tmpls.append(va)
            #                 else:
            #                     if var not in tmpls:
            #                         tmpls.append(var)
            # state_vars = tmpls + state_vars
            # parent = contract['baseContracts']
        try:
            all_contracts_dict[contract['name']] = {
                'vars': state_vars, 'parent': parent, 'type': contract['type']}
        except:
            continue
    return all_vars, all_contracts_dict, diamonds

def format_variable_new(var_struct, all_contracts_dict):
    '''Takes in a variable, returns the formatted variable according to it's type'''
    if 'enum' in var_struct['nodeType'].lower():
        var_dict = {}
        var_dict['type'] = 'ElementaryTypeName'
        var_dict['dataType'] = 'enum'
        var_dict['name'] = var_struct['name']
    elif var_struct['typeName']['nodeType'] == 'ElementaryTypeName':
        var_dict = {}
        var_dict['type'] = var_struct['typeName']['nodeType']
        var_dict['dataType'] = var_struct['typeName']['name']
        var_dict['name'] = var_struct['name']
        return var_dict
    elif var_struct['typeName']['nodeType'] == 'UserDefinedTypeName':
        if 'enum' in var_struct['typeDescriptions']['typeIdentifier']:
            var_dict = {}
            var_dict['type'] = 'ElementaryTypeName'
            var_dict['dataType'] = 'enum'
            var_dict['name'] = var_struct['name']
        else:
            var_dict = {}
            var_dict['type'] = var_struct['typeName']['nodeType']
            try:
                var_dict['dataType'] = var_struct['typeName']['pathNode']['name']
            except:
                var_dict['dataType'] = var_struct['typeName']['name']
            # var_dict['defType'] = all_contracts_dict[var_dict['dataType']]['type']
            var_dict['name'] = var_struct['name']
            try:
                var_dict['typeVars'] = all_contracts_dict[var_dict['dataType']]['vars']
            except:
                var_dict['typeVars'] = []
        return var_dict
    elif var_struct['typeName']['nodeType'] == 'Mapping':
        var_dict = {}
        var_dict['type'] = var_struct['typeName']['nodeType']
        var_dict['keyType'] = var_struct['typeName']['keyType']
        var_dict['valueType'] = var_struct['typeName']['valueType']
        var_dict['name'] = var_struct['name']
        return var_dict
    elif var_struct['typeName']['nodeType'] == 'ArrayTypeName':
        name_struct = var_struct['typeName']['baseType']
        lens = []
        try:
            if var_struct['typeName']['length']['nodeType'] == 'Literal':
                lens.append(var_struct['typeName']['length']['value'])
            else:
                lens.append(var_struct['typeName']['length']['name'])
        except:
            try:
                lens.append(var_struct['typeName']['length'])
            except:
                lens.append(None)
        # iterate over all dimensions of array to get length of each dimension
        while not ('name' in name_struct or 'namePath' in name_struct):
            try:
                if name_struct['length']['nodeType'] == 'Literal':
                    lens.append(name_struct['length']['value'])
                else:
                    lens.append(name_struct['length']['name'])
            except:
                try:
                    lens.append(name_struct['length'])
                except:
                    lens.append(None)
            name_struct = name_struct['baseType']
        type_struct = name_struct['nodeType']
        
        new_lens = []
        for x in range(1, len(lens)+1):
            new_lens.append(lens[-x])
        
        var_dict = {}
        var_dict['type'] = var_struct['typeName']['nodeType']
        var_dict['dataTypeType'] = type_struct
        var_dict['dataTypeName'] = name_struct['name']
        var_dict['length'] = new_lens
        var_dict['name'] = var_struct['name']
        var_dict['curr'] = -1
        if len(lens) > 1:
            var_dict['dimension'] = 'multi'
        else:
            var_dict['dimension'] = 'single'
        if None not in lens:
            var_dict['StorageType'] = 'static'
        else:
            var_dict['StorageType'] = 'dynamic'
        return var_dict

def unroll_struct_new(struct, all_contract_dict):
    '''Takes in a struct data type, returns list of variables in the struct'''
    var_lst = []
    for var_struct in struct['members']:
        var_lst.append(format_variable_new(var_struct, all_contract_dict))
    return var_lst


def variable_unrolling_new(subnodes, all_contracts_dict, all_vars):
    statevars = []
    for node in subnodes:
        if node['nodeType'] == "VariableDeclaration":
          if node['stateVariable'] == True:
            try:
                if node['constant'] == True or node['mutability'] == "immutable":
                    # grab the value if the value is assigned to a variable at compile time
                    try:
                        if 'number' in node['value']['kind'] or 'string' in node['value']['kind']:
                            all_vars.append(
                                [node['name'], node['typeDescriptions']['typeString'], node['value']['value']])
                            continue
                    except:
                        continue
                else:
                    st_var = format_variable_new(node, all_contracts_dict)
                    if st_var != None:
                        statevars.append(st_var)
            except:
                if node['constant'] == True:
                    # grab the value if the value is assigned to a variable at compile time
                    try:
                        if 'number' in node['value']['kind'] or 'string' in node['value']['kind']:
                            all_vars.append(
                                [node['name'], node['typeDescriptions']['typeString'], node['value']['value']])
                            continue
                    except:
                        continue
                else:
                    st_var = format_variable_new(node, all_contracts_dict)
                    if st_var != None:
                        statevars.append(st_var)
        elif node['nodeType'] == 'StructDefinition':
            tmp = unroll_struct_new(node, all_contracts_dict)
            all_contracts_dict[node['name']] = {'vars': tmp, 'type': node['nodeType']}
        elif node['nodeType'] == 'EnumDefinition':
            var_dict = {}
            var_dict['type'] = 'ElementaryTypeName'
            var_dict['dataType'] = 'enum'
            var_dict['name'] = node['name']
            all_contracts_dict[node['name']] = {'vars': [var_dict]}

    return statevars, all_contracts_dict, all_vars

def get_contract_details_new(contracts, contract_name):
    all_vars = []
    all_contracts_dict = {}
    inherit_tree = {}
    linearized_inherit_tree = {}
    for contract in contracts:
        if contract == None:
            continue
        if contract['nodeType'] == 'PragmaDirective':
            continue
        if 'baseContracts' not in contract:
            continue
        if contract['baseContracts'] != []:
            lst = contract['baseContracts']
            parent_list = []
            for basecontract in lst:
                parent_list.append(basecontract['baseName']['name'])
            inherit_tree[contract['name']] = parent_list
    # pprint.pprint(inherit_tree)
    diamonds = find_diamond_for_class(inherit_tree, contract_name)
    if diamonds:
        print("************************************")
        print(f"Diamond inheritance detected for class {contract_name}: {diamonds}")
        print("************************************")
    else:
        print(f"No diamond inheritance detected for class {contract_name}.")

    for cont in inherit_tree:
        temp = c3_linearization(cont, inherit_tree)
        linearized_inherit_tree[cont] = temp[:-1]
    # print(linearized_inherit_tree)

    for contract in contracts:
        parent = []
        if contract == None:
            continue
        if contract['nodeType'] == 'PragmaDirective':
            continue
        if 'nodes' in contract: #contract definition
            sub_nodes = contract['nodes']
        elif 'members' in contract: # struct definition
            tmp = unroll_struct_new(contract, all_contracts_dict)
            all_contracts_dict[contract['name']] = {'vars': tmp}
            continue
        else: # unknown case
            sub_nodes = []
        state_vars, all_contracts_dict, all_vars = variable_unrolling_new(
            sub_nodes, all_contracts_dict, all_vars)
        # parent contract
        if 'baseContracts' in contract:
            if contract['baseContracts'] != []:
                # if contract['name'] == contract_name:
                    lst = linearized_inherit_tree[contract['name']]
                    parent_vars = []
                    for parent_cont_name in lst:
                        if len(all_contracts_dict) != 0:
                            b_statevars = all_contracts_dict[parent_cont_name]['vars']
                            for var in b_statevars:
                                if type(var) == list:
                                    for va in var:
                                        if va not in parent_vars:
                                            parent_vars.append(va)
                                else:
                                    if var not in parent_vars:
                                        parent_vars.append(var)
                    state_vars = parent_vars + state_vars
                    parent = lst
            # else:
            #     lst = contract['baseContracts']
            #     parent_vars = []
            #     for basecontract in lst:
            #         parent_cont_name = basecontract['baseName']['name']
            #         if len(all_contracts_dict) != 0:
            #             b_statevars = all_contracts_dict[parent_cont_name]['vars']
            #             for var in b_statevars:
            #                 if type(var) == list:
            #                     for va in var:
            #                         if va not in parent_vars:
            #                             parent_vars.append(va)
            #                 else:
            #                     if var not in parent_vars:
            #                         parent_vars.append(var)
            #     state_vars = parent_vars + state_vars
            #     parent = contract['baseContracts']
        all_contracts_dict[contract['name']] = {
            'vars': state_vars, 'parent': parent, 'type': contract['nodeType']}
    return all_vars, all_contracts_dict, diamonds
