# Dated Notepad

A notebook with one page per day. Open it, write, close it — every day gets
its own plain Markdown file, named by date.

Built for Lubuntu/LXQt, works on any Linux desktop.

![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Why this exists

Journalling apps tend to lock your writing inside a database, a sync service,
or a proprietary format. This one writes **plain `.md` files you own**:

```
~/Documents/DatedNotepad/
├── 2026-09-09.md
├── 2026-09-10.md
└── 2026-09-11.md
```

You can `grep` them, edit them in any editor, sync them with anything, and read
them in twenty years without this app. If you uninstall it, your writing stays.

**It installs nothing.** No pip, no apt, no root — Python's standard library
plus the browser you already have.

## Features

- **A page per day**, created automatically. Today is always one click away.
- **Autosave** about a second after you stop typing. Also saves when you close
  the window, and `Ctrl+S` forces it.
- **Month-grouped sidebar** with word counts and a preview line per day.
- **Full-text search** across every note, with matching snippets.
- **Jump to any date** — prev/next day buttons and a date picker, past or
  future.
- **Live word and character count.**
- Emptying a note deletes its file, so you never accumulate blank days.

## Requirements

| Need | Why | Check |
|---|---|---|
| Python 3.8+ | Runs the local server | `python3 --version` |
| Chrome or Chromium | Renders the editor | `which google-chrome chromium` |

## Install

```bash
git clone <your-repo-url> dated-notepad
cd dated-notepad
./install.sh
```

The installer checks your Python, finds a browser, installs to
`~/.local/share/notepad/`, puts `notepad-dated` on your `PATH`, generates a
desktop entry with the right path for your machine, adds a desktop shortcut,
and creates the notes directory.

If `~/Documents/DatedNotepad` already exists with notes in it, the installer
leaves it completely alone — reinstalling is safe.

## Usage

| Command | Does |
|---|---|
| `notepad-dated` | Launch the notepad window |
| `notepad-dated --serve` | Run the server only; open the printed URL yourself |
| `notepad-dated --help` | Show this list |

Also available from your application menu and the desktop shortcut.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+S` | Save now |
| `Ctrl+D` | Jump to today |
| `Ctrl+F` | Search all notes |
| `Esc` | Clear search, back to the editor |

## Your notes

Stored as `~/Documents/DatedNotepad/YYYY-MM-DD.md`, UTF-8, one per day.

Because they are ordinary files:

```bash
# find every note mentioning a thing
grep -ril "invoice" ~/Documents/DatedNotepad/

# back them up
tar czf notes-backup.tar.gz ~/Documents/DatedNotepad/

# put them in their own git repo
cd ~/Documents/DatedNotepad && git init && git add . && git commit -m "notes"
```

Writes are **atomic** — the app writes a temporary file and renames it over the
target, so a crash mid-save can never leave a half-written note.

## How it works

```
  notepad-dated (bash)
      |
      |-- starts --> server.py          127.0.0.1, random port, random token
      |                 |               - GET  /api/notes   list days
      |                 |               - GET  /api/note    read one day
      |                 |               - POST /api/note    save one day
      |                 +-------------> - GET  /api/search  full text search
      |
      +-- opens ---> chrome --app=<url> chromeless window, own profile
```

Filenames are validated against a strict `YYYY-MM-DD` pattern and parsed as a
real date, then the resolved path is checked to be inside the notes directory —
so a crafted request cannot write outside it.

### Security model

Loopback-only bind, fresh random token per launch, required on every endpoint.
Not reachable from your network.

## Layout

```
.
├── app/
│   ├── server.py           # stdlib HTTP server, reads/writes the .md files
│   ├── notepad-dated       # launcher
│   └── static/index.html   # the whole UI, one file
├── desktop/
│   └── dated-notepad.desktop.in
├── docs/
├── install.sh
├── uninstall.sh
└── LICENSE
```

## Uninstall

```bash
./uninstall.sh
```

Removes the app and **keeps every note.** The uninstaller will not delete your
writing under any circumstances — if you want the notes gone, delete
`~/Documents/DatedNotepad` yourself, deliberately.

## Troubleshooting

**A note didn't save.**
Look at the status text top-right — it shows "Saved <time>" or the error. Check
that `~/Documents/DatedNotepad` is writable and the disk isn't full.

**The command isn't found.**
Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc`, open a new terminal.

**A server was left running.**
`pkill -f 'notepad/server.py'`

## License

MIT — see [LICENSE](LICENSE).
