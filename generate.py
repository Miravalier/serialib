#!/usr/bin/env python3
from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

from prettyprinter import install_extras, pprint
from sly import Lexer, Parser

# Pretty printer dataclasses support
install_extras(include=['dataclasses'], warn_on_error=True)


def indent(s, amount=2):
    return str(s).replace('\n', '\n' + '  '*amount)


def dedent(s):
    return textwrap.dedent(s.rstrip()).lstrip()


ESCAPE_CODES = {
    'r': ord('\r'),
    'n': ord('\n'),
    't': ord('\t'),
    'v': ord('\v'),
    '\\': ord('\\'),
    '\'': ord('\''),
    '"': ord('"'),
    '0': 0,
    '1': 1,
    '2': 2,
    '3': 3,
    '4': 4,
    '5': 5,
    '6': 6,
    '7': 7,
    '8': 8,
    '9': 9,
}


class SeriaLexer(Lexer):
    # Set of tokens
    tokens = {
        IDENTIFIER, NUMBER_LITERAL, STRING_LITERAL,

        COLON, SEMICOLON, COMMA, EQUALS,

        #OPEN_PAREN, CLOSE_PAREN,
        OPEN_BRACKET, CLOSE_BRACKET,
        OPEN_BRACE, CLOSE_BRACE,

        TABLE, ENUM, STRUCT,
    }

    # Characters ignored between tokens
    ignore = ' \t'
    ignore_comment = r'/\*(.|\n)*?\*/|//.*'

    @_(r'\n+')
    def ignore_newline(self, t):
        self.lineno += len(t.value)

    # Regex Rules for tokens
    @_(r'[a-zA-Z_.][a-zA-Z0-9_.]*')
    def IDENTIFIER(self, t):
        match_value = t.value.lower()
        # Convert 'false' and 'true' to number literals
        if match_value == 'false':
            t.value = 0
            t.type = 'NUMBER_LITERAL'
        elif match_value == 'true':
            t.value = 1
            t.type = 'NUMBER_LITERAL'
        # Apply reserved word types
        elif match_value == 'table':
            t.type = 'TABLE'
        elif match_value == 'enum':
            t.type = 'ENUM'
        elif match_value == 'struct':
            t.type = 'STRUCT'
        return t

    @_(r'\d+|0x[0-9a-fA-F]+|\'\\?[^\']\'|\'\\\'\'')
    def NUMBER_LITERAL(self, t):
        if t.value[0] == '\'' and t.value[-1] == '\'':
            if t.value[1] == '\\':
                if t.value[2] in ESCAPE_CODES:
                    t.value = ESCAPE_CODES[t.value[2]]
                else:
                    raise ValueError("Invalid escape sequence {}".format(t.value))
            else:
                t.value = ord(t.value[1])
        elif t.value[:2] == '0x':
            t.value = int(t.value, 16)
        else:
            t.value = int(t.value)
        return t

    @_(r'"[^"]*"')
    def STRING_LITERAL(self, t):
        t.value = t.value[1:-1]
        return t

    COLON           = r':'
    SEMICOLON       = r';'
    COMMA           = r','
    EQUALS          = r'='

    #OPEN_PAREN      = r'\('
    #CLOSE_PAREN     = r'\)'
    OPEN_BRACKET    = r'\['
    CLOSE_BRACKET   = r'\]'
    OPEN_BRACE      = r'\{'
    CLOSE_BRACE     = r'\}'


