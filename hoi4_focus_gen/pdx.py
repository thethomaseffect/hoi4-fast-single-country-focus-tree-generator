from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

FOCUS_BLOCK_KEYS = frozenset({"focus", "shared_focus", "joint_focus"})


@dataclass
class PdxObject:
    items: list[tuple[str | None, Any]] = field(default_factory=list)
    start: int = 0
    end: int = 0

    def get_all(self, key: str) -> list[Any]:
        return [value for item_key, value in self.items if item_key == key]

    def get(self, key: str) -> Any | None:
        values = self.get_all(key)
        return values[0] if values else None


def read_pdx_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _is_ident_char(char: str) -> bool:
    return char.isalnum() or char in {"_", ".", "-", ":", "@", "'"}


def tokenize(text: str) -> list[tuple[str, str, int, int]]:
    """Return (kind, value, start, end) tokens, skipping comments and whitespace."""
    tokens: list[tuple[str, str, int, int]] = []
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if char in " \t\r\n":
            i += 1
            continue
        if char == "#":
            while i < length and text[i] not in "\r\n":
                i += 1
            continue
        if char == '"':
            start = i
            i += 1
            while i < length and text[i] != '"':
                if text[i] == "\\" and i + 1 < length:
                    i += 2
                    continue
                i += 1
            if i < length:
                i += 1
            tokens.append(("string", text[start:i], start, i))
            continue
        if char == "{":
            tokens.append(("lbrace", char, i, i + 1))
            i += 1
            continue
        if char == "}":
            tokens.append(("rbrace", char, i, i + 1))
            i += 1
            continue
        if char == "=":
            tokens.append(("eq", char, i, i + 1))
            i += 1
            continue
        start = i
        if char in "<>":
            i += 1
            if i < length and text[i] == "=":
                i += 1
            tokens.append(("atom", text[start:i], start, i))
            continue
        while i < length and _is_ident_char(text[i]):
            i += 1
        if i == start:
            i += 1
            continue
        tokens.append(("atom", text[start:i], start, i))
    return tokens


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = tokenize(text)
        self.index = 0

    def peek(self) -> tuple[str, str, int, int] | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def pop(self) -> tuple[str, str, int, int]:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def parse_file(self) -> PdxObject:
        items: list[tuple[str | None, Any]] = []
        start = 0
        while self.peek() is not None:
            items.append(self.parse_statement())
        return PdxObject(items=items, start=start, end=len(self.text))

    def parse_statement(self) -> tuple[str | None, Any]:
        token = self.pop()
        kind, value, start, _end = token
        if kind == "lbrace":
            return None, self.parse_object(start)
        if self.peek() and self.peek()[0] == "eq":
            self.pop()
            return self.unquote(value), self.parse_value()
        return None, self.unquote(value)

    def parse_value(self) -> Any:
        token = self.peek()
        if token is None:
            return ""
        if token[0] == "lbrace":
            start = token[2]
            self.pop()
            return self.parse_object(start)
        kind, value, _start, _end = self.pop()
        return self.unquote(value)

    def parse_object(self, start: int) -> PdxObject:
        items: list[tuple[str | None, Any]] = []
        while True:
            token = self.peek()
            if token is None:
                return PdxObject(items=items, start=start, end=len(self.text))
            if token[0] == "rbrace":
                end = token[3]
                self.pop()
                return PdxObject(items=items, start=start, end=end)
            items.append(self.parse_statement())

    @staticmethod
    def unquote(value: str) -> str:
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            return value[1:-1]
        return value


def parse_pdx(text: str) -> PdxObject:
    return _Parser(text).parse_file()


def parse_pdx_file(path: Path) -> PdxObject:
    return parse_pdx(read_pdx_text(path))


SCORE_SKIP_KEYS = frozenset({"add", "factor", "base"})


@dataclass(frozen=True)
class CountryEval:
    """The country HOI4 would score a focus tree against."""

    tag: str
    original_tag: str
    overlord: str | None = None


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _eval_trigger(key: str | None, value: Any, country: CountryEval) -> bool:
    name = (key or "").lower()
    if name in SCORE_SKIP_KEYS:
        return True
    if name == "or":
        return _eval_or(value, country)
    if name == "and":
        return _eval_and(value, country)
    if name == "not":
        return not _eval_or(value, country)
    if name == "tag":
        return str(value).upper() == country.tag
    if name == "original_tag":
        return str(value).upper() == country.original_tag
    if name == "is_subject_of":
        return country.overlord is not None and str(value).upper() == country.overlord
    return False


def _iter_conditions(node: Any) -> list[tuple[str | None, Any]]:
    if not isinstance(node, PdxObject):
        return []
    return [(key, value) for key, value in node.items if (key or "").lower() not in SCORE_SKIP_KEYS]


def _eval_and(node: Any, country: CountryEval) -> bool:
    conditions = _iter_conditions(node)
    if not conditions:
        return True
    return all(_eval_trigger(key, value, country) for key, value in conditions)


def _eval_or(node: Any, country: CountryEval) -> bool:
    conditions = _iter_conditions(node)
    if not conditions:
        return False
    return any(_eval_trigger(key, value, country) for key, value in conditions)


