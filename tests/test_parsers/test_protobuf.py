"""Protobuf parser tests — ported from protobuf-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.protobuf import ProtobufParser


class TestProtobufParser:
    """Tests for ProtobufParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = ProtobufParser()
        assert parser.name == "protobuf-parser"
        assert parser.languages == ["protobuf"]

    def test_extracts_message_definitions(self):
        """Extract message definitions with fields."""
        content = """syntax = "proto3";

message User {
    int32 id = 1;
    string name = 2;
    string email = 3;
}

message Post {
    int32 id = 1;
    string title = 2;
}
"""
        parser = ProtobufParser()
        result = parser.analyze_file("test.proto", content)

        messages = [d for d in result.definitions if d.kind == "message"]
        assert len(messages) == 2
        assert messages[0].name == "User"
        assert "id" in messages[0].fields
        assert "name" in messages[0].fields
        assert "email" in messages[0].fields
        assert messages[1].name == "Post"
        assert "id" in messages[1].fields

    def test_extracts_enum_definitions(self):
        """Extract enum definitions with values."""
        content = """enum Status {
    UNKNOWN = 0;
    ACTIVE = 1;
    INACTIVE = 2;
}
"""
        parser = ProtobufParser()
        result = parser.analyze_file("test.proto", content)

        enums = [d for d in result.definitions if d.kind == "enum"]
        assert len(enums) == 1
        assert enums[0].name == "Status"
        assert "UNKNOWN" in enums[0].fields
        assert "ACTIVE" in enums[0].fields
        assert "INACTIVE" in enums[0].fields

    def test_handles_repeated_optional_fields(self):
        """Handles repeated, optional, required modifiers."""
        content = """message SearchRequest {
    string query = 1;
    int32 page_number = 2;
    optional int32 result_per_page = 3;
    repeated string filters = 4;
}
"""
        parser = ProtobufParser()
        result = parser.analyze_file("test.proto", content)

        assert len(result.definitions) == 1
        assert "query" in result.definitions[0].fields
        assert "page_number" in result.definitions[0].fields
        assert "result_per_page" in result.definitions[0].fields
        assert "filters" in result.definitions[0].fields

    def test_handles_map_fields(self):
        """Handles map<K, V> fields."""
        content = """message Settings {
    map<string, string> config = 1;
    string name = 2;
}
"""
        parser = ProtobufParser()
        result = parser.analyze_file("test.proto", content)

        assert len(result.definitions) == 1
        # map field name should be extracted
        assert "config" in result.definitions[0].fields
        assert "name" in result.definitions[0].fields

    def test_extracts_service_rpc_endpoints(self):
        """Extract service RPC methods as endpoints."""
        content = """service UserService {
    rpc GetUser (GetUserRequest) returns (User);
    rpc ListUsers (ListUsersRequest) returns (stream User);
    rpc CreateUser (CreateUserRequest) returns (User);
}
"""
        parser = ProtobufParser()
        result = parser.analyze_file("test.proto", content)

        assert len(result.endpoints) == 3
        assert result.endpoints[0].method == "rpc"
        assert result.endpoints[0].path == "UserService.GetUser"
        assert result.endpoints[1].path == "UserService.ListUsers"
        assert result.endpoints[2].path == "UserService.CreateUser"

    def test_message_line_ranges_are_correct(self):
        """Message line ranges cover the full block."""
        content = """message Foo {
    int32 x = 1;
    int32 y = 2;
}

message Bar {
    string z = 1;
}
"""
        parser = ProtobufParser()
        result = parser.analyze_file("test.proto", content)

        assert len(result.definitions) >= 2
        for d in result.definitions:
            assert d.line_range[1] >= d.line_range[0]

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = ProtobufParser()
        result = parser.analyze_file("test.proto", 'message Foo { int32 x = 1; }')
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
