"""Knuth-Morris-Pratt pattern matching, implemented without string search helpers."""
from time import sleep


def prefix_table(pattern: str) -> list[int]:
    table = [0] * len(pattern)
    length = 0
    for index in range(1, len(pattern)):
        while length and pattern[index] != pattern[length]:
            length = table[length - 1]
        if pattern[index] == pattern[length]:
            length += 1
        table[index] = length
    return table


def find_all(text: str, pattern: str) -> list[int]:
    """Return every (including overlapping) zero-based match position."""
    if not pattern:
        return []
    table, matches, matched = prefix_table(pattern), [], 0
    for index, character in enumerate(text):
        while matched and character != pattern[matched]:
            matched = table[matched - 1]
        if character == pattern[matched]:
            matched += 1
        if matched == len(pattern):
            matches.append(index - len(pattern) + 1)
            matched = table[matched - 1]
    return matches


def find_all_by_capacity(text: str, pattern: str, capacity: int, delay_seconds: float = 0) -> list[int]:
    """Run KMP in chunks, pausing after each simulated second when requested."""
    if not pattern or capacity < 1:
        return []
    table, matches, matched = prefix_table(pattern), [], 0
    for start in range(0, len(text), capacity):
        for index in range(start, min(start + capacity, len(text))):
            character = text[index]
            while matched and character != pattern[matched]:
                matched = table[matched - 1]
            if character == pattern[matched]:
                matched += 1
            if matched == len(pattern):
                matches.append(index - len(pattern) + 1)
                matched = table[matched - 1]
        if delay_seconds:
            sleep(delay_seconds)
    return matches
