"""Notification hook: notify-send on non-WSL Linux, PowerShell WinRT toast on
WSL. Failures are logged silently to ~/.claude/hooks-notify.log."""

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

TITLE = "Claude Code"
LOG_PATH = Path.home() / ".claude" / "hooks-notify.log"
TIMEOUT_MS = 5000
# Unregistered AppIds cause Windows to silently drop the toast; borrow the
# well-known Windows PowerShell AppId so the notifier is treated as registered.
POWERSHELL_APP_ID = (
    r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
)
NOTIFY_SEND_TIMEOUT_SEC = 5
POWERSHELL_TIMEOUT_SEC = 10
LINUX_DEFAULT_SOUND = "message"
LINUX_SOUND_BY_TYPE = {
    "permission_prompt": "complete",
    "idle_prompt": "message",
}
WINRT_DEFAULT_SOUND = "ms-winsoundevent:Notification.Default"
WINRT_SOUND_BY_TYPE = {
    "permission_prompt": "ms-winsoundevent:Notification.IM",
    "idle_prompt": "ms-winsoundevent:Notification.Reminder",
}


def _detect_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text(errors="ignore").lower()
    except OSError:
        return False


# On WSL, notify-send + libnotify-bin can exit 0 while silently failing, so the
# fallback never runs. Skip notify-send entirely and go straight to PowerShell.
IS_WSL = _detect_wsl()


def log_failure(reason: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{ts} {reason}\n")
    except OSError:
        pass


def try_notify_send(body: str, sound_name: str) -> bool:
    try:
        result = subprocess.run(
            [
                "notify-send",
                "-t",
                str(TIMEOUT_MS),
                f"--hint=string:sound-name:{sound_name}",
                TITLE,
                body,
            ],
            capture_output=True,
            timeout=NOTIFY_SEND_TIMEOUT_SEC,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")[:200]
        log_failure(f"notify-send rc={result.returncode} stderr={stderr!r}")
        return False
    return True


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def try_powershell_toast(body: str, sound_uri: str) -> bool:
    # PowerShell 5.1 does not auto-load WinRT assemblies, so explicitly load
    # XmlDocument and ToastNotification. Use ::new() rather than New-Object to
    # ensure the WinRT constructor resolves correctly.
    ps_script = (
        "[Windows.UI.Notifications.ToastNotificationManager,"
        "Windows.UI.Notifications,ContentType=WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument,"
        "Windows.Data.Xml.Dom,ContentType=WindowsRuntime] > $null;"
        "[Windows.UI.Notifications.ToastNotification,"
        "Windows.UI.Notifications,ContentType=WindowsRuntime] > $null;"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f'$xml.LoadXml(\'<toast><visual><binding template="ToastGeneric">'
        f"<text>{_escape_xml(TITLE)}</text>"
        f"<text>{_escape_xml(body)}</text>"
        "</binding></visual>"
        f'<audio src="{_escape_xml(sound_uri)}"/>'
        "</toast>');"
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
        "[Windows.UI.Notifications.ToastNotificationManager]"
        f"::CreateToastNotifier('{POWERSHELL_APP_ID}').Show($toast)"
    )
    encoded = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-EncodedCommand", encoded],
            capture_output=True,
            timeout=POWERSHELL_TIMEOUT_SEC,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")[:200]
        log_failure(f"powershell rc={result.returncode} stderr={stderr!r}")
        return False
    return True


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    body = str(event.get("message") or "").strip() or "Notification"
    notif_type = event.get("notification_type", "")
    linux_sound = LINUX_SOUND_BY_TYPE.get(notif_type, LINUX_DEFAULT_SOUND)
    winrt_sound = WINRT_SOUND_BY_TYPE.get(notif_type, WINRT_DEFAULT_SOUND)

    if not IS_WSL and try_notify_send(body, linux_sound):
        return
    if try_powershell_toast(body, winrt_sound):
        return
    log_failure(f"notification failed: {body!r}")


if __name__ == "__main__":
    main()