class SeriaParser(Parser):
    start = 'schema'
    tokens = SeriaLexer.tokens
    #debugfile = 'parser.debug'

    @_('STRING_LITERAL')
    def literal(self, p):
        return p[0]

    @_('NUMBER_LITERAL')
    def literal(self, p):
        return p[0]

    @_('IDENTIFIER')
    def enum_members(self, p):
        return [EnumMember(name=p[0])]

    @_('IDENTIFIER EQUALS NUMBER_LITERAL')
    def enum_members(self, p):
        return [EnumMember(name=p[0], value=p[2])]

    @_('enum_members COMMA IDENTIFIER')
    def enum_members(self, p):
        p[0].append(EnumMember(name=p[2]))
        return p[0]

    @_('enum_members COMMA IDENTIFIER EQUALS NUMBER_LITERAL')
    def enum_members(self, p):
        p[0].append(EnumMember(name=p[2], value=p[4]))
        return p[0]

    @_('IDENTIFIER COLON IDENTIFIER SEMICOLON')
    def struct_member(self, p):
        return StructMember(name=p[0], type=p[2])

    @_('IDENTIFIER COLON IDENTIFIER EQUALS literal SEMICOLON')
    def struct_member(self, p):
        return StructMember(name=p[0], type=p[2], default=p[4])

    @_('IDENTIFIER COLON OPEN_BRACKET IDENTIFIER CLOSE_BRACKET SEMICOLON')
    def struct_member(self, p):
        return StructMember(name=p[0], type=p[3], vector=True)

    @_('IDENTIFIER COLON OPEN_BRACKET IDENTIFIER CLOSE_BRACKET EQUALS literal SEMICOLON')
    def struct_member(self, p):
        return StructMember(name=p[0], type=p[3], vector=True, default=p[6])

    @_('IDENTIFIER COLON OPEN_BRACKET IDENTIFIER COLON NUMBER_LITERAL CLOSE_BRACKET SEMICOLON')
    def struct_member(self, p):
        return StructMember(name=p[0], type=p[3], vector=True, vector_size=p[5])

    @_('IDENTIFIER COLON OPEN_BRACKET IDENTIFIER COLON NUMBER_LITERAL CLOSE_BRACKET EQUALS literal SEMICOLON')
    def struct_member(self, p):
        return StructMember(name=p[0], type=p[3], vector=True, default=p[8], vector_size=p[5])

    @_('')
    def struct_members(self, p):
        return []

    @_('struct_members struct_member')
    def struct_members(self, p):
        p[0].append(p[1])
        return p[0]

    @_('ENUM IDENTIFIER OPEN_BRACE enum_members CLOSE_BRACE')
    def definition(self, p):
        return EnumDefinition(name=p[1], members=p[3])

    @_('ENUM IDENTIFIER COLON IDENTIFIER OPEN_BRACE enum_members CLOSE_BRACE')
    def definition(self, p):
        return EnumDefinition(name=p[1], members=p[5], size=p[3])

    @_('STRUCT IDENTIFIER OPEN_BRACE struct_members CLOSE_BRACE')
    def definition(self, p):
        return StructDefinition(name=p[1], members=p[3])

    @_('TABLE IDENTIFIER OPEN_BRACE struct_members CLOSE_BRACE')
    def definition(self, p):
        return TableDefinition(name=p[1], members=p[3])

    @_('definition')
    def schema(self, p):
        return Schema({p.definition.name: p.definition})

    @_('schema definition')
    def schema(self, p):
        p.schema.definitions[p.definition.name] = p.definition
        return p.schema


@dataclass
class Primitive:
    c_name: str
    bit_width: Optional[int] = None
    signed: Optional[bool] = None

    @property
    def name(self):
        return self.c_name

    def __hash__(self):
        return hash(id(self))


class Primitives:
    Boolean = Primitive(c_name="bool")
    String = Primitive(c_name="char *")
    UInt8 = Primitive(c_name="uint8_t", bit_width=1, signed=False)
    Int8 = Primitive(c_name="int8_t", bit_width=1, signed=True)
    UInt16 = Primitive(c_name="uint16_t", bit_width=2, signed=False)
    Int16 = Primitive(c_name="int16_t", bit_width=2, signed=True)
    UInt32 = Primitive(c_name="uint32_t", bit_width=4, signed=False)
    Int32 = Primitive(c_name="int32_t", bit_width=4, signed=True)
    UInt64 = Primitive(c_name="uint64_t", bit_width=8, signed=False)
    Int64 = Primitive(c_name="int64_t", bit_width=8, signed=True)