def score_country_block(country_block: Any, country: CountryEval) -> float:
    """HOI4 picks the focus_tree whose country = { factor/base + matching modifier add } is highest."""
    if not isinstance(country_block, PdxObject):
        return 0.0
    score = _as_float(country_block.get("factor"))
    if country_block.get("base") is not None:
        score = _as_float(country_block.get("base"))
    for modifier in country_block.get_all("modifier"):
        if isinstance(modifier, PdxObject) and _eval_and(modifier, country):
            score += _as_float(modifier.get("add"))
    return score


@dataclass
class FocusTreeInfo:
    tree_id: str
    country: PdxObject | None
    start: int
    end: int
    is_default: bool = False

    def score(self, country: CountryEval) -> float:
        return score_country_block(self.country, country)


def focus_trees_in_file(root: PdxObject) -> list[FocusTreeInfo]:
    trees: list[FocusTreeInfo] = []
    for key, value in root.items:
        if key != "focus_tree" or not isinstance(value, PdxObject):
            continue
        default_value = value.get("default")
        trees.append(
            FocusTreeInfo(
                tree_id=str(value.get("id") or ""),
                country=value.get("country") if isinstance(value.get("country"), PdxObject) else None,
                start=value.start,
                end=value.end,
                is_default=isinstance(default_value, str) and default_value.lower() == "yes",
            )
        )
    return trees


def country_tags_from_text(text: str) -> list[str]:
    tags: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Z0-9]{2,4})\s*=\s*\"", stripped)
        if match:
            tags.append(match.group(1))
    return tags


DESCRIPTOR_NAME_RE = re.compile(r'^\s*name\s*=\s*"([^"]*)"', re.MULTILINE)
REPLACE_PATH_RE = re.compile(r'^\s*replace_path\s*=\s*"([^"]*)"', re.MULTILINE)
SUPPORTED_VERSION_RE = re.compile(r'^\s*supported_version\s*=\s*"([^"]*)"', re.MULTILINE)
VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]*)"', re.MULTILINE)


@dataclass
class DescriptorInfo:
    name: str | None
    replace_paths: set[str]
    supported_version: str | None
    version: str | None
    text: str


def parse_descriptor_text(text: str) -> DescriptorInfo:
    return DescriptorInfo(
        name=(DESCRIPTOR_NAME_RE.search(text).group(1) if DESCRIPTOR_NAME_RE.search(text) else None),
        replace_paths={match.group(1).replace("\\", "/") for match in REPLACE_PATH_RE.finditer(text)},
        supported_version=(
            SUPPORTED_VERSION_RE.search(text).group(1) if SUPPORTED_VERSION_RE.search(text) else None
        ),
        version=VERSION_RE.search(text).group(1) if VERSION_RE.search(text) else None,
        text=text,
    )


def parse_descriptor_file(path: Path) -> DescriptorInfo | None:
    if not path.is_file():
        return None
    return parse_descriptor_text(read_pdx_text(path))


def _format_cost(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def rewrite_focus_costs(text: str, new_cost: float, allowed_spans: Iterable[tuple[int, int]] | None = None) -> tuple[str, int]:
    """Set focus/shared_focus/joint_focus cost values."""
    spans = list(allowed_spans) if allowed_spans is not None else [(0, len(text))]
    tokens = tokenize(text)
    stack: list[str] = []
    replacements: list[tuple[int, int, str]] = []
    changed = 0
    formatted = _format_cost(new_cost)

    i = 0
    while i < len(tokens):
        kind, value, start, end = tokens[i]
        if kind == "lbrace":
            key = ""
            if i >= 2 and tokens[i - 1][0] == "eq" and tokens[i - 2][0] in {"atom", "string"}:
                key = tokens[i - 2][1].strip('"')
            stack.append(key)
            i += 1
            continue
        if kind == "rbrace":
            if stack:
                stack.pop()
            i += 1
            continue
        if (
            kind == "atom"
            and value == "cost"
            and i + 2 < len(tokens)
            and tokens[i + 1][0] == "eq"
            and tokens[i + 2][0] in {"atom", "string"}
            and stack
            and stack[-1] in FOCUS_BLOCK_KEYS
        ):
            value_token = tokens[i + 2]
            value_start, value_end = value_token[2], value_token[3]
            in_span = any(span_start <= value_start < span_end for span_start, span_end in spans)
            if in_span:
                replacements.append((value_start, value_end, formatted))
                changed += 1
            i += 3
            continue
        i += 1

    if not replacements:
        return text, 0
    pieces: list[str] = []
    cursor = 0
    for start, end, replacement in replacements:
        pieces.append(text[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces), changed


def write_descriptor(
    name: str,
    tags: list[str],
    dependencies: list[str],
    supported_version: str,
    picture: str = "thumbnail.png",
    version: str = "1.0",
    path: str | None = None,
) -> str:
    lines = [f'version="{version}"', "tags={"]
    for tag in tags:
        lines.append(f'\t"{tag}"')
    lines.append("}")
    if dependencies:
        lines.append("dependencies={")
        for dependency in dependencies:
            lines.append(f'\t"{dependency}"')
        lines.append("}")
    lines.append(f'name="{name}"')
    lines.append(f'picture="{picture}"')
    lines.append(f'supported_version="{supported_version}"')
    if path:
        lines.append(f'path="{path}"')
    lines.append("")
    return "\n".join(lines)
