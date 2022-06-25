#!/usr/bin/python3
# coding=utf8


import regex as re
import pprint
from datetime import datetime
import hashlib


#Regex for parsing input header file
regex = r"((?<initializer>^(?:struct|union)\s+)(?<name>[^{]+)(?<body>{(?:[^}])+})(?<post>;\n*)|(?:(?<typedef_init>^typedef)\s+(?<td_initializer>[^\s]+)\s*)(?<td_name>[^;{]+)(?<td_post1>[;\s]+)(([;\s]+)|(?<td_body>{[^;{}]+})(?<td_post2>[^;{}]+)(?<td_post3>;\n*)))|(?<unknown>^.*?$)"
#sorry...
#if struct | union:
# initializer name {body} post
# struct abc123 { bool regex; };
#elif typedef
#typedef_init td_initializer td_name td_post1
#typedef enum name;\n
#typedef void * PTR_NAME;\n

#typedef_init td_initializer td_name { td_body } td_post2 td_post3
#typedef enum enumName { THING=1 } enumName;\n



#config

# basic C++ types that should get ignored for type parsing
#TODO: these should be defined in the shared file
basic_types = [
        'undefined', 
        'bool', 
        'uchar', 'unsignedchar', 'byte',
        'char', 'signedchar', 'sbyte',
        'ushort', 'word', 'unsignedshort',
        'short', 
        'uint', 'unsignedint', 'dword',
        'int', 
        'double', 
        'void', 
        'float', 
        'ulong',
        'long', 
        'ulonglong', '__uint64', 'qword',
        'longlong', '__int64',
        'void', 'void *', 'void * *',
        ]

#Rename a type, doesn't always actually rename
#TODO: is const stuff superfluous now that I added other const code below?
type_renames = {
        'unsignedint': 'uint',
        'unsignedchar': 'uchar',
        'signedchar': 'char',
        'unsignedshort': 'ushort',
        'CGalacticObjectClusterconst*': 'CGalacticObjectCluster *',
        'CEconomicCategoryconst*': 'CEconomicCategory *',
        'CTraitconst*': 'CTrait *',

        }

#Templates that should be ignored for the final resolution
#includes standard templates, included libraries (Eigen), and stuff that can't genericize because they are too complex
#(IE, if we have one variant of a template and it includes <0,0,0> then we can't figure out which parameter is which 0 in the body).
#TODO: Better solution for that ^
#TODO: Better solution for included libraries?
template_ignore = [
        'Eigen::Matrix', 'Matrix',
        'allocator',
        'array',
        'basic_string',
        'char_traits',
        'equal_to',
        'hash',
        'less',
        'map',
        'pair',
        'shared_ptr',
        'unordered_map',
        'vector',
        'std::allocator',
        'std::array', 
        'std::basic_string',
        'std::char_traits',
        'std::equal_to',
        'std::hash',
        'std::less',
        'std::map',
        'std::pair',
        'std::shared_ptr',
        'std::unordered_map',
        'std::vector',
        'CPdxHybridArray', # isn't possible to auto-resolve, uses sizeof() one of the fields
        'CPdxUnorderedMap', # isn't possible to auto-resolve, uses multiple integers that match
        ]


#"Wanted" major types are the root of our resolution tree of types.
wanted_major_types = [
        'CApplication',
        'CGameApplication',
        'CGameIdler',
        'CGameState',
        'CGameStateDatabase',
        'CConsoleCmdManager',
        ]

#Version is defined seperately so we can easily use it in the output filenames and in a define
input_version = '3.4.4'
input_file = 'stellaris.%s.input.h' % (input_version,)

#/config

#Read the input header file into memory
header_content = "";
with open(input_file, 'r') as fh:
    header_content += fh.read()

#Build a checksum of the input file to put in the output file comments for future troubleshooting
input_checksum = hashlib.md5(header_content.encode('utf-8')).hexdigest()


#We output things we can't/don't parse to this file (semi-debug)
fh_other = open('other.h', 'w')


#Initially we parse ALL of the single input header file, into the structs below
typedefs = {}

structs = {}
classes = {}
enums   = {}
unions  = {}

union_templates = {}
enum_templates = {}
struct_templates = {}
class_templates = {}

