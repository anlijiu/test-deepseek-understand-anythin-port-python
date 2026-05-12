"""内置语言配置 — XML。

Python port of the TypeScript ``xmlConfig``.
"""
from __future__ import annotations

from understand_anything.languages.types import FilePatternConfig, LanguageConfig

xml_config = LanguageConfig(
    id="xml",
    displayName="XML",
    extensions=[".xml", ".xsl", ".xsd", ".svg", ".plist"],
    concepts=[
        "elements",
        "attributes",
        "namespaces",
        "DTD",
        "XPath",
        "XSLT",
        "schemas",
    ],
    filePatterns=FilePatternConfig(
        config=["pom.xml", "web.xml", "AndroidManifest.xml"],
    ),
)
