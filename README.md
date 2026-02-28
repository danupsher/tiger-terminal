# Tiger Terminal

A modern terminal emulator for PowerPC Macs running Mac OS X Tiger (10.4).

Built with Python 3.13 and Tk, Tiger Terminal brings a usable, feature-rich terminal to vintage Mac hardware that Apple left behind.

## Features

- **Canvas-based rendering** — smooth, flicker-free drawing
- **256-color support** — ANSI colors, 256-color palette, and RGB true color
- **VT100/xterm emulation** — works with vim, tmux, htop, and more
- **Tabbed interface** — Cmd+T for new tabs, Cmd+1-9 to switch
- **Copy/paste** — mouse selection, Cmd+C/V
- **Scrollback** — mouse wheel and Shift+PageUp/PageDown
- **Font resizing** — Cmd+Plus/Minus
- **Mouse tracking** — SGR and X10 modes for vim, tmux, etc.
- **Catppuccin Mocha** color scheme

## Requirements

- PowerPC Mac (G4 or G5)
- Mac OS X 10.4 Tiger
- No other dependencies — Python is bundled in the .app

## Install

1. Download `TigerTerminal.dmg` from [Releases](https://github.com/danupsher/tiger-terminal/releases)
2. Open the DMG
3. Drag `TigerTerminal.app` to `/Applications`
4. Double-click to launch

## Screenshots

*Coming soon*

## Building from Source

If you want to build the .app yourself:

1. Install Python 3.13 on your PPC Mac (see [tiger-ppc-builds](https://github.com/danupsher/tiger-ppc-builds))
2. Clone this repo to your Mac
3. Run the build script:

```bash
cd tiger-terminal
chmod +x build_app.sh
./build_app.sh
```

The built `.app` bundle will be at `/tmp/tigerterminal-build/TigerTerminal.app`.

## Architecture

```
TigerTerminal.app/Contents/MacOS/
├── TigerTerm          C launcher (resolves bundle paths, execs Python)
├── python3.13         PPC Python binary (~29MB)
├── terminal/
│   ├── terminal_app.py    Main app — window, tabs, keyboard handling
│   ├── screen.py          Terminal screen buffer + state machine
│   ├── renderer.py        Canvas-based cell renderer
│   ├── vt_parser.py       VT100/xterm escape sequence parser
│   └── pty_shell.py       PTY/fork shell management
└── lib/python3.13/        Pruned stdlib (~55MB)
```

The C launcher sets `PYTHONHOME` relative to the bundle, making the app fully self-contained and relocatable.

## Source Files

| File | Lines | Description |
|------|-------|-------------|
| `terminal_app.py` | ~530 | Main app, window management, tabs, keyboard |
| `screen.py` | ~700 | Screen buffer, cursor, scrollback, attributes |
| `renderer.py` | ~520 | Canvas drawing, selection, font metrics |
| `vt_parser.py` | ~200 | ANSI/VT escape sequence parser |
| `pty_shell.py` | ~90 | PTY allocation and shell process |
| `launcher.c` | ~50 | Bundle-relative path resolution |

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Cmd+T | New tab |
| Cmd+W | Close tab |
| Cmd+1-9 | Switch to tab N |
| Cmd+C | Copy selection |
| Cmd+V | Paste |
| Cmd++ | Increase font size |
| Cmd+- | Decrease font size |
| Shift+PageUp | Scroll up |
| Shift+PageDown | Scroll down |

## License

MIT
