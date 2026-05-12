"""C/C++ extractor tests — ported from cpp-extractor.test.ts."""

from __future__ import annotations

from understand_anything.plugins.extractors.cpp import CppExtractor


# ---------------------------------------------------------------------------
# Basic extractor properties
# ---------------------------------------------------------------------------


def test_language_ids():
    extractor = CppExtractor()
    assert extractor.language_ids == ["cpp", "c"]


# ---------------------------------------------------------------------------
# extractStructure - functions
# ---------------------------------------------------------------------------


class TestExtractStructureFunctions:
    """Tests for function extraction."""

    def test_top_level_functions_with_params_and_return_types(self, parse_cpp):
        root = parse_cpp("""
int add(int a, int b) {
    return a + b;
}

void greet(const char* name) {
    printf("Hello %s", name);
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 2

        assert result.functions[0].name == "add"
        assert result.functions[0].params == ["a", "b"]
        assert result.functions[0].return_type == "int"

        assert result.functions[1].name == "greet"
        assert result.functions[1].params == ["name"]
        assert result.functions[1].return_type == "void"

    def test_functions_with_no_params(self, parse_cpp):
        root = parse_cpp("""
int get_value() {
    return 42;
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].name == "get_value"
        assert result.functions[0].params == []
        assert result.functions[0].return_type == "int"

    def test_correct_line_ranges_for_multi_line_functions(self, parse_cpp):
        root = parse_cpp("""
int multiline(
    int a,
    int b
) {
    int result = a + b;
    return result;
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].line_range[0] == 2
        assert result.functions[0].line_range[1] == 8

    def test_pointer_and_reference_parameters(self, parse_cpp):
        root = parse_cpp("""
void process(int* ptr, const char& ref, int arr[]) {
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].params == ["ptr", "ref", "arr"]


# ---------------------------------------------------------------------------
# extractStructure - classes
# ---------------------------------------------------------------------------


class TestExtractStructureClasses:
    """Tests for class extraction."""

    def test_class_with_properties_and_method_declarations(self, parse_cpp):
        root = parse_cpp("""
class Server {
public:
    std::string host;
    int port;

    void start();
    int getPort() { return port; }
};
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].name == "Server"
        assert result.classes[0].properties == ["host", "port"]
        assert "start" in result.classes[0].methods
        assert "getPort" in result.classes[0].methods

    def test_respects_access_specifiers_for_exports(self, parse_cpp):
        root = parse_cpp("""
class Foo {
private:
    int secret;
    void hidden();
public:
    int visible;
    void exposed();
};
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "exposed" in export_names
        assert "hidden" not in export_names
        assert "secret" not in export_names
        assert "Foo" in export_names

    def test_defaults_class_members_to_private_access(self, parse_cpp):
        root = parse_cpp("""
class Priv {
    int x;
    void secret();
};
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "Priv" in export_names
        assert "secret" not in export_names

    def test_inline_method_definitions_inside_class(self, parse_cpp):
        root = parse_cpp("""
class Calculator {
public:
    int add(int a, int b) { return a + b; }
};
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert "add" in result.classes[0].methods

        add_fn = next((f for f in result.functions if f.name == "add"), None)
        assert add_fn is not None
        assert add_fn.params == ["a", "b"]
        assert add_fn.return_type == "int"


# ---------------------------------------------------------------------------
# extractStructure - structs
# ---------------------------------------------------------------------------


class TestExtractStructureStructs:
    """Tests for struct extraction."""

    def test_struct_with_fields(self, parse_cpp):
        root = parse_cpp("""
struct Point {
    int x;
    int y;
};
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].name == "Point"
        assert result.classes[0].properties == ["x", "y"]
        assert result.classes[0].methods == []

    def test_struct_members_default_to_public_and_exported(self, parse_cpp):
        root = parse_cpp("""
struct Config {
    int port;
    void init();
};
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "Config" in export_names
        assert "init" in export_names


# ---------------------------------------------------------------------------
# extractStructure - includes (imports)
# ---------------------------------------------------------------------------


class TestExtractStructureIncludes:
    """Tests for #include extraction."""

    def test_system_includes_angle_brackets(self, parse_cpp):
        root = parse_cpp("""
#include <iostream>
#include <vector>
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 2
        assert result.imports[0].source == "iostream"
        assert result.imports[0].specifiers == ["iostream"]
        assert result.imports[1].source == "vector"

    def test_local_includes_quoted(self, parse_cpp):
        root = parse_cpp("""
#include "config.h"
#include "utils/helper.h"
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 2
        assert result.imports[0].source == "config.h"
        assert result.imports[0].specifiers == ["config.h"]
        assert result.imports[1].source == "utils/helper.h"

    def test_correct_import_line_numbers(self, parse_cpp):
        root = parse_cpp("""
#include <iostream>
#include "config.h"
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 2
        assert result.imports[0].line_number == 2
        assert result.imports[1].line_number == 3


# ---------------------------------------------------------------------------
# extractStructure - namespaces
# ---------------------------------------------------------------------------


class TestExtractStructureNamespaces:
    """Tests for namespace extraction."""

    def test_functions_inside_namespaces(self, parse_cpp):
        root = parse_cpp("""
namespace utils {
    int add(int a, int b) {
        return a + b;
    }

    void log(const char* msg) {}
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 2
        names = [f.name for f in result.functions]
        assert "add" in names
        assert "log" in names

    def test_classes_inside_namespaces(self, parse_cpp):
        root = parse_cpp("""
namespace models {
    class User {
    public:
        std::string name;
        int id;
    };
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].name == "User"
        assert result.classes[0].properties == ["name", "id"]


# ---------------------------------------------------------------------------
# extractStructure - out-of-class method definitions
# ---------------------------------------------------------------------------


class TestExtractStructureOutOfClassMethods:
    """Tests for out-of-class method definitions."""

    def test_associates_out_of_class_method_with_class(self, parse_cpp):
        root = parse_cpp("""
class Server {
public:
    void start();
};

void Server::start() {
    // implementation
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        assert "start" in result.classes[0].methods

        start_fn = next((f for f in result.functions if f.name == "start"), None)
        assert start_fn is not None
        assert start_fn.return_type == "void"


# ---------------------------------------------------------------------------
# extractStructure - exports
# ---------------------------------------------------------------------------


class TestExtractStructureExports:
    """Tests for export extraction."""

    def test_exports_non_static_functions_only(self, parse_cpp):
        root = parse_cpp("""
int public_fn(int x) { return x; }

static void private_fn() {}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "public_fn" in export_names
        assert "private_fn" not in export_names

    def test_correct_export_line_numbers(self, parse_cpp):
        root = parse_cpp("""
struct Point {
    int x;
    int y;
};

int compute(int n) { return n * 2; }
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        point_export = next((e for e in result.exports if e.name == "Point"), None)
        assert point_export is not None
        assert point_export.line_number == 2

        compute_export = next((e for e in result.exports if e.name == "compute"), None)
        assert compute_export is not None
        assert compute_export.line_number == 7


# ---------------------------------------------------------------------------
# extractCallGraph
# ---------------------------------------------------------------------------


class TestExtractCallGraph:
    """Tests for call graph extraction."""

    def test_simple_function_calls(self, parse_cpp):
        root = parse_cpp("""
void helper(int x) {}

int main() {
    helper(42);
}
""")
        extractor = CppExtractor()
        result = extractor.extract_call_graph(root)

        main_calls = [e for e in result if e.caller == "main"]
        assert any(e.callee == "helper" for e in main_calls)

    def test_multiple_calls_from_one_function(self, parse_cpp):
        root = parse_cpp("""
void foo() {}
void bar() {}

int main() {
    foo();
    bar();
}
""")
        extractor = CppExtractor()
        result = extractor.extract_call_graph(root)

        main_calls = [e for e in result if e.caller == "main"]
        assert len(main_calls) == 2
        assert any(e.callee == "foo" for e in main_calls)
        assert any(e.callee == "bar" for e in main_calls)

    def test_calls_inside_namespace_functions(self, parse_cpp):
        root = parse_cpp("""
int baz(int x) { return x; }

namespace ns {
    void inner() {
        baz(42);
    }
}
""")
        extractor = CppExtractor()
        result = extractor.extract_call_graph(root)

        assert any(e.caller == "inner" and e.callee == "baz" for e in result)

    def test_correct_call_line_numbers(self, parse_cpp):
        root = parse_cpp("""
int main() {
    foo();
    bar();
}
""")
        extractor = CppExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) == 2
        assert result[0].line_number == 3
        assert result[1].line_number == 4

    def test_ignores_calls_outside_functions(self, parse_cpp):
        root = parse_cpp("""
int x = compute();
""")
        extractor = CppExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) == 0

    def test_tracks_member_function_calls(self, parse_cpp):
        root = parse_cpp("""
void process() {
    obj.method();
}
""")
        extractor = CppExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) == 1
        assert result[0].caller == "process"
        assert result[0].callee == "method"


# ---------------------------------------------------------------------------
# Comprehensive tests
# ---------------------------------------------------------------------------


class TestComprehensiveCPP:
    """Full C++ test scenarios from the spec."""

    def test_full_cpp_scenario(self, parse_cpp):
        root = parse_cpp("""#include <iostream>
#include "config.h"

class Server {
public:
    std::string host;
    int port;

    void start();
    int getPort() { return port; }
};

void Server::start() {
    std::cout << "starting" << std::endl;
}

namespace utils {
    int add(int a, int b) {
        return a + b;
    }
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        # Imports: 2 includes
        assert len(result.imports) == 2
        assert result.imports[0].source == "iostream"
        assert result.imports[1].source == "config.h"

        # Classes: Server
        assert len(result.classes) == 1
        assert result.classes[0].name == "Server"
        assert result.classes[0].properties == ["host", "port"]
        assert "start" in result.classes[0].methods
        assert "getPort" in result.classes[0].methods

        # Functions: getPort (inline), start (out-of-class), add (namespace)
        assert len(result.functions) == 3
        fn_names = sorted(f.name for f in result.functions)
        assert fn_names == ["add", "getPort", "start"]

        # add() params
        add_fn = next(f for f in result.functions if f.name == "add")
        assert add_fn.params == ["a", "b"]
        assert add_fn.return_type == "int"

        # getPort() inline
        get_port_fn = next(f for f in result.functions if f.name == "getPort")
        assert get_port_fn.params == []
        assert get_port_fn.return_type == "int"

        # Exports: Server, start, getPort, add
        export_names = sorted(e.name for e in result.exports)
        assert "Server" in export_names
        assert "start" in export_names
        assert "getPort" in export_names
        assert "add" in export_names


class TestComprehensiveC:
    """Full pure C test scenarios from the spec."""

    def test_pure_c_with_structs_and_functions(self, parse_cpp):
        root = parse_cpp("""#include <stdio.h>
#include "helper.h"

struct Point {
    int x;
    int y;
};

void print_point(struct Point* p) {
    printf("(%d, %d)", p->x, p->y);
}

int main() {
    struct Point p = {1, 2};
    print_point(&p);
    return 0;
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        # Imports: 2 includes
        assert len(result.imports) == 2
        assert result.imports[0].source == "stdio.h"
        assert result.imports[0].specifiers == ["stdio.h"]
        assert result.imports[1].source == "helper.h"

        # Classes: Point (struct)
        assert len(result.classes) == 1
        assert result.classes[0].name == "Point"
        assert result.classes[0].properties == ["x", "y"]
        assert result.classes[0].methods == []

        # Functions
        assert len(result.functions) == 2
        fn_names = sorted(f.name for f in result.functions)
        assert fn_names == ["main", "print_point"]

        # print_point params
        print_fn = next(f for f in result.functions if f.name == "print_point")
        assert print_fn.params == ["p"]
        assert print_fn.return_type == "void"

        # main params
        main_fn = next(f for f in result.functions if f.name == "main")
        assert main_fn.params == []
        assert main_fn.return_type == "int"

        # Exports
        export_names = [e.name for e in result.exports]
        assert "Point" in export_names
        assert "print_point" in export_names
        assert "main" in export_names

        # Call graph
        calls = extractor.extract_call_graph(root)

        print_calls = [e for e in calls if e.caller == "print_point"]
        assert any(e.callee == "printf" for e in print_calls)

        main_calls = [e for e in calls if e.caller == "main"]
        assert any(e.callee == "print_point" for e in main_calls)

    def test_pure_c_without_classes_or_structs(self, parse_cpp):
        root = parse_cpp("""
#include <stdlib.h>

int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

int main() {
    int result = factorial(5);
    return 0;
}
""")
        extractor = CppExtractor()
        result = extractor.extract_structure(root)

        # No classes
        assert len(result.classes) == 0

        # Functions
        assert len(result.functions) == 2
        assert result.functions[0].name == "factorial"
        assert result.functions[0].params == ["n"]
        assert result.functions[1].name == "main"

        # Call graph: recursive factorial + main calls factorial
        calls = extractor.extract_call_graph(root)
        assert any(e.caller == "factorial" and e.callee == "factorial" for e in calls)
        assert any(e.caller == "main" and e.callee == "factorial" for e in calls)