#Initial parsing logic
#TODO: move into a func, collapse all types into a single dict types = {'structs': {}, 'classes': {}...
matches = re.finditer(regex, header_content, re.MULTILINE)
for matchNum, match in enumerate(matches, start=1):
    unknown = match.group('unknown')

    initializer = match.group('initializer')
    is_typedef = False
    type_name = match.group('name')
    body = match.group('body')
    post = match.group('post')

    output_arr = None

    if unknown is None and initializer is None:
        #Regex above is two regexes smushed together, one for typedefs, one for not-typedefs
        is_typedef = True
        typedef_init = match.group('typedef_init')
        initializer = match.group('td_initializer')
        type_name = match.group('td_name')
        body = match.group('td_body')
        if(body is None):
            post_name = None
            post = match.group('td_post1')
        else:
            post_name = match.group('td_post2')
            post = match.group('td_post3')

    #fh here is our OUTPUT file handle, if any.
    fh = None
    if is_typedef:
        #typedef
        arr = {'initializer': initializer, 'type_name': type_name, 'body': body, 'post_name': post_name, 'post': post}

        if body is None:
            arr['full_text'] = '%s %s %s %s\n' % (typedef_init, initializer, type_name, post)
        else:
            arr['full_text'] = '%s %s %s %s %s%s\n' % (typedef_init, initializer, type_name, body, post_name, post)

        if type_name.find('::') >= 0:
            #strip class name
            arr['original_type_name'] = type_name
            arr['type_name'] = type_name = type_name[type_name.find('::')+2:]

        if initializer == 'enum':
            type_name = 'enum' + type_name
            if type_name.find('<') >= 0:
                output_arr = enum_templates
            else:
                #typedef enum
                output_arr = enums
        else:
            output_arr = typedefs

    else:
        #If it looks like a class, make it a class, since ghidra outputs everything as structs.
        if(initializer == 'struct ' and type_name[0:1] == "C" and type_name[1:2].isupper()):
            initializer = 'class '

        if type_name is not None:
            template_start = type_name.find('<')
            template_end = type_name.rfind('>')
        else:
            template_start = -1
            template_end = -1

        if template_start >= 0 and template_end >= 0:
            type_name = type_name[0:template_end+1] 
            #For some reason some types have text AFTER the template value, which doesn't work with the code here... Hoping it's only a handful and / or it's coming from Ghidra rather than the original code.
            #Just going to strip it for now.

        arr = {'initializer': initializer, 'type_name': type_name, 'body': body, 'post': post}
       

        if(unknown is not None):
            fh = fh_other
            arr['full_text'] = '%s\n' % (match.group(),)
            if arr['full_text'][0:2] == '/*' and arr['full_text'] [-2:] == '*/':
                #ghidra warning comment
                continue

        elif(initializer not in ['struct ', 'class ', 'union '] ):
            fh = fh_other
            arr['full_text'] = '%s%s%s%s\n' % (initializer, type_name, body, post)

        elif(initializer == 'struct '):
            if(type_name is not None and '<' in type_name):
                output_arr = struct_templates
            else:
                output_arr = structs

            arr['full_text'] = '%s%s%s%s\n' % (initializer, type_name, body, post)
        elif(initializer == 'class ') :
            if type_name is not None and '<' in type_name:
                output_arr = class_templates
            else:
                output_arr = classes

            arr['full_text'] = '%s%s%s%s\n' % (initializer, type_name, body, post)
        elif(initializer == 'union '):
            if type_name is not None and '<' in type_name:
                output_arr = union_templates
            else:
                output_arr = unions

            arr['type_name'] = type_name = 'union'+type_name
            arr['full_text'] = '%s%s%s%s\n' % (initializer, type_name, body, post)


    # Clean up any extra whitespace
    if(output_arr is not None and type_name is not None):
        output_arr[type_name.rstrip()] = arr


    # Body modifications
    if(body is not None):
        #add enum to the front of all enums
        body_regex = r"^((\s+)(enum)(\s+)(enum){0,1}((?:[^;]+)[\s]*)+(;))$"
        body_subst = "\g<2>\g<3>\g<4>enum\g<6>\g<7>"
        new_body = re.sub(body_regex, body_subst, arr['full_text'], 0, re.MULTILINE)
        arr['full_text'] = new_body

        #switch structs to classes for things that start with C[SINGLE CAPITAL LETTER]*;
        body_regex = r"^((\s+)(struct)(\s+)((?:C[A-Z][^;]+)[\s]*)+(;))$"
        body_subst = "\g<2>class\g<4>\g<5>\g<6>"
        new_body = re.sub(body_regex, body_subst, arr['full_text'], 0, re.MULTILINE)
        arr['full_text'] = new_body

        #add union to the front of all unions
        body_regex = r"^((\s+)(union)(\s+)(union){0,1}((?:[^;]+)[\s]*)+(;))$"
        body_subst = "\g<2>\g<3>\g<4>union\g<6>\g<7>"
        new_body = re.sub(body_regex, body_subst, arr['full_text'], 0, re.MULTILINE)
        arr['full_text'] = new_body

        for type_from, type_to in type_renames.items():
            body_regex = r"^((\s+)(%s)(\s+)((?:[^;]+)[\s]*)+(;))$" % (type_from, )
            body_subst = "\g<2>%s\g<4>\g<5>\g<6>" % (type_to, )
            new_body = re.sub(body_regex, body_subst, arr['full_text'], 0, re.MULTILINE)
            arr['full_text'] = new_body

    #Write to an output file if it's set
    if fh is not None:
        fh.write(arr['full_text'])


