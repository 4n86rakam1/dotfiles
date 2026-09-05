"""Checks for the Bash command classifier. Run with `python3 -m unittest discover`."""

import importlib.util
import os
import unittest

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit.py")
_SPEC = importlib.util.spec_from_file_location("tool_mix_audit", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load {_PATH}")
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


def families(command):
    counts, _ = audit.classify_bash(command)
    return {name: value for name, value in counts.items() if value}


def kinds(command):
    _, seen = audit.classify_bash(command)
    return {name: value for name, value in seen.items() if value}


class FamilyCounts(unittest.TestCase):
    """One operation per family per segment. These counts pin the reported rates."""

    CASES = [
        ("cat foo.py", {"read": 1}),
        ("cat", {}),
        ("cat a.md b.md", {"read": 1}),
        ("head -50 src/main.py", {"read": 1}),
        ("sed -n '1,200p' a.txt", {"read": 1}),
        ("sed -i 's/a/b/' a.txt", {"edit": 1}),
        ("tail -f app.log", {"read": 1}),
        ("grep -rn TODO src/", {"search": 1}),
        ("grep -rn TODO", {"search": 1}),
        ("ls -la", {"search": 1}),
        ("find . -name '*.py'", {"search": 1}),
        ("tee out.txt", {"edit": 1}),
        ("cat a.txt > b.txt", {"read": 1, "edit": 1}),
        ("echo hi > notes.md", {"edit": 1}),
        ("cat a.txt && grep foo b.txt", {"read": 1, "search": 1}),
        ("sudo cat /etc/hosts", {"read": 1}),
        ("wc -l a.txt", {}),
    ]

    def test_counts(self):
        for command, expected in self.CASES:
            with self.subTest(command=command):
                self.assertEqual(families(command), expected)


class NotFileAccess(unittest.TestCase):
    """Things that look like file access but are not."""

    CASES = [
        # A pipe stage with no path of its own is filtering, not reading.
        ("git log | head -40", {}),
        ("ls | head -3", {"search": 1}),
        ("docker ps | grep foo", {}),
        ("grep -E 'inet' ", {}),
        # Another machine's filesystem.
        ("timeout 20 ssh remote-host 'cat /etc/hosts'", {}),
        # An interpreter's file access cannot be read off the command line.
        ("python3 - <<'EOF'\ncat x\nEOF", {}),
        # Scratch space is not the user's files.
        ("echo hi > /tmp/x", {}),
        ("cmd 2>/dev/null", {}),
    ]

    def test_counts(self):
        for command, expected in self.CASES:
            with self.subTest(command=command):
                self.assertEqual(families(command), expected)


class MultiLineCommands(unittest.TestCase):
    """A newline ends a command; shlex alone would fuse every line into one."""

    def test_each_line_is_its_own_command(self):
        self.assertEqual(families("cd /tmp\ncat a.md\ncat b.md"), {"read": 2})

    def test_family_is_not_inherited_from_the_previous_line(self):
        self.assertEqual(families("ls -la\ncat notes.md"), {"search": 1, "read": 1})
        self.assertEqual(
            audit.bash_file_targets("ls -la\ncat notes.md"), [("read", "notes.md")]
        )

    def test_a_backslash_continues_the_line(self):
        self.assertEqual(families("cat \\\n  a.md"), {"read": 1})

    def test_a_quoted_newline_stays_inside_its_argument(self):
        self.assertEqual(families("ssh remote-host 'cat /etc/hosts\nuptime'"), {})


class Wrappers(unittest.TestCase):
    """Wrappers with positional or valued arguments must not become the command."""

    CASES = [
        ("timeout 30 cat foo.md", {"read": 1}),
        ("timeout -k 5 30 cat foo.md", {"read": 1}),
        ("sudo -u maya cat /etc/hosts", {"read": 1}),
        ("nice -n 10 cat foo.md", {"read": 1}),
        ("env FOO=1 cat foo.md", {"read": 1}),
    ]

    def test_counts(self):
        for command, expected in self.CASES:
            with self.subTest(command=command):
                self.assertEqual(families(command), expected)


class Heredocs(unittest.TestCase):
    def test_a_heredoc_write_is_not_a_read(self):
        command = "cat > out.md <<'EOF'\nbody\nEOF"
        self.assertEqual(families(command), {"edit": 1})
        self.assertEqual(audit.bash_file_targets(command), [("edit", "out.md")])

    def test_the_body_is_not_parsed_as_commands(self):
        self.assertEqual(families("python3 - <<'EOF'\ncat /etc/passwd\nEOF"), {})


class Redirections(unittest.TestCase):
    def test_a_descriptor_is_not_an_operand(self):
        self.assertEqual(audit.bash_file_targets("cat a.md 2>&1"), [("read", "a.md")])

    def test_an_input_redirect_is_not_a_write(self):
        self.assertEqual(
            audit.bash_file_targets("tee out.md < in.md"), [("edit", "out.md")]
        )

    def test_append_and_clobber_forms_are_writes(self):
        self.assertEqual(families("echo hi >> notes.md"), {"edit": 1})
        self.assertEqual(families("echo hi &> notes.md"), {"edit": 1})


class LoggedPaths(unittest.TestCase):
    """Only concrete paths may reach the log; a command line can carry secrets."""

    def test_find_exec_arguments_are_not_paths(self):
        command = "find . -name '*.md' -exec grep -l sk-ant-SECRET {} +"
        self.assertEqual(audit.bash_file_targets(command), [])

    def test_find_keeps_its_leading_paths(self):
        self.assertEqual(
            audit.bash_file_targets("find src/ docs/ -name '*.md'"),
            [("search", "src/"), ("search", "docs/")],
        )

    def test_a_glob_is_not_a_resolved_path(self):
        self.assertFalse(audit.looks_like_path("*.md"))
        self.assertFalse(audit.looks_like_path("$HOME"))
        self.assertFalse(audit.looks_like_path("sk-ant-api03-SECRET"))
        self.assertTrue(audit.looks_like_path("src/main.py"))
        self.assertTrue(audit.looks_like_path("notes.md"))

    def test_a_word_boundary_starts_a_comment_but_a_path_does_not(self):
        self.assertEqual(
            audit.bash_file_targets("cat foo#1.md"), [("read", "foo#1.md")]
        )


class GlobMatching(unittest.TestCase):
    def test_a_rule_glob_matches_relative_to_the_project(self):
        self.assertTrue(audit.glob_matches(["**/*.md"], "/p/docs/a.md", "/p"))
        self.assertTrue(audit.glob_matches(["**/*.md"], "/p/a.md", "/p"))
        self.assertFalse(audit.glob_matches(["**/*.md"], "/p/a.sh", "/p"))

    def test_a_leading_slash_anchors_rather_than_absolutises(self):
        self.assertTrue(audit.glob_matches(["/**/*.sh"], "/p/bootstrap/x.sh", "/p"))

    def test_a_path_outside_the_project_never_matches(self):
        self.assertFalse(audit.glob_matches(["**/*.md"], "/other/a.md", "/p"))


class Robustness(unittest.TestCase):
    def test_unbalanced_quotes_are_reported_rather_than_raised(self):
        self.assertEqual(kinds("cat 'unterminated"), {"unparsed": 1})

    def test_an_unterminated_heredoc_terminates(self):
        self.assertEqual(families("cat <<'EOF'\nbody without a terminator"), {})

    def test_an_empty_command_is_not_an_operation(self):
        self.assertEqual(families(""), {})


if __name__ == "__main__":
    unittest.main()
