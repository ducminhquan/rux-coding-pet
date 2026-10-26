---
name: rux-setup
description: Configure or diagnose this plugin's local Rux robot connection and project scope. Use for Rux companion setup, not ordinary coding work.
---

Locate this installed plugin's root (the folder with provider.json). Run `python3 <root>/scripts/rux_plugin.py doctor` first; it does not send robot commands.

Configure this provider only with `configure --serial <USB-serial-or-IP:5555> --project <absolute-project-path>`. Honor an explicitly requested all-project scope with `--all-projects`. Use the user's known ADB device and project; ask only if either cannot be established. `--adb <absolute-path>` handles GUI environments without adb in PATH.

Configuration is outside the plugin cache, independent of other providers. Each chat has its own metadata queue and heartbeat. Rux chooses which queue to follow; do not add a host-wide lock or choose another chat on the host. State updates coalesce on the robot and never replay obsolete motion history.

Installation does not change robot scenarios, voices or wireless ADB authorization. The companion must support rux-session-queues-v1. For Kiro, install hooks with `install-kiro --project <path> --flavor cli-v2|cli-v3|ide-v1` matching the installed harness; this creates only a Rux-owned definition and refuses to overwrite a different one. CLI v2 uses a separate rux-assistant agent; it does not replace the default agent.

Hooks must return `{}` and exit 0 even when the robot is offline. Never print prompt text, tool inputs, transcripts or assistant responses. Only session metadata, an explicit session title/project fallback, and a bounded tool-kind/basename activity label may reach the robot. Never forward raw commands or file contents. To disable this provider, use `disable`; use the robot's Stop control for immediate motor stop.
