"""集成测试共享夹具 — 使用 pytest tmp_path 创建迷你项目."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest


def _write_file(root: Path, rel_path: str, content: str) -> None:
    """在 root 下创建文件（自动创建父目录）."""
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)


# ---------------------------------------------------------------------------
# Python mini-project
# ---------------------------------------------------------------------------

MiniProjectFactory = Callable[[Path | None], Path]


@pytest.fixture
def mini_python_project(tmp_path: Path) -> Path:
    """创建一个迷你 Python 项目."""
    root = tmp_path / "mini-python"
    root.mkdir(parents=True, exist_ok=True)

    _write_file(root, "src/__init__.py", "")
    _write_file(
        root,
        "src/main.py",
        """\"\"\"Main application entry point.\"\"\"

from src.utils import helper, validate


def main() -> None:
    \"\"\"Application entry point.\"\"\"
    data = load_data()
    processed = process_data(data)
    helper(processed)


def load_data() -> list[str]:
    \"\"\"Load data from source.\"\"\"
    return ["a", "b", "c"]


def process_data(items: list[str]) -> list[str]:
    \"\"\"Process loaded data.\"\"\"
    return [item.upper() for item in items]
""",
    )
    _write_file(
        root,
        "src/utils.py",
        """\"\"\"Shared utility functions.\"\"\"


def helper(data: list[str]) -> None:
    \"\"\"Print processed data.\"\"\"
    for item in data:
        print(f"  - {item}")


def validate(value: str) -> bool:
    \"\"\"Validate a string value.\"\"\"
    return len(value) > 0
""",
    )
    _write_file(root, "src/models/__init__.py", "")
    _write_file(
        root,
        "src/models/user.py",
        """\"\"\"User model.\"\"\"

from dataclasses import dataclass


@dataclass
class User:
    \"\"\"A user entity.\"\"\"

    name: str
    age: int

    def greet(self) -> str:
        \"\"\"Return a greeting.\"\"\"
        return f"Hello, I'm {self.name}"

    def to_dict(self) -> dict:
        \"\"\"Convert to dictionary.\"\"\"
        return {"name": self.name, "age": self.age}
""",
    )
    _write_file(
        root,
        "tests/test_main.py",
        """\"\"\"Tests for main module.\"\"\"


def test_main() -> None:
    \"\"\"Smoke test for main.\"\"\"
    from src.main import load_data

    assert load_data() == ["a", "b", "c"]
""",
    )
    _write_file(
        root,
        "README.md",
        "# mini-python\n\nA minimal Python project for integration testing.\n",
    )
    _write_file(
        root,
        "config.yaml",
        "app:\n  name: mini-python\n  debug: true\n",
    )
    _write_file(
        root,
        "Makefile",
        "test:\n\tpython -m pytest tests/\n\nlint:\n\truff check src/\n",
    )
    _write_file(
        root,
        ".gitignore",
        "*.log\n__pycache__/\n",
    )

    return root


# ---------------------------------------------------------------------------
# TypeScript mini-project
# ---------------------------------------------------------------------------


@pytest.fixture
def mini_typescript_project(tmp_path: Path) -> Path:
    """创建一个迷你 TypeScript 项目."""
    root = tmp_path / "mini-ts"
    root.mkdir(parents=True, exist_ok=True)

    _write_file(
        root,
        "src/index.ts",
        """import { greet } from "./utils";

function main(): void {
  console.log(greet("World"));
}

main();
""",
    )
    _write_file(
        root,
        "src/utils.ts",
        """export function greet(name: string): string {
  return `Hello, ${name}!`;
}

export function add(a: number, b: number): number {
  return a + b;
}
""",
    )
    _write_file(
        root,
        "tsconfig.json",
        '{\n  "compilerOptions": {\n    "target": "ES2020",\n    "module": "commonjs",\n    "strict": true\n  }\n}\n',
    )

    return root


# ---------------------------------------------------------------------------
# Config/schema/infra mini-project (non-code only)
# ---------------------------------------------------------------------------


@pytest.fixture
def mini_configs_project(tmp_path: Path) -> Path:
    """创建一个纯非代码项目（配置、schema、基础设施）."""
    root = tmp_path / "mini-configs"
    root.mkdir(parents=True, exist_ok=True)

    _write_file(
        root,
        "docker-compose.yml",
        """version: "3.8"
services:
  web:
    image: nginx:alpine
    ports:
      - "8080:80"
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: app
""",
    )
    _write_file(
        root,
        "schema.sql",
        """CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE
);

CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id)
);
""",
    )
    _write_file(
        root,
        "schema.graphql",
        """type Query {
  user(id: ID!): User
  users: [User!]!
}

type User {
  id: ID!
  name: String!
  email: String
}
""",
    )
    _write_file(
        root,
        "main.tf",
        """resource "aws_s3_bucket" "assets" {
  bucket = "my-assets-bucket"
  acl    = "private"
}

resource "aws_dynamodb_table" "locks" {
  name         = "terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
""",
    )
    _write_file(
        root,
        ".env",
        "DATABASE_URL=postgres://localhost:5432/app\nDEBUG=true\n",
    )
    _write_file(
        root,
        "Dockerfile",
        "FROM python:3.11-slim\n\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nCMD [\"python\", \"main.py\"]\n",
    )
    _write_file(
        root,
        "script.sh",
        '#!/bin/bash\necho "Hello, World!"\n',
    )

    return root
