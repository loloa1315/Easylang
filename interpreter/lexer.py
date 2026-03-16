import re

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")


def strip_comment(line: str) -> str:
    """Remove comments starting with #."""
    if "#" in line:
        return line.split("#", 1)[0]
    return line


def is_number(text: str) -> bool:
    return bool(NUMBER_RE.match(text.strip()))


def is_valid_name(text: str) -> bool:
    return bool(NAME_RE.match(text.strip()))


def split_words(text: str):
    return text.strip().split()
