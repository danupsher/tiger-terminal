"""
VT100 screen buffer — 2D cell grid with cursor, scrolling, alternate screen.
Each cell is [char, fg, bg, attrs] where attrs is a bitmask.
"""
import unicodedata

# Attribute bitmask
ATTR_BOLD      = 0x01
ATTR_DIM       = 0x02
ATTR_ITALIC    = 0x04
ATTR_UNDERLINE = 0x08
ATTR_REVERSE       = 0x10
ATTR_WIDE          = 0x20  # first cell of a double-width character
ATTR_STRIKETHROUGH = 0x40

# Color tables
COLORS_16 = {
    0: '#2e2e2e', 1: '#e06c75', 2: '#98c379', 3: '#e5c07b',
    4: '#61afef', 5: '#c678dd', 6: '#56b6c2', 7: '#abb2bf',
    8: '#545862', 9: '#e06c75', 10: '#98c379', 11: '#e5c07b',
    12: '#61afef', 13: '#c678dd', 14: '#56b6c2', 15: '#ffffff',
}

DEFAULT_FG = '#cdd6f4'
DEFAULT_BG = '#1e1e2e'
SCROLLBACK_MAX = 2000


def _color_256(n):
    if n < 16:
        return COLORS_16.get(n, DEFAULT_FG)
    if n < 232:
        n -= 16
        b = n % 6; n //= 6
        g = n % 6; r = n // 6
        def c(x): return 0 if x == 0 else 55 + x * 40
        return '#{:02x}{:02x}{:02x}'.format(c(r), c(g), c(b))
    grey = 8 + (n - 232) * 10
    return '#{:02x}{:02x}{:02x}'.format(grey, grey, grey)


def _blank_cell():
    return [' ', None, None, 0]


def _blank_row(cols):
    return [_blank_cell() for _ in range(cols)]


def _char_width(ch):
    """Return display width: 2 for wide/fullwidth chars, 1 otherwise."""
    eaw = unicodedata.east_asian_width(ch)
    return 2 if eaw in ('W', 'F') else 1