#Recursively parse type bodies to find all types
def parse_wanted_types(wanted_types, unresolved_types, parent_major_type = ''):
    global classes, structs, unions, enums

    for type_name in unresolved_types[parent_major_type]:
        if type_name in wanted_types[parent_major_type]:
            continue

        if parent_major_type not in unresolved_types:
            unresolved_types[parent_major_type] = []
        if 'missing' not in unresolved_types:
            unresolved_types['missing'] = []

        if parent_major_type not in wanted_types:
            wanted_types[parent_major_type] = []
        new_body = "{\n"
        body_re = r"(^\s+)([^\s]+)\s+([^;]+);"
        try:
            if type_name[0:5] == 'union':
                body_matches = re.finditer(body_re, unions[type_name]['body'], re.MULTILINE)
            elif type_name[0:4] == 'enum':
                body_matches = re.finditer(body_re, enums[type_name]['body'], re.MULTILINE)
            elif type_name in classes:
                body_matches = re.finditer(body_re, classes[type_name]['body'], re.MULTILINE)
            elif type_name in structs:
                body_matches = re.finditer(body_re, structs[type_name]['body'], re.MULTILINE)
            else:
                if type_name not in unresolved_types[parent_major_type]: #formerly 'missing'
                    unresolved_types[parent_major_type].append(type_name) #formerly "missing"
                continue
        except:
            if type_name not in unresolved_types[parent_major_type]: #formerly 'missing'
                unresolved_types[parent_major_type].append(type_name) #formerly "missing"
            continue

        for matchNum, match in enumerate(body_matches, start=1):
            body_pre = match.group(1)
            body_typename = match.group(2);
            body_typevalue = match.group(3);
            if body_typename == 'struct':
                body_typevalue_arr = body_typevalue.split(' ');
                if body_typevalue[0:1] == 'C' and body_typevalue[1:2].isupper():
                    body_typename = 'class'
                if body_typevalue_arr[0] not in unresolved_types[parent_major_type]:
                    unresolved_types[parent_major_type].append(body_typevalue_arr[0])
            elif body_typename == 'enum':
                body_typevalue_arr = body_typevalue.split(' ');
                body_typevalue_arr[0] = 'enum' + body_typevalue_arr[0]

                if body_typevalue_arr[0] not in unresolved_types[parent_major_type]:
                    unresolved_types[parent_major_type].append(body_typevalue_arr[0])
            elif body_typename == 'union':
                body_typevalue_arr = body_typevalue.split(' ');
                body_typevalue_arr[0] = 'union' + body_typevalue_arr[0]

                if body_typevalue_arr[0] not in unresolved_types[parent_major_type] and body_typevalue_arr[0] not in basic_types:
                    unresolved_types[parent_major_type].append(body_typevalue_arr[0])
            else:
                if body_typename not in unresolved_types[parent_major_type] and body_typename not in basic_types:
                    unresolved_types[parent_major_type].append(body_typename)
        wanted_types[parent_major_type].append(type_name)
        wanted_types, unresolved_types = parse_wanted_types(wanted_types, unresolved_types, parent_major_type)

    return (wanted_types, unresolved_types)



