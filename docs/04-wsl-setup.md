# 4 · WSL setup

## Install

```powershell
# Windows PowerShell, once
wsl --install -d Ubuntu
```

```bash
# inside Ubuntu
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
python3 --version          # needs 3.11 or newer
git clone https://github.com/cloudaigeni-cell/agentic-curator
cd agentic-curator
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
curator doctor
```

If Ubuntu ships Python 3.10: `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12 python3.12-venv`, then use `python3.12 -m venv .venv`.

## Where to keep the library

| Location | Path in WSL | Notes |
| --- | --- | --- |
| Linux home | `~/library` | Fastest. Use this while learning. |
| Windows drive | `/mnt/c/Users/<you>/...` | Works; file access is several times slower. |
| Google Drive for desktop | `/mnt/g/My Drive/...` | Mount first: `sudo mount -t drvfs G: /mnt/g`. Online-only files download when hashed. |

Keep the repository itself in the Linux home directory, not under `/mnt/c`.

## Keys

```bash
cp .env.example .env && chmod 600 .env
```

`.env` is in `.gitignore`. Never commit it.

For Google credentials without an API key:

```bash
sudo apt install -y google-cloud-cli     # or follow cloud.google.com/sdk/docs/install
gcloud auth application-default login
export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=us-central1
CURATOR_PROVIDER=gemini curator demo --fresh
```

## Viewing the 3D guide

```bash
explorer.exe docs\\architecture.html
```

## Common problems

| Symptom | Cause and fix |
| --- | --- |
| `Connection closed` on start | The server process could not import the package. Activate the venv and `pip install -e .` |
| `No module named mcp.server.mcpserver` | MCP SDK v1 is installed. `pip install -U "mcp>=2"` |
| Very slow run on `/mnt/c` | Expected. Copy a sample to `~/library` to iterate. |
| Years look wrong | Year comes from the filename, then modification time. Copies made by Windows reset the time. |
