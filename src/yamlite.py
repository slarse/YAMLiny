import contextlib
import pathlib
import re
import sys

import dataclasses

from typing import Union, List, Optional

__all__ = ["YamliteError", "loads"]

_LINE_PATTERN = re.compile(r"^[-_\w]+:")
_KEY_DELIMITER = ":"

_COMMENT_CHAR = "#"


_Value = Union[str, "_Node", List[str]]


@dataclasses.dataclass(frozen=True)
class _Root:
    children: List["_Node"]


@dataclasses.dataclass(frozen=True)
class _Node:
    key: str
    indent: int
    parent: Union["_Node", _Root]
    children: List[_Value]
    line_nr: int


class YamliteError(RuntimeError):
    pass


def loads(text: str) -> dict:
    root = _Root(children=[])
    parent: Union["_Node", _Root] = root

    for line_nr, raw_line in enumerate(text.strip().split("\n"), start=1):
        with _insert_line_number_in_error(line_nr):
            line = _remove_comments(raw_line)
            if not line:
                continue
            stripped = line.strip()
            _check_line_syntax(stripped)

            indent = _count_indent(line)

            while not isinstance(parent, _Root) and parent.indent >= indent:
                parent = parent.parent

            key, rest = stripped.split(_KEY_DELIMITER)
            children = [] if not rest else [_parse_terminal_value(rest)]
            node = _Node(key, indent, parent, children, line_nr)
            parent.children.append(node)

            if not children:
                parent = node

    return _to_dict(root)


@contextlib.contextmanager
def _insert_line_number_in_error(line_nr: int):
    try:
        yield
    except Exception as exc:
        raise YamliteError(f"Line {line_nr}: {str(exc)}") from exc


def _check_line_syntax(line: str) -> None:
    if not re.match(_LINE_PATTERN, line):
        raise YamliteError("expected line to start with '<key>:'")


def _remove_comments(line: str) -> str:
    comment_start_idx = line.find(_COMMENT_CHAR)
    if _is_comment_hash_at(line, comment_start_idx):
        return line[:comment_start_idx].rstrip()
    return line


def _is_comment_hash_at(line: str, idx: int) -> bool:
    return idx == 0 or idx > 0 and line[idx - 1].isspace()


def _parse_terminal_value(raw_value: str) -> Union[str, List[str]]:
    stripped = raw_value.strip()
    return _parse_array(stripped) if stripped.startswith("[") else stripped


def _parse_array(stripped: str) -> List[str]:
    if not stripped.endswith("]"):
        raise YamliteError(f"array must start and end on same line")
    return [value.strip() for value in stripped[1:-1].split(",")]


def _to_dict(root: _Root) -> dict:
    return {node.key: _children_to_dict(node.children) for node in root.children}


def _children_to_dict(children: List[Union[str, _Node]]) -> Optional[Union[dict, str]]:
    if not children:
        return None

    _check_consistent_indent([child for child in children if isinstance(child, _Node)])
    first, *_ = children
    if isinstance(first, (str, list)):
        return first
    else:
        assert all(isinstance(child, _Node) for child in children)
        return {child.key: _children_to_dict(child.children) for child in children}


def _check_consistent_indent(nodes: List[_Node]) -> None:
    if not nodes:
        return

    expected_indent = nodes[0].indent
    for node in nodes[1:]:
        if node.indent != expected_indent:
            raise YamliteError(
                f"Line {node.line_nr}: bad indentation, "
                f"expected {expected_indent} but was {node.indent}"
            )


def _count_indent(line: str) -> int:
    return len(line) - len(line.lstrip())
