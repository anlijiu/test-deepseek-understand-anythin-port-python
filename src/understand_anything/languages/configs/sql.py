"""内置语言配置 — SQL。

Python port of the TypeScript ``sqlConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

sql_config = LanguageConfig(
    id="sql",
    displayName="SQL",
    extensions=[".sql"],
    concepts=[
        "tables",
        "columns",
        "indexes",
        "foreign keys",
        "views",
        "stored procedures",
        "triggers",
        "migrations",
    ],
    filePatterns=FilePatternConfig(),
)