#Parse through wanted_major_types recursively searching for wanted_types
# if we can't find a type, add it to unresolved types
wanted_types = {}
unresolved_types = {}

for type_name in wanted_major_types:
    wanted_types[type_name] = []
    unresolved_types[type_name] = [type_name,]
    wanted_types, unresolved_types = parse_wanted_types(wanted_types, unresolved_types , type_name)

    #Remove types in unresolved types if they were resolved 
    #(Past me did this, future me is not sure if this makes sense? Why would we resolve a type that we didn't on the last iteration? Future Future me: Think about this and delete these comments)
    for minor_type_name in wanted_types[type_name]:
        if minor_type_name in unresolved_types[type_name] :
            unresolved_types[type_name].remove(minor_type_name)

    #Remove basic types from unresolved types, they aren't unresolved, they're basic!
    for minor_type_name in unresolved_types[type_name]:
        if minor_type_name in basic_types:
            unresolved_types[type_name].remove(minor_type_name)


#Recursively parse a template type (this_is_a_template<not_me,but_I_am_too<abc123>,7)
# output is recursive, so confusing to parse.

def parse_template(template, depth = 0):
    template_regex = r"([^,\s<]*)(<(?:[^<>]|((?2)))+>)|([^,\s]+)"
    matches = re.finditer(template_regex, template)
    output = {}

    value_count = 0
    
    for match in matches:
        value = match.group(4)
        value_count += 1

        template_type = match.group(1)
        template_value = match.group(2)

        if template_value is None:
            #We don't need to recurse, no sub-templates
            if template_type is None: #Parsing "A,B,C,1,2,3"
                if value is not None:
                    output[value_count] = value
            else:
                if value is not None:
                    output[value_count] = value
        else:
            #recurse into template value
            result = parse_template(template_value[1:-1], depth+1)

            if(template_type is None): #If template type isn't set we don't know where we are, we just have a list of values
                #print(result)
                output = {value_count: result}
            elif('values' in output): #if template type already exists, we just finished parsing a sub-template and result appended as a sub-type?
                output['values'][value_count] = {'template_type': template_type, 'template_value': template_value, 'values': result, 'depth': depth+1}
            else:   #otherwise we just returned from parsing the first value ?
                output[value_count] = {'template_type': template_type, 'template_value': template_value, 'values':  result, 'depth': depth+1}
                            #We don't need to recurse, no sub-templates
    return output

# Parse templates out of the body of a template, non-recursively.
def parse_template_body(template):
    template_body_regex = r""
    matches = re.finditer(template_regex, template)
    output = {}


#Recursively make the recursive template list not-recursive, but only for template VALUES
#TODO: Is not including template['template_value'] a bug?
def collapse_templates(templates):
    result = []
    for minor_type_name in templates:
        for template in templates[minor_type_name]:
            try:
                for key, value in template['values'].items():
                    if type(value) is dict:
                        sub_result = collapse_templates({'x': [value,]})
                        for sub_value in sub_result:
                            if sub_value not in result:
                                result.append(sub_value)
                    else:
                        if value not in result:
                            result.append(value)
            except Exception as e:
                print('Exception %s %s while processing %s' % (type(e), e, template))

    return result

#Recursively make the recursive template list less-recursive, but including all of the recursive data (confusing right?)
#Basically, we move everything into 1 layer, but keep the other layers.
#TODO: See, this one has template['template_value'] (re: the TODO above me...)
def collapse_templates_with_detail(templates):
    result = {}
    for minor_type_name in templates:
        for template in templates[minor_type_name]:
            #pprint.pprint(template)
            try:
                for key, value in template['values'].items():
                    if type(value) is dict:
                        if value['template_type'] not in result:
                            result[value['template_type']] = {}
                        if value['template_value'] not in result[value['template_type']]:
                            result[value['template_type']][value['template_value']] = value

                        sub_result = collapse_templates_with_detail({'x': [value,]})
                        #pprint.pprint(sub_result)

                        for sub_key, type_arr in sub_result.items():
                            for sub_key2, sub_value in type_arr.items():
                                if type(sub_value) is not dict:
                                    continue

                                if sub_value['template_type'] not in result:
                                    result[sub_value['template_type']] = {}
                                if sub_value['template_value'] not in result[sub_value['template_type']]:
                                    result[sub_value['template_type']][sub_value['template_value']] = sub_value
            except Exception as e:
                #raise
                print('Exception %s %s while processing %s' % (type(e), e, template))

            if type(template) is dict:

                if template['template_type'] not in result:
                    result[template['template_type']] = {}
                if template['template_value'] not in result[template['template_type']]:
                    result[template['template_type']][template['template_value']] = template

    return result


