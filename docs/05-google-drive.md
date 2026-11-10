# 5 · Pointing the agents at Google Drive

Agents call tools by name through `ctx.mcp`. They do not know whether the bytes are on a disk or in Drive. There are two ways to reach Drive.

## Option A — Drive for desktop, unchanged code (start here)

Install Google Drive for desktop on Windows, mount the drive letter in WSL, and run the bundled server on it:

```bash
sudo mkdir -p /mnt/g && sudo mount -t drvfs G: /mnt/g
curator run --library "/mnt/g/My Drive"          # plan only
```

Everything works as in the demo, including the reversible trash. Native Google Docs, Sheets and Slides appear as small `.gdoc` pointer files and are ignored; export them first if you want them compared.

## Option B — a Drive MCP server

Add a second connection in `runtime.py`:

```python
await registry.connect(ServerSpec(
    name="drive",
    command="npx",
    args=["-y", "<a Google Drive MCP server package>"],
    env={"GOOGLE_APPLICATION_CREDENTIALS": os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
         "PATH": os.environ["PATH"]},
))
print(registry.describe_for_prompt("drive"))     # see what it offers
```

Then write a thin adapter agent that maps the server's tools onto the same blackboard records (`path`, `size`, `modified`, `sha256`). Drive's API returns an `md5Checksum` for binary files, which serves as the exact-duplicate fingerprint without downloading anything.

Check three things on any third-party server before giving it write access: which OAuth scopes it requests, whether it offers trash rather than permanent delete, and who publishes it.

## What does not carry over

| Area | Reality |
| --- | --- |
| Google Photos | A separate library from Drive. Its API only lets an app see and manage media that the app itself created, so a third-party tool cannot list or delete your existing photos. Use Google Takeout to export, curate the export locally, and remove originals in the Photos app. |
| Permanent deletion | Keep it out of the agents. Trash, review, then empty the trash yourself. |
| Shared files | You can remove them from your view but not delete them; they do not use your quota. Filter to files you own. |
| Native Google files | No byte hash exists. Compare exported text instead. |

## Credentials

- OAuth client for a desktop app, scope `drive.metadata.readonly` while planning; add `drive` only when you are ready to trash.
- Store tokens outside the repository. `.env` and `*.json` credentials are ignored by git here, but check before each commit.