BUILTIN_TYPES = {
    # Integer primitives
    'uint8': Primitives.UInt8,
    'int8': Primitives.Int8,
    'uint16': Primitives.UInt16,
    'int16': Primitives.Int16,
    'uint32': Primitives.UInt32,
    'int32': Primitives.Int32,
    'uint64': Primitives.UInt64,
    'int64': Primitives.Int64,
    # Non-integer primitives
    'boolean': Primitives.Boolean,
    'string': Primitives.String,
    # Aliases
    'long': Primitives.Int64,
    'ulong': Primitives.UInt64,
    'slong': Primitives.Int64,
    'int': Primitives.Int32,
    'uint': Primitives.UInt32,
    'sint': Primitives.Int32,
    'short': Primitives.Int16,
    'ushort': Primitives.UInt16,
    'sshort': Primitives.Int16,
    'byte': Primitives.UInt8,
    'ubyte': Primitives.UInt8,
    'sbyte': Primitives.Int8,
    'char': Primitives.Int8,
    'uchar': Primitives.UInt8,
    'schar': Primitives.Int8,
    'bool': Primitives.Boolean,
    'str': Primitives.String,
}


INTEGER_PRIMITIVES = {
    Primitives.UInt8,
    Primitives.Int8,
    Primitives.UInt16,
    Primitives.Int16,
    Primitives.UInt32,
    Primitives.Int32,
    Primitives.UInt64,
    Primitives.Int64,
}


