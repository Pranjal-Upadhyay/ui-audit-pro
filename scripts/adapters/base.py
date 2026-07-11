import re
#!/usr/bin/env python3
"""
Base Adapter — Abstract interface that all framework adapters implement.

Each adapter provides the same four functions so the rest of the skill
doesn't need to change regardless of which framework is detected.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RouteInfo:
    """Information about a discovered route."""
    path: str
    file: str
    framework: str
    params: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class APICallSite:
    """Information about an API call in the codebase."""
    endpoint: str
    method: str  # GET, POST, PUT, DELETE, etc.
    file: str
    line: int
    framework: str
    hooks: List[str] = field(default_factory=list)  # e.g., ["useQuery", "useSWR"]
    metadata: Dict = field(default_factory=dict)


@dataclass
class ComponentInfo:
    """Information about a component definition."""
    name: str
    file: str
    line: int
    framework: str
    props: List[str] = field(default_factory=list)
    exports_default: bool = True
    metadata: Dict = field(default_factory=dict)


@dataclass
class TypeContract:
    """Information about a type contract (interface, type, schema)."""
    name: str
    file: str
    kind: str  # "interface", "type", "schema", "openapi", "graphql"
    definition: str
    fields: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class AdapterResult:
    """Combined result from an adapter's analysis."""
    routes: List[RouteInfo] = field(default_factory=list)
    api_calls: List[APICallSite] = field(default_factory=list)
    components: List[ComponentInfo] = field(default_factory=list)
    type_contracts: List[TypeContract] = field(default_factory=list)
    design_tokens: Optional[Dict] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class BaseAdapter(ABC):
    """Abstract base class for framework adapters."""

    def __init__(self, codebase_path: str):
        self.codebase = Path(codebase_path)

    @abstractmethod
    def list_routes(self) -> List[RouteInfo]:
        """
        Enumerate all pages/screens/routes for this framework.

        Examples:
          - Next.js: parse app/ or pages/ directory structure
          - React Router: parse route config file
          - Vue: parse vue-router config
          - Static site: enumerate .html files
        """
        pass

    @abstractmethod
    def find_api_call_sites(self) -> List[APICallSite]:
        """
        Find all places where the frontend calls the backend.

        Examples:
          - Next.js: fetch/getServerSideProps/app api routes/Server Actions
          - React: fetch/axios calls in components/hooks
          - Vue: axios/fetch in components/composables
        """
        pass

    @abstractmethod
    def find_component_definitions(self) -> List[ComponentInfo]:
        """
        Map rendered DOM elements back to their source files.

        Examples:
          - React: component name from file exports
          - Vue: single-file component name
          - Static HTML: direct file/line match
        """
        pass

    @abstractmethod
    def get_type_contracts(self) -> List[TypeContract]:
        """
        Find type definitions used for API contracts.

        Examples:
          - TypeScript interfaces/types
          - PropTypes definitions
          - GraphQL schema files
          - OpenAPI/Swagger spec files
          - Zod/Yup/Joi schemas

        If the project has no types (plain JS), return empty list gracefully.
        """
        pass

    def analyze(self) -> AdapterResult:
        """Run all adapter functions and return combined result."""
        result = AdapterResult()

        try:
            result.routes = self.list_routes()
        except Exception as e:
            result.warnings.append(f"Route discovery failed: {e}")

        try:
            result.api_calls = self.find_api_call_sites()
        except Exception as e:
            result.warnings.append(f"API call discovery failed: {e}")

        try:
            result.components = self.find_component_definitions()
        except Exception as e:
            result.warnings.append(f"Component discovery failed: {e}")

        try:
            result.type_contracts = self.get_type_contracts()
        except Exception as e:
            result.warnings.append(f"Type contract discovery failed: {e}")

        return result

    def _glob_files(self, patterns: List[str]) -> List[Path]:
        """Helper to find files matching patterns.
        
        Handles brace expansion (e.g., **/*.{ts,tsx}) by expanding braces
        into separate glob patterns, since Python's Path.glob() doesn't support
        shell-style brace expansion.
        """
        import re
        
        files = []
        for pattern in patterns:
            # Find brace groups like {ts,tsx}
            brace_match = re.search(r'\{([^}]+)\}', pattern)
            if brace_match:
                # Expand brace group into separate patterns
                prefix = pattern[:brace_match.start()]
                suffix = pattern[brace_match.end():]
                alternatives = brace_match.group(1).split(',')
                for alt in alternatives:
                    expanded = f"{prefix}{alt.strip()}{suffix}"
                    files.extend(self.codebase.glob(expanded))
            else:
                files.extend(self.codebase.glob(pattern))
        
        # Filter out .git, node_modules, and .next directories
        filtered = []
        for f in files:
            f_str = str(f)
            if ".git" not in f_str and "node_modules" not in f_str and ".next" not in f_str:
                filtered.append(f)
        return filtered

    def _read_file(self, path: Path) -> Optional[str]:
        """Helper to safely read a file."""
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None
