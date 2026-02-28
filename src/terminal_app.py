#!/usr/bin/env python3
"""
Tiger Terminal v2 — Canvas-based terminal emulator.
Target: iMac G5 (PPC, Tiger 10.4, Tk 8.4, Python 3.13)
"""
import os
import sys
import threading
import ctypes
import ctypes.util
try:
    import tkinter as tk
except ImportError:
    import Tkinter as tk

from pty_shell import PTYShell
from vt_parser import VTParser
from screen import Screen
from renderer import CanvasRenderer


def _setup_mac_app():
    """Register as a foreground GUI app (only needed when run from CLI)."""
    if os.environ.get('TIGERTERM_BUNDLE'):
        return  # .app bundle already registered by Finder
    try:
        carbon = ctypes.CDLL(ctypes.util.find_library('Carbon'))
        PSN = ctypes.c_uint32 * 2
        psn = PSN(0, 2)
        carbon.TransformProcessType(psn, 1)
        carbon.SetFrontProcess(psn)
    except Exception:
        pass

_setup_mac_app()

# ── Colors ──
BG       = '#1e1e2e'
BG_DARK  = '#181825'
FG       = '#cdd6f4'
ACCENT   = '#89b4fa'
ACCENT2  = '#a6e3a1'
SURFACE0 = '#313244'
SURFACE1 = '#45475a'
OVERLAY  = '#6c7086'
TAB_BG   = '#181825'
TAB_SEL  = '#313244'

DEFAULT_COLS = 80
DEFAULT_ROWS = 24
FONT_FAMILY = 'Monaco'
FONT_SIZE = 13


