#!/usr/bin/python3
# coding=utf8


import regex as re
import pprint
from datetime import datetime
import hashlib

#regex = r"(^struct\s+)([^{]+)({([^}])+})(;\n*)"
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


basic_types = ['undefined', 'bool', '__uint64', 'int', 'double', 'uchar', 'uint', 'void', 'char', '__int64', 'ushort', 'float', 'short']

header_content = "";
input_version = '3.4.3'
input_file = 'stellaris.%s.input.h' % (input_version,)

with open(input_file, 'r') as fh:
    header_content += fh.read()

input_checksum = hashlib.md5(header_content.encode('utf-8')).hexdigest()


matches = re.finditer(regex, header_content, re.MULTILINE)

fh_struct = open('struct.h', 'w')
fh_struct_template = open('struct.template.h', 'w')

fh_typedef = open('typedef.h', 'w')
fh_typedef_enum = open('typedef.enum.h', 'w')
fh_typedef_template = open('typedef.template.h', 'w')

fh_other = open('other.h', 'w')



wanted_major_types = [
        'CApplication', 
        'CGameApplication', 
        'CGameIdler'
        ]

types = {}
typedefs = {}
enums = {}

templates = {}
typedef_templates = {}

for matchNum, match in enumerate(matches, start=1):
    unknown = match.group('unknown')

    initializer = match.group('initializer')
    is_typedef = False
    type_name = match.group('name')
    body = match.group('body')
    post = match.group('post')

    output_arr = None

    if unknown is None and initializer is None:
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

    if is_typedef:
        #typedef
        arr = {'initializer': initializer, 'type_name': type_name, 'body': body, 'post_name': post_name, 'post': post}
        output_arr = typedefs

        if body is None:
            arr['full_text'] = '%s %s %s %s\n' % (typedef_init, initializer, type_name, post)
        else:
            arr['full_text'] = '%s %s %s %s %s%s\n' % (typedef_init, initializer, type_name, body, post_name, post)

        if type_name.find('<') >= 0:
            fh = fh_typedef_template
        elif(initializer == 'enum'):
            #typedef enum
            fh = fh_typedef_enum
            type_name = 'enum' + type_name
            output_arr = enums
        else:
            fh = fh_typedef

    else:
        arr = {'initializer': initializer, 'type_name': type_name, 'body': body, 'post': post}

        if(unknown is not None):
            fh = fh_other
            arr['full_text'] = '%s\n' % (match.group(),)
    
        if(initializer != 'struct '):
            #not typedef, not struct
            fh = fh_other
            arr['full_text'] = '%s%s%s%s\n' % (initializer, type_name, body, post)

        if(initializer == 'struct ' and type_name[0:1] == "C"):
            initializer = 'class '       

        if(body is not None):
            #replace struct with class on objects that start with C
            body_regex = r"^((\s+)(struct)(\s+)((?:C[A-Z][^;]+)[\s]*)+(;))$"
            body_subst = "\g<2>class\g<4>\g<5>\g<6>"
            new_body = re.sub(body_regex, body_subst, body, 0, re.MULTILINE)
            body = new_body


        if(type_name is not None and '<' in type_name):
            #template
            fh = fh_struct_template
            output_arr = templates
            arr['full_text'] = '%s%s%s%s\n' % (initializer, type_name, body, post)
        else:
            #non-template struct
            fh = fh_struct
            output_arr = types
            arr['full_text'] = '%s%s%s%s\n' % (initializer, type_name, body, post)

    if(output_arr is not None and type_name is not None):
        output_arr[type_name.rstrip()] = arr

    fh.write(arr['full_text'])

#with open('dbg.types','w') as fh:
#    pprint.pprint(types, stream=fh)

#with open('dbg.templates', 'w') as fh:
#    pprint.pprint(templates, stream=fh)