#look at types that haven't been resolved
# and find templates and sub-templates in template string 
# <this_is_a_template,this_is_also_a_template<dont_forget_me<or_me>>> 
# and add them to wanted templates
wanted_templates = {}
still_unresolved_types = []

for parent_type_name in unresolved_types:
    for type_name in unresolved_types[parent_type_name]:
        if type_name in basic_types: #builtins
            continue
        if '<' not in type_name: #not a template
            still_unresolved_types.append(type_name)
            continue

        template_start = type_name.find('<')
        template_end = type_name.rfind('>')
        template_type = type_name[0:template_start]
        template_str = type_name[template_start+1:template_end]

        if parent_type_name not in wanted_templates:
            wanted_templates[parent_type_name] = {}
        if template_type not in wanted_templates[parent_type_name]:
            wanted_templates[parent_type_name][template_type] = []

        #template_arr = {'full_string': template_str, 'parent_type': template_type, 'template_inner': template_inner}
        template_arr = parse_template(type_name)
        wanted_templates[parent_type_name][template_type].append(template_arr[1])



#Seems obvious...
def is_integer(n):
    try:
        float(n)
    except ValueError:
        return False
    else:
        return float(n).is_integer()



#Add templated types and sub types to wanted_types
for major_type_name in wanted_templates:
    result = collapse_templates(wanted_templates[major_type_name])
    for value in result:
        if value[-1:] == '*':
            value = value[:-1] #remove ptr character

        if value.find('::') >= 0: # ghidra doesn't export with class namespaces, so need to remove... probably a better solution with more ghidra scripting
            if value.find('enum') >= 0:
                value = value[value.find('::')+2:]
                value = 'enum' + value
            else:
                value = value[value.find('::')+2:]

        if value[-5:] == 'const':
            value = value[:-5]

        if value not in wanted_types[major_type_name] and value not in basic_types and not is_integer(value) and value != '':
            wanted_types[major_type_name].append(value)


# Creates a single layer of all templates but without removing their depth-ness
def build_collapsed_templates_with_detail(wanted_templates, template_ignore = {}):
    collapsed_templates = {}
    for major_type_name in wanted_templates:
        result = collapse_templates_with_detail(wanted_templates[major_type_name])
        for parent_type_name, arr in result.items():
            if parent_type_name in template_ignore:
                continue

            if parent_type_name.find('::') >= 0:
                parent_type_name = parent_type_name[parent_type_name.find('::') + 2:]

            if parent_type_name in template_ignore:
                continue
            if parent_type_name not in collapsed_templates:
                collapsed_templates[parent_type_name] = {}

            for template_value, arr2 in arr.items():
                if template_value not in collapsed_templates[parent_type_name]:
                    arr2['parent_major_types'] = [major_type_name,]
                    collapsed_templates[parent_type_name][template_value] = arr2
                else:
                    collapsed_templates[parent_type_name][template_value]['parent_major_types'].append(major_type_name)
    return collapsed_templates

collapsed_templates = build_collapsed_templates_with_detail(wanted_templates, template_ignore)


#debug output
with open('dbg.collapsed_templates', 'w') as fh:
        pprint.pprint(collapsed_templates, stream=fh)

#debug output
with open('dbg.collapsed_templates.text', 'w') as fh:
    for template_name in collapsed_templates:
        for template_value in collapsed_templates[template_name]:
            for template_arr in [class_templates, struct_templates, enum_templates, union_templates]:
                if template_name + template_value in template_arr:
                    fh.write(template_arr[template_name+template_value]['full_text'])
                elif template_name + template_value + ' ' in template_arr:
                    fh.write(template_arr[template_name + template_value + ' ']['full_text'])