class Screen:
    def __init__(self, cols=80, rows=24):
        self.cols = cols
        self.rows = rows
        self.cx = 0  # cursor column
        self.cy = 0  # cursor row

        # Current attributes for new chars
        self._fg = None
        self._bg = None
        self._attrs = 0

        # Grid
        self.grid = [_blank_row(cols) for _ in range(rows)]

        # Scroll region (top, bottom inclusive)
        self.scroll_top = 0
        self.scroll_bottom = rows - 1

        # Mode flags
        self.autowrap = True
        self.origin_mode = False
        self.cursor_visible = True
        self.app_cursor_keys = False
        self.app_keypad = False
        self.bracketed_paste = False
        self.mouse_tracking = 0  # 0=off, 1000=basic, 1002=button, 1003=any
        self.mouse_sgr = False   # SGR mouse encoding (mode 1006)
        self.focus_events = False  # mode 1004 — send focus in/out
        self.sync_output = False   # mode 2026 — synchronized output
        self.cursor_shape = 0      # DECSCUSR: 0=default, 1=block blink, 2=block, 3=underline blink, 4=underline, 5=bar blink, 6=bar
        self._wrap_next = False  # pending wrap at right margin

        # Saved cursor
        self._saved_cx = 0
        self._saved_cy = 0
        self._saved_fg = None
        self._saved_bg = None
        self._saved_attrs = 0
        self._saved_origin = False

        # Alternate screen buffer
        self._alt_grid = None
        self._alt_cx = 0
        self._alt_cy = 0
        self._main_grid = None
        self._main_cx = 0
        self._main_cy = 0
        self._in_alt = False

        # Scrollback
        self.scrollback = []

        # Dirty tracking
        self.dirty_rows = set()
        self.dirty_all = True

        # Tab stops (every 8 columns)
        self.tab_stops = set(range(0, cols, 8))

        # Window title (set by OSC)
        self.title = ''

    def _mark_dirty(self, row):
        self.dirty_rows.add(row)

    def _mark_all_dirty(self):
        self.dirty_all = True
        self.dirty_rows = set(range(self.rows))

    def clear_dirty(self):
        self.dirty_all = False
        self.dirty_rows = set()

    # ── Print character ──

    def print_char(self, ch):
        w = _char_width(ch) if len(ch) == 1 else 1

        if self._wrap_next:
            self._wrap_next = False
            self.cx = 0
            self._scroll_up_if_needed()
            self.cy += 1
            if self.cy > self.scroll_bottom:
                self.cy = self.scroll_bottom
                self._scroll_up()

        # Wide char at last column — wrap first
        if w == 2 and self.cx == self.cols - 1:
            if self.autowrap:
                self.grid[self.cy][self.cx] = _blank_cell()
                self._mark_dirty(self.cy)
                self.cx = 0
                self.cy += 1
                if self.cy > self.scroll_bottom:
                    self.cy = self.scroll_bottom
                    self._scroll_up()
            else:
                return

        if 0 <= self.cy < self.rows and 0 <= self.cx < self.cols:
            # Clear any wide char we're overwriting
            self._fix_wide_overlap(self.cy, self.cx)
            if w == 2 and self.cx + 1 < self.cols:
                self._fix_wide_overlap(self.cy, self.cx + 1)
                self.grid[self.cy][self.cx] = [ch, self._fg, self._bg,
                                                self._attrs | ATTR_WIDE]
                self.grid[self.cy][self.cx + 1] = ['', self._fg, self._bg, 0]
                self._mark_dirty(self.cy)
                self.cx += 2
            else:
                self.grid[self.cy][self.cx] = [ch, self._fg, self._bg, self._attrs]
                self._mark_dirty(self.cy)
                self.cx += 1

        if self.cx >= self.cols:
            if self.autowrap:
                self.cx = self.cols - 1
                self._wrap_next = True
            else:
                self.cx = self.cols - 1

    def _fix_wide_overlap(self, row, col):
        """When overwriting part of a wide char, blank the other half."""
        cell = self.grid[row][col]
        if cell[3] & ATTR_WIDE and col + 1 < self.cols:
            self.grid[row][col + 1] = _blank_cell()
        if cell[0] == '' and col > 0:
            prev = self.grid[row][col - 1]
            if prev[3] & ATTR_WIDE:
                self.grid[row][col - 1] = _blank_cell()

    # ── C0 controls ──

    def execute(self, b):
        if b == 0x08:  # BS
            self._wrap_next = False
            if self.cx > 0:
                self.cx -= 1
        elif b == 0x09:  # HT
            self._wrap_next = False
            # Advance to next tab stop
            next_tab = self.cx + 1
            while next_tab < self.cols and next_tab not in self.tab_stops:
                next_tab += 1
            self.cx = min(next_tab, self.cols - 1)
        elif b == 0x0A:  # LF
            self._wrap_next = False
            if self.cy == self.scroll_bottom:
                self._scroll_up()
            elif self.cy < self.rows - 1:
                self.cy += 1
        elif b == 0x0D:  # CR
            self._wrap_next = False
            self.cx = 0
        elif b == 0x07:  # BEL
            pass  # Could trigger bell visual

    def _scroll_up_if_needed(self):
        pass  # handled inline

    # ── Scroll operations ──

    def _scroll_up(self, n=1):
        for _ in range(n):
            if not self._in_alt and self.scroll_top == 0:
                self.scrollback.append(self.grid[self.scroll_top])
                if len(self.scrollback) > SCROLLBACK_MAX:
                    self.scrollback.pop(0)
            del self.grid[self.scroll_top]
            self.grid.insert(self.scroll_bottom, _blank_row(self.cols))
        self._mark_all_dirty()

    def _scroll_down(self, n=1):
        for _ in range(n):
            del self.grid[self.scroll_bottom]
            self.grid.insert(self.scroll_top, _blank_row(self.cols))
        self._mark_all_dirty()

    # ── CSI dispatch ──

    def csi_dispatch(self, params, intermediate, final, private):
        if private == '?':
            self._csi_private(params, final)
            return

        if private == '>' or private == '!':
            return  # ignore

        p = params if params else [0]

        if final == 'm':
            self._sgr(params if params else [0])
        elif final == 'A':  # CUU — cursor up
            self._wrap_next = False
            n = max(p[0], 1)
            self.cy = max(self.cy - n, self.scroll_top if self.origin_mode else 0)
        elif final == 'B':  # CUD — cursor down
            self._wrap_next = False
            n = max(p[0], 1)
            self.cy = min(self.cy + n, self.scroll_bottom if self.origin_mode else self.rows - 1)
        elif final == 'C':  # CUF — cursor forward
            self._wrap_next = False
            n = max(p[0], 1)
            self.cx = min(self.cx + n, self.cols - 1)
        elif final == 'D':  # CUB — cursor back
            self._wrap_next = False
            n = max(p[0], 1)
            self.cx = max(self.cx - n, 0)
        elif final == 'E':  # CNL — cursor next line
            self._wrap_next = False
            n = max(p[0], 1)
            self.cy = min(self.cy + n, self.rows - 1)
            self.cx = 0
        elif final == 'F':  # CPL — cursor previous line
            self._wrap_next = False
            n = max(p[0], 1)
            self.cy = max(self.cy - n, 0)
            self.cx = 0
        elif final == 'G':  # CHA — cursor horizontal absolute
            self._wrap_next = False
            col = max(p[0], 1) - 1
            self.cx = min(col, self.cols - 1)
        elif final == 'H' or final == 'f':  # CUP — cursor position
            self._wrap_next = False
            row = max(p[0], 1) - 1
            col = max(p[1] if len(p) > 1 else 1, 1) - 1
            if self.origin_mode:
                row += self.scroll_top
            self.cy = min(row, self.rows - 1)
            self.cx = min(col, self.cols - 1)
        elif final == 'J':  # ED — erase display
            self._erase_display(p[0])
        elif final == 'K':  # EL — erase line
            self._erase_line(p[0])
        elif final == 'L':  # IL — insert lines
            self._insert_lines(max(p[0], 1))
        elif final == 'M':  # DL — delete lines
            self._delete_lines(max(p[0], 1))
        elif final == 'P':  # DCH — delete characters
            self._delete_chars(max(p[0], 1))
        elif final == '@':  # ICH — insert characters
            self._insert_chars(max(p[0], 1))
        elif final == 'X':  # ECH — erase characters
            n = max(p[0], 1)
            for i in range(n):
                col = self.cx + i
                if col < self.cols:
                    self.grid[self.cy][col] = _blank_cell()
            self._mark_dirty(self.cy)
        elif final == 'S':  # SU — scroll up
            self._scroll_up(max(p[0], 1))
        elif final == 'T':  # SD — scroll down
            self._scroll_down(max(p[0], 1))
        elif final == 'd':  # VPA — line position absolute
            self._wrap_next = False
            row = max(p[0], 1) - 1
            self.cy = min(row, self.rows - 1)
        elif final == 'r':  # DECSTBM — set scrolling region
            top = max(p[0], 1) - 1
            bottom = (p[1] if len(p) > 1 and p[1] > 0 else self.rows) - 1
            if top < bottom and bottom < self.rows:
                self.scroll_top = top
                self.scroll_bottom = bottom
            else:
                self.scroll_top = 0
                self.scroll_bottom = self.rows - 1
            self.cx = 0
            self.cy = self.scroll_top if self.origin_mode else 0
            self._wrap_next = False
        elif final == 'n':  # DSR — device status report
            if p[0] == 6:  # cursor position report
                self._respond('\x1b[{};{}R'.format(self.cy + 1, self.cx + 1))
            elif p[0] == 5:
                self._respond('\x1b[0n')  # terminal OK
        elif final == 'c':  # DA — device attributes
            self._respond('\x1b[?1;2c')
        elif final == 'h':  # SM — set mode
            for code in p:
                if code == 4:
                    pass  # insert mode (ignore)
                elif code == 20:
                    pass  # auto newline
        elif final == 'l':  # RM — reset mode
            for code in p:
                if code == 4:
                    pass
        elif final == 's':  # SCP — save cursor
            self._save_cursor()
        elif final == 'u':  # RCP — restore cursor
            self._restore_cursor()
        elif final == 't':  # window manipulation (ignore)
            pass
        elif final == 'b':  # REP — repeat last char
            pass  # rarely used
        elif final == 'g':  # TBC — tab clear
            if p[0] == 0:
                self.tab_stops.discard(self.cx)
            elif p[0] == 3:
                self.tab_stops.clear()
        elif final == 'q' and intermediate == ' ':  # DECSCUSR — cursor shape
            self.cursor_shape = p[0] if p else 0

    def _respond(self, data):
        """Send response back to PTY. Set by terminal_app."""
        if hasattr(self, 'on_respond') and self.on_respond:
            self.on_respond(data)

    # ── Private mode (CSI ? ...) ──

    def _csi_private(self, params, final):
        for code in (params if params else [0]):
            if final == 'h':  # DECSET
                self._decset(code, True)
            elif final == 'l':  # DECRST
                self._decset(code, False)

    def _decset(self, code, on):
        if code == 1:  # DECCKM — app cursor keys
            self.app_cursor_keys = on
        elif code == 5:  # DECSCNM — reverse video (ignore)
            pass
        elif code == 6:  # DECOM — origin mode
            self.origin_mode = on
            self.cx = 0
            self.cy = self.scroll_top if on else 0
            self._wrap_next = False
        elif code == 7:  # DECAWM — autowrap
            self.autowrap = on
        elif code == 12:  # cursor blink (ignore, handled by renderer)
            pass
        elif code == 25:  # DECTCEM — cursor visible
            self.cursor_visible = on
        elif code == 47:  # alt screen (no clear)
            if on:
                self._enter_alt_screen(clear=False)
            else:
                self._leave_alt_screen()
        elif code == 66:  # DECNKM — app keypad
            self.app_keypad = on
        elif code == 1000:  # mouse tracking — basic
            self.mouse_tracking = 1000 if on else 0
        elif code == 1002:  # mouse tracking — button events
            self.mouse_tracking = 1002 if on else 0
        elif code == 1003:  # mouse tracking — all events
            self.mouse_tracking = 1003 if on else 0
        elif code == 1004:  # focus events
            self.focus_events = on
        elif code == 1006:  # SGR mouse encoding
            self.mouse_sgr = on
        elif code == 1047:  # alt screen (clear on enter)
            if on:
                self._enter_alt_screen(clear=True)
            else:
                self._leave_alt_screen()
        elif code == 1049:  # alt screen + save cursor
            if on:
                self._save_cursor()
                self._enter_alt_screen(clear=True)
            else:
                self._leave_alt_screen()
                self._restore_cursor()
        elif code == 2004:  # bracketed paste
            self.bracketed_paste = on
        elif code == 2026:  # synchronized output

            self.sync_output = on

    # ── Alt screen ──

    def _enter_alt_screen(self, clear=True):

        if self._in_alt:
            return
        self._in_alt = True
        self._main_grid = self.grid
        self._main_cx = self.cx
        self._main_cy = self.cy
        if clear:
            self.grid = [_blank_row(self.cols) for _ in range(self.rows)]
        else:
            import copy
            self.grid = [row[:] for row in self.grid]
        self.cx = 0
        self.cy = 0
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self._mark_all_dirty()

    def _leave_alt_screen(self):

        if not self._in_alt:
            return
        self._in_alt = False
        self.grid = self._main_grid
        self.cx = self._main_cx
        self.cy = self._main_cy
        self._main_grid = None
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self._mark_all_dirty()

    # ── ESC dispatch ──

    def esc_dispatch(self, intermediate, final):
        if intermediate == '' and final == 'M':  # RI — reverse index
            if self.cy == self.scroll_top:
                self._scroll_down(1)
            elif self.cy > 0:
                self.cy -= 1
        elif intermediate == '' and final == 'D':  # IND — index (move down)
            if self.cy == self.scroll_bottom:
                self._scroll_up(1)
            elif self.cy < self.rows - 1:
                self.cy += 1
        elif intermediate == '' and final == 'E':  # NEL — next line
            self.cx = 0
            if self.cy == self.scroll_bottom:
                self._scroll_up(1)
            elif self.cy < self.rows - 1:
                self.cy += 1
        elif intermediate == '' and final == '7':  # DECSC — save cursor
            self._save_cursor()
        elif intermediate == '' and final == '8':  # DECRC — restore cursor
            self._restore_cursor()
        elif intermediate == '' and final == 'c':  # RIS — full reset
            self.reset()
        elif intermediate == '#' and final == '8':  # DECALN — alignment test
            for r in range(self.rows):
                for c in range(self.cols):
                    self.grid[r][c] = ['E', None, None, 0]
            self._mark_all_dirty()
        elif intermediate == '(' or intermediate == ')':
            pass  # charset designation, ignore
        elif intermediate == '' and final == '=':  # DECKPAM
            self.app_keypad = True
        elif intermediate == '' and final == '>':  # DECKPNM
            self.app_keypad = False
        elif intermediate == '' and final == 'H':  # HTS — set tab stop
            self.tab_stops.add(self.cx)

    # ── OSC dispatch ──

    def osc_dispatch(self, data):
        # OSC format: "code;data"
        if ';' in data:
            code_str, _, text = data.partition(';')
            try:
                code = int(code_str)
            except ValueError:
                return
            if code in (0, 2):  # set window title
                self.title = text
            elif code == 1:  # set icon name (ignore)
                pass
        # Other OSC codes ignored

    # ── SGR ──

    def _sgr(self, params):
        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                self._fg = None
                self._bg = None
                self._attrs = 0
            elif p == 1:
                self._attrs |= ATTR_BOLD
            elif p == 2:
                self._attrs |= ATTR_DIM
            elif p == 3:
                self._attrs |= ATTR_ITALIC
            elif p == 4:
                self._attrs |= ATTR_UNDERLINE
            elif p == 7:
                self._attrs |= ATTR_REVERSE
            elif p == 9:
                self._attrs |= ATTR_STRIKETHROUGH
            elif p == 21 or p == 22:
                self._attrs &= ~(ATTR_BOLD | ATTR_DIM)
            elif p == 23:
                self._attrs &= ~ATTR_ITALIC
            elif p == 24:
                self._attrs &= ~ATTR_UNDERLINE
            elif p == 27:
                self._attrs &= ~ATTR_REVERSE
            elif p == 29:
                self._attrs &= ~ATTR_STRIKETHROUGH
            elif p == 39:
                self._fg = None
            elif p == 49:
                self._bg = None
            elif 30 <= p <= 37:
                self._fg = COLORS_16[p - 30]
            elif 40 <= p <= 47:
                self._bg = COLORS_16[p - 40]
            elif 90 <= p <= 97:
                self._fg = COLORS_16[p - 90 + 8]
            elif 100 <= p <= 107:
                self._bg = COLORS_16[p - 100 + 8]
            elif p == 38:  # extended FG
                if i + 1 < len(params):
                    if params[i+1] == 5 and i + 2 < len(params):
                        self._fg = _color_256(params[i+2])
                        i += 2
                    elif params[i+1] == 2 and i + 4 < len(params):
                        r, g, b = params[i+2], params[i+3], params[i+4]
                        self._fg = '#{:02x}{:02x}{:02x}'.format(r, g, b)
                        i += 4
            elif p == 48:  # extended BG
                if i + 1 < len(params):
                    if params[i+1] == 5 and i + 2 < len(params):
                        self._bg = _color_256(params[i+2])
                        i += 2
                    elif params[i+1] == 2 and i + 4 < len(params):
                        r, g, b = params[i+2], params[i+3], params[i+4]
                        self._bg = '#{:02x}{:02x}{:02x}'.format(r, g, b)
                        i += 4
            i += 1

    # ── Erase ──

    def _erase_display(self, mode):

        if mode == 0:  # below cursor
            # Clear rest of current line
            for c in range(self.cx, self.cols):
                self.grid[self.cy][c] = _blank_cell()
            # Clear all lines below
            for r in range(self.cy + 1, self.rows):
                self.grid[r] = _blank_row(self.cols)
        elif mode == 1:  # above cursor
            for r in range(0, self.cy):
                self.grid[r] = _blank_row(self.cols)
            for c in range(0, self.cx + 1):
                if c < self.cols:
                    self.grid[self.cy][c] = _blank_cell()
        elif mode == 2 or mode == 3:  # entire screen
            for r in range(self.rows):
                self.grid[r] = _blank_row(self.cols)
        self._mark_all_dirty()

    def _erase_line(self, mode):
        if mode == 0:  # right of cursor
            for c in range(self.cx, self.cols):
                self.grid[self.cy][c] = _blank_cell()
        elif mode == 1:  # left of cursor
            for c in range(0, self.cx + 1):
                self.grid[self.cy][c] = _blank_cell()
        elif mode == 2:  # entire line
            self.grid[self.cy] = _blank_row(self.cols)
        self._mark_dirty(self.cy)

    # ── Insert / Delete ──

    def _insert_lines(self, n):
        if self.cy < self.scroll_top or self.cy > self.scroll_bottom:
            return
        n = min(n, self.scroll_bottom - self.cy + 1)
        for _ in range(n):
            if self.scroll_bottom < len(self.grid):
                del self.grid[self.scroll_bottom]
            self.grid.insert(self.cy, _blank_row(self.cols))
        self.cx = 0
        self._mark_all_dirty()

    def _delete_lines(self, n):
        if self.cy < self.scroll_top or self.cy > self.scroll_bottom:
            return
        n = min(n, self.scroll_bottom - self.cy + 1)
        for _ in range(n):
            del self.grid[self.cy]
            self.grid.insert(self.scroll_bottom, _blank_row(self.cols))
        self.cx = 0
        self._mark_all_dirty()

    def _insert_chars(self, n):
        row = self.grid[self.cy]
        for _ in range(n):
            if len(row) > self.cols:
                row.pop()
            row.insert(self.cx, _blank_cell())
        # Trim to cols
        while len(row) > self.cols:
            row.pop()
        self._mark_dirty(self.cy)

    def _delete_chars(self, n):
        row = self.grid[self.cy]
        for _ in range(n):
            if self.cx < len(row):
                row.pop(self.cx)
                row.append(_blank_cell())
        self._mark_dirty(self.cy)

    # ── Cursor save/restore ──

    def _save_cursor(self):
        self._saved_cx = self.cx
        self._saved_cy = self.cy
        self._saved_fg = self._fg
        self._saved_bg = self._bg
        self._saved_attrs = self._attrs
        self._saved_origin = self.origin_mode

    def _restore_cursor(self):
        self.cx = self._saved_cx
        self.cy = self._saved_cy
        self._fg = self._saved_fg
        self._bg = self._saved_bg
        self._attrs = self._saved_attrs
        self.origin_mode = self._saved_origin
        self._wrap_next = False

    # ── Resize ──

    def resize(self, cols, rows):
        old_rows = self.rows
        old_cols = self.cols
        self.cols = cols
        self.rows = rows

        # Adjust grid rows
        while len(self.grid) < rows:
            self.grid.append(_blank_row(cols))
        while len(self.grid) > rows:
            if self.cy < len(self.grid) - 1:
                self.grid.pop()
            else:
                self.grid.pop(0)

        # Adjust each row's column count
        for r in range(len(self.grid)):
            row = self.grid[r]
            if len(row) < cols:
                row.extend(_blank_cell() for _ in range(cols - len(row)))
            elif len(row) > cols:
                del row[cols:]

        # Clamp cursor
        self.cx = min(self.cx, cols - 1)
        self.cy = min(self.cy, rows - 1)

        # Reset scroll region
        self.scroll_top = 0
        self.scroll_bottom = rows - 1

        # Rebuild tab stops
        self.tab_stops = set(range(0, cols, 8))

        self._mark_all_dirty()

    # ── Reset ──

    def reset(self):
        self.cx = 0
        self.cy = 0
        self._fg = None
        self._bg = None
        self._attrs = 0
        self.grid = [_blank_row(self.cols) for _ in range(self.rows)]
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self.autowrap = True
        self.origin_mode = False
        self.cursor_visible = True
        self.app_cursor_keys = False
        self.app_keypad = False
        self.bracketed_paste = False
        self.mouse_tracking = 0
        self.mouse_sgr = False
        self.focus_events = False
        self.sync_output = False
        self.cursor_shape = 0
        self._wrap_next = False
        self._in_alt = False
        self._main_grid = None
        self.tab_stops = set(range(0, self.cols, 8))
        self._mark_all_dirty()
