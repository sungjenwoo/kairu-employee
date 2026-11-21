"""Adds up the amounts in what you say."""
import re


def run(text: str) -> str:
    numbers = [int(n) for n in re.findall(r"-?\d+", text)]
    return f"The total is {sum(numbers)}."