#find sub-templates in body of each template
for template_name in collapsed_templates:
    for template_value in collapsed_templates[template_name]:
        for template_arr in [class_templates, struct_templates, enum_templates, union_templates]:
            if template_name + template_value in template_arr:
                template = template_arr[template_name+template_value]
            elif template_name + template_value + ' ' in template_arr:
                template = template_arr[template_name + template_value + ' ']

            template_full_text = template['full_text']
            template_body_regex = r"^(\s+)(.*?)\s([^{};\s]+)[;\s]*$"
            parent_major_types = collapsed_templates[template_name][template_value]['parent_major_types']
            matches = re.finditer(template_body_regex, template_full_text, re.MULTILINE)
            for match in matches:
                full_type_name = match.group(2)
                type_variable = match.group(3)
                
                type_name_parts = full_type_name.split(' ')
                initializer = type_name_parts[0]
                try:
                    type_name = type_name_parts[1]
                except:
                    type_name = full_type_name



                if '<' in type_name:
                    template_start = type_name.find('<')
                    template_end = type_name.rfind('>')
                    template_type = type_name[0:template_start]

                    for parent_major_type in parent_major_types:
                        if template_type not in wanted_templates[parent_type_name]:
                            wanted_templates[parent_type_name][template_type] = []

                            template_arr = parse_template(type_name)
                            wanted_templates[parent_type_name][template_type].append(template_arr[1])

                elif type_name in basic_types:
                    continue
                else:
                    #continue
                    if type_name not in wanted_types[parent_type_name]:
                        wanted_types[parent_type_name].append(type_name)




#rebuild collapsed templates so it includes our new data.
collapsed_templates = build_collapsed_templates_with_detail(wanted_templates, template_ignore)


#build types_wanted_by detail, so we can figure out merged shared types... probably a better way to do this.
types_wanted_by = {}

for major_type_name in wanted_types:
    for minor_type_name in wanted_types[major_type_name]:
        if minor_type_name not in types_wanted_by:
            types_wanted_by[minor_type_name] = [major_type_name,]
        else:
            types_wanted_by[minor_type_name].append(major_type_name)

# figure out which types are shared and move them to a shared file (so we can include them from multiple places)
# I really dont like this, but I can't find a better way to solve this multiple-definition problem right now
# Maybe there is something with llvm-pdb that can export the original locations so they can be reconstructed?
# or something with ghidra to export more detail about namespaces?
wanted_types['shared'] = []
for minor_type_name in types_wanted_by:
    if len(types_wanted_by[minor_type_name]) > 1:
        #print('WARN: Duplicate types for %s:\t %s' % (minor_type_name, types_wanted_by[minor_type_name]))
        for major_type_name in types_wanted_by[minor_type_name]:
            wanted_types[major_type_name].remove(minor_type_name)

        if minor_type_name not in wanted_types['shared']:
            wanted_types['shared'].append(minor_type_name)


