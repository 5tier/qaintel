from __future__ import annotations

import re
from pathlib import Path


TREE_SITTER_LANGUAGES = {
    ".py": ("tree_sitter_python", "language"),
    ".js": ("tree_sitter_javascript", "language"),
    ".jsx": ("tree_sitter_javascript", "language"),
    ".ts": ("tree_sitter_typescript", "language_typescript"),
    ".tsx": ("tree_sitter_typescript", "language_tsx"),
    ".go": ("tree_sitter_go", "language"),
    ".rb": ("tree_sitter_ruby", "language"),
    ".java": ("tree_sitter_java", "language"),
    ".cs": ("tree_sitter_c_sharp", "language"),
}

TREE_SITTER_KINDS = {
    "class_definition": "class",
    "class_declaration": "class",
    "interface_declaration": "type",
    "enum_declaration": "type",
    "function_definition": "function",
    "function_declaration": "function",
    "method_definition": "method",
    "method_declaration": "method",
    "function_item": "function",
    "method": "method",
    "module": "module",
}

IMPORT_PATTERNS = {
    ".py": [
        re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE),
    ],
    ".js": [
        re.compile(r"(?:from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\))"),
    ],
    ".jsx": [
        re.compile(r"(?:from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\))"),
    ],
    ".ts": [
        re.compile(r"(?:from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\))"),
    ],
    ".tsx": [
        re.compile(r"(?:from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\))"),
    ],
    ".go": [re.compile(r"^\s*(?:import\s+)?\"([^\"]+)\"", re.MULTILINE)],
    ".java": [re.compile(r"^\s*import\s+([\w.*]+);", re.MULTILINE)],
    ".cs": [re.compile(r"^\s*using\s+([\w.]+);", re.MULTILINE)],
    ".rb": [re.compile(r"^\s*require(?:_relative)?\s+['\"]([^'\"]+)['\"]", re.MULTILINE)],
}

SYMBOL_PATTERNS = {
    ".py": [
        ("class", re.compile(r"^(\s*)class\s+([A-Za-z_]\w*)\b.*", re.MULTILINE)),
        ("function", re.compile(r"^(\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\([^)]*\).*", re.MULTILINE)),
    ],
    ".js": [],
    ".jsx": [],
    ".ts": [],
    ".tsx": [],
    ".go": [
        ("function", re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\([^)]*\).*", re.MULTILINE)),
        ("type", re.compile(r"^type\s+([A-Za-z_]\w*)\s+", re.MULTILINE)),
    ],
    ".java": [
        ("class", re.compile(r"^\s*(?:public\s+)?(?:class|interface|enum)\s+([A-Za-z_]\w*)\b.*", re.MULTILINE)),
        ("method", re.compile(r"^\s*(?:public|private|protected)\s+[\w<>\[\], ?]+\s+([A-Za-z_]\w*)\s*\([^)]*\).*", re.MULTILINE)),
    ],
    ".cs": [
        ("class", re.compile(r"^\s*(?:public\s+)?(?:class|interface|enum|record)\s+([A-Za-z_]\w*)\b.*", re.MULTILINE)),
        ("method", re.compile(r"^\s*(?:public|private|protected|internal)\s+[\w<>\[\], ?]+\s+([A-Za-z_]\w*)\s*\([^)]*\).*", re.MULTILINE)),
    ],
    ".rb": [
        ("class", re.compile(r"^\s*class\s+([A-Za-z_]\w*)\b.*", re.MULTILINE)),
        ("module", re.compile(r"^\s*module\s+([A-Za-z_]\w*)\b.*", re.MULTILINE)),
        ("method", re.compile(r"^\s*def\s+([A-Za-z_]\w*[!?=]?)\b.*", re.MULTILINE)),
    ],
}

JS_SYMBOL_PATTERNS = [
    ("class", re.compile(r"^\s*(export\s+)?class\s+([A-Za-z_$][\w$]*)\b.*", re.MULTILINE)),
    ("function", re.compile(r"^\s*(export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\).*", re.MULTILINE)),
    ("function", re.compile(r"^\s*(export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>.*", re.MULTILINE)),
    ("constant", re.compile(r"^\s*(export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=", re.MULTILINE)),
    ("type", re.compile(r"^\s*(export\s+)?(?:type|interface)\s+([A-Za-z_$][\w$]*)\b.*", re.MULTILINE)),
]


def extract_symbols(files: list[Path], repo_path: Path) -> tuple[dict, dict]:
    file_texts = _read_files(files, repo_path)
    symbols = _extract_all_symbols(file_texts)
    callgraph = _extract_callgraph(file_texts)
    _connect_symbol_calls(symbols, file_texts, callgraph)
    return dict(sorted(symbols.items())), dict(sorted(callgraph.items()))


def _read_files(files: list[Path], repo_path: Path) -> dict[str, tuple[Path, str]]:
    result = {}
    for file in sorted(files, key=lambda path: str(path.relative_to(repo_path))):
        rel = str(file.relative_to(repo_path))
        result[rel] = (file, file.read_text(errors="ignore"))
    return result


def _extract_all_symbols(file_texts: dict[str, tuple[Path, str]]) -> dict:
    symbols = {}
    for rel, (file, text) in file_texts.items():
        for symbol in _extract_file_symbols(file, rel, text):
            key = f"{rel}:{symbol['kind']}:{symbol['name']}:{symbol['line']}"
            symbols[key] = symbol
    return symbols


