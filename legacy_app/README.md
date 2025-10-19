Legacy Realms Client Binary

Overview
- This folder contains `realms.exe`, a legacy Windows client binary historically used for connecting to Realms of Despair.
- The binary is provided for archival/reference purposes only. The modern Python client in this repository supersedes it.

Known Details
- File: `realms.exe`
- Size (as tracked in repo): approximately 292–300 KB
- Platform: Windows (16/32‑bit era heritage; runs on modern Windows via compatibility settings in many cases)
- Purpose: Telnet‑based MUD client tailored for Realms of Despair

Usage Notes
- There is no supported source code for this binary in this repository.
- Modern replacements: use `modern_realms_client.py` (and packaged builds) from the root of this project.
- This binary is not built or shipped by the current build scripts. It is retained only for historical compatibility/testing.

Security/Compatibility
- Do not run untrusted binaries from unknown sources. Keep this for historical comparison only.
- Prefer the current Python client for ongoing use. It supports ANSI, NAWS, TTYPE and other RoD‑friendly features and is portable across platforms.