@dataclass
class StructMember:
    name: str
    type: str
    default: Union[str, int, None] = None
    vector: bool = False
    vector_size: Optional[int] = None

    def resolve_type(self, schema):
        if self.type in BUILTIN_TYPES:
            self.type = BUILTIN_TYPES[self.type]
        else:
            self.type = schema.definitions[self.type]

    @property
    def pointer_type(self):
        if self.type.c_name.endswith('*'):
            separator = ""
        else:
            separator = " "

        if self.vector:
            return "{}{}**{}".format(self.type.c_name, separator, self.name)
        else:
            return "{}{}*{}".format(self.type.c_name, separator, self.name)

    @property
    def const_type(self):
        if self.type.c_name.endswith('*'):
            separator = ""
        else:
            separator = " "

        if self.vector:
            type_name = "{}{}*{}".format(self.type.c_name, separator, self.name)
        else:
            type_name = "{}{}{}".format(self.type.c_name, separator, self.name)
        
        if '*' in type_name:
            return 'const {}'.format(type_name)
        else:
            return type_name

    @property
    def c_type(self):
        if self.type.c_name.endswith('*'):
            separator = ""
        else:
            separator = " "

        if self.vector:
            if self.vector_size:
                return "{}{}{}[{}]".format(self.type.c_name, separator, self.name, self.vector_size)
            else:
                return "{}{}*{}".format(self.type.c_name, separator, self.name)
        else:
            return "{}{}{}".format(self.type.c_name, separator, self.name)

    def generate_typedef_field(self):
        if self.vector and self.vector_size is None:
            return (
                "{};\n".format(self.c_type) +
                "size_t {}_length;".format(self.name)
            )
        else:
            return "{};".format(self.c_type)

    def generate_typedef_present(self):
        return "bool {}_present;".format(self.name)

    def generate_signatures(self, parent):
        return dedent("""
            bool {struct}_set_{field}({struct}_t *s, {const_field_type}, size_t {field}_length);
            bool {struct}_get_{field}({struct}_t *s, {pointer_field_type}, size_t *{field}_length);
        """ if self.vector and self.vector_size is None else """
            bool {struct}_set_{field}({struct}_t *s, {const_field_type});
            bool {struct}_get_{field}({struct}_t *s, {pointer_field_type});
        """).format(
            struct=parent.name,
            field=self.name,
            pointer_field_type=self.pointer_type,
            const_field_type=self.const_type
        )

    def generate_free(self):
        if self.vector:
            free = "s->{}_present = false;".format(self.name)
            if self.type is Primitives.String:
                free += indent("\n" + dedent("""
                    for (size_t i=0; i < {length}; i++) {{
                        free(s->{name}[i]);
                    }}
                """).format(
                    name=self.name,
                    length=(
                        "s->{}_length".format(self.name)
                        if self.vector_size is None else
                        self.vector_size
                    )
                ))
            elif isinstance(self.type, (TableDefinition, StructDefinition)):
                free += indent("\n" + dedent("""
                    for (size_t i=0; i < {length}; i++) {{
                        {type_name}_free(s->{name}[i]);
                    }}
                """).format(
                    name=self.name,
                    type_name=self.type.name,
                    length=(
                        "s->{}_length".format(self.name)
                        if self.vector_size is None else
                        self.vector_size
                    )
                ))
            if self.vector_size is None:
                free += indent("\nfree(s->{name});".format(name=self.name), 2)
            return indent(dedent("""
                if (s->{name}_present) {{
                    {free}
                }}
            """).format(
                name=self.name,
                free=free
            ) + "\n")
        elif self.type is Primitives.String:
            return indent(dedent("""
                if (s->{name}_present) {{
                    s->{name}_present = false;
                    free(s->{name});
                }}
            """).format(
                name=self.name
            ) + "\n")
        elif isinstance(self.type, (TableDefinition, StructDefinition)):
            return indent(dedent("""
                if (s->{name}_present) {{
                    s->{name}_present = false;
                    {type_name}_free(s->{name});
                }}
            """).format(
                type_name=self.type.name,
                name=self.name
            ) + "\n")
        else:
            return ""

    def generate_member_sets(self, parent: Union[StructDefinition, TableDefinition]):
        if self.vector and not self.vector_size:
            return indent(dedent("""
                if (s->{name}_present) {{
                    {parent_name}_set_{name}(new_s, s->{name}, s->{name}_length);
                }}
            """).format(
                name=self.name,
                parent_name=parent.name
            ) + "\n")
        else:
            return indent(dedent("""
                if (s->{name}_present) {{
                    {parent_name}_set_{name}(new_s, s->{name});
                }}
            """).format(
                name=self.name,
                parent_name=parent.name
            ) + "\n")

    def generate_get_set(self, parent: Union[StructDefinition, TableDefinition]):
        params = {
            "parent_name": parent.name,
            "name": self.name,
            "const_type": self.const_type,
            "pointer_type": self.pointer_type,
            "type_name": self.type.name,
            "vector_size": self.vector_size,
            "default": self.default,
        }

        set_signature = "bool {parent_name}_set_{name}({parent_name}_t *s, {const_type}) {{".format(**params)
        set_implementation = self.generate_free()
        get_signature = "bool {parent_name}_get_{name}({parent_name}_t *s, {pointer_type}) {{".format(**params)
        get_implementation = "*{name} = s->{name};".format(**params)
        missing_get_implementation = "return false;".format(**params)

        if self.default is not None:
            if isinstance(self.default, str):
                missing_get_implementation = indent(dedent("""
                    *{name} = (char *)"{default}";
                    return true;
                """), 4).format(**params)
            else:
                missing_get_implementation = indent(dedent("""
                    *{name} = {default};
                    return true;
                """), 4).format(**params)

        if self.vector:
            if self.vector_size is None:
                set_signature = (
                    "bool {parent_name}_set_{name}({parent_name}_t *s, {const_type}, size_t {name}_length) {{"
                ).format(**params)
                get_signature = (
                    "bool {parent_name}_get_{name}({parent_name}_t *s, {pointer_type}, size_t *{name}_length) {{"
                ).format(**params)
                set_implementation += indent(dedent("""
                    s->{name}_length = {name}_length;
                    s->{name} = malloc(sizeof(*{name}) * {name}_length);
                    if (s->{name} == NULL) {{
                        return false;
                    }}
                """)).format(**params) + "\n    "
            else:
                set_implementation += (
                    "size_t {name}_length = {vector_size};"
                ).format(**params) + "\n    "
            if self.type is Primitives.String:
                set_implementation += indent(dedent("""
                    for (size_t i=0; i < {name}_length; i++) {{
                        s->{name}[i] = strdup({name}[i]);
                        if (s->{name}[i] == NULL) {{
                            for (size_t j=0; j < i; j++) {{
                                free(s->{name}[j]);
                            }}
                """) + (
                    indent("\n" + dedent("""
                        free(s->{name});
                    """) + "\n", 4)
                    if self.vector_size is None else
                    indent("\n", 4)
                ) +
                dedent("""
                            return false;
                        }}
                    }}
                """)).format(**params)
            elif isinstance(self.type, (TableDefinition, StructDefinition)):
                set_implementation += indent(dedent("""
                    for (size_t i=0; i < {name}_length; i++) {{
                        s->{name}[i] = {type_name}_copy({name}[i]);
                        if (s->{name}[i] == NULL) {{
                            for (size_t j=0; j < i; j++) {{
                                {type_name}_free(s->{name}[j]);
                            }}
                """) + (
                    indent("\n" + dedent("""
                        free(s->{name});
                    """) + "\n", 4)
                    if self.vector_size is None else
                    indent("\n", 4)
                ) +
                dedent("""
                            return false;
                        }}
                    }}
                """)).format(**params)
            else:
                set_implementation += indent(dedent("""
                    memcpy(s->{name}, {name}, sizeof(*{name}) * {name}_length);
                """)).format(**params)

        elif self.type is Primitives.String:
            set_implementation += indent(dedent("""
                s->{name} = strdup({name});
                if (s->{name} == NULL) {{
                    return false;
                }}
            """)).format(**params)
        elif isinstance(self.type, (TableDefinition, StructDefinition)):  
            set_implementation += indent(dedent("""
                s->{name} = {type_name}_copy({name});
                if (s->{name} == NULL) {{
                    return false;
                }}
            """)).format(**params)
        else:
            set_implementation += "s->{name} = {name};".format(**params)

        params["set_implementation"] = set_implementation
        params["set_signature"] = set_signature
        params["get_signature"] = get_signature
        params["missing_get_implementation"] = missing_get_implementation
        params["get_implementation"] = get_implementation
        
        return dedent("""
            {set_signature}
                {set_implementation}
                s->{name}_present = true;
                return true;
            }}

            {get_signature}
                if (s->{name}_present) {{
                    {get_implementation}
                    return true;
                }}
                else {{
                    {missing_get_implementation}
                }}
            }}
        """).format(**params)


