"""Python extractor tests — ported from python-extractor.test.ts."""

from __future__ import annotations

from understand_anything.plugins.extractors.python import PythonExtractor


def test_language_ids():
    """Verify the extractor reports correct language IDs."""
    extractor = PythonExtractor()
    assert extractor.language_ids == ["python"]


# ---------------------------------------------------------------------------
# extractStructure - functions
# ---------------------------------------------------------------------------


class TestExtractStructureFunctions:
    """Tests for function extraction."""

    def test_simple_functions_with_type_annotations(self, parse_python):
        """Extract simple functions with type annotations."""
        root = parse_python("""
def hello(name: str) -> str:
    return f"Hello {name}"

def add(a: int, b: int) -> int:
    return a + b
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 2

        assert result.functions[0].name == "hello"
        assert result.functions[0].params == ["name"]
        assert result.functions[0].return_type == "str"
        assert result.functions[0].line_range[0] > 0

        assert result.functions[1].name == "add"
        assert result.functions[1].params == ["a", "b"]
        assert result.functions[1].return_type == "int"

    def test_functions_without_type_annotations(self, parse_python):
        """Extract functions without type annotations."""
        root = parse_python("""
def greet(name):
    print(name)

def noop():
    pass
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 2
        assert result.functions[0].name == "greet"
        assert result.functions[0].params == ["name"]
        assert result.functions[0].return_type is None

        assert result.functions[1].name == "noop"
        assert result.functions[1].params == []

    def test_functions_with_default_parameters(self, parse_python):
        """Extract functions with default parameter values."""
        root = parse_python("""
def connect(host: str, port: int = 8080, timeout: float = 30.0):
    pass
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].name == "connect"
        assert result.functions[0].params == ["host", "port", "timeout"]

    def test_functions_with_args_and_kwargs(self, parse_python):
        """Extract functions with *args and **kwargs."""
        root = parse_python("""
def flexible(*args, **kwargs):
    pass
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].params == ["*args", "**kwargs"]

    def test_decorated_functions(self, parse_python):
        """Extract decorated functions."""
        root = parse_python("""
@decorator
def decorated_func():
    pass

@app.route("/api")
def api_handler():
    pass
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 2
        assert result.functions[0].name == "decorated_func"
        assert result.functions[1].name == "api_handler"

    def test_correct_line_ranges(self, parse_python):
        """Report correct line ranges for functions."""
        root = parse_python("""
def multiline(
    a: int,
    b: int,
) -> int:
    result = a + b
    return result
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.functions) == 1
        assert result.functions[0].line_range[0] == 2
        assert result.functions[0].line_range[1] == 7


# ---------------------------------------------------------------------------
# extractStructure - classes
# ---------------------------------------------------------------------------


class TestExtractStructureClasses:
    """Tests for class extraction."""

    def test_classes_with_methods_and_properties(self, parse_python):
        """Extract class with methods and annotated properties."""
        root = parse_python("""
class DataProcessor:
    name: str

    def __init__(self, name: str):
        self.name = name

    def process(self, data: list) -> dict:
        return transform(data)
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].name == "DataProcessor"
        assert "__init__" in result.classes[0].methods
        assert "process" in result.classes[0].methods
        assert "name" in result.classes[0].properties

    def test_dataclass_style_annotated_properties(self, parse_python):
        """Extract dataclass-style annotated class properties."""
        root = parse_python("""
class Config:
    name: str
    value: int
    debug: bool
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].properties == ["name", "value", "debug"]
        assert result.classes[0].methods == []

    def test_decorated_classes(self, parse_python):
        """Extract decorated classes."""
        root = parse_python("""
@dataclass
class Config:
    name: str
    value: int = 0
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].name == "Config"
        assert "name" in result.classes[0].properties
        assert "value" in result.classes[0].properties

    def test_decorated_methods_within_class(self, parse_python):
        """Extract decorated methods (@staticmethod, @classmethod, @property)."""
        root = parse_python("""
class MyClass:
    @staticmethod
    def static_method():
        pass

    @classmethod
    def class_method(cls):
        pass

    @property
    def prop(self):
        return self._prop
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert "static_method" in result.classes[0].methods
        assert "class_method" in result.classes[0].methods
        assert "prop" in result.classes[0].methods

    def test_filters_self_and_cls_from_method_params(self, parse_python):
        """Filter self and cls from method params but NOT top-level funcs."""
        root = parse_python("""
class Foo:
    def instance_method(self, x: int):
        pass

    @classmethod
    def class_method(cls, y: str):
        pass
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)
        # Methods are on the class, top-level functions should not include them
        assert len(result.functions) == 0
        assert result.classes[0].methods == ["instance_method", "class_method"]

    def test_correct_class_line_ranges(self, parse_python):
        """Report correct line ranges for classes."""
        root = parse_python("""
class MyClass:
    def method_a(self):
        pass

    def method_b(self):
        pass
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.classes) == 1
        assert result.classes[0].line_range[0] == 2
        assert result.classes[0].line_range[1] == 7


# ---------------------------------------------------------------------------
# extractStructure - imports
# ---------------------------------------------------------------------------


class TestExtractStructureImports:
    """Tests for import extraction."""

    def test_simple_import_statements(self, parse_python):
        """Extract simple import statements."""
        root = parse_python("""
import os
import sys
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 2
        assert result.imports[0].source == "os"
        assert result.imports[0].specifiers == ["os"]
        assert result.imports[1].source == "sys"
        assert result.imports[1].specifiers == ["sys"]

    def test_from_import_statements(self, parse_python):
        """Extract from-import statements."""
        root = parse_python("""
from pathlib import Path
from typing import Optional, List
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 2
        assert result.imports[0].source == "pathlib"
        assert result.imports[0].specifiers == ["Path"]
        assert result.imports[1].source == "typing"
        assert result.imports[1].specifiers == ["Optional", "List"]

    def test_aliased_imports(self, parse_python):
        """Extract aliased from-imports."""
        root = parse_python("""
from foo import bar as baz
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 1
        assert result.imports[0].source == "foo"
        assert result.imports[0].specifiers == ["baz"]

    def test_dotted_module_imports(self, parse_python):
        """Extract dotted module import paths."""
        root = parse_python("""
import os.path
from os.path import join, exists
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 2
        assert result.imports[0].source == "os.path"
        assert result.imports[0].specifiers == ["os.path"]
        assert result.imports[1].source == "os.path"
        assert result.imports[1].specifiers == ["join", "exists"]

    def test_wildcard_imports(self, parse_python):
        """Extract wildcard imports."""
        root = parse_python("""
from os.path import *
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) == 1
        assert result.imports[0].source == "os.path"
        assert result.imports[0].specifiers == ["*"]

    def test_all_import_types_together(self, parse_python):
        """Handle all import types together."""
        root = parse_python("""
import os
from pathlib import Path
from typing import Optional, List
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.imports) >= 3

    def test_correct_import_line_numbers(self, parse_python):
        """Report correct import line numbers."""
        root = parse_python("""
import os
from pathlib import Path
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert result.imports[0].line_number == 2
        assert result.imports[1].line_number == 3


# ---------------------------------------------------------------------------
# extractStructure - exports
# ---------------------------------------------------------------------------


class TestExtractStructureExports:
    """Tests for export extraction."""

    def test_top_level_functions_as_exports(self, parse_python):
        """Treat top-level functions as exports."""
        root = parse_python("""
def public_func():
    pass

def another_func(x: int) -> str:
    return str(x)
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "public_func" in export_names
        assert "another_func" in export_names
        assert len(result.exports) == 2

    def test_top_level_classes_as_exports(self, parse_python):
        """Treat top-level classes as exports."""
        root = parse_python("""
class MyService:
    pass

class MyModel:
    pass
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "MyService" in export_names
        assert "MyModel" in export_names
        assert len(result.exports) == 2

    def test_decorated_top_level_defs_as_exports(self, parse_python):
        """Treat decorated top-level definitions as exports."""
        root = parse_python("""
@dataclass
class Config:
    name: str

@app.route("/")
def index():
    pass
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        export_names = [e.name for e in result.exports]
        assert "Config" in export_names
        assert "index" in export_names

    def test_does_not_treat_imports_as_exports(self, parse_python):
        """Does not treat import statements as exports."""
        root = parse_python("""
import os
from pathlib import Path

def my_func():
    pass
""")
        extractor = PythonExtractor()
        result = extractor.extract_structure(root)

        assert len(result.exports) == 1
        assert result.exports[0].name == "my_func"


# ---------------------------------------------------------------------------
# extractCallGraph
# ---------------------------------------------------------------------------


class TestExtractCallGraph:
    """Tests for call graph extraction."""

    def test_simple_function_calls(self, parse_python):
        """Extract simple function call relationships."""
        root = parse_python("""
def process(data):
    result = transform(data)
    return format_output(result)

def main():
    process([1, 2, 3])
""")
        extractor = PythonExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) >= 2

        process_calls = [e for e in result if e.caller == "process"]
        assert any(e.callee == "transform" for e in process_calls)
        assert any(e.callee == "format_output" for e in process_calls)

        main_calls = [e for e in result if e.caller == "main"]
        assert any(e.callee == "process" for e in main_calls)

    def test_attribute_based_calls(self, parse_python):
        """Extract attribute-based calls (method calls, dotted access)."""
        root = parse_python("""
def process():
    self.method()
    os.path.join("a", "b")
    result.save()
""")
        extractor = PythonExtractor()
        result = extractor.extract_call_graph(root)

        callees = [e.callee for e in result]
        assert "self.method" in callees
        assert "os.path.join" in callees
        assert "result.save" in callees

    def test_nested_call_tracking(self, parse_python):
        """Track correct caller context for nested function calls."""
        root = parse_python("""
def outer():
    helper()
    def inner():
        deep_call()
    another()
""")
        extractor = PythonExtractor()
        result = extractor.extract_call_graph(root)

        outer_calls = [e for e in result if e.caller == "outer"]
        assert any(e.callee == "helper" for e in outer_calls)
        assert any(e.callee == "another" for e in outer_calls)

        inner_calls = [e for e in result if e.caller == "inner"]
        assert any(e.callee == "deep_call" for e in inner_calls)

    def test_correct_call_line_numbers(self, parse_python):
        """Report correct line numbers for calls."""
        root = parse_python("""
def main():
    foo()
    bar()
""")
        extractor = PythonExtractor()
        result = extractor.extract_call_graph(root)

        assert len(result) == 2
        assert result[0].line_number == 3
        assert result[1].line_number == 4

    def test_ignores_top_level_calls(self, parse_python):
        """Ignore calls at the top level (no enclosing function)."""
        root = parse_python("""
print("hello")
main()
""")
        extractor = PythonExtractor()
        result = extractor.extract_call_graph(root)

        # Top-level calls have no enclosing function, so they are skipped
        assert len(result) == 0

    def test_calls_inside_class_methods(self, parse_python):
        """Handle calls inside class methods."""
        root = parse_python("""
class Service:
    def start(self):
        self.setup()
        run_server()
""")
        extractor = PythonExtractor()
        result = extractor.extract_call_graph(root)

        start_calls = [e for e in result if e.caller == "start"]
        assert any(e.callee == "self.setup" for e in start_calls)
        assert any(e.callee == "run_server" for e in start_calls)


# ---------------------------------------------------------------------------
# Comprehensive
# ---------------------------------------------------------------------------


def test_comprehensive_realistic_python_module(parse_python):
    """Handle a comprehensive realistic Python module."""
    root = parse_python("""
import os
from pathlib import Path
from typing import Optional, List

class FileProcessor:
    name: str
    verbose: bool

    def __init__(self, name: str, verbose: bool = False):
        self.name = name
        self.verbose = verbose

    def process(self, paths: List[str]) -> dict:
        results = {}
        for p in paths:
            results[p] = self._read_file(p)
        return results

    def _read_file(self, path: str) -> Optional[str]:
        full = Path(path)
        if full.exists():
            return full.read_text()
        return None

def create_processor(name: str) -> FileProcessor:
    return FileProcessor(name)

@staticmethod
def utility_func(*args, **kwargs) -> None:
    print(args, kwargs)
""")
    extractor = PythonExtractor()
    result = extractor.extract_structure(root)

    # Imports
    assert len(result.imports) >= 3

    # Class
    assert len(result.classes) == 1
    assert result.classes[0].name == "FileProcessor"
    assert "__init__" in result.classes[0].methods
    assert "process" in result.classes[0].methods
    assert "_read_file" in result.classes[0].methods
    assert "name" in result.classes[0].properties
    assert "verbose" in result.classes[0].properties

    # Top-level functions
    assert any(f.name == "create_processor" for f in result.functions)
    assert any(f.name == "utility_func" for f in result.functions)

    # Exports (top-level defs)
    export_names = [e.name for e in result.exports]
    assert "FileProcessor" in export_names
    assert "create_processor" in export_names
    assert "utility_func" in export_names

    # Call graph
    calls = extractor.extract_call_graph(root)
    assert len(calls) > 0
