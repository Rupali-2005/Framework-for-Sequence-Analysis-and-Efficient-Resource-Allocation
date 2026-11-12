import time


def prefix_table(pattern: str) -> list[int]:
    table = [0] * len(pattern)
    matched = 0

    for index in range(1, len(pattern)):
        while matched and pattern[index] != pattern[matched]:
            matched = table[matched - 1]

        if pattern[index] == pattern[matched]:
            matched += 1

        table[index] = matched

    return table


def find_all(
    text: str,
    pattern: str,
    comparison_capacity: int | None = None,
) -> list[int]:
    if not pattern:
        return []
    if comparison_capacity is not None and comparison_capacity < 1:
        raise ValueError("Comparison capacity must be positive")

    table = prefix_table(pattern)
    matches = []
    matched = 0
    characters_since_pause = 0

    for index, character in enumerate(text):
        while matched and character != pattern[matched]:
            matched = table[matched - 1]

        if character == pattern[matched]:
            matched += 1

        if matched == len(pattern):
            matches.append(index - len(pattern) + 1)
            matched = table[matched - 1]

        if comparison_capacity is not None:
            characters_since_pause += 1
            if characters_since_pause == comparison_capacity:
                time.sleep(1)
                characters_since_pause = 0

    return matches