@dataclass
class EnumMember:
    name: str
    value: Optional[int] = None

    def resolve_value(self, parent):
        if self.value is None:
            self.value = parent.next_value
        parent.values.add(self.value)
        parent.next_value = self.value + 1

    def generate_typedefs(self):
        return "{} = {}".format(self.name, self.value)


@dataclass
class StructDefinition:
    name: str
    members: List[StructMember] = field(default_factory=list)

    @property
    def c_name(self):
        return "{}_t *".format(self.name)

    def resolve_types(self, schema):
        for struct_member in self.members:
            struct_member.resolve_type(schema)

    def validate(self):
        for struct_member in self.members:
            # Below this are checks run only when a default is present
            if struct_member.default is None:
                continue
            # If this type is a struct or table, verify no default is set
            elif isinstance(struct_member.type, (StructDefinition, TableDefinition)):
                raise TypeError("Struct member of type '{} (Struct)' {}.{} cannot have a default value.".format(
                    struct_member.type.name, self.name, struct_member.name))
            # If this type is an enum, verify default is in the range of enum values
            elif isinstance(struct_member.type, EnumDefinition):
                if struct_member.default not in struct_member.type.values:
                    raise TypeError("Struct member of type '{} (Enum)' {}.{} cannot have value '{}'".format(
                        struct_member.type.name, self.name, struct_member.name, struct_member.default))
            # If this type is an integer primitive, verify default is an int
            elif struct_member.type in INTEGER_PRIMITIVES:
                if not isinstance(struct_member.default, int):
                    raise TypeError("The default value of {}.{} must be an integer.".format(
                        self.name, struct_member.name))
            # If this type is a string primitive, verify default is a string
            elif struct_member.type is Primitives.String:
                if not isinstance(struct_member.default, str):
                    raise TypeError("The default value of string {}.{} must be a string.".format(
                        self.name, struct_member.name))
            # If this type is a boolean primitive, verify default is 0 or 1
            elif struct_member.type is Primitives.Boolean:
                if struct_member.default != 0 and struct_member.default != 1:
                    raise TypeError("The default value of boolean {}.{} must be true (1) or false (0).".format(
                        self.name, struct_member.name))
            # Unrecognized type
            else:
                raise TypeError("Struct member {}.{} has an unrecognized type: '{}'".format(
                    self.name, struct_member.name, struct_member.type))

    def generate_typedefs(self):
        return dedent("""
            typedef struct {name}_t {{
                {members}
                {present}
            }} {name}_t;
        """).format(
            name=self.name,
            members=indent(
                "\n".join(m.generate_typedef_field() for m in self.members)
            ),
            present=indent(
                "\n".join(m.generate_typedef_present() for m in self.members)
            )
        )

    def generate_signatures(self):
        return (
            "{name}_t *{name}_new(void);\n".format(name=self.name) +
            "{name}_t *{name}_copy(const {name}_t *s);\n".format(name=self.name) +
            "void {name}_free({name}_t *s);\n".format(name=self.name) +
            "bool {name}_serialize({name}_t *s, uint8_t **buffer, size_t *buffer_size);\n".format(name=self.name) +
            "{name}_t *{name}_deserialize(const uint8_t *buffer, size_t buffer_size);\n".format(name=self.name) +
            "bool {name}_verify(const uint8_t *buffer, size_t buffer_size);\n".format(name=self.name) +
            "\n".join(m.generate_signatures(self) for m in self.members)
        )

    def generate_c_source(self):
        return dedent("""
            {name}_t *{name}_copy(const {name}_t *s) {{
                {name}_t *new_s = {name}_new();
                {member_sets}
                return new_s;
            }}

            {name}_t *{name}_new(void) {{
                return calloc(1, sizeof({name}_t));
            }}

            void {name}_free({name}_t *s) {{
                {frees}
                free(s);
            }}
            
            bool {name}_serialize({name}_t *s, uint8_t **buffer, size_t *buffer_size) {{

            }}

            {name}_t *{name}_deserialize(const uint8_t *buffer, size_t buffer_size) {{

            }}

            bool {name}_verify(const uint8_t *buffer, size_t buffer_size) {{

            }}

            {get_set}
        """).format(
            frees="".join(m.generate_free() for m in self.members),
            get_set="\n\n".join(m.generate_get_set(self) for m in self.members),
            member_sets="".join(m.generate_member_sets(self) for m in self.members),
            name=self.name
        )

    def generate_python(self):
        return ""