class TerminalTab:
    """One terminal session: PTY + parser + screen + renderer."""

    def __init__(self, parent, app, cols=DEFAULT_COLS, rows=DEFAULT_ROWS):
        self.app = app
        self.cols = cols
        self.rows = rows
        self.parent = parent

        # Frame for this tab's content
        self.frame = tk.Frame(parent, bg=BG)

        # Screen model
        self.screen = Screen(cols, rows)
        self.screen.on_respond = self._pty_respond

        # Renderer
        self.renderer = CanvasRenderer(self.frame, self.screen,
                                       FONT_FAMILY, FONT_SIZE)

        # PTY
        self.shell = PTYShell(self._on_pty_output, cols=cols, rows=rows)

        # Parser
        self.parser = VTParser(self.screen)

        # Data queue (thread-safe: PTY thread → main thread)
        self._data_queue = []
        self._queue_lock = threading.Lock()

        # Render scheduling
        self._render_pending = False
        self._render_timer = None

        # Bind keyboard to the ROOT window (Canvas on Tk 8.4 Aqua
        # doesn't reliably receive key events even with focus)
        root = self.app.root
        root.bind('<Key>', self._on_key)
        root.bind('<KeyPress>', self._on_key)

        # Mouse events stay on canvas
        canvas = self.renderer.canvas
        canvas.bind('<Button-1>', self._on_click)
        canvas.bind('<B1-Motion>', self._on_drag)
        canvas.bind('<ButtonRelease-1>', self._on_release)
        canvas.bind('<MouseWheel>', self._on_mousewheel)
        canvas.bind('<Button-4>', self._on_scroll_up)
        canvas.bind('<Button-5>', self._on_scroll_down)

        # Start PTY
        self.shell.start()
        self.renderer.start_blink()

        # Start render timer
        self._schedule_render_timer()

    def show(self):
        self.frame.pack(fill='both', expand=True)

    def hide(self):
        self.frame.pack_forget()

    def destroy(self):
        self.renderer.stop_blink()
        if self._render_timer:
            try:
                self.frame.after_cancel(self._render_timer)
            except Exception:
                pass
        self.shell.stop()
        self.frame.destroy()

    # ── PTY I/O ──

    def _on_pty_output(self, data):
        """Called from PTY reader thread."""
        with self._queue_lock:
            self._data_queue.append(data)
        # Schedule processing on main thread
        try:
            self.frame.after_idle(self._process_queue)
        except Exception:
            pass

    def _pty_respond(self, data):
        """Send response data back to PTY (e.g., cursor position report)."""
        self.shell.write(data)

    def _process_queue(self):
        """Process all queued PTY data and render once."""
        with self._queue_lock:
            chunks = self._data_queue
            self._data_queue = []

        if not chunks:
            return

        # Snap to bottom on new output
        self.renderer.snap_to_bottom()

        # Parse all chunks
        for data in chunks:
            self.parser.feed(data)

        # Render
        self.renderer.render()

    def _schedule_render_timer(self):
        """Fallback 33ms timer to ensure rendering."""
        self._render_timer = self.frame.after(33, self._render_tick)

    def _render_tick(self):
        self._process_queue()
        # Check if shell died
        if not self.shell.is_alive:
            self.app.close_tab(self)
            return
        self._render_timer = self.frame.after(33, self._render_tick)

    # ── Keyboard input ──

    def _on_key(self, event):
        self.renderer.reset_blink()
        self.renderer.clear_selection()

        keysym = event.keysym
        state = event.state
        char = event.char

        # Detect modifier keys
        ctrl = bool(state & 0x4)
        meta = bool(state & 0x8) or bool(state & 0x80)  # Command on Mac
        shift = bool(state & 0x1)

        # Meta/Cmd shortcuts handled by app
        if meta:
            if keysym == 't':
                self.app.new_tab()
                return 'break'
            if keysym == 'w':
                self.app.close_tab(self)
                return 'break'
            if keysym == 'c':
                self.app.copy_selection(self)
                return 'break'
            if keysym == 'v':
                self.app.paste(self)
                return 'break'
            if keysym == 'plus' or keysym == 'equal':
                self.app.change_font_size(1)
                return 'break'
            if keysym == 'minus':
                self.app.change_font_size(-1)
                return 'break'
            for i in range(1, 10):
                if keysym == str(i):
                    self.app.switch_tab(i - 1)
                    return 'break'
            return 'break'

        # Arrow keys
        scr = self.screen
        if keysym in ('Up', 'Down', 'Right', 'Left'):
            if scr.app_cursor_keys:
                code = {'Up': 'A', 'Down': 'B', 'Right': 'C', 'Left': 'D'}[keysym]
                self.shell.write('\x1bO' + code)
            else:
                code = {'Up': 'A', 'Down': 'B', 'Right': 'C', 'Left': 'D'}[keysym]
                self.shell.write('\x1b[' + code)
            return 'break'

        # Function keys
        fkey_map = {
            'F1': '\x1bOP', 'F2': '\x1bOQ', 'F3': '\x1bOR', 'F4': '\x1bOS',
            'F5': '\x1b[15~', 'F6': '\x1b[17~', 'F7': '\x1b[18~', 'F8': '\x1b[19~',
            'F9': '\x1b[20~', 'F10': '\x1b[21~', 'F11': '\x1b[23~', 'F12': '\x1b[24~',
        }
        if keysym in fkey_map:
            self.shell.write(fkey_map[keysym])
            return 'break'

        # Special keys
        if keysym == 'Home':
            self.shell.write('\x1b[H')
            return 'break'
        if keysym == 'End':
            self.shell.write('\x1b[F')
            return 'break'
        if keysym == 'Insert':
            self.shell.write('\x1b[2~')
            return 'break'
        if keysym == 'Delete':
            self.shell.write('\x1b[3~')
            return 'break'
        if keysym == 'Prior':  # Page Up
            if shift:
                self.renderer.scroll_up(self.rows // 2)
                return 'break'
            self.shell.write('\x1b[5~')
            return 'break'
        if keysym == 'Next':  # Page Down
            if shift:
                self.renderer.scroll_down(self.rows // 2)
                return 'break'
            self.shell.write('\x1b[6~')
            return 'break'
        if keysym == 'BackSpace':
            self.shell.write('\x7f')
            return 'break'
        if keysym == 'Tab':
            self.shell.write('\t')
            return 'break'
        if keysym == 'Return':
            self.shell.write('\r')
            return 'break'
        if keysym == 'Escape':
            self.shell.write('\x1b')
            return 'break'

        # Ctrl+key
        if ctrl and len(keysym) == 1:
            ch = keysym.lower()
            if 'a' <= ch <= 'z':
                self.shell.write(chr(ord(ch) - ord('a') + 1))
                return 'break'
            if ch == '[':
                self.shell.write('\x1b')
                return 'break'
            if ch == '\\':
                self.shell.write('\x1c')
                return 'break'
            if ch == ']':
                self.shell.write('\x1d')
                return 'break'

        # Regular character
        if char and ord(char) >= 32:
            self.shell.write(char)
            return 'break'
        if char and 1 <= ord(char) <= 26:
            self.shell.write(char)
            return 'break'

        return 'break'

    # ── Mouse ──

    def _on_click(self, event):
        self.renderer.canvas.focus_set()
        row, col = self.renderer.pixel_to_cell(event.x, event.y)

        # Mouse tracking for apps like vim/tmux
        if self.screen.mouse_tracking:
            self._send_mouse(0, row, col, False)
            return

        self.renderer.start_selection(row, col)

    def _on_drag(self, event):
        if self.screen.mouse_tracking:
            if self.screen.mouse_tracking >= 1002:
                row, col = self.renderer.pixel_to_cell(event.x, event.y)
                self._send_mouse(32, row, col, False)
            return
        row, col = self.renderer.pixel_to_cell(event.x, event.y)
        self.renderer.update_selection(row, col)

    def _on_release(self, event):
        if self.screen.mouse_tracking:
            row, col = self.renderer.pixel_to_cell(event.x, event.y)
            self._send_mouse(0, row, col, True)
            return

    def _send_mouse(self, button, row, col, release):
        if self.screen.mouse_sgr:
            ch = 'm' if release else 'M'
            self.shell.write('\x1b[<{};{};{}{}'.format(button, col + 1, row + 1, ch))
        else:
            if release:
                button = 3
            self.shell.write('\x1b[M{}{}{}'.format(
                chr(32 + button), chr(32 + col + 1), chr(32 + row + 1)
            ))

    def _on_mousewheel(self, event):
        if event.delta > 0:
            self._on_scroll_up(event)
        else:
            self._on_scroll_down(event)

    def _on_scroll_up(self, event):
        if self.screen.mouse_tracking:
            row, col = self.renderer.pixel_to_cell(event.x, event.y)
            self._send_mouse(64, row, col, False)
            return
        self.renderer.scroll_up(3)

    def _on_scroll_down(self, event):
        if self.screen.mouse_tracking:
            row, col = self.renderer.pixel_to_cell(event.x, event.y)
            self._send_mouse(65, row, col, False)
            return
        self.renderer.scroll_down(3)

    # ── Resize ──

    def resize_grid(self, cols, rows):
        if cols == self.cols and rows == self.rows:
            return
        self.cols = cols
        self.rows = rows
        self.screen.resize(cols, rows)
        self.renderer.resize(cols, rows)
        self.shell.resize(rows, cols)


class TigerTerminal:
    """Main application window with tabs."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # hide until fully configured (prevents white flash)

        # Hide Tk console window (Aqua creates one for .app bundles)
        try:
            self.root.tk.call('console', 'hide')
        except Exception:
            pass
        self.root.title('Tiger Terminal')

        # Set Mac application menu name
        try:
            self.root.tk.call('tk', 'appname', 'Tiger Terminal')
        except Exception:
            pass

        # Force dark palette on Tk 8.4 / Aqua (overrides systemWindowBody)
        self.root.tk_setPalette(
            background=BG_DARK,
            foreground=FG,
            highlightBackground=BG_DARK,
            highlightColor=ACCENT,
            selectBackground=SURFACE1,
            selectForeground=FG,
            activeBackground=SURFACE0,
            activeForeground=FG,
            troughColor=BG,
        )
        self.root.configure(bg=BG_DARK)
        self.root.option_add('*Frame.background', BG_DARK)
        self.root.option_add('*Label.background', BG_DARK)
        self.root.option_add('*Canvas.background', BG)
        self.root.option_add('*highlightThickness', 0)
        self.root.option_add('*borderWidth', 0)
        self.root.geometry('1024x640')
        self.root.minsize(400, 300)

        self.tabs = []
        self.active_tab = None
        self._resize_timer = None

        self._build_menubar()
        self._build_ui()
        self.new_tab()

        # Bind window resize
        self._content.bind('<Configure>', self._on_configure)

        # Focus events (mode 1004)
        self.root.bind('<FocusIn>', self._on_focus_in)
        self.root.bind('<FocusOut>', self._on_focus_out)

        # Show window now that everything is dark
        self.root.deiconify()
        self.root.lift()
        self.root.after(200, self._grab_focus)

    def _grab_focus(self):
        """Force our window to front and grab keyboard focus."""
        self.root.lift()
        self.root.focus_force()
        if self.active_tab:
            self.active_tab.renderer.canvas.focus_force()

    def _build_menubar(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # App menu (name='apple' makes it the Mac application menu)
        app_menu = tk.Menu(menubar, name='apple', tearoff=0)
        menubar.add_cascade(menu=app_menu, label='Tiger Terminal')
        app_menu.add_command(label='About Tiger Terminal')
        app_menu.add_separator()

        # Shell menu
        shell_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label='Shell', menu=shell_menu)
        shell_menu.add_command(label='New Tab', accelerator='Cmd+T',
                               command=self.new_tab)
        shell_menu.add_command(label='Close Tab', accelerator='Cmd+W',
                               command=lambda: self.close_tab(self.active_tab) if self.active_tab else None)

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label='Edit', menu=edit_menu)
        edit_menu.add_command(label='Copy', accelerator='Cmd+C',
                              command=lambda: self.copy_selection(self.active_tab) if self.active_tab else None)
        edit_menu.add_command(label='Paste', accelerator='Cmd+V',
                              command=lambda: self.paste(self.active_tab) if self.active_tab else None)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label='View', menu=view_menu)
        view_menu.add_command(label='Bigger', accelerator='Cmd++',
                              command=lambda: self.change_font_size(1))
        view_menu.add_command(label='Smaller', accelerator='Cmd+-',
                              command=lambda: self.change_font_size(-1))

    def _build_ui(self):
        # Tab bar
        self._tab_bar = tk.Frame(self.root, bg=TAB_BG, height=28)
        self._tab_bar.pack(fill='x', side='top')
        self._tab_bar.pack_propagate(False)

        self._tab_buttons = []

        # New tab button
        self._new_btn = tk.Label(
            self._tab_bar, text=' + ', bg=TAB_BG, fg=OVERLAY,
            font=(FONT_FAMILY, 11), cursor='hand2'
        )
        self._new_btn.pack(side='left', padx=(2, 0))
        self._new_btn.bind('<Button-1>', lambda e: self.new_tab())

        # Content area
        self._content = tk.Frame(self.root, bg=BG)
        self._content.pack(fill='both', expand=True)


    # ── Tab management ──

    def _refresh_tab_bar(self):
        for btn in self._tab_buttons:
            btn.destroy()
        self._tab_buttons = []

        for i, tab in enumerate(self.tabs):
            is_active = (tab is self.active_tab)
            bg = TAB_SEL if is_active else TAB_BG
            fg_color = FG if is_active else OVERLAY
            label = ' {} '.format(i + 1)

            btn = tk.Label(
                self._tab_bar, text=label, bg=bg, fg=fg_color,
                font=(FONT_FAMILY, 11), padx=8, cursor='hand2'
            )
            btn.pack(side='left', padx=(2, 0), pady=2)
            btn.bind('<Button-1>', lambda e, t=tab: self._activate_tab(t))
            self._tab_buttons.append(btn)

    def new_tab(self):
        # Calculate cols/rows from content area
        self.root.update_idletasks()
        w = self._content.winfo_width()
        h = self._content.winfo_height()

        cols = DEFAULT_COLS
        rows = DEFAULT_ROWS

        if self.active_tab:
            renderer = self.active_tab.renderer
            cols, rows = renderer.cols_rows_for_size(w, h)
            if cols < 10:
                cols = DEFAULT_COLS
            if rows < 4:
                rows = DEFAULT_ROWS

        tab = TerminalTab(self._content, self, cols, rows)
        self.tabs.append(tab)
        self._activate_tab(tab)

    def close_tab(self, tab):
        if tab in self.tabs:
            idx = self.tabs.index(tab)
            tab.hide()
            tab.destroy()
            self.tabs.remove(tab)

            if not self.tabs:
                self.root.destroy()
                return

            new_idx = min(idx, len(self.tabs) - 1)
            self._activate_tab(self.tabs[new_idx])

    def _activate_tab(self, tab):
        if self.active_tab:
            # Unbind old tab's key handler from root
            self.root.unbind('<Key>')
            self.root.unbind('<KeyPress>')
            self.active_tab.hide()
        self.active_tab = tab
        tab.show()
        # Bind new tab's key handler to root
        self.root.bind('<Key>', tab._on_key)
        self.root.bind('<KeyPress>', tab._on_key)
        self._refresh_tab_bar()

    def switch_tab(self, idx):
        if 0 <= idx < len(self.tabs):
            self._activate_tab(self.tabs[idx])

    # ── Copy/paste ──

    def copy_selection(self, tab):
        text = tab.renderer.get_selection_text()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            tab.renderer.clear_selection()

    def paste(self, tab):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        if tab.screen.bracketed_paste:
            tab.shell.write('\x1b[200~')
            tab.shell.write(text)
            tab.shell.write('\x1b[201~')
        else:
            tab.shell.write(text)

    # ── Font size ──

    def change_font_size(self, delta):
        if not self.active_tab:
            return
        renderer = self.active_tab.renderer
        renderer.change_font_size(delta)
        # Recalculate grid for new font size
        w = self._content.winfo_width()
        h = self._content.winfo_height()
        cols, rows = renderer.cols_rows_for_size(w, h)
        if cols >= 10 and rows >= 4:
            self.active_tab.resize_grid(cols, rows)

    # ── Window resize ──

    def _on_configure(self, event):
        if self._resize_timer:
            self.root.after_cancel(self._resize_timer)
        self._resize_timer = self.root.after(100, self._do_resize)

    def _do_resize(self):
        self._resize_timer = None
        if not self.active_tab:
            return
        w = self._content.winfo_width()
        h = self._content.winfo_height()
        renderer = self.active_tab.renderer
        cols, rows = renderer.cols_rows_for_size(w, h)
        if cols >= 10 and rows >= 4:
            self.active_tab.resize_grid(cols, rows)

    # ── Focus events ──

    def _on_focus_in(self, event):
        if self.active_tab and self.active_tab.screen.focus_events:
            self.active_tab.shell.write('\x1b[I')

    def _on_focus_out(self, event):
        if self.active_tab and self.active_tab.screen.focus_events:
            self.active_tab.shell.write('\x1b[O')

    def run(self):
        self.root.mainloop()


def main():
    app = TigerTerminal()
    app.run()


if __name__ == '__main__':
    main()
