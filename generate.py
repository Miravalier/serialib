#!/usr/bin/env python3
from __future__ import annotations

import sys
import textwrap
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

from prettyprinter import install_extras, pprint
from sly import Lexer, Parser

# Pretty printer dataclasses support
install_extras(include=['dataclasses'], warn_on_error=True)


def join_iterate(seq):
    seq = iter(seq)
    try:
        item = next(seq)
    except StopIteration:
        return

    while True:
        try:
            next_item = next(seq)
            yield item, False
            item = next_item
        except StopIteration:
            yield item, True
            return


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

    OPEN_BRACKET    = r'\['
    CLOSE_BRACKET   = r'\]'
    OPEN_BRACE      = r'\{'
    CLOSE_BRACE     = r'\}'


class SeriaParser(Parser):
    start = '_schema'
    tokens = SeriaLexer.tokens
    schema = None

    @_('STRING_LITERAL')
    def literal(self, p):
        return p[0]

    @_('NUMBER_LITERAL')
    def literal(self, p):
        return p[0]

    @_('IDENTIFIER')
    def enum_members(self, p):
        return [EnumMember(self.schema, name=p[0])]

    @_('IDENTIFIER EQUALS NUMBER_LITERAL')
    def enum_members(self, p):
        return [EnumMember(self.schema, name=p[0], value=p[2])]

    @_('enum_members COMMA IDENTIFIER')
    def enum_members(self, p):
        p[0].append(EnumMember(self.schema, name=p[2]))
        return p[0]

    @_('enum_members COMMA IDENTIFIER EQUALS NUMBER_LITERAL')
    def enum_members(self, p):
        p[0].append(EnumMember(self.schema, name=p[2], value=p[4]))
        return p[0]

    @_('IDENTIFIER COLON IDENTIFIER SEMICOLON')
    def struct_member(self, p):
        return StructMember(self.schema, name=p[0], type=p[2])

    @_('IDENTIFIER COLON IDENTIFIER EQUALS literal SEMICOLON')
    def struct_member(self, p):
        return StructMember(self.schema, name=p[0], type=p[2], default=p[4])

    @_('IDENTIFIER COLON OPEN_BRACKET IDENTIFIER CLOSE_BRACKET SEMICOLON')
    def struct_member(self, p):
        return StructMember(self.schema, name=p[0], type=p[3], vector=True)

    @_('IDENTIFIER COLON OPEN_BRACKET IDENTIFIER CLOSE_BRACKET EQUALS literal SEMICOLON')
    def struct_member(self, p):
        return StructMember(self.schema, name=p[0], type=p[3], vector=True, default=p[6])

    @_('IDENTIFIER COLON OPEN_BRACKET IDENTIFIER COLON NUMBER_LITERAL CLOSE_BRACKET SEMICOLON')
    def struct_member(self, p):
        return StructMember(self.schema, name=p[0], type=p[3], vector=True, vector_size=p[5])

    @_('IDENTIFIER COLON OPEN_BRACKET IDENTIFIER COLON NUMBER_LITERAL CLOSE_BRACKET EQUALS literal SEMICOLON')
    def struct_member(self, p):
        return StructMember(self.schema, name=p[0], type=p[3], vector=True, default=p[8], vector_size=p[5])

    @_('')
    def struct_members(self, p):
        return []

    @_('struct_members struct_member')
    def struct_members(self, p):
        p[0].append(p[1])
        return p[0]

    @_('ENUM IDENTIFIER OPEN_BRACE enum_members CLOSE_BRACE')
    def definition(self, p):
        return EnumDefinition(self.schema, name=p[1], members=p[3])

    @_('ENUM IDENTIFIER COLON IDENTIFIER OPEN_BRACE enum_members CLOSE_BRACE')
    def definition(self, p):
        return EnumDefinition(self.schema, name=p[1], members=p[5], size=p[3])

    @_('STRUCT IDENTIFIER OPEN_BRACE struct_members CLOSE_BRACE')
    def definition(self, p):
        return StructDefinition(self.schema, name=p[1], members=p[3])

    @_('TABLE IDENTIFIER OPEN_BRACE struct_members CLOSE_BRACE')
    def definition(self, p):
        return TableDefinition(self.schema, name=p[1], members=p[3])

    @_('definition')
    def _schema(self, p):
        self.schema = Schema({p.definition.name: p.definition})
        p.definition.schema = self.schema
        for member in p.definition.members:
            member.schema = self.schema
        return self.schema

    @_('_schema definition')
    def _schema(self, p):
        p._schema.definitions[p.definition.name] = p.definition
        return p._schema


@dataclass
class Primitive:
    c_name: str
    byte_width: Optional[int] = None
    signed: Optional[bool] = None

    @property
    def name(self):
        return self.c_name

    def __hash__(self):
        return hash(id(self))


class Primitives:
    Boolean = Primitive(c_name="bool")
    String = Primitive(c_name="char *")
    UInt8 = Primitive(c_name="uint8_t", byte_width=1, signed=False)
    Int8 = Primitive(c_name="int8_t", byte_width=1, signed=True)
    UInt16 = Primitive(c_name="uint16_t", byte_width=2, signed=False)
    Int16 = Primitive(c_name="int16_t", byte_width=2, signed=True)
    UInt32 = Primitive(c_name="uint32_t", byte_width=4, signed=False)
    Int32 = Primitive(c_name="int32_t", byte_width=4, signed=True)
    UInt64 = Primitive(c_name="uint64_t", byte_width=8, signed=False)
    Int64 = Primitive(c_name="int64_t", byte_width=8, signed=True)


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


class SchemaElement:
    schema: Schema

    def add_c_comment(self, *args, **kwargs):
        self.schema.add_c_comment(*args, **kwargs)

    def add_py_comment(self, *args, **kwargs):
        self.schema.add_py_comment(*args, **kwargs)

    def add_comment(self, *args, **kwargs):
        self.schema.add_comment(*args, **kwargs)

    def push_parameters(self, *args, **kwargs):
        self.schema.push_parameters(*args, **kwargs)

    def pop_parameters(self, *args, **kwargs):
        self.schema.pop_parameters(*args, **kwargs)

    def set_parameter(self, *args, **kwargs):
        self.schema.set_parameter(*args, **kwargs)

    def add_line(self, *args, **kwargs):
        self.schema.add_line(*args, **kwargs)

    def skip_line(self, *args, **kwargs):
        self.schema.skip_line(*args, **kwargs)

    def pop_line(self, *args, **kwargs):
        return self.schema.pop_line(*args, **kwargs)

    def start_block(self, *args, **kwargs):
        self.schema.start_block(*args, **kwargs)

    def end_block(self, *args, **kwargs):
        self.schema.end_block(*args, **kwargs)

    def serialize_py_varint(self, *args, **kwargs):
        self.schema.serialize_py_varint(*args, **kwargs)

    def serialize_c_varint(self, *args, **kwargs):
        self.schema.serialize_c_varint(*args, **kwargs)

    def deserialize_py_varint(self, *args, **kwargs):
        self.schema.deserialize_py_varint(*args, **kwargs)

    def deserialize_c_varint(self, *args, **kwargs):
        self.schema.deserialize_c_varint(*args, **kwargs)