def _extract_file_symbols(file: Path, rel: str, text: str) -> list[dict]:
    tree_sitter_symbols = _extract_tree_sitter_symbols(file.suffix.lower(), rel, text)
    if tree_sitter_symbols:
        return tree_sitter_symbols
    if file.suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}:
        return _extract_js_symbols(rel, text)
    return _extract_regex_symbols(file.suffix.lower(), rel, text)


def _extract_tree_sitter_symbols(suffix: str, rel: str, text: str) -> list[dict]:
    parser = _tree_sitter_parser(suffix)
    if not parser:
        return []

    tree = parser.parse(text.encode())
    symbols = []
    for node in _walk(tree.root_node):
        kind = TREE_SITTER_KINDS.get(node.type)
        name = _node_name(node, text)
        if kind and name:
            symbols.append(_symbol(name, rel, text, node.start_byte, kind, _is_exported(text, node), _node_text(text, node)))
    return _dedupe_symbols(symbols)


def _tree_sitter_parser(suffix: str):
    if suffix not in TREE_SITTER_LANGUAGES:
        return None
    try:
        from importlib import import_module
        from tree_sitter import Language, Parser

        module_name, language_name = TREE_SITTER_LANGUAGES[suffix]
        language_fn = getattr(import_module(module_name), language_name)
        return Parser(Language(language_fn()))
    except Exception:
        return None


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _node_name(node, text: str) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(text, name_node).strip()
    for child in node.children:
        if child.type in {"identifier", "property_identifier", "type_identifier", "constant"}:
            return _node_text(text, child).strip()
    return None


def _node_text(text: str, node) -> str:
    return text.encode()[node.start_byte : node.end_byte].decode(errors="ignore")


def _is_exported(text: str, node) -> bool:
    line_start = text.rfind("\n", 0, node.start_byte) + 1
    prefix = text[line_start : node.start_byte]
    name = _node_name(node, text) or ""
    return "export" in prefix or (name[:1].isupper() and not name.startswith("_"))


def _extract_js_symbols(rel: str, text: str) -> list[dict]:
    symbols = []
    for kind, pattern in JS_SYMBOL_PATTERNS:
        for match in pattern.finditer(text):
            exported = bool(match.group(1))
            name = match.group(2)
            symbols.append(_symbol(name, rel, text, match.start(), kind, exported, match.group(0)))
    return _dedupe_symbols(symbols)


def _extract_regex_symbols(suffix: str, rel: str, text: str) -> list[dict]:
    symbols = []
    for kind, pattern in SYMBOL_PATTERNS.get(suffix, []):
        for match in pattern.finditer(text):
            name = match.group(2) if suffix == ".py" else match.group(1)
            exported = not name.startswith("_")
            symbols.append(_symbol(name, rel, text, match.start(), kind, exported, match.group(0)))
    return _dedupe_symbols(symbols)


def _symbol(name: str, rel: str, text: str, offset: int, kind: str, exported: bool, signature: str) -> dict:
    return {
        "name": name,
        "file": rel,
        "line": text.count("\n", 0, offset) + 1,
        "kind": kind,
        "exported": exported,
        "signature": signature.strip(),
        "callers": [],
        "callees": [],
    }


def _extract_callgraph(file_texts: dict[str, tuple[Path, str]]) -> dict[str, list[str]]:
    graph = {}
    for rel, (file, text) in file_texts.items():
        deps = _imports_for(file.suffix.lower(), text)
        graph[rel] = sorted(deps)
    return graph


def _imports_for(suffix: str, text: str) -> set[str]:
    deps = set()
    for pattern in IMPORT_PATTERNS.get(suffix, []):
        for match in pattern.finditer(text):
            deps.update(group for group in match.groups() if group)
    return deps


def _connect_symbol_calls(symbols: dict, file_texts: dict[str, tuple[Path, str]], callgraph: dict) -> None:
    by_name = {}
    for key, symbol in symbols.items():
        by_name.setdefault(symbol["name"], []).append((key, symbol))

    for rel, (_, text) in file_texts.items():
        names = _called_names(text, by_name.keys())
        callgraph[rel] = sorted(set(callgraph.get(rel, [])) | names)
        for name in names:
            for _, callee in by_name.get(name, []):
                for caller_key, caller in _symbols_in_file(symbols, rel):
                    if caller["name"] != name:
                        caller["callees"] = sorted(set(caller["callees"]) | {name})
                        callee["callers"] = sorted(set(callee["callers"]) | {caller_key})


def _called_names(text: str, names) -> set[str]:
    found = set()
    for name in sorted(names):
        if re.search(rf"\b{re.escape(name)}\s*\(", text):
            found.add(name)
    return found


def _symbols_in_file(symbols: dict, rel: str):
    return [(key, symbol) for key, symbol in symbols.items() if symbol["file"] == rel]


def _dedupe_symbols(symbols: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for symbol in sorted(symbols, key=lambda item: (item["line"], item["name"], item["kind"])):
        key = (symbol["name"], symbol["line"], symbol["kind"])
        if key not in seen:
            seen.add(key)
            result.append(symbol)
    return result
