#!/usr/bin/env python3
"""Node.js/Express Adapter — Backend source-level analysis for Node.js apps."""

import re
from pathlib import Path
from typing import List
from .base import BaseAdapter, RouteInfo, APICallSite, ComponentInfo, TypeContract


class NodeExpressAdapter(BaseAdapter):
    """Adapter for Node.js/Express/Fastify backend applications."""

    def list_routes(self) -> List[RouteInfo]:
        routes = []

        # Look for Express route files
        for file_path in self._glob_files([
            "**/routes/**/*.{ts,js}",
            "**/api/**/*.{ts,js}",
            "**/controllers/**/*.{ts,js}",
        ]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            # Extract Express routes
            for match in re.finditer(
                r"""(?:router|app)\.(get|post|put|patch|delete)\s*\(\s*["'`]([^"'`]+)["'`]""",
                content,
            ):
                routes.append(RouteInfo(
                    path=match.group(2),
                    file=rel_path,
                    framework="express",
                    metadata={"method": match.group(1).upper()},
                ))

        return routes

    def find_api_call_sites(self) -> List[APICallSite]:
        # Backend doesn't call the API - it IS the API
        # But we can find outgoing calls to other services
        calls = []

        for file_path in self._glob_files(["**/*.{ts,js}"]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            for match in re.finditer(
                r"""(?:await\s+)?fetch\s*\(\s*["'`]([^"'`]+)["'`]""",
                content,
            ):
                calls.append(APICallSite(
                    endpoint=match.group(1),
                    method="GET",
                    file=rel_path,
                    line=content[:match.start()].count("\n") + 1,
                    framework="node-fetch",
                ))

        return calls

    def find_component_definitions(self) -> List[ComponentInfo]:
        # Backend doesn't have UI components
        return []

    def get_type_contracts(self) -> List[TypeContract]:
        contracts = []

        for file_path in self._glob_files(["**/*.{ts,tsx}"]):
            content = self._read_file(file_path)
            if not content:
                continue

            rel_path = str(file_path.relative_to(self.codebase))

            # TypeScript interfaces/types for API responses
            for match in re.finditer(
                r"(?:export\s+)?(?:interface|type)\s+(\w*(?:Response|Request|Payload|DTO|Schema)\w*)\s*(?:=\s*)?\{([^}]+)\}",
                content,
            ):
                fields = [m.group(1) for m in re.finditer(r"(\w+)\s*[?:]", match.group(2))]
                contracts.append(TypeContract(
                    name=match.group(1),
                    file=rel_path,
                    kind="interface" if "interface" in match.group(0) else "type",
                    definition=match.group(0)[:200],
                    fields=fields,
                ))

            # Zod schemas (common in Node.js backends)
            for match in re.finditer(
                r"(?:export\s+)?(?:const|let)\s+(\w+Schema)\s*=\s*z\.\w+",
                content,
            ):
                contracts.append(TypeContract(
                    name=match.group(1),
                    file=rel_path,
                    kind="zod",
                    definition=match.group(0)[:200],
                ))

        # OpenAPI specs
        for spec_file in self._glob_files(["**/openapi.{json,yaml,yml}", "**/swagger.{json,yaml,yml}"]):
            content = self._read_file(spec_file)
            if content:
                contracts.append(TypeContract(
                    name=spec_file.stem,
                    file=str(spec_file.relative_to(self.codebase)),
                    kind="openapi",
                    definition=content[:500],
                ))

        return contracts