@dataclass
class StructMember(SchemaElement):
    schema: Schema
    name: str
    type: Union[
        StructDefinition, 
        TableDefinition, 
        EnumDefinition, 
        Primitives.String, 
        Primitives.Boolean,
        Primitives.Int8
    ]
    default: Union[str, int, None] = None
    vector: bool = False
    vector_size: Optional[int] = None
    field_id: Optional[int] = None

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
    def param_type(self):
        if self.type.c_name.endswith('*'):
            separator = ""
        else:
            separator = " "

        if self.vector:
            type_name = "{}{}*{}".format(self.type.c_name, separator, self.name)
        else:
            type_name = "{}{}{}".format(self.type.c_name, separator, self.name)
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

    @property
    def cast(self):
        if self.type.c_name.endswith('*'):
            separator = ""
        else:
            separator = " "

        if self.vector:
            return "{}{}*".format(self.type.c_name, separator)
        else:
            return "{}".format(self.type.c_name)
    
    @property
    def python_type(self):
        if isinstance(self.type, (StructDefinition, TableDefinition, EnumDefinition)):
            s = self.type.name
        elif self.type is Primitives.String:
            s = 'str'
        elif self.type is Primitives.Boolean:
            s = 'bool'
        elif self.type in INTEGER_PRIMITIVES:
            s = 'int'

        if self.vector:
            s = "Optional[List[{}]]".format(s)
        else:
            s = "Optional[{}]".format(s)
        return s

    @property
    def python_parameter(self):
        return "{}: {} = None".format(self.name, self.python_type)

    def generate_typedef_field(self):
        self.add_line("{};".format(self.c_type))
        if self.vector and self.vector_size is None:
            self.add_line("size_t {}_length;".format(self.name))

    def generate_typedef_present(self):
        self.add_line("bool {}_present: 1;".format(self.name))

    def generate_signatures(self, parent: Union[StructDefinition, TableDefinition]):
        self.set_parameter("struct", parent.name)
        self.set_parameter("field", self.name)
        self.set_parameter("type_name", self.type.name)
        self.set_parameter(
            "default",
            '"{}"'.format(self.default)
            if isinstance(self.default, str) else
            self.default
        )
        params = {
            "s": """
                Any {struct}_t, returned from one of `{struct}_new()`, `{struct}_copy()`,
                or `{struct}_deserialize()`.
            """,
        }
        if self.vector:
            if self.vector_size is None:
                params[self.name] = "Array of `{field}_length` {type_name} to store in the {struct}."
            else:
                params[self.name] = "Array of " + str(self.vector_size) + " {type_name} to store in the {struct}."
        else:
            params[self.name] = "{type_name} to store in the {struct}."
        if self.vector and self.vector_size is None:
            if isinstance(self.type, StructDefinition) or self.type is Primitives.String:
                params[self.name] = "{type_name} to store in the {field} field of the given {struct}."
            self.add_c_comment(
                comment="Store a copy of the given {type_name} array in the given {struct}.",
                return_comment="True on success, false if memory allocation fails.",
                **params
            )
            self.add_line("bool {struct}_set_{field}({struct}_t *s, " + self.param_type + ", size_t {field}_length);")
            self.skip_line()

            if self.default is not None:
                self.add_c_comment(
                    comment="""
                        Retrieve the {field} field from the given {struct} if that field is present,
                        or the default value ({default}) if the {field} field is not present.
                    """,
                    return_comment="Always returns true."
                )
            else:
                self.add_c_comment(
                    comment="Retrieve the {field} field from the given {struct}.",
                    return_comment="True if the field is present, false otherwise."
                )
            self.add_line("bool {struct}_get_{field}({struct}_t *s, " + self.pointer_type + ", size_t *{field}_length);")
            self.skip_line()
        else:
            if self.vector:
                self.add_c_comment(
                    comment="Store a copy of the given {type_name} array in the {field} field of the given {struct}.",
                    return_comment="True on success, false if memory allocation fails.",
                    **params
                )
            elif isinstance(self.type, StructDefinition) or self.type is Primitives.String:
                self.add_c_comment(
                    comment="Store a copy of the given {type_name} in the {field} field of the given {struct}.",
                    return_comment="True on success, false if memory allocation fails.",
                    **params
                )
            else:
                self.add_c_comment(
                    comment="Store the given {type_name} in the {field} field of the given {struct}.",
                    return_comment="True on success, false if memory allocation fails.",
                    **params
                )
            self.add_line("bool {struct}_set_{field}({struct}_t *s, " + self.param_type + ");")
            self.skip_line()

            if self.default is not None:
                self.add_c_comment(
                    comment="""
                        Retrieve the {field} field from the given {struct} if that field is present,
                        or the default value ({default}) if the {field} field is not present.
                    """,
                    return_comment="Always returns true."
                )
            else:
                self.add_c_comment(
                    comment="Retrieve the {field} field from the given {struct}.",
                    return_comment="True if the field is present, false otherwise."
                )
            self.add_line("bool {struct}_get_{field}({struct}_t *s, " + self.pointer_type + ");")
            self.skip_line()

    def generate_free(self, parent: Union[StructDefinition, TableDefinition]):
        self.push_parameters()
        self.set_parameter("name", self.name)
        self.set_parameter("type_name", self.type.name)
        if self.vector:
            self.start_block("if (s->{name}_present) {{")
            self.add_line("s->{name}_present = false;")
            if self.type is Primitives.String:
                if self.vector_size is None:
                    self.start_block("for (size_t i=0; i < s->{name}_length; i++) {{")
                else:
                    self.start_block("for (size_t i=0; i < " + str(self.vector_size) + "; i++) {{")
                self.add_line("free(s->{name}[i]);")
                self.end_block("}}")
            elif isinstance(self.type, (TableDefinition, StructDefinition)):
                if self.vector_size is None:
                    self.start_block("for (size_t i=0; i < s->{name}_length; i++) {{")
                else:
                    self.start_block("for (size_t i=0; i < " + str(self.vector_size) + "; i++) {{")
                self.add_line("{type_name}_free(s->{name}[i]);")
                self.end_block("}}")
            if self.vector_size is None:
                self.add_line("free(s->{name});")
            self.end_block("}}")
        elif self.type is Primitives.String:
            self.start_block("if (s->{name}_present) {{")
            self.add_line("s->{name}_present = false;")
            self.add_line("free(s->{name});")
            self.end_block("}}")
        elif isinstance(self.type, (TableDefinition, StructDefinition)):
            self.start_block("if (s->{name}_present) {{")
            self.add_line("s->{name}_present = false;")
            self.add_line("{type_name}_free(s->{name});")
            self.end_block("}}")
        self.pop_parameters()

    def generate_c_deserialize(self, parent: Union[StructDefinition, TableDefinition]):
        self.push_parameters()
        self.set_parameter("name", self.name)
        self.set_parameter("type_name", self.type.name)
        self.set_parameter("field_id", self.field_id)
        self.add_line("// TODO deserialize {name}")
        self.pop_parameters()

    def generate_c_serialize(self, parent: Union[StructDefinition, TableDefinition]):
        self.push_parameters()
        self.set_parameter("name", self.name)
        self.set_parameter("type_name", self.type.name)
        self.set_parameter("field_id", self.field_id)
        self.start_block("if (s->{name}_present) {{")
        self.add_line("((uint16_t *)buffer)[1] += 1;")

        if self.vector:
            self.set_parameter("length", self.vector_size if self.vector_size is not None else "s->{}_length".format(self.name))
            if self.vector_size is None:
                self.start_block("if (s->{name}_length > 0xFF) {{")
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id} | 0x8000;")
                self.add_line("bytes_written += 2;")
                self.add_line("((uint32_t*)(buffer + bytes_written))[0] = (uint32_t)s->{name}_length;")
                self.add_line("bytes_written += 4;")
                self.end_block("}}")
                self.start_block("else {{")
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id};")
                self.add_line("bytes_written += 2;")
                self.add_line("((uint8_t*)(buffer + bytes_written))[0] = (uint8_t)s->{name}_length;")
                self.add_line("bytes_written += 1;")
                self.end_block("}}")
            else:
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id};")
                self.add_line("bytes_written += 2;")
            if self.type is Primitives.Boolean:
                self.add_line("size_t byte_count = (({length} - 1) / 8) + 1;")
                self.add_line("bzero(buffer + bytes_written, byte_count);")
            self.start_block("for (size_t i = 0; i < {length}; i++) {{")
            if isinstance(self.type, (TableDefinition, StructDefinition)):
                self.add_line("uint8_t *child_buffer;")
                self.add_line("size_t child_buffer_size;")
                self.add_line("{type_name}_serialize(s->{name}[i], &child_buffer, &buffer_size);")
                self.serialize_c_varint("child_buffer_size")
                self.add_line("memcpy(buffer + bytes_written, child_buffer, child_buffer_size);")
                self.add_line("bytes_written += child_buffer_size;")
                self.add_line("free(child_buffer);")
            elif isinstance(self.type, EnumDefinition):
                self.set_parameter("byte_width", self.type.size.byte_width)
                self.set_parameter("c_type", self.type.size.c_name)
                self.add_line("(({c_type}*)(buffer + bytes_written))[0] = ({c_type})s->{name}[i];")
                self.add_line("bytes_written += {byte_width};")
            elif self.type in INTEGER_PRIMITIVES:
                self.set_parameter("byte_width", self.type.byte_width)
                self.set_parameter("c_type", self.type.c_name)
                self.add_line("(({c_type}*)(buffer + bytes_written))[0] = ({c_type})s->{name}[i];")
                self.add_line("bytes_written += {byte_width};")
            elif self.type is Primitives.String:
                self.add_line("size_t string_size = strlen(s->{name}[i]);")
                self.serialize_c_varint("string_size")
                self.add_line("memcpy(buffer + bytes_written, s->{name}[i], string_size);")
                self.add_line("bytes_written += string_size;")
            elif self.type is Primitives.Boolean:
                self.add_line("(buffer + bytes_written + i / 8)[0] |= 1 << (7 - (i & 7));")
            else:
                raise TypeError("Unrecognized member type '{}'".format(self.type))
            self.end_block("}}")
            if self.type is Primitives.Boolean:
                self.add_line("bytes_written += byte_count;")

        else:
            if isinstance(self.type, (TableDefinition, StructDefinition)):
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id};")
                self.add_line("bytes_written += 2;")
                self.add_line("uint8_t *child_buffer;")
                self.add_line("size_t child_buffer_size;")
                self.add_line("{type_name}_serialize(s->{name}, &child_buffer, &buffer_size);")
                self.add_line("memcpy(buffer + bytes_written, child_buffer, child_buffer_size);")
                self.add_line("bytes_written += child_buffer_size;")
                self.add_line("free(child_buffer);")
            elif isinstance(self.type, EnumDefinition):
                self.set_parameter("byte_width", self.type.size.byte_width)
                self.set_parameter("c_type", self.type.size.c_name)
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id};")
                self.add_line("bytes_written += 2;")
                self.add_line("(({c_type}*)(buffer + bytes_written))[0] = s->{name};")
                self.add_line("bytes_written += {byte_width};")
            elif self.type in INTEGER_PRIMITIVES:
                self.set_parameter("byte_width", self.type.byte_width)
                self.set_parameter("c_type", self.type.c_name)
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id};")
                self.add_line("bytes_written += 2;")
                self.add_line("(({c_type}*)(buffer + bytes_written))[0] = s->{name};")
                self.add_line("bytes_written += {byte_width};")
            elif self.type is Primitives.String:
                self.add_line("size_t string_size = strlen(s->{name});")
                self.start_block("if (string_size > 255) {{")
                self.add_line("buffer_size += 2 + sizeof(uint32_t) + string_size;")
                self.add_line("buffer = realloc(buffer, buffer_size);")
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id} | 0x8000;")
                self.add_line("bytes_written += 2;")
                self.add_line("((uint32_t*)(buffer + bytes_written))[0] = string_size;")
                self.add_line("bytes_written += 4;")
                self.add_line("memcpy(buffer + bytes_written, s->{name}, string_size);")
                self.add_line("bytes_written += string_size;")
                self.end_block("}}")
                self.start_block("else {{")
                self.add_line("buffer_size += 2 + sizeof(uint8_t) + strlen(s->{name});")
                self.add_line("buffer = realloc(buffer, buffer_size);")
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id};")
                self.add_line("bytes_written += 2;")
                self.add_line("((uint8_t*)(buffer + bytes_written))[0] = string_size;")
                self.add_line("bytes_written += 1;")
                self.add_line("memcpy(buffer + bytes_written, s->{name}, string_size);")
                self.add_line("bytes_written += string_size;")
                self.end_block("}}")
            elif self.type is Primitives.Boolean:
                self.start_block("if (s->{name}) {{")
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id} | 0x8000;")
                self.end_block("}}")
                self.start_block("else {{")
                self.add_line("((uint16_t*)(buffer + bytes_written))[0] = {field_id};")
                self.end_block("}}")
                self.add_line("bytes_written += 2;")
            else:
                raise TypeError("Unrecognized member type '{}'".format(self.type))

        self.end_block("}}")
        self.pop_parameters()

    def generate_copy_sets(self, parent: Union[StructDefinition, TableDefinition]):
        self.push_parameters()
        self.set_parameter("parent_name", parent.name)
        self.set_parameter("name", self.name)
        self.set_parameter("cast", self.cast)
        self.start_block("if (s->{name}_present) {{")

        if self.vector and not self.vector_size:
            self.start_block("if (!{parent_name}_set_{name}(new_s, ({cast})s->{name}, s->{name}_length)) {{")
        else:
            self.start_block("if (!{parent_name}_set_{name}(new_s, s->{name})) {{")

        self.add_line("{parent_name}_free(new_s);")
        self.add_line("return NULL;")
        self.end_block("}}")
        self.end_block("}}")
        self.pop_parameters()

    def generate_get_set(self, parent: Union[StructDefinition, TableDefinition]):
        self.push_parameters()
        self.set_parameter("parent_name", parent.name)
        self.set_parameter("name", self.name)
        self.set_parameter("param_type", self.param_type)
        self.set_parameter("pointer_type", self.pointer_type)
        self.set_parameter("type_name", self.type.name)
        self.set_parameter("vector_size", self.vector_size)
        self.set_parameter("default", self.default)
        if self.vector_size is None:
            self.set_parameter("length", "{}_length".format(self.name))
        else:
            self.set_parameter("length", str(self.vector_size))

        # Set
        if self.vector and self.vector_size is None:
            self.start_block("bool {parent_name}_set_{name}({parent_name}_t *s, {param_type}, size_t {name}_length) {{")
        else:
            self.start_block("bool {parent_name}_set_{name}({parent_name}_t *s, {param_type}) {{")

        if self.vector:
            self.generate_free(parent)
            # Allocate space for sizeless arrays
            if self.vector_size is None:
                self.add_line("s->{name}_length = {name}_length;")
                self.add_line("s->{name} = malloc(sizeof(*{name}) * {name}_length);")
                self.start_block("if (s->{name} == NULL) {{")
                self.add_line("return false;")
                self.end_block("}}")
            # Strdup() in all strings
            if self.type is Primitives.String:
                self.start_block("for (size_t i=0; i < {length}; i++) {{")
                self.add_line("s->{name}[i] = strdup({name}[i]);")
                self.start_block("if (s->{name}[i] == NULL) {{")
                self.start_block("for (size_t j=0; j < i; j++) {{")
                self.add_line("free(s->{name}[j]);")
                self.end_block("}}")
                self.add_line("return false;")
                self.end_block("}}")
                self.end_block("}}")
            # <name>_copy() in all structs
            elif isinstance(self.type, (TableDefinition, StructDefinition)):
                self.start_block("for (size_t i=0; i < {length}; i++) {{")
                self.add_line("s->{name}[i] = {type_name}_copy({name}[i]);")
                self.start_block("if (s->{name}[i] == NULL) {{")
                self.start_block("for (size_t j=0; j < i; j++) {{")
                self.add_line("{type_name}_free(s->{name}[j]);")
                self.end_block("}}")
                self.add_line("return false;")
                self.end_block("}}")
                self.end_block("}}")
            else:
                self.add_line("memcpy(s->{name}, {name}, sizeof(*{name}) * {length});")
        elif self.type is Primitives.String:
            self.generate_free(parent)
            self.add_line("s->{name} = strdup({name});")
            self.start_block("if (s->{name} == NULL) {{")
            self.add_line("return false;")
            self.end_block("}}")
        elif isinstance(self.type, (TableDefinition, StructDefinition)):
            self.generate_free(parent)
            self.add_line("s->{name} = {type_name}_copy({name});")
            self.start_block("if (s->{name} == NULL) {{")
            self.add_line("return false;")
            self.end_block("}}")
        else:
            self.add_line("s->{name} = {name};")

        self.add_line("s->{name}_present = true;")
        self.add_line("return true;")

        self.end_block("}}")
        self.skip_line()

        # Get
        if self.vector and self.vector_size is None:
            self.start_block("bool {parent_name}_get_{name}({parent_name}_t *s, {pointer_type}, size_t *{name}_length) {{")
        else:
            self.start_block("bool {parent_name}_get_{name}({parent_name}_t *s, {pointer_type}) {{")
        self.start_block("if (s->{name}_present) {{")
        if self.vector and self.vector_size is not None:
            self.add_line("*{name} = (void *)&s->{name};")
        else:
            self.add_line("*{name} = s->{name};")
        if self.vector and self.vector_size is None:
            self.add_line("*{name}_length = s->{name}_length;")
        self.end_block("}}")
        self.start_block("else {{")
        if isinstance(self.default, str):
            self.add_line('*{name} = (char *)"{default}";')
        elif isinstance(self.default, int):
            self.add_line("*{name} = {default};")
        else:
            self.add_line("return false;")
        self.end_block("}}")

        self.add_line("return true;")
        self.end_block("}}")
        self.skip_line()

        self.pop_parameters()

    def generate_python_serialize(self):
        """
        Struct Member - Serialize
        """
        if self.vector:
            if self.vector_size is None:
                self.add_line("field_length = len(self.{field})")
                self.serialize_py_varint("field_length")
            else:
                self.set_parameter("vector_size", self.vector_size)
                self.add_line("field_length = {vector_size}")

            if self.type is Primitives.Boolean:
                self.add_line("data = bytearray(((field_length - 1) // 8) + 1)")

            self.start_block("for i in range(field_length):")
            if isinstance(self.type, (StructDefinition, TableDefinition)):
                self.add_line("child_buf = self.{field}[i].serialize()")
                self.add_line("child_length = len(child_buf)")
                self.serialize_py_varint("child_length")
                self.add_line("buf.extend(child_buf)")
            elif isinstance(self.type, EnumDefinition):
                self.set_parameter("bit_width", self.type.size.byte_width*8)
                self.add_line("buf.extend(uint{bit_width}(self.{field}[i]))")
            elif self.type is Primitives.String:
                self.add_line("string_length = len(self.{field}[i])")
                self.serialize_py_varint("string_length")
                self.add_line("buf.extend(self.{field}[i].encode('utf-8'))")
            elif self.type is Primitives.Boolean:
                self.start_block("if self.{field}[i]:")
                self.add_line("data[i//8] |= 1 << (7 - i & 7)")
                self.end_block()
            elif self.type in INTEGER_PRIMITIVES:
                self.set_parameter("bit_width", self.type.byte_width*8)
                self.add_line("buf.extend(uint{bit_width}(self.{field}[i]))")
            else:
                raise TypeError("Unrecognized struct member type")
            self.end_block()

            if self.type is Primitives.Boolean:
                self.add_line("buf.extend(data)")
        else:
            if isinstance(self.type, (StructDefinition, TableDefinition)):
                self.add_line("child_buf = self.{field}.serialize()")
                self.add_line("child_length = len(child_buf)")
                self.serialize_py_varint("child_length")
                self.add_line("buf.extend(child_buf)")
            elif isinstance(self.type, EnumDefinition):
                self.set_parameter("bit_width", self.type.size.byte_width*8)
                self.add_line("buf.extend(uint{bit_width}(self.{field}))")
            elif self.type is Primitives.String:
                self.add_line("string_length = len(self.{field})")
                self.serialize_py_varint("string_length")
                self.add_line("buf.extend(self.{field}.encode('utf-8'))")
            elif self.type is Primitives.Boolean:
                self.start_block("if self.{field}:")
                self.add_line("buf.extend(uint8(1))")
                self.end_block()
                self.start_block("else:")
                self.add_line("buf.extend(uint8(0))")
                self.end_block()
            elif self.type in INTEGER_PRIMITIVES:
                self.set_parameter("bit_width", self.type.byte_width*8)
                self.add_line("buf.extend(uint{bit_width}(self.{field}))")
            else:
                raise TypeError("Unrecognized struct member type")

    def generate_python_deserialize(self):
        """
        Struct Member - Deserialize
        """

    def generate_python_initialize(self):
        """
        Struct Member - Initialization
        """
        self.set_parameter("type_name", self.type.name)

        if self.vector and self.vector_size is None:
            self.start_block("if {field} is None:")
            self.add_line("self.{field} = []")
            self.end_block()
            self.start_block("else:")
            self.add_line("self.{field} = {field}")
            self.end_block()
        else:
            self.add_line("self.{field} = {field}")