class TableDefinition(StructDefinition):
    pass


@dataclass
class EnumDefinition:
    name: str
    members: List[EnumMember] = field(default_factory=list)
    size: str = 'uint16'
    next_value: int = 0
    values: Set[int] = field(default_factory=set)

    @property
    def c_name(self):
        return "{}_e".format(self.name)

    def resolve_types(self, schema):
        self.size = BUILTIN_TYPES.get(self.size, self.size)
        if self.size not in INTEGER_PRIMITIVES:
            raise TypeError("the type of an enum definition must be an integer primitive, not '{}'".format(self.size))
        for enum_member in self.members:
            enum_member.resolve_value(self)

    def validate(self):
        pass

    def generate_typedefs(self):
        return dedent("""
            typedef enum {name}_e {{
                {members}
            }} {name}_e;
        """).format(name=self.name, members=indent(
            ",\n".join(m.generate_typedefs() for m in self.members)
        ))

    def generate_python(self):
        return ""


@dataclass
class Schema:
    definitions: Dict[str, Union[EnumDefinition, StructDefinition, TableDefinition]]
    name: str = "ANONYMOUS_SCHEMA"

    @property
    def structs(self):
        return (d for d in self.definitions.values() if not isinstance(d, EnumDefinition))

    def resolve_types(self):
        for definition in self.definitions.values():
            definition.resolve_types(self)

    def validate(self):
        for definition in self.definitions.values():
            definition.validate()

    def generate_c_header(self):
        i = 0
        return (
            "#ifndef _SERIALIB_{}_H\n".format(self.name) +
            "#define _SERIALIB_{}_H\n".format(self.name) +
            "\n" +
            "#include <stdint.h>\n"  +
            "#include <stdbool.h>\n" +
            "#include <stdlib.h>\n"  +
            "\n" +
            "typedef enum TableType_e {\n" +
            "    TABLE_TYPE_INVALID = 0,\n    " +
            indent(',\n'.join(
                "TABLE_TYPE_{} = {}".format(d.name, i := i+1)
                for d in self.structs
            )) +
            "\n} TableType_e;\n\n" +
            "\n\n".join(d.generate_typedefs() for d in self.definitions.values()) +
            "\n\n" +
            "TableType_e {}_table_type(const uint8_t *buffer, size_t buffer_size);\n".format(
                self.name.lower()
            ) +
            "\n" + "\n\n".join(d.generate_signatures() for d in self.structs) + "\n\n" +
            "#endif\n"
        )

    def generate_c_source(self, header_path):
        return (
            "#include <stdlib.h>\n" +
            "#include \"{}\"\n\n".format(header_path) +
            "\n\n".join(d.generate_c_source() for d in self.structs)
        )

    def generate_python(self):
        return "\n".join(d.generate_python() for d in self.definitions.values())


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('schema', type=Path)
    parser.add_argument('--python', type=Path, default=None)
    parser.add_argument('--c-source', type=Path, default=None)
    parser.add_argument('--c-header', type=Path, default=None)
    args = parser.parse_args()

    # Read schema file
    with open(args.schema, "r") as f:
        text_schema = f.read()

    # Lex and parse schema
    lexer = SeriaLexer()
    seria_parser = SeriaParser()
    schema: Schema = seria_parser.parse(lexer.tokenize(text_schema))
    if not schema:
        print("error: invalid schema file", file=sys.stderr)
        return 1

    schema.name = str(args.schema).replace('.', '_').upper()

    # Resolve type references
    schema.resolve_types()

    # Validate defaults
    schema.validate()

    # Output to files
    if not args.python:
        args.python = args.schema.with_suffix('.py')

    if not args.c_source:
        args.c_source = args.schema.with_suffix('.c')
    
    if not args.c_header:
        args.c_header = args.schema.with_suffix('.h')

    python_lib = schema.generate_python()
    with open(args.python, "w") as f:
        f.write(python_lib)

    c_source = schema.generate_c_source(args.c_header.name)
    with open(args.c_source, "w") as f:
        f.write(c_source)

    c_header = schema.generate_c_header()
    with open(args.c_header, "w") as f:
        f.write(c_header)

    return 0


if __name__ == '__main__':
    sys.exit(main())
