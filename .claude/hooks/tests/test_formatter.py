import importlib.util
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "formatter.py"

_spec = importlib.util.spec_from_file_location("formatter", HOOK)
assert _spec and _spec.loader
formatter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(formatter)


def check(text: str) -> list[str]:
    """The prose findings for text, without touching the filesystem.

    Mirrors check_markdown_style() but takes the content directly, so a case is
    one string instead of a temporary file.
    """
    findings = []
    bold = 0
    for lineno, line in formatter.prose_lines(text):
        bold += len(formatter.BOLD_RE.findall(line))
        if formatter.FULLWIDTH_PAREN_RE.search(line):
            findings.append(f"{lineno}: full-width parentheses")
        if formatter.JA_ASCII_RE.search(line):
            findings.append(f"{lineno}: missing space")
        if formatter.PUNCT_SPACE_RE.search(line):
            findings.append(f"{lineno}: space after punctuation")
    if bold >= formatter.BOLD_LIMIT:
        findings.append(f"{bold} bold spans")
    return findings


class FlagsViolations(unittest.TestCase):
    def test_full_width_parentheses(self):
        self.assertEqual(
            ["3: full-width parentheses"], check("# h\n\n全角括弧（テスト）。\n")
        )

    def test_japanese_touching_ascii(self):
        self.assertEqual(["3: missing space"], check("# h\n\nScannerが返す値。\n"))

    def test_space_after_japanese_punctuation(self):
        self.assertEqual(
            ["3: space after punctuation"], check("# h\n\n句読点の後に、 空白。\n")
        )

    def test_bold_past_the_limit(self):
        self.assertEqual(["3 bold spans"], check("**一** と **二** と **三**。\n"))


class AcceptsCompliantProse(unittest.TestCase):
    def test_half_width_parentheses(self):
        self.assertEqual([], check("半角括弧 (テスト) を使う。\n"))

    def test_spaced_ascii(self):
        self.assertEqual([], check("Scanner が返す値。\n"))

    def test_bold_within_the_limit(self):
        self.assertEqual([], check("**一つ目** と **二つ目** だけ。\n"))

    def test_punctuation_is_not_ascii_for_the_spacing_rule(self):
        self.assertEqual([], check("`Scanner`、`Reporter`。\n"))


class IgnoresMarkup(unittest.TestCase):
    def test_fenced_block_is_exempt(self):
        text = "文章。\n\n```php\n// 全角括弧（テスト）と Scannerが返す値\n```\n"
        self.assertEqual([], check(text))

    def test_bold_inside_a_fence_does_not_count(self):
        self.assertEqual([], check("```python\nd = {**a, **b, **c}\n```\n"))

    # Deleting a code span would join the text on either side and invent a
    # violation absent from the file. This is a regression the checks hit.
    def test_code_span_does_not_fabricate_adjacency(self):
        self.assertEqual([], check("値を返す。`Scanner` が受け取る。\n"))

    def test_code_span_touching_japanese_is_still_flagged(self):
        self.assertEqual(["1: missing space"], check("値を`Scanner`が受け取る。\n"))


class LineNumbers(unittest.TestCase):
    def test_reported_line_survives_a_fence(self):
        text = "# h\n\n```text\nx\n```\n\n全角括弧（テスト）。\n"
        self.assertEqual(["7: full-width parentheses"], check(text))


if __name__ == "__main__":
    unittest.main()
