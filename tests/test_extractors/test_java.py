"""Java extractor tests — ported from java-extractor.test.ts."""

from __future__ import annotations

from understand_anything.plugins.extractors.java import JavaExtractor


# ---------------------------------------------------------------------------
# Basic extractor properties
# ---------------------------------------------------------------------------


def test_language_ids():
    extractor = JavaExtractor()
    assert extractor.language_ids == ["java"]


# ---------------------------------------------------------------------------
# extractStructure - functions (methods & constructors)
# ---------------------------------------------------------------------------


class TestExtractStructureFunctions:
    """Tests for method and constructor extraction (mapped to functions)."""

    def test_extracts_methods_with_params_and_return_types(self, parse_java):
        root = parse_java("""public class Foo {
    public String getName(int id) {
        return "";
    }
    private void process(String data, int count) {
    }
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 2

        assert result.functions[0].name == "getName"
        assert result.functions[0].params == ["id"]
        assert result.functions[0].return_type == "String"

        assert result.functions[1].name == "process"
        assert result.functions[1].params == ["data", "count"]
        assert result.functions[1].return_type == "void"

    def test_extracts_constructors(self, parse_java):
        root = parse_java("""public class Foo {
    public Foo(String name, int value) {
        this.name = name;
    }
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].name == "Foo"
        assert result.functions[0].params == ["name", "value"]
        assert result.functions[0].return_type is None

    def test_extracts_methods_with_no_params(self, parse_java):
        root = parse_java("""public class Foo {
    public void run() {}
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].name == "run"
        assert result.functions[0].params == []
        assert result.functions[0].return_type == "void"

    def test_extracts_methods_with_generic_return_types(self, parse_java):
        root = parse_java("""public class Foo {
    public List<String> getItems() {
        return null;
    }
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].name == "getItems"
        assert result.functions[0].return_type == "List<String>"

    def test_reports_correct_line_ranges_for_multi_line_methods(self, parse_java):
        root = parse_java("""public class Foo {
    public int calculate(
        int a,
        int b
    ) {
        int result = a + b;
        return result;
    }
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].line_range[0] == 2
        assert result.functions[0].line_range[1] == 8


# ---------------------------------------------------------------------------
# extractStructure - classes
# ---------------------------------------------------------------------------


class TestExtractStructureClasses:
    """Tests for class extraction."""

    def test_extracts_class_with_methods_and_fields(self, parse_java):
        root = parse_java("""public class Server {
    private String host;
    private int port;
    public void start() {}
    public void stop() {}
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].name == "Server"
        assert result.classes[0].properties == ["host", "port"]
        assert result.classes[0].methods == ["start", "stop"]
        assert result.classes[0].line_range[0] == 1

    def test_extracts_empty_class(self, parse_java):
        root = parse_java("""public class Empty {
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].name == "Empty"
        assert result.classes[0].properties == []
        assert result.classes[0].methods == []

    def test_includes_constructors_in_methods_list(self, parse_java):
        root = parse_java("""public class Foo {
    public Foo() {}
    public void run() {}
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert result.classes[0].methods == ["Foo", "run"]


# ---------------------------------------------------------------------------
# extractStructure - interfaces
# ---------------------------------------------------------------------------


class TestExtractStructureInterfaces:
    """Tests for interface extraction."""

    def test_extracts_interface_with_method_signatures(self, parse_java):
        root = parse_java("""interface Repository {
    List<User> findAll();
    User findById(int id);
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].name == "Repository"
        assert result.classes[0].methods == ["findAll", "findById"]
        assert result.classes[0].properties == []

    def test_extracts_empty_interface(self, parse_java):
        root = parse_java("""interface Marker {
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].name == "Marker"
        assert result.classes[0].methods == []


# ---------------------------------------------------------------------------
# extractStructure - imports
# ---------------------------------------------------------------------------


class TestExtractStructureImports:
    """Tests for import extraction."""

    def test_extracts_regular_imports(self, parse_java):
        root = parse_java("""import java.util.List;
import java.util.Map;
public class Foo {}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 2
        assert result.imports[0].source == "java.util.List"
        assert result.imports[0].specifiers == ["List"]
        assert result.imports[0].line_number == 1
        assert result.imports[1].source == "java.util.Map"
        assert result.imports[1].specifiers == ["Map"]
        assert result.imports[1].line_number == 2

    def test_extracts_wildcard_imports(self, parse_java):
        root = parse_java("""import java.util.*;
public class Foo {}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 1
        assert result.imports[0].source == "java.util"
        assert result.imports[0].specifiers == ["*"]

    def test_reports_correct_import_line_numbers(self, parse_java):
        root = parse_java("""import java.util.List;

import java.util.Map;
public class Foo {}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert result.imports[0].line_number == 1
        assert result.imports[1].line_number == 3


# ---------------------------------------------------------------------------
# extractStructure - exports
# ---------------------------------------------------------------------------


class TestExtractStructureExports:
    """Tests for export extraction (public visibility)."""

    def test_exports_public_class_methods_and_constructor(self, parse_java):
        root = parse_java("""public class UserService {
    private String name;
    public UserService(String name) {
        this.name = name;
    }
    public void start() {}
    private void helper() {}
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "UserService" in export_names  # class
        # Constructor is also named UserService, check it's listed twice
        user_service_exports = [e for e in result.exports if e.name == "UserService"]
        assert len(user_service_exports) == 2  # class + constructor
        assert "start" in export_names
        assert "helper" not in export_names
        assert "name" not in export_names  # private field

    def test_does_not_export_non_public_classes(self, parse_java):
        root = parse_java("""class Internal {
    void run() {}
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        assert len(result.exports) == 0

    def test_exports_public_fields(self, parse_java):
        root = parse_java("""public class Config {
    public String apiKey;
    private int retries;
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "Config" in export_names
        assert "apiKey" in export_names
        assert "retries" not in export_names

    def test_exports_public_interface(self, parse_java):
        root = parse_java("""public interface Repository {
    void save();
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "Repository" in export_names


# ---------------------------------------------------------------------------
# extractCallGraph
# ---------------------------------------------------------------------------


class TestExtractCallGraph:
    """Tests for call graph extraction."""

    def test_extracts_simple_method_calls(self, parse_java):
        root = parse_java("""public class Foo {
    public void process(int data) {
        transform(data);
        format(data);
    }
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) == 2
        assert result[0].caller == "process"
        assert result[0].callee == "transform"
        assert result[1].caller == "process"
        assert result[1].callee == "format"

    def test_extracts_qualified_method_calls(self, parse_java):
        root = parse_java("""public class Foo {
    private void log(String message) {
        System.out.println(message);
    }
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) == 1
        assert result[0].caller == "log"
        assert result[0].callee == "System.out.println"

    def test_extracts_object_creation_expressions(self, parse_java):
        root = parse_java("""public class Foo {
    public void create() {
        Bar b = new Bar();
    }
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) == 1
        assert result[0].caller == "create"
        assert result[0].callee == "new Bar"

    def test_tracks_correct_caller_for_constructors(self, parse_java):
        root = parse_java("""public class Foo {
    public Foo() {
        init();
    }
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) == 1
        assert result[0].caller == "Foo"
        assert result[0].callee == "init"

    def test_reports_correct_line_numbers_for_calls(self, parse_java):
        root = parse_java("""public class Foo {
    public void run() {
        foo();
        bar();
    }
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) == 2
        assert result[0].line_number == 3
        assert result[1].line_number == 4

    def test_ignores_calls_outside_methods_no_caller(self, parse_java):
        # Field initializers can have method calls. We skip those without a
        # method context.
        root = parse_java("""public class Foo {
    private String value = String.valueOf(42);
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_call_graph(root)

        # No enclosing method, so these are skipped
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Comprehensive test
# ---------------------------------------------------------------------------


class TestComprehensiveJava:
    """Full Java test scenarios ported from the TypeScript test suite."""

    def test_handles_a_realistic_java_module(self, parse_java):
        root = parse_java("""import java.util.List;
import java.util.Map;

public class UserService {
    private String name;
    private int maxRetries;

    public UserService(String name) {
        this.name = name;
    }

    public List<User> getUsers(int limit) {
        return fetchFromDb(limit);
    }

    private void log(String message) {
        System.out.println(message);
    }
}

interface Repository {
    List<User> findAll();
    User findById(int id);
}
""")
        extractor = JavaExtractor()
        result = extractor.extract_structure(root)

        # Functions: UserService (constructor), getUsers, log
        assert len(result.functions) == 3
        assert sorted(f.name for f in result.functions) == sorted(
            ["UserService", "getUsers", "log"]
        )

        # Constructor has params but no return type
        ctor = next(f for f in result.functions if f.name == "UserService")
        assert ctor.params == ["name"]
        assert ctor.return_type is None

        # getUsers has params and generic return type
        get_users = next(f for f in result.functions if f.name == "getUsers")
        assert get_users.params == ["limit"]
        assert get_users.return_type == "List<User>"

        # log has params and void return type
        log = next(f for f in result.functions if f.name == "log")
        assert log.params == ["message"]
        assert log.return_type == "void"

        # Classes: UserService, Repository
        assert len(result.classes) == 2

        user_service = next(c for c in result.classes if c.name == "UserService")
        assert user_service is not None
        assert sorted(user_service.methods) == sorted(
            ["UserService", "getUsers", "log"]
        )
        assert sorted(user_service.properties) == sorted(["name", "maxRetries"])

        repository = next(c for c in result.classes if c.name == "Repository")
        assert repository is not None
        assert repository.methods == ["findAll", "findById"]
        assert repository.properties == []

        # Imports: 2 (java.util.List, java.util.Map)
        assert len(result.imports) == 2
        assert result.imports[0].source == "java.util.List"
        assert result.imports[0].specifiers == ["List"]
        assert result.imports[1].source == "java.util.Map"
        assert result.imports[1].specifiers == ["Map"]

        # Exports: UserService (class), UserService (constructor), getUsers (public)
        export_names = [e.name for e in result.exports]
        assert "UserService" in export_names
        assert "getUsers" in export_names
        assert "log" not in export_names  # private
        assert "name" not in export_names  # private field
        assert "maxRetries" not in export_names  # private field

        # Call graph
        calls = extractor.extract_call_graph(root)

        get_users_calls = [e for e in calls if e.caller == "getUsers"]
        assert any(e.callee == "fetchFromDb" for e in get_users_calls)

        log_calls = [e for e in calls if e.caller == "log"]
        assert any(e.callee == "System.out.println" for e in log_calls)
