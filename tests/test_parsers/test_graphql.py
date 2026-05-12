"""GraphQL parser tests — ported from graphql-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.graphql import GraphQLParser


class TestGraphQLParser:
    """Tests for GraphQLParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = GraphQLParser()
        assert parser.name == "graphql-parser"
        assert parser.languages == ["graphql"]

    def test_extracts_type_definitions(self):
        """Extract type, input, enum, interface definitions."""
        content = """type User {
    id: ID!
    name: String!
    email: String
}

input CreateUserInput {
    name: String!
    email: String!
}

enum Role {
    ADMIN
    USER
    GUEST
}
"""
        parser = GraphQLParser()
        result = parser.analyze_file("schema.graphql", content)

        assert len(result.definitions) == 3
        kinds = {d.name: d.kind for d in result.definitions}
        assert kinds["User"] == "type"
        assert kinds["CreateUserInput"] == "input"
        assert kinds["Role"] == "enum"

    def test_extracts_fields_from_type_definitions(self):
        """Field names are extracted from type definitions."""
        content = """type Product {
    id: ID!
    name: String!
    price: Float
}
"""
        parser = GraphQLParser()
        result = parser.analyze_file("schema.graphql", content)

        assert len(result.definitions) == 1
        assert result.definitions[0].name == "Product"
        assert "id" in result.definitions[0].fields
        assert "name" in result.definitions[0].fields
        assert "price" in result.definitions[0].fields

    def test_skips_query_mutation_subscription_type_names(self):
        """Query/Mutation/Subscription are not counted as type definitions."""
        content = """type Query {
    users: [User!]!
    product(id: ID!): Product
}

type User {
    id: ID!
    name: String!
}
"""
        parser = GraphQLParser()
        result = parser.analyze_file("schema.graphql", content)

        # User should be extracted, Query should be skipped
        names = [d.name for d in result.definitions]
        assert "User" in names
        assert "Query" not in names

    def test_extracts_endpoints_from_query_mutation_subscription(self):
        """Query/Mutation/Subscription fields are extracted as endpoints."""
        content = """type Query {
    users: [User!]!
    product(id: ID!): Product
}

type Mutation {
    createUser(input: CreateUserInput!): User!
    deleteUser(id: ID!): Boolean
}

type User {
    id: ID!
    name: String!
}
"""
        parser = GraphQLParser()
        result = parser.analyze_file("schema.graphql", content)

        assert len(result.endpoints) == 4
        query_endpoints = [e for e in result.endpoints if e.method == "Query"]
        mutation_endpoints = [e for e in result.endpoints if e.method == "Mutation"]

        assert len(query_endpoints) == 2
        assert query_endpoints[0].path == "users"
        assert query_endpoints[1].path == "product"

        assert len(mutation_endpoints) == 2
        assert mutation_endpoints[0].path == "createUser"

    def test_supports_scalar_union_interface_definitions(self):
        """Scalar, union, and interface types are extracted."""
        content = """scalar DateTime
union SearchResult = User | Product
interface Node {
    id: ID!
}
"""
        parser = GraphQLParser()
        result = parser.analyze_file("schema.graphql", content)

        assert len(result.definitions) == 3
        kinds = {d.name: d.kind for d in result.definitions}
        assert kinds["DateTime"] == "scalar"
        assert kinds["SearchResult"] == "union"
        assert kinds["Node"] == "interface"

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = GraphQLParser()
        result = parser.analyze_file("test.graphql", "type Foo { id: ID }")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
