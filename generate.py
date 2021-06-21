#!/usr/bin/env python3
import sys

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Union, Tuple, Optional, Set

from prettyprinter import pprint, install_extras
from sly import Lexer, Parser


# Pretty printer dataclasses support
install_extras(include=['dataclasses'], warn_on_error=True)


def indent(s, amount=1):
    return str(s).replace('\n', '\n' + '  '*amount)




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
    ignore_comment = r'/\*(.|\n)*?\*/'

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

    @_('STRING_LITERAL')
    def literal(self, p):
        return p[0]

    @_('NUMBER_LITERAL')
    def literal(self, p):
        return p[0]

    @_('')
    def enum_members(self, p):
        return []

    @_('enum_members COMMA IDENTIFIER')
    def enum_members(self, p):
        p[0].append(EnumMember(name=p[2]))
        return p[0]

    @_('enum_members COMMA IDENTIFIER EQUALS NUMBER_LITERAL')
    def enum_members(self, p):
        p[0].append(EnumMember(name=p[2], value=p[4]))
        return p[0]

    @_('IDENTIFIER')
    def enum_members(self, p):
        return [EnumMember(name=p[0])]

    @_('IDENTIFIER EQUALS NUMBER_LITERAL')
    def enum_members(self, p):
        return [EnumMember(name=p[0], value=p[2])]

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

    @_('struct_member')
    def struct_members(self, p):
        return [p[0]]

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

class Primitive(Enum):
    Boolean = object()
    String = object()
    UInt8 = object()
    Int8 = object()
    UInt16 = object()
    Int16 = object()
    UInt32 = object()
    Int32 = object()
    UInt64 = object()
    Int64 = object()

BUILTIN_TYPES = {
    # Integer primitives
    'uint8': Primitive.UInt8,
    'int8': Primitive.Int8,
    'uint16': Primitive.UInt16,
    'int16': Primitive.Int16,
    'uint32': Primitive.UInt32,
    'int32': Primitive.Int32,
    'uint64': Primitive.UInt64,
    'int64': Primitive.Int64,
    # Non-integer primitives
    'boolean': Primitive.Boolean,
    'string': Primitive.String,
    # Aliases
    'long': Primitive.Int64,
    'ulong': Primitive.UInt64,
    'slong': Primitive.Int64,
    'int': Primitive.Int32,
    'uint': Primitive.UInt32,
    'sint': Primitive.Int32,
    'short': Primitive.Int16,
    'ushort': Primitive.UInt16,
    'sshort': Primitive.Int16,
    'byte': Primitive.UInt8,
    'ubyte': Primitive.UInt8,
    'sbyte': Primitive.Int8,
    'char': Primitive.Int8,
    'uchar': Primitive.UInt8,
    'schar': Primitive.Int8,
    'bool': Primitive.Boolean,
    'str': Primitive.String,
}

INTEGER_PRIMITIVES = {
    Primitive.UInt8: (1, False),
    Primitive.Int8: (1, True),
    Primitive.UInt16: (2, False),
    Primitive.Int16: (2, True),
    Primitive.UInt32: (4, False),
    Primitive.Int32: (4, True),
    Primitive.UInt64: (8, False),
    Primitive.Int64: (8, True),
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


@dataclass
class EnumMember:
    name: str
    value: Optional[int] = None

    def resolve_value(self, parent):
        if self.value is None:
            self.value = parent.next_value
        parent.values.add(self.value)
        parent.next_value = self.value + 1


@dataclass
class StructDefinition:
    name: str
    members: List[StructMember] = field(default_factory=list)

    def resolve_types(self, schema):
        for struct_member in self.members:
            struct_member.resolve_type(schema)

    def validate(self, schema):
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
            elif struct_member.type is Primitive.String:
                if not isinstance(struct_member.default, str):
                    raise TypeError("The default value of string {}.{} must be a string.".format(
                        self.name, struct_member.name))
            # If this type is a boolean primitive, verify default is 0 or 1
            elif struct_member.type is Primitive.Boolean:
                if struct_member.default != 0 and struct_member.default != 1:
                    raise TypeError("The default value of boolean {}.{} must be true (1) or false (0).".format(
                        self.name, struct_member.name))
            # Unrecognized type
            else:
                raise TypeError("Struct member {}.{} has an unrecognized type: '{}'".format(
                    self.name, struct_member.name, struct_member.type))


class TableDefinition(StructDefinition):
    pass


@dataclass
class EnumDefinition:
    name: str
    members: List[EnumMember] = field(default_factory=list)
    size: str = 'uint16'
    next_value: int = 0
    values: Set[int] = field(default_factory=set)

    def resolve_types(self, schema):
        self.size = BUILTIN_TYPES.get(self.size, self.size)
        if self.size not in INTEGER_PRIMITIVES:
            raise TypeError("the type of an enum definition must be an integer primitive, not '{}'".format(self.size))
        for enum_member in self.members:
            enum_member.resolve_value(self)

    def validate(self, schema):
        pass


@dataclass
class Schema:
    definitions: Dict[str, Union[EnumDefinition, StructDefinition, TableDefinition]]

    def resolve_types(self):
        for definition in self.definitions.values():
            definition.resolve_types(self)

    def validate(self):
        for definition in self.definitions.values():
            definition.validate(self)

    def generate_c_header(self):
        return "\n"

    def generate_c_source(self):
        return "\n"

    def generate_python_lib(self):
        return "\n"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('schema', type=Path)
    parser.add_argument('--generate-python', type=str, default=None)
    parser.add_argument('--generate-c-source', type=str, default=None)
    parser.add_argument('--generate-c-header', type=str, default=None)
    args = parser.parse_args()

    # Read schema file
    with open(args.schema, "r") as f:
        text_schema = f.read()

    # Lex and parse schema
    lexer = SeriaLexer()
    parser = SeriaParser()
    schema = parser.parse(lexer.tokenize(text_schema))
    if not schema:
        print("error: invalid schema file", file=sys.stderr)
        return 1

    # Debug
    print("[First Pass]")
    pprint(schema)

    # Resolve type references
    schema.resolve_types()

    # Debug
    print("[After Type Resolution]")
    pprint(schema)

    # Validate defaults
    schema.validate()

    # Output to files
    if args.generate_python:
        python_lib = schema.generate_python_lib()
        with open(args.generate_python, "w") as f:
            f.write(python_lib)

    if args.generate_c_source:
        c_source = schema.generate_c_source()
        with open(args.generate_c_source, "w") as f:
            f.write(c_source)

    if args.generate_c_header:
        c_header = schema.generate_c_header()
        with open(args.generate_c_header, "w") as f:
            f.write(c_header)

    return 0


if __name__ == '__main__':
    sys.exit(main())