for template_name in collapsed_templates:
    this_template_versions = {}

    #Dig through collapsed templates, and make sure we can resolve them
    #Build a dict of each template that has all the different versions of that template so we can build a merged template definition
    resolved = 0
    unresolved = 0
    for template_value in collapsed_templates[template_name]:
        found = False
        for template_arr in [class_templates, struct_templates, enum_templates, union_templates]:
            if template_name + template_value in template_arr:
                this_template_versions[template_value] = template_arr[template_name+template_value]
                found = True
            elif template_name + template_value + ' ' in template_arr:
                this_template_versions[template_value] = template_arr[template_name + template_value + ' ']
                found = True
        if not found:
            unresolved += 1
            print('ERROR: Unable to resolve template %s %s' % (template_name, template_value))
        else:
            resolved += 1

    #print('INFO: Template resolution stats for %s, unresolved / resolved: %s / %s' % (template_name, unresolved , resolved))
    
    
    parsed_versions = {}
    #Build our parsed collection of the variants of this template
    #(Step 1 in trying to resolve down to a generic template automatically)
    #(Basically, look at the template parameters and try to replace them in the body of the template with ###VALUE###parameter_position_value)
    for template_value in this_template_versions:
        parsed_versions[template_value] = parse_template(this_template_versions[template_value]['type_name'])[1]
        parsed_versions[template_value]['value_pos'] = {}
        parsed_versions[template_value]['full_text_parts'] = []
        parsed_versions[template_value]['full_text'] = ''.join([this_template_versions[template_value]['full_text'], ])

        value_set = {}
        for key, value in parsed_versions[template_value]['values'].items():
            if type(value) is dict:
                value_arr = value
                value = '%s%s' % (value['template_type'], value['template_value'])

            parsed_versions[template_value]['value_pos'][key] = []


            value_set[key] = [value,]
            

            #Remove this weird const-ness, I dunno what is causing it, feels like a ghidra-ism or bug
            if(value[-5:] == 'const'):
                value_set[key].append(value[:-5])
            if(value[-6:] == 'const*'):
                value_set[key].append(value[:-6] + '*')

            for type_from, type_to in type_renames.items():
                if(value == type_from):
                    value_set[key].append(type_to)

        
        i = parsed_versions[template_value]['full_text'].find(template_name)
        i += len(template_name)

        parsed_versions[template_value]['full_text_parts'].append(parsed_versions[template_value]['full_text'][0:i])

        parsed_versions[template_value]['value_set'] = value_set
        while True:
            found_any = False
            for key, values in value_set.items():
                for value in values:
                    bt_size = 0

                    pos = parsed_versions[template_value]['full_text'].find(value, i)
                    if(pos < 0 and value.find('::') >= 0):
                        #if no match, AND it has a class at the front, try again without the class.
                        value = value[value.find('::')+2:]
                        pos = parsed_versions[template_value]['full_text'].find(value, i)
                    if(pos < 0 and value[-1] == '*'):
                        #if no match and ptr, add a space for the ptr and try again. 
                        value = value[0:-1] + ' *'
                        pos = parsed_versions[template_value]['full_text'].find(value, i)
                    
                    if pos >= 0:
                        found_any = True
                        backtracks = ['class ', 'enum ', 'struct ', 'union ',]

                        parsed_versions[template_value]['value_pos'][key].append((pos, len(value)))
                        for bt in backtracks:
                            if parsed_versions[template_value]['full_text'][pos-len(bt):pos] == bt:
                                bt_size = len(bt)
                                pos -= bt_size
                                break

                        parsed_versions[template_value]['full_text_parts'].append(parsed_versions[template_value]['full_text'][i:pos])
                        parsed_versions[template_value]['full_text_parts'].append('###VALUE###%s' % (key, ))
                        i = pos+len(value)+bt_size
                        break
            
            if found_any == False:
                break
        parsed_versions[template_value]['full_text_parts'].append(parsed_versions[template_value]['full_text'][i:])
        parsed_versions[template_value]['full_text_parts'] = ''.join(parsed_versions[template_value]['full_text_parts'])

    
    #Compare each genericized template to the one before it, and see how many are exactly matching
    #TODO: Wait, with the Md5 part I wrote after this, is this part doing anything? (I guess it's generating the error message...)
    last_template = ''
    template_count = 0
    match_count = 1
    for template_value in this_template_versions:
        template_count += 1
        if template_count == 1:
            last_template = parsed_versions[template_value]['full_text_parts']
            continue
        if(template_count > 1 and last_template != parsed_versions[template_value]['full_text_parts']):
            all_match = False
        else:
            match_count +=1
    
    template_versions = {}
    #print('%s: Match(%s) count(%s)' % (template_name, all_match, template_count))
    if(match_count < template_count):
        print('ERROR auto-template failure %s: count(%s) match_count(%s)' % (template_name, template_count, match_count))


    #Build a dict with the variants of this template using the md5 hash of the genericized text and sort them on that
    for template_value in parsed_versions:
        md5sum = hashlib.md5(parsed_versions[template_value]['full_text_parts'].encode('utf-8')).hexdigest()
        if md5sum not in template_versions:
            template_versions[md5sum] = {'text': parsed_versions[template_value]['full_text_parts'], 'count': 1, 'template_values': [template_value, ]}
        else:
            template_versions[md5sum]['count'] += 1
            template_versions[md5sum]['template_values'].append(template_value)

    
    #Write our output file for this template
    fh = open('output/stellaris.autogenerated.templates.%s.h' % (template_name,), 'w')

    fh.write('#pragma once\n\n\n')
    fh.write('//THIS FILE WAS AUTOMATICALLY GENERATED\n//DO NOT MODIFY!\n//Modifications will be OVERWRITTEN\n\n')
    fh.write('//Generated at %s for version %s from %s\n' %(datetime.now(), input_version, input_file))
    fh.write('//Input MD5: %s\n\n' % (input_checksum, ))

    fh.write('#include "stellaris.autogenerated.types.shared.h"\n\n')
    fh.write('using namespace std;\n')
    fh.write('using namespace Eigen;\n\n')

    # Currently we write all versions, but if there are more than 5 variants we comment out any "singular" variant
    # Also, the original template parameters are output in a comment before it's matching template
    for md5sum in template_versions:
        fh.write('// Template version %s matches %s template instances\n' % (md5sum, template_versions[md5sum]['count']))
        for template_value in template_versions[md5sum]['template_values']:
            fh.write('//     %s \n' % (template_value,))
        if(template_count > 5 and template_versions[md5sum]['count'] == 1):
            fh.write('/*\n')

        template_text = template_versions[md5sum]['text']


        #TODO: de-genericize this into a valid template. Will probably need to make some kind of collapsed value array so we can look at all the values and determine the templated parameter type (IE, is it a typename, is it an integer, etc)



        fh.write(template_text)
        if(template_count > 5 and template_versions[md5sum]['count'] == 1):
            fh.write('*/\n')

    fh.close()




