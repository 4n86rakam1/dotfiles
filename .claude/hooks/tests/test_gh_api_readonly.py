import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "gh_api_readonly.py"


def run_hook(command: str) -> dict | None:
    event = {"tool_name": "Bash", "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        check=True,
    )
    if not proc.stdout.strip():
        return None
    return json.loads(proc.stdout)


class AllowsReadOnly(unittest.TestCase):
    def assertAllowed(self, command: str) -> None:
        self.assertIsNone(run_hook(command), f"unexpectedly denied: {command}")

    def test_plain_get(self):
        self.assertAllowed("gh api repos/o/r")

    def test_jq_pipe_inside_quotes(self):
        self.assertAllowed("gh api repos/o/r --jq '.[] | .name'")

    def test_awk_field_separator_downstream_of_pipe(self):
        self.assertAllowed("gh api repos/o/r/issues --paginate | awk -F, '{print $1}'")

    def test_git_commit_message_file_after_and(self):
        self.assertAllowed(
            "gh api repos/o/r > /tmp/x.json && git commit -F /tmp/msg.txt"
        )

    def test_grep_fixed_strings_downstream(self):
        self.assertAllowed("gh api repos/o/r | grep -F 'needle'")

    def test_sort_field_flag_downstream(self):
        self.assertAllowed("gh api repos/o/r | sort -f; echo done")

    def test_apostrophe_in_unrelated_text(self):
        self.assertAllowed("gh api repos/o/r --jq .name # gh's endpoint")

    def test_non_gh_command_upstream(self):
        self.assertAllowed("cat data.csv | awk -F, '{print}' ; gh api repos/o/r")

    def test_wrapping_command_flags_are_not_ghs(self):
        self.assertAllowed("curl -X POST https://x/$(gh api repos/o/r --jq .url)")

    def test_flag_inside_trailing_comment(self):
        self.assertAllowed("gh api repos/o/r --jq '.description' # use -f later")

    def test_quoted_mention_is_not_an_invocation(self):
        self.assertAllowed('git commit -m "call gh api with -F later"')


class DeniesWrites(unittest.TestCase):
    def assertDenied(self, command: str) -> None:
        result = run_hook(command)
        if result is None:
            self.fail(f"unexpectedly allowed: {command}")
        decision = result["hookSpecificOutput"]["permissionDecision"]
        self.assertEqual(decision, "deny")

    def test_method_flag_spaced(self):
        self.assertDenied("gh api -X POST repos/o/r/issues")

    def test_method_flag_concatenated(self):
        self.assertDenied("gh api -XPOST repos/o/r/issues")

    def test_long_method_flag_with_equals(self):
        self.assertDenied("gh api --method=DELETE repos/o/r")

    def test_raw_field_spaced(self):
        self.assertDenied("gh api repos/o/r/issues -f title=x")

    def test_raw_field_concatenated(self):
        self.assertDenied("gh api repos/o/r/issues -ftitle=x")

    def test_typed_field(self):
        self.assertDenied("gh api repos/o/r/issues -F number=1")

    def test_long_field_flag(self):
        self.assertDenied("gh api --field a=b repos/o/r")

    def test_input_file(self):
        self.assertDenied("gh api repos/o/r --input body.json")

    def test_graphql_subcommand(self):
        self.assertDenied("gh api graphql -f query='{viewer{login}}'")

    def test_write_in_second_segment_of_chain(self):
        self.assertDenied("echo hi && gh api -X POST repos/o/r")

    def test_write_downstream_of_pipe(self):
        self.assertDenied("cat body.json | gh api repos/o/r --input -")

    def test_unbalanced_quotes_fall_back_to_whole_command_scan(self):
        self.assertDenied("gh api repos/o/r -f 'unterminated")

    def test_double_space_between_gh_and_api(self):
        self.assertDenied("gh  api -X POST repos/o/r/issues")

    def test_tab_between_gh_and_api(self):
        self.assertDenied("gh\tapi -X POST repos/o/r/issues")

    def test_line_continuation_between_gh_and_api(self):
        self.assertDenied("gh \\\n  api -X POST repos/o/r/issues")

    def test_single_quoted_method_value(self):
        self.assertDenied("gh api -X 'POST' repos/o/r/issues")

    def test_double_quoted_method_value(self):
        self.assertDenied('gh api -X "POST" repos/o/r/issues')

    def test_long_method_flag_with_quoted_value(self):
        self.assertDenied("gh api --method='POST' repos/o/r")

    def test_method_flag_with_equals_and_no_space(self):
        self.assertDenied("gh api -X=POST repos/o/r")

    def test_quoted_method_value_after_the_path(self):
        self.assertDenied("gh api repos/o/r -X 'DELETE'")

    def test_write_inside_command_substitution(self):
        self.assertDenied("echo $(gh api -X POST repos/o/r)")

    def test_ansi_c_quoted_method_value(self):
        self.assertDenied("gh api -X$'POST' repos/o/r")


if __name__ == "__main__":
    unittest.main()
