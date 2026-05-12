"""内置语言配置 — GraphQL。

Python port of the TypeScript ``graphqlConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

graphql_config = LanguageConfig(
    id="graphql",
    displayName="GraphQL",
    extensions=[".graphql", ".gql"],
    concepts=[
        "types",
        "queries",
        "mutations",
        "subscriptions",
        "resolvers",
        "directives",
        "fragments",
        "schema",
    ],
    filePatterns=FilePatternConfig(
        entryPoints=["schema.graphql"],
    ),
)