#TODO: Output the types for our major wanted types and the shared file.
for major_type_name in wanted_types:
    fh = open('output/stellaris.autogenerated.types.%s.h' % (major_type_name,), 'w')
    
    #TODO: This is ugly, move to some kind of templated header file?
    fh.write('#pragma once\n\n\n//THIS FILE WAS AUTOMATICALLY GENERATED\n//DO NOT MODIFY!\n//Modifications will be OVERWRITTEN\n\n')
    fh.write('//Generated at %s for version %s from %s\n' %(datetime.now(), input_version, input_file))
    fh.write('//Input MD5: %s\n\n' % (input_checksum, ))

    fh.write('#ifndef stellar_header_%s_version\n' % (major_type_name,))
    fh.write('#define stellar_header_%s_version=%s\n' % (major_type_name,input_version))
    fh.write('#endif\n\n\n')

    if major_type_name != 'shared':
        fh.write('#include "stellaris.autogenerated.types.shared.h"\n\n')
        fh.write('using namespace std;\n')
        fh.write('using namespace Eigen;\n\n')
    else:
        fh.write(
                'using namespace std;\n\n'
                '#include <string>\n'
                '#include <cstring>\n'
                '#include <vector>\n'
                '#include <unordered_map>\n'
                '#include <atomic>\n'
                '#include <deque>\n'
                '#include <queue>\n'
                '#include <map>\n'
                '#include <mutex>\n'
                '\n'
                '#include "lib/eigen/Eigen/core"\n'
                '#include "hooking_windows.h"\n\n'
		)

    #Final resolution of type to write to file
    for minor_type_name in wanted_types[major_type_name]:
        if minor_type_name in classes:
            fh.write(classes[minor_type_name]['full_text'])
        elif minor_type_name in structs:
            fh.write(structs[minor_type_name]['full_text'])
        elif minor_type_name in enums:
            fh.write(enums[minor_type_name]['full_text'])
        elif minor_type_name in unions: 
            fh.write(unions[minor_type_name]['full_text'])
        elif minor_type_name in basic_types:
            print('WARNING: Basic type somehow made it to file output, ignoring type %s in wanted type: %s' % (minor_type_name, major_type_name))
        else:
            #If we can't resolve anything at this point, we'll output an error message and write it in a comment so it's obvious, but continue, there is some weirdness that will probably need to be fixed by hand
            print('ERROR: Missing type %s in wanted type: %s' % (minor_type_name, major_type_name))
            fh.write('//Missing type %s in wanted type: %s\n\n' % (minor_type_name, major_type_name))

    fh.close()

#Close this open file handle, has the "other" (IE, we didn't parse this stuff) header output.
fh_other.close()

#Debug
with open('dbg.typedefs', 'w') as fh:
    pprint.pprint(typedefs, stream=fh)

with open('dbg.union_templates', 'w') as fh:
    pprint.pprint(union_templates, stream=fh)

with open('dbg.wanted_types', 'w') as fh:
    pprint.pprint(wanted_types, stream=fh)

with open('dbg.wanted_templates', 'w') as fh:
    pprint.pprint(wanted_templates, stream=fh)


with open('dbg.unresolved_types', 'w') as fh:
    pprint.pprint(unresolved_types, stream=fh)

#with open('dbg.enums', 'w') as fh:
#    pprint.pprint(enums, stream=fh)

with open('dbg.types_wanted_by', 'w') as fh:
    pprint.pprint(types_wanted_by, stream=fh)