def parse_wanted_types(wanted_types, unresolved_types, parent_major_type = ''):
    global types
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
            body_matches = re.finditer(body_re, types[type_name]['body'], re.MULTILINE)
        except:
            if type_name not in unresolved_types['missing']:
                unresolved_types['missing'].append(type_name)
            continue
        for matchNum, match in enumerate(body_matches, start=1):
            body_pre = match.group(1)
            body_typename = match.group(2);
            body_typevalue = match.group(3);
            if body_typename == 'struct':
                body_typevalue_arr = body_typevalue.split(' ');
                if body_typevalue[0:1] == 'C':
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




wanted_types = {}
unresolved_types = {}

for type_name in wanted_major_types:
    wanted_types[type_name] = []
    unresolved_types[type_name] = [type_name,]
    wanted_types, unresolved_types = parse_wanted_types(wanted_types, unresolved_types , type_name)
    for minor_type_name in wanted_types[type_name]:
        if minor_type_name in unresolved_types[type_name] :
            unresolved_types[type_name].remove(minor_type_name)
    for minor_type_name in unresolved_types[type_name]:
        if minor_type_name in basic_types:
            print('DEL %s %s' % (type_name, minor_type_name))
            unresolved_types[type_name].remove(minor_type_name)


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



wanted_templates = {}
still_unresolved_types = []

for type_name in unresolved_types['missing']:
    if type_name in basic_types: #builtins
        continue
    if '<' not in type_name: #not a template
        still_unresolved_types.append(type_name)
        continue

    template_start = type_name.find('<')
    template_end = type_name.rfind('>')
    template_type = type_name[0:template_start]
    template_str = type_name[template_start+1:template_end]

    if template_type not in wanted_templates:
        wanted_templates[template_type] = []

    #template_regex = r"<(?:(?>[^<>]+)|(?R))*>"
    #template_iter = re.finditer(template_regex, template_str)
    #template_inner = []
    #for match in template_iter:
        #print(match)
    #    template_inner.append((match.start(), match.end(), match.group()))

    #template_arr = {'full_string': template_str, 'parent_type': template_type, 'template_inner': template_inner}
    template_arr = parse_template(type_name)
    wanted_templates[template_type].append(template_arr)


#add templated types to wanted types

with open('dbg.wanted_templates', 'w') as fh:
    pprint.pprint(wanted_templates, stream=fh)

types_wanted_by = {}

for major_type_name in wanted_types:
    for minor_type_name in wanted_types[major_type_name]:
        if minor_type_name not in types_wanted_by:
            types_wanted_by[minor_type_name] = [major_type_name,]
        else:
            types_wanted_by[minor_type_name].append(major_type_name)

for minor_type_name in types_wanted_by:
    if len(types_wanted_by[minor_type_name]) > 1:
        print('WARN: Duplicate types for %s:\t %s' % (minor_type_name, types_wanted_by[minor_type_name]))


for major_type_name in wanted_types:
    fh = open('stellaris.autogenerated.types.%s.h' % (major_type_name,), 'w')
    fh.write('#pragma once\n\n\n//THIS FILE WAS AUTOMATICALLY GENERATED\n//DO NOT MODIFY!\n//Modifications will be OVERWRITTEN\n\n')
    fh.write('//Generated at %s for version %s from %s\n' %(datetime.now(), input_version, input_file))
    fh.write('//Input MD5: %s\n\n' % (input_checksum, ))

    fh.write('#ifndef stellar_header_%s_version\n' % (major_type_name,))
    fh.write('#define stellar_header_%s_version=%s\n' % (major_type_name,input_version))
    fh.write('#endif\n')


    for minor_type_name in wanted_types[major_type_name]:
        fh.write(types[minor_type_name]['full_text'])
    fh.close()

with open('dbg.wanted_types', 'w') as fh:
    pprint.pprint(wanted_types, stream=fh)

with open('dbg.wanted_templates', 'w') as fh:
    pprint.pprint(wanted_templates, stream=fh)

with open('dbg.unresolved_types', 'w') as fh:
    pprint.pprint(unresolved_types, stream=fh)

fh_struct.close()
fh_struct_template.close()
fh_typedef.close()
fh_typedef_enum.close()
fh_typedef_template.close()
fh_other.close()
