"""Contract version constants."""

from typing import Literal

SchemaVersion = Literal["1.0", "1.1"]
SCHEMA_VERSION: SchemaVersion = "1.1"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0", SCHEMA_VERSION})