@dataclass
class EnumMember(SchemaElement):
    schema: Schema
    name: str
    value: Optional[int] = None

    def resolve_value(self, parent):
        if self.value is None:
            self.value = parent.next_value
        parent.values.add(self.value)
        parent.next_value = self.value + 1


@dataclass
class StructDefinition(SchemaElement):
    schema: Schema
    name: str
    members: List[StructMember] = field(default_factory=list)
    table_id: Optional[int] = None

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
        self.set_parameter("name", self.name)
        self.start_block("typedef struct {name}_t {{")
        for member in self.members:
            member.generate_typedef_field()
        for member in self.members:
            member.generate_typedef_present()
        self.end_block("}} {name}_t;")

    def generate_signatures(self):
        self.set_parameter("name", self.name)

        self.add_c_comment(
            comment="Creates a new {name}_t on the heap.",
            return_comment="A newly allocated {name}_t. Must be freed with `{name}_free()`."
        )
        self.add_line("{name}_t *{name}_new(void);")
        self.skip_line()

        self.add_c_comment(
            comment="Creates a copy of an existing {name}_t.",
            return_comment="A newly allocated {name}_t. Must be freed with `{name}_free()`."
        )
        self.add_line("{name}_t *{name}_copy({name}_t *s);")
        self.skip_line()

        self.add_c_comment(
            comment="""
                Deallocates an existing {name}_t that was previously allocated with `{name}_new()`,
                `{name}_copy()`, or `{name}_deserialize()`.
            """
        )
        self.add_line("void {name}_free({name}_t *s);")
        self.skip_line()

        self.add_c_comment(
            comment="Serialize a {name}_t into a buffer. The {name}_t is unchanged.",
            s="The {name}_t to serialize.",
            buffer="Place to store the newly allocated buffer.",
            buffer_size="Place to store the size of the newly allocated buffer.",
            return_comment="True on success, false if memory allocation fails.",
        )
        self.add_line("bool {name}_serialize({name}_t *s, uint8_t **buffer, size_t *buffer_size);")
        self.skip_line()

        self.add_c_comment(
            comment="Parse a buffer that was created by serializing a {name}_t and re-create the {name}_t.",
            return_comment="A newly allocated {name}_t. Must be freed with `{name}_free()`."
        )
        self.add_line("{name}_t *{name}_deserialize(const uint8_t *buffer, size_t buffer_size);")
        self.skip_line()

        self.add_c_comment(
            return_comment="True if the given buffer holds a valid serialized {name}_t, false otherwise.",
        )
        self.add_line("bool {name}_verify(const uint8_t *buffer, size_t buffer_size);")
        self.skip_line()

        for member in self.members:
            member.generate_signatures(self)

    def generate_c_source(self):
        self.set_parameter("name", self.name)
        self.set_parameter("table_id", self.table_id)

        # Copy
        self.start_block("{name}_t *{name}_copy({name}_t *s) {{")

        self.add_line("{name}_t *new_s = {name}_new();")
        self.start_block("if (new_s == NULL) {{")
        self.add_line("return NULL;")
        self.end_block("}}")

        for member in self.members:
            member.generate_copy_sets(self)

        self.add_line("return new_s;")
        self.end_block("}}")
        self.skip_line()

        # New
        self.start_block("{name}_t *{name}_new(void) {{")
        self.add_line("return calloc(1, sizeof({name}_t));")
        self.end_block("}}")
        self.skip_line()

        # Free
        self.start_block("void {name}_free({name}_t *s) {{")
        for member in self.members:
            member.generate_free(self)
        self.add_line("free(s);")
        self.end_block("}}")
        self.skip_line()
        
        # Serialize
        self.start_block("bool {name}_serialize({name}_t *s, uint8_t **out_buffer, size_t *out_buffer_size) {{")
        self.add_line("uint8_t *buffer = malloc(4);")
        self.add_line("size_t buffer_size = 4;")
        self.add_line("size_t bytes_written = 4;")
        self.add_line("((uint16_t *)buffer)[0] = (uint16_t)TABLE_TYPE_{name};")
        self.add_line("((uint16_t *)buffer)[1] = 0;")
        for member in self.members:
            member.generate_c_serialize(self)
        self.add_line("*out_buffer = buffer;")
        self.add_line("*out_buffer_size = buffer_size;")
        self.end_block("}}")
        self.skip_line()

        # Deserialize
        self.start_block("{name}_t *{name}_deserialize(const uint8_t *buffer, size_t buffer_size) {{")
        self.add_line("{name}_t* s = {name}_new();")
        self.start_block("if (s == NULL) {{")
        self.add_line("return NULL;")
        self.end_block("}}")
        self.add_line("size_t bytes_read = 0;")
        self.deserialize_c_varint("table_id", declare=True)
        self.start_block("if (table_id != {table_id}) {{")
        self.add_line("goto ERROR;")
        self.end_block("}}")
        self.skip_line()
        for member in self.members:
            member.generate_c_deserialize(self)
        self.add_line("return s;")
        self.skip_line()
        self.start_block("ERROR: {{")
        self.add_line("{name}_free(s);")
        self.add_line("return NULL;")
        self.end_block("}}")
        self.end_block("}}")
        self.skip_line()

        # Verify
        self.start_block("bool {name}_verify(const uint8_t *buffer, size_t buffer_size) {{")
        self.add_line("size_t bytes_read = 0;")
        self.deserialize_c_varint("table_id", declare=True)
        self.start_block("if (table_id != {table_id}) {{")
        self.add_line("goto ERROR;")
        self.end_block("}}")
        self.add_line("return true;")
        self.start_block("ERROR: {{")
        self.add_line("return false;")
        self.end_block("}}")
        self.end_block("}}")
        self.skip_line()

        # Get/Sets
        for member in self.members:
            member.generate_get_set(self)

    def generate_python(self):
        """
        Struct Definition
        """
        self.set_parameter("cls", self.name)
        self.set_parameter("table_id", self.table_id)
        self.set_parameter("bitfield_byte_width", (len(self.members) - 1) // 8 + 1)

        self.start_block("class {cls}:")

        self.add_line("__slots__ = [{}]".format(", ".join('"_{}"'.format(m.name) for m in self.members)))
        self.skip_line()

        parameters = ['self']
        for member in self.members:
            parameters.append(member.python_parameter)
        self.start_block("def __init__({}):".format(
            ", ".join(parameters)
        ))
        for member in self.members:
            self.set_parameter("field", member.name)
            member.generate_python_initialize()
        self.end_block()
        self.skip_line()

        self.start_block("def __repr__(self):")
        self.add_line("values = []")
        
        for member in self.members:
            self.set_parameter("field", member.name)
            if member.vector and member.vector_size is None:
                self.start_block("if len(self.{field}) > 0:")
            else:
                self.start_block("if self.{field} is not None:")
            self.add_line("values.append('{field}=' + repr(self.{field}))")
            self.end_block()

        self.add_line("return '{cls}(' + ', '.join(values) + ')'")
        self.end_block()
        self.skip_line()

        for member in self.members:
            self.set_parameter("field", member.name)
            self.set_parameter("python_type", member.python_type)
            self.set_parameter("type_name", member.type.name)
            self.set_parameter("vector_size", member.vector_size)

            self.add_line("@property")
            self.start_block("def {field}(self):")
            if member.default is not None:
                if member.type is Primitives.Boolean:
                    self.set_parameter("default", repr(bool(member.default)))
                else:
                    self.set_parameter("default", repr(member.default))
                self.start_block("if self._{field} is None:")
                if isinstance(member.type, EnumDefinition):
                    self.add_line("return {type_name}({default})")
                else:
                    self.add_line("return {default}")
                self.end_block()
                self.start_block("else:")
                self.add_line("return self._{field}")
                self.end_block()
            else:
                self.add_line("return self._{field}")
            self.end_block()
            self.skip_line()

            self.add_line("@{field}.setter")
            self.start_block("def {field}(self, value: {python_type}):")
            if member.vector and member.vector_size:
                self.start_block("if value is not None and len(value) != {vector_size}:")
                self.add_line("raise ValueError('{cls}.{field} must be a list of fixed size: {vector_size}')")
                self.end_block()
            if not member.vector and isinstance(member.type, EnumDefinition):
                self.start_block("if value is None:")
                self.add_line("self._{field} = None")
                self.end_block()
                self.start_block("else:")
                self.add_line("self._{field} = {type_name}(value)")
                self.end_block()
            else:
                self.add_line("self._{field} = value")
            self.end_block()
            self.skip_line()

        self.start_block("def serialize(self) -> bytes:")
        self.add_line("buf = bytearray()")
        if self.table_id > 0xFFFFFFFF:
            table_id_bytes = "b'0xFF' + uint64({})".format(self.table_id)
        elif self.table_id > 0xFFFF:
            table_id_bytes = "b'0xFE' + uint32({})".format(self.table_id)
        elif self.table_id >= 0xFD:
            table_id_bytes = "b'0xFD' + uint16({})".format(self.table_id)
        else:
            table_id_bytes = "uint8({})".format(self.table_id)
        self.add_line("buf.extend({})".format(table_id_bytes))
        self.add_line("bitfield_index = len(buf)")
        self.add_line("buf.extend(bytearray({bitfield_byte_width}))")
        for member in self.members:
            self.set_parameter("field", member.name)
            if member.vector and member.vector_size is None:
                self.start_block("if len(self._{field}) > 0:")
            else:
                self.start_block("if self._{field} is not None:")
            self.add_line("buf[bitfield_index+{}] |= {}".format(
                member.field_id // 8,
                1 << (7 - member.field_id & 7)
            ))
            member.generate_python_serialize()
            self.end_block()
        self.add_line("return bytes(buf)")
        self.end_block()
        self.skip_line()

        self.add_line("@classmethod")
        self.start_block("def deserialize(cls, buf: Union[bytes, bytearray]) -> {cls}:")
        self.add_line("buf_index = 0")
        self.deserialize_py_varint("table_id")
        self.start_block("if table_id != {table_id}:")
        self.add_line("raise ValueError('Invalid table ID {{}}'.format(table_id))")
        self.end_block()
        self.add_line("table = cls()")
        for member in self.members:
            self.set_parameter("field", member.name)
            member.generate_python_deserialize()
        self.add_line("return table")
        self.end_block()

        self.end_block()
        self.skip_line()
        self.skip_line()


class TableDefinition(StructDefinition):
    pass


@dataclass
class EnumDefinition(SchemaElement):
    schema: Schema
    name: str
    members: List[EnumMember] = field(default_factory=list)
    size: Union[Primitives.Int8, Primitives.UInt8] = 'uint16'
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
        self.set_parameter("name", self.name)
        self.start_block("typedef enum {name}_e {{")
        for member, end in join_iterate(self.members):
            line = "{} = {}".format(member.name, member.value)
            if not end:
                line += ','
            self.add_line(line)
        self.end_block("}} {name}_e;")

    def generate_python(self):
        """
        Enum Definition
        """
        self.set_parameter("cls", self.name)
        self.start_block("class {cls}(IntEnum):")
        for member in self.members:
            self.add_line("{} = {}".format(member.name, member.value))
        self.end_block()
        self.skip_line()
        self.skip_line()


@dataclass
class Schema:
    definitions: Dict[str, Union[EnumDefinition, StructDefinition, TableDefinition]]
    name: str = "ANONYMOUS_SCHEMA"
    next_table_id: int = 0
    indentation: str = '    '
    indentation_level: int = 0
    current_output: List[str] = field(default_factory=list)
    format_parameters: Dict[str, str] = field(default_factory=dict)
    format_parameters_stack: List[Dict[str, str]] = field(default_factory=list)

    def add_c_comment(self, comment="", **kwargs):
        self.add_comment(comment, opener="/**", line_start=" *", closer=" */", **kwargs)

    def add_py_comment(self, comment="", **kwargs):
        self.add_comment(comment, opener="\"\"\"", line_start="   ", closer="\"\"\"", **kwargs)

    def add_comment(self, comment="", *, return_comment=None, opener, line_start, closer, **kwargs):
        self.add_line(opener)
        if comment:
            for line in textwrap.wrap(re.sub('\s+', ' ', comment.strip()), width=80):
                self.add_line(line_start + " " + line)

            self.add_line(line_start)

        for param, comment in kwargs.items():
            padding_length = len(param) + len("@param ")
            for i, line in enumerate(textwrap.wrap(re.sub('\s+', ' ', comment.strip()), width=80)):
                if i == 0:
                    self.add_line("{} @param {} {}".format(line_start, param, line))
                else:
                    self.add_line("{} {} {}".format(line_start, " " * padding_length, line))
            self.add_line(line_start)

        if return_comment:
            for i, line in enumerate(textwrap.wrap(re.sub('\s+', ' ', return_comment.strip()), width=80)):
                if i == 0:
                    self.add_line("{} @return {}".format(line_start, line))
                else:
                    self.add_line("{}         {}".format(line_start, line))
        else:
            self.pop_line()

        self.add_line(closer)
    
    def serialize_py_varint(self, expr: str):
        self.start_block("if {} > 0xFFFFFFFF:".format(expr))
        self.add_line("buf.extend(uint8(0xFF))")
        self.add_line("buf.extend(uint64(length))")
        self.end_block()
        self.start_block("elif {} > 0xFFFF:".format(expr))
        self.add_line("buf.extend(uint8(0xFE))")
        self.add_line("buf.extend(uint32({}))".format(expr))
        self.end_block()
        self.start_block("elif {} >= 0xFD:".format(expr))
        self.add_line("buf.extend(uint8(0xFD))")
        self.add_line("buf.extend(uint16({}))".format(expr))
        self.end_block()
        self.start_block("else:")
        self.add_line("buf.extend(uint8({}))".format(expr))
        self.end_block()

    def serialize_c_varint(self, expr: str):
        self.start_block("if ({} > 0xFFFFFFFF) {{{{".format(expr))
        self.add_line("((uint8_t*)(buffer + bytes_written))[0] = 0xFF;")
        self.add_line("bytes_written += 1;")
        self.add_line("((uint64_t*)(buffer + bytes_written))[0] = (uint64_t)({});".format(expr))
        self.add_line("bytes_written += 8;")
        self.end_block("}}")
        self.start_block("else if ({} > 0xFFFF) {{{{".format(expr))
        self.add_line("((uint8_t*)(buffer + bytes_written))[0] = 0xFE;")
        self.add_line("bytes_written += 1;")
        self.add_line("((uint32_t*)(buffer + bytes_written))[0] = (uint32_t)({});".format(expr))
        self.add_line("bytes_written += 4;")
        self.end_block("}}")
        self.start_block("else if ({} >= 0xFD) {{{{".format(expr))
        self.add_line("((uint8_t*)(buffer + bytes_written))[0] = 0xFD;")
        self.add_line("bytes_written += 1;")
        self.add_line("((uint16_t*)(buffer + bytes_written))[0] = (uint16_t)({});".format(expr))
        self.add_line("bytes_written += 2;")
        self.end_block("}}")
        self.start_block("else {{")
        self.add_line("((uint8_t*)(buffer + bytes_written))[0] = (uint8_t)({});".format(expr))
        self.add_line("bytes_written += 1;")
        self.end_block("}}")

    def deserialize_py_varint(self, name: str):
        self.add_line("specifier = buf[buf_index]")
        self.add_line("buf_index += 1")
        self.start_block("if specifier == 0xFF:")
        self.add_line("{} = unsigned_int(buf[buf_index:buf_index+8])".format(name))
        self.add_line("buf_index += 8")
        self.end_block()
        self.start_block("elif specifier == 0xFE:")
        self.add_line("{} = unsigned_int(buf[buf_index:buf_index+4])".format(name))
        self.add_line("buf_index += 4")
        self.end_block()
        self.start_block("elif specifier == 0xFD:")
        self.add_line("{} = unsigned_int(buf[buf_index:buf_index+2])".format(name))
        self.add_line("buf_index += 2")
        self.end_block()
        self.start_block("else:")
        self.add_line("{} = specifier".format(name))
        self.end_block()

    def deserialize_c_int(self, name: str, size: int, *, declare: bool = False, signed: bool = False):
        self.start_block("if (bytes_read + {} > buffer_size) {{{{".format(size))
        self.add_line("goto ERROR;")
        self.end_block("}}")
        ctype = "{}int{}_t".format("" if signed else "u", size * 8)
        converter = "be{}toh".format(size * 8)
        if declare:
            self.add_line("{} {} = {}(*({}*)(buffer+bytes_read));".format(ctype, name, converter, ctype))
        else:
            self.add_line("{} = {}(*({}*)(buffer+bytes_read));".format(name, converter, ctype))
        self.add_line("bytes_read += {};".format(size))


    def deserialize_c_varint(self, name: str, *, declare: bool = False):
        self.start_block("if (bytes_read + 1 > buffer_size) {{")
        self.add_line("goto ERROR;")
        self.end_block("}}")
        if declare:
            self.add_line("size_t {};".format(name))
        self.start_block("if (buffer[bytes_read] == 0xFF) {{")
        self.add_line("bytes_read += 1;")
        self.deserialize_c_int(name, 8)
        self.end_block("}}")
        self.start_block("else if (buffer[bytes_read] == 0xFE) {{")
        self.add_line("bytes_read += 1;")
        self.deserialize_c_int(name, 4)
        self.end_block("}}")
        self.start_block("else if (buffer[bytes_read] == 0xFD) {{")
        self.add_line("bytes_read += 1;")
        self.deserialize_c_int(name, 2)
        self.end_block("}}")
        self.start_block("else {{")
        self.deserialize_c_int(name, 1)
        self.end_block("}}")

    def set_parameter(self, key, value):
        self.format_parameters[key] = value

    def push_parameters(self):
        self.format_parameters_stack.append(self.format_parameters.copy())

    def pop_parameters(self):
        self.format_parameters = self.format_parameters_stack.pop()

    def add_line(self, code=None):
        if code:
            self.current_output.append(
                self.indentation * self.indentation_level + code.format(**self.format_parameters)
            )
        else:
            self.current_output.append('')

    def pop_line(self):
        return self.current_output.pop()

    def skip_line(self, count=1):
        for i in range(count):
            self.current_output.append('')

    def start_block(self, code=""):
        if code:
            self.add_line(code)
        self.indentation_level += 1

    def end_block(self, code=""):
        self.indentation_level -= 1
        if code:
            self.add_line(code)

    def output(self):
        result = "\n".join(self.current_output) + "\n"
        self.current_output = []
        return result

    @property
    def structs(self):
        return (d for d in self.definitions.values() if not isinstance(d, EnumDefinition))

    def resolve_types(self):
        for definition in self.definitions.values():
            definition.resolve_types(self)
        
        for definition in self.structs:
            definition.table_id = self.next_table_id
            self.next_table_id += 1
            next_field_id = 0
            for member in definition.members:
                member.field_id = next_field_id
                next_field_id += 1

    def validate(self):
        for definition in self.definitions.values():
            definition.validate()

    def generate_c_header(self):
        self.set_parameter("schema_name", self.name.lower())

        self.add_line("#ifndef _SERIALIB_{schema_name}_H")
        self.add_line("#define _SERIALIB_{schema_name}_H")
        self.skip_line()

        self.add_line("#include <stdint.h>")
        self.add_line("#include <stdbool.h>")
        self.add_line("#include <stdlib.h>")
        self.skip_line()

        self.start_block("typedef enum TableType_e {{")
        self.add_line("TABLE_TYPE_INVALID = 0,")
        for definition, end in join_iterate(self.structs):
            self.set_parameter("table_name", definition.name)
            self.set_parameter("table_id", definition.table_id)
            if end:
                self.add_line("TABLE_TYPE_{table_name} = {table_id}")
            else:
                self.add_line("TABLE_TYPE_{table_name} = {table_id},")
        self.end_block("}} TableType_e;")
        self.skip_line()

        for definition in self.definitions.values():
            definition.generate_typedefs()
            self.skip_line()

        try:
            example_definition = next(iter(self.structs))
            self.set_parameter("example", example_definition.name)

            self.add_c_comment(
                comment="""
                    Checks a buffer that has been serialized with one of the <table/struct>_serialize() functions
                    and returns the TableType_e that corresponds with the table used to create the buffer.
                    For example, if {example}_serialize() was used to create the buffer, this function will return
                    TABLE_TYPE_{example}. If the buffer cannot be any of the known tables, TABLE_TYPE_INVALID is
                    returned instead.
                """
            )
            self.add_line("TableType_e determine_table_type(const uint8_t *buffer, size_t buffer_size);")
            self.skip_line()
        except StopIteration:
            pass

        for definition in self.structs:
            definition.generate_signatures()
            self.skip_line()

        self.add_line("#endif")
        return self.output()

    def generate_c_source(self, header_path):
        self.set_parameter("schema_name", self.name.lower())
        self.set_parameter("header_path", header_path)

        self.add_line("#include <stdint.h>")
        self.add_line("#include <stdbool.h>")
        self.add_line("#include <stdlib.h>")
        self.add_line("#include <string.h>")
        self.add_line("#include \"{header_path}\"")
        self.skip_line()

        for definition in self.structs:
            definition.generate_c_source()

        return self.output()

    def generate_python(self):
        """
        Schema
        """
        self.add_line("from __future__ import annotations")
        self.add_line("from dataclasses import dataclass, field")
        self.add_line("from enum import IntEnum")
        self.add_line("from typing import Union, List, Optional")
        self.skip_line(2)

        self.start_block("def uint8(value):")
        self.add_line("return value.to_bytes(1, 'big', signed=False)")
        self.end_block()
        self.skip_line(2)

        self.start_block("def uint16(value):")
        self.add_line("return value.to_bytes(2, 'big', signed=False)")
        self.end_block()
        self.skip_line(2)

        self.start_block("def uint32(value):")
        self.add_line("return value.to_bytes(4, 'big', signed=False)")
        self.end_block()
        self.skip_line(2)

        self.start_block("def uint64(value):")
        self.add_line("return value.to_bytes(8, 'big', signed=False)")
        self.end_block()
        self.skip_line(2)

        self.start_block("def int8(value):")
        self.add_line("return value.to_bytes(1, 'big', signed=True)")
        self.end_block()
        self.skip_line(2)

        self.start_block("def int16(value):")
        self.add_line("return value.to_bytes(2, 'big', signed=True)")
        self.end_block()
        self.skip_line(2)

        self.start_block("def int32(value):")
        self.add_line("return value.to_bytes(4, 'big', signed=True)")
        self.end_block()
        self.skip_line(2)

        self.start_block("def int64(value):")
        self.add_line("return value.to_bytes(8, 'big', signed=True)")
        self.end_block()
        self.skip_line(2)

        self.start_block("def unsigned_int(buf):")
        self.add_line("return int.from_bytes(buf, 'big', signed=False)")
        self.end_block()
        self.skip_line(2)

        self.start_block("def signed_int(buf):")
        self.add_line("return int.from_bytes(buf, 'big', signed=True)")
        self.end_block()
        self.skip_line(2)

        for definition in self.definitions.values():
            definition.generate_python()

        self.start_block("TABLE_ID_MAP = {{")
        for definition in self.structs:
            self.add_line("{}: {},".format(definition.table_id, definition.name))
        self.end_block("}}")
        self.skip_line(2)

        self.start_block("def deserialize(buf: Union[bytes, bytearray]):")
        self.add_line("buf_index = 0")
        self.deserialize_py_varint("table_id")

        self.start_block("try:")
        self.add_line("cls = TABLE_ID_MAP[table_id]")
        self.end_block()
        self.start_block("except KeyError:")
        self.add_line("raise ValueError('Unrecognized Table ID')")
        self.end_block()

        self.add_line("return cls.deserialize(buf)")
        self.end_block()

        return self.output()


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
