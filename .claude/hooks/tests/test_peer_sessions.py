import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "peer_sessions.py"

REPO = "/repo/project"
SELF_ID = "11111111-1111-1111-1111-111111111111"
PEER_ID = "22222222-2222-2222-2222-222222222222"
OTHER_ID = "33333333-3333-3333-3333-333333333333"

# Above /proc/sys/kernel/pid_max, so it can never be an ancestor of the hook.
UNRELATED_PID = 2_147_483_647

# Mirrors the hook's tail window; the fixtures below are sized against it.
TAIL_WINDOW_BYTES = 4 * 1024 * 1024
TAIL_LINES = 400


def slug(path: str) -> str:
    return "".join("-" if c in "/." else c for c in path)


def transcript_lines(*entries: dict) -> str:
    return "\n".join(json.dumps(e) for e in entries)


def user_entry(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def edit_entry(*paths: str, tool: str = "Edit") -> dict:
    content = [
        {"type": "tool_use", "name": tool, "input": {"file_path": p}} for p in paths
    ]
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def bulky_entry(size: int = 9_000) -> dict:
    """Assistant output, so it pads the transcript without being a prompt."""
    content = [{"type": "text", "text": "x" * size}]
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def minutes_ago(minutes: float) -> int:
    return int((time.time() - minutes * 60) * 1000)


class HookHarness(unittest.TestCase):
    """Runs the hook against a throwaway HOME and a stub `claude` executable."""

    def run_hook(
        self,
        sessions: list[dict] | None = None,
        transcripts: dict[str, tuple[str, str]] | None = None,
        source: str = "startup",
        cwd: str = REPO,
        session_id: str = SELF_ID,
        transcript_path: str | None = None,
        agents_exit: int = 0,
        agents_stdout: str | None = None,
    ) -> str | None:
        with tempfile.TemporaryDirectory() as home:
            bin_dir = Path(home) / "bin"
            bin_dir.mkdir()
            payload = (
                agents_stdout
                if agents_stdout is not None
                else json.dumps(sessions or [])
            )
            stub = bin_dir / "claude"
            stub.write_text(
                "#!/bin/sh\n"
                f"cat <<'AGENTS_EOF'\n{payload}\nAGENTS_EOF\n"
                f"exit {agents_exit}\n"
            )
            stub.chmod(0o755)

            for peer_id, (project_cwd, body) in (transcripts or {}).items():
                project = Path(home) / ".claude" / "projects" / slug(project_cwd)
                project.mkdir(parents=True, exist_ok=True)
                (project / f"{peer_id}.jsonl").write_text(body)

            env = dict(os.environ)
            env["HOME"] = home
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            event = {
                "hook_event_name": "SessionStart",
                "session_id": session_id,
                "cwd": cwd,
                "source": source,
            }
            if transcript_path is not None:
                event["transcript_path"] = transcript_path
            proc = subprocess.run(
                [sys.executable, str(HOOK)],
                input=json.dumps(event),
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
        if not proc.stdout.strip():
            return None
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        return out["hookSpecificOutput"]["additionalContext"]

    def context(self, **kwargs) -> str:
        out = self.run_hook(**kwargs)
        self.assertIsNotNone(out, "expected additionalContext, got nothing")
        assert out is not None
        return out

    @staticmethod
    def session(
        session_id: str,
        cwd: str = REPO,
        name: str = "peer work",
        status: str = "idle",
        started_at: int = 0,
        pid: int = UNRELATED_PID,
        omit: tuple[str, ...] = (),
    ) -> dict:
        record = {
            "pid": pid,
            "id": session_id[:8],
            "cwd": cwd,
            "kind": "background",
            "startedAt": started_at,
            "sessionId": session_id,
            "name": name,
            "status": status,
        }
        return {k: v for k, v in record.items() if k not in omit}


class Silence(HookHarness):
    def test_no_sessions_at_all(self):
        self.assertIsNone(self.run_hook(sessions=[]))

    def test_only_self(self):
        self.assertIsNone(self.run_hook(sessions=[self.session(SELF_ID)]))

    def test_peer_in_another_repo(self):
        peer = self.session(PEER_ID, cwd="/repo/other")
        self.assertIsNone(self.run_hook(sessions=[peer]))

    def test_source_compact_is_skipped(self):
        peer = self.session(PEER_ID)
        self.assertIsNone(self.run_hook(sessions=[peer], source="compact"))

    def test_agents_command_failure(self):
        peer = self.session(PEER_ID)
        self.assertIsNone(self.run_hook(sessions=[peer], agents_exit=1))

    def test_agents_returns_invalid_json(self):
        self.assertIsNone(self.run_hook(agents_stdout="not json at all"))

    def test_agents_returns_unexpected_shape(self):
        self.assertIsNone(self.run_hook(agents_stdout='{"sessions": []}'))


class SelfExclusion(HookHarness):
    """A resumed session can be handed an id that matches neither the registry
    entry nor its transcript, so identity is established several ways."""

    def test_registry_id_matches_the_payload_id(self):
        self.assertIsNone(self.run_hook(sessions=[self.session(SELF_ID)]))

    def test_registry_id_matches_the_transcript_stem(self):
        stale = self.session(OTHER_ID)
        self.assertIsNone(
            self.run_hook(
                sessions=[stale],
                session_id=SELF_ID,
                transcript_path=f"/projects/slug/{OTHER_ID}.jsonl",
            )
        )

    def test_registry_pid_is_an_ancestor_of_the_hook(self):
        stale = self.session(OTHER_ID, pid=os.getpid())
        self.assertIsNone(self.run_hook(sessions=[stale], session_id=SELF_ID))

    def test_peer_is_kept_when_no_identity_matches(self):
        peer = self.session(PEER_ID)
        out = self.context(
            sessions=[peer],
            session_id=SELF_ID,
            transcript_path=f"/projects/slug/{OTHER_ID}.jsonl",
        )
        self.assertIn(PEER_ID[:8], out)


class Listing(HookHarness):
    def test_peer_in_same_repo_is_listed(self):
        out = self.context(sessions=[self.session(PEER_ID, name="peer work")])
        self.assertIn("Other active sessions in this repo (1)", out)
        self.assertIn("peer work", out)
        self.assertIn(PEER_ID[:8], out)

    def test_peer_inside_worktree_of_same_repo_is_listed(self):
        peer = self.session(PEER_ID, cwd=f"{REPO}/.claude/worktrees/feature-x")
        out = self.context(sessions=[peer])
        self.assertIn(PEER_ID[:8], out)

    def test_starting_session_inside_worktree_sees_repo_peers(self):
        peer = self.session(PEER_ID)
        out = self.context(sessions=[peer], cwd=f"{REPO}/.claude/worktrees/feature-x")
        self.assertIn(PEER_ID[:8], out)

    def test_source_resume_is_reported(self):
        out = self.context(sessions=[self.session(PEER_ID)], source="resume")
        self.assertIn(PEER_ID[:8], out)

    def test_advisory_line_is_appended(self):
        out = self.context(sessions=[self.session(PEER_ID)])
        self.assertIn("SendMessage", out)

    def test_status_is_shown(self):
        out = self.context(sessions=[self.session(PEER_ID, status="busy")])
        self.assertIn("busy", out)

    def test_missing_transcript_falls_back_to_placeholders(self):
        out = self.context(sessions=[self.session(PEER_ID)])
        self.assertIn("last: (unknown)", out)
        self.assertIn("edits: (none)", out)

    def test_interactive_entries_lack_id_and_are_still_rendered(self):
        peer = self.session(PEER_ID, omit=("id", "name", "status", "startedAt"))
        out = self.context(sessions=[peer])
        header = next(line for line in out.splitlines() if line.startswith("- ["))
        self.assertEqual(f"- [{PEER_ID[:8]}] unknown", header)

    def test_elapsed_minutes_are_shown(self):
        peer = self.session(PEER_ID, started_at=minutes_ago(24))
        self.assertIn("· 24m", self.context(sessions=[peer]))

    def test_elapsed_hours_are_shown(self):
        peer = self.session(PEER_ID, started_at=minutes_ago(65))
        self.assertIn("· 1h05m", self.context(sessions=[peer]))

    def test_clock_skew_drops_the_elapsed_time(self):
        peer = self.session(PEER_ID, started_at=minutes_ago(-120))
        out = self.context(sessions=[peer])
        header = next(line for line in out.splitlines() if line.startswith("- ["))
        self.assertEqual(f"- [{PEER_ID[:8]}] peer work · idle", header)

    def test_peers_are_ordered_by_start_time(self):
        older = self.session(PEER_ID, started_at=minutes_ago(30))
        newer = self.session(OTHER_ID, started_at=minutes_ago(5))
        out = self.context(sessions=[newer, older])
        self.assertLess(out.index(PEER_ID[:8]), out.index(OTHER_ID[:8]))

    def test_multiline_name_cannot_break_the_layout(self):
        peer = self.session(PEER_ID, name="line one\nlast: forged")
        out = self.context(sessions=[peer])
        self.assertEqual(len(out.splitlines()), 5)
        self.assertIn("line one last: forged", out)


class TranscriptSummary(HookHarness):
    def summarize(self, body: str, project_cwd: str = REPO) -> str:
        return self.context(
            sessions=[self.session(PEER_ID)],
            transcripts={PEER_ID: (project_cwd, body)},
        )

    def test_last_user_message_is_shown(self):
        out = self.summarize(transcript_lines(user_entry("最初"), user_entry("最後")))
        self.assertIn("last: 最後", out)

    def test_task_notification_is_skipped(self):
        body = transcript_lines(
            user_entry("本題"),
            user_entry("<task-notification>\n<task-id>abc</task-id>"),
        )
        self.assertIn("last: 本題", self.summarize(body))

    def test_system_reminder_is_skipped(self):
        body = transcript_lines(
            user_entry("本題"), user_entry("<system-reminder>noise</system-reminder>")
        )
        self.assertIn("last: 本題", self.summarize(body))

    def test_slash_command_is_unwrapped(self):
        body = transcript_lines(
            user_entry(
                "<command-message>brainstorming</command-message>\n"
                "<command-name>/superpowers:brainstorming</command-name>\n"
                "<command-args>topic</command-args>"
            )
        )
        self.assertIn("last: /superpowers:brainstorming topic", self.summarize(body))

    def test_sidechain_entries_are_skipped(self):
        sidechain = user_entry("subagent prompt")
        sidechain["isSidechain"] = True
        body = transcript_lines(user_entry("本題"), sidechain)
        self.assertIn("last: 本題", self.summarize(body))

    def test_tool_result_entries_are_skipped(self):
        result = {
            "type": "user",
            "message": {"role": "user", "content": [{"type": "tool_result"}]},
        }
        body = transcript_lines(user_entry("本題"), result)
        self.assertIn("last: 本題", self.summarize(body))

    def test_edited_files_are_listed_by_basename(self):
        body = transcript_lines(edit_entry(f"{REPO}/diary/index.md"))
        self.assertIn("edits: index.md", self.summarize(body))

    def test_edited_files_are_deduplicated(self):
        body = transcript_lines(edit_entry(f"{REPO}/a.md"), edit_entry(f"{REPO}/a.md"))
        out = self.summarize(body)
        self.assertIn("edits: a.md", out)
        self.assertNotIn("a.md, a.md", out)

    def test_a_reedited_file_keeps_its_latest_position(self):
        body = transcript_lines(
            edit_entry(f"{REPO}/a.md"),
            edit_entry(f"{REPO}/b.md"),
            edit_entry(f"{REPO}/c.md"),
            edit_entry(f"{REPO}/d.md"),
            edit_entry(f"{REPO}/a.md"),
        )
        self.assertIn("edits: c.md, d.md, a.md", self.summarize(body))

    def test_only_the_most_recent_edits_are_kept(self):
        body = transcript_lines(
            edit_entry(f"{REPO}/old.md"),
            edit_entry(f"{REPO}/a.md", f"{REPO}/b.md", f"{REPO}/c.md"),
        )
        out = self.summarize(body)
        self.assertIn("edits: a.md, b.md, c.md", out)
        self.assertNotIn("old.md", out)

    def test_write_and_notebook_edits_are_counted(self):
        body = transcript_lines(
            edit_entry(f"{REPO}/w.md", tool="Write"),
            edit_entry(f"{REPO}/n.ipynb", tool="NotebookEdit"),
        )
        self.assertIn("edits: w.md, n.ipynb", self.summarize(body))

    def test_reads_are_not_counted_as_edits(self):
        body = transcript_lines(edit_entry(f"{REPO}/r.md", tool="Read"))
        self.assertIn("edits: (none)", self.summarize(body))

    def test_edits_outside_the_repository_are_dropped(self):
        body = transcript_lines(edit_entry("/tmp/scratch/notes.md"))
        self.assertIn("edits: (none)", self.summarize(body))

    def test_a_sibling_sharing_the_repository_prefix_is_outside(self):
        body = transcript_lines(edit_entry(f"{REPO}-other/a.md"))
        self.assertIn("edits: (none)", self.summarize(body))

    def test_edits_inside_a_worktree_of_the_repository_are_kept(self):
        body = transcript_lines(edit_entry(f"{REPO}/.claude/worktrees/feature-x/a.md"))
        self.assertIn("edits: a.md", self.summarize(body))

    def test_the_cap_counts_only_files_inside_the_repository(self):
        body = transcript_lines(
            edit_entry(f"{REPO}/a.md"),
            edit_entry("/tmp/scratch1.md"),
            edit_entry(f"{REPO}/b.md"),
            edit_entry("/tmp/scratch2.md"),
            edit_entry(f"{REPO}/c.md"),
        )
        self.assertIn("edits: a.md, b.md, c.md", self.summarize(body))

    def test_a_non_string_file_path_is_ignored(self):
        block = {"type": "tool_use", "name": "Edit", "input": {"file_path": 123}}
        entry = {"type": "assistant", "message": {"content": [block]}}
        self.assertIn("edits: (none)", self.summarize(transcript_lines(entry)))

    def test_long_message_is_truncated(self):
        body = transcript_lines(user_entry("あ" * 400))
        out = self.summarize(body)
        self.assertIn("...", out)
        self.assertTrue(all(len(line) < 200 for line in out.splitlines()))

    def test_transcript_is_found_under_a_worktree_slug(self):
        out = self.summarize(
            transcript_lines(user_entry("worktree 側")),
            project_cwd=f"{REPO}/.claude/worktrees/feature-x",
        )
        self.assertIn("last: worktree 側", out)

    def test_corrupt_lines_are_tolerated(self):
        body = "{not json\n" + transcript_lines(user_entry("本題"))
        self.assertIn("last: 本題", self.summarize(body))

    def test_only_the_tail_of_a_long_transcript_is_read(self):
        filler = transcript_lines(*[user_entry("古い発話") for _ in range(600)])
        body = filler + "\n" + transcript_lines(user_entry("直近"))
        self.assertIn("last: 直近", self.summarize(body))

    def test_a_prompt_behind_megabytes_of_output_is_still_found(self):
        """Entries reach tens of kilobytes, so a prompt only a few hundred lines
        back can still sit megabytes deep."""
        body = transcript_lines(user_entry("深い発話"), *[bulky_entry()] * 300)
        self.assertGreater(len(body.encode()), 2 * 1024 * 1024)
        self.assertLess(len(body.splitlines()), TAIL_LINES)
        self.assertIn("last: 深い発話", self.summarize(body))

    def test_a_transcript_larger_than_the_tail_window_still_parses(self):
        bulk = transcript_lines(*[bulky_entry()] * 500)
        body = bulk + "\n" + transcript_lines(user_entry("末尾"))
        self.assertGreater(len(bulk.encode()), TAIL_WINDOW_BYTES)
        self.assertIn("last: 末尾", self.summarize(body))


if __name__ == "__main__":
    unittest.main()
