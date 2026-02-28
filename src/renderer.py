"""
Canvas-based character grid renderer for Tiger Terminal.
Pre-creates text items for each cell, updates only dirty cells.
"""
try:
    import tkinter as tk
except ImportError:
    import Tkinter as tk

from screen import DEFAULT_FG, DEFAULT_BG, ATTR_BOLD, ATTR_DIM, ATTR_ITALIC, \
    ATTR_UNDERLINE, ATTR_REVERSE, ATTR_WIDE, ATTR_STRIKETHROUGH


class CanvasRenderer:
    def __init__(self, parent, screen, font_family='Monaco', font_size=13):
        self.screen = screen
        self.font_family = font_family
        self.font_size = font_size
        self.rows = screen.rows
        self.cols = screen.cols

        # Colors
        self.default_fg = DEFAULT_FG
        self.default_bg = DEFAULT_BG

        # Calculate cell size
        self.cell_w = 0
        self.cell_h = 0

        # Canvas — takefocus=1 required for Tk 8.4 Aqua key events
        self.canvas = tk.Canvas(parent, bg=self.default_bg,
                                highlightthickness=0, cursor='xterm',
                                takefocus=1)
        self.canvas.pack(fill='both', expand=True)

        # Grid of text item IDs: text_items[row][col]
        self.text_items = []
        # Cache of what's displayed: displayed[row][col] = (char, fg, bg, attrs)
        self.displayed = []
        # Background rectangle items (created on demand)
        self.bg_items = {}  # (row, col) -> item_id
        # Underline/strikethrough line items (created on demand)
        self.line_items = {}  # (row, col) -> item_id

        # Cursor
        self.cursor_item = None
        self.cursor_visible = True
        self.cursor_blink_on = True
        self._blink_id = None

        # Selection
        self.sel_start = None  # (row, col)
        self.sel_end = None    # (row, col)
        self.sel_items = []    # highlight rectangle IDs

        # Scrollback view state
        self.scroll_offset = 0  # 0 = live view, >0 = scrolled back

        # Measure font and create grid
        self._measure_font()
        self._setup_grid()

    def _measure_font(self):
        """Measure actual character dimensions with current font."""
        font_spec = (self.font_family, self.font_size)
        # Create a temp text item to measure
        tid = self.canvas.create_text(0, 0, text='M', font=font_spec,
                                      anchor='nw', fill=self.default_fg)
        bbox = self.canvas.bbox(tid)
        self.canvas.delete(tid)
        if bbox:
            self.cell_w = bbox[2] - bbox[0]
            self.cell_h = bbox[3] - bbox[1]
        else:
            # Fallback
            self.cell_w = self.font_size * 6 // 10
            self.cell_h = self.font_size + 3
        # Ensure minimum
        if self.cell_w < 1:
            self.cell_w = 8
        if self.cell_h < 1:
            self.cell_h = 16

    def _setup_grid(self):
        """Create all text items for the grid."""
        # Remove old items
        self.canvas.delete('cell')
        self.canvas.delete('bgr')
        self.canvas.delete('decor')
        self.text_items = []
        self.displayed = []
        self.bg_items = {}
        self.line_items = {}

        font_spec = (self.font_family, self.font_size)
        for r in range(self.rows):
            row_items = []
            row_disp = []
            y = r * self.cell_h
            for c in range(self.cols):
                x = c * self.cell_w
                tid = self.canvas.create_text(
                    x, y, text=' ', font=font_spec,
                    anchor='nw', fill=self.default_fg, tags='cell'
                )
                row_items.append(tid)
                row_disp.append((' ', self.default_fg, None, 0))
            self.text_items.append(row_items)
            self.displayed.append(row_disp)

        # Size canvas
        w = self.cols * self.cell_w
        h = self.rows * self.cell_h
        self.canvas.config(width=w, height=h)

        # Create cursor
        if self.cursor_item:
            self.canvas.delete(self.cursor_item)
        self.cursor_item = self.canvas.create_rectangle(
            0, 0, self.cell_w, self.cell_h,
            fill='#f5e0dc', outline='', tags='cursor'
        )
        self.canvas.tag_raise('cell')  # text above cursor

        self.screen.dirty_all = True
        self.screen.dirty_rows = set(range(self.rows))

    def resize(self, cols, rows):
        """Resize the grid (called after screen.resize)."""
        self.rows = rows
        self.cols = cols
        self._setup_grid()

    def get_grid_size(self):
        """Return (width_pixels, height_pixels) of the grid."""
        return (self.cols * self.cell_w, self.rows * self.cell_h)

    def cols_rows_for_size(self, width, height):
        """Calculate cols, rows that fit in the given pixel size."""
        cols = max(width // self.cell_w, 1)
        rows = max(height // self.cell_h, 1)
        return cols, rows

    # ── Rendering ──

    def render(self, force=False):
        """Update canvas from screen state. Only touches dirty cells."""
        scr = self.screen

        # Synchronized output — defer rendering until mode is cleared
        if scr.sync_output and not force:
            return

        if self.scroll_offset > 0:
            self._render_scrollback()
            return

        dirty_all = scr.dirty_all
        dirty_rows = scr.dirty_rows
        scr.clear_dirty()

        if not dirty_all and not dirty_rows:
            self._update_cursor()
            return

        font_spec = (self.font_family, self.font_size)
        font_bold = (self.font_family, self.font_size, 'bold')
        font_italic = (self.font_family, self.font_size, 'italic')
        font_bold_italic = (self.font_family, self.font_size, 'bold italic')

        rows_to_update = range(self.rows) if dirty_all else dirty_rows

        for r in rows_to_update:
            if r >= self.rows or r >= len(scr.grid):
                continue
            grid_row = scr.grid[r]
            for c in range(self.cols):
                if c >= len(grid_row):
                    break
                cell = grid_row[c]
                ch, fg, bg, attrs = cell[0], cell[1], cell[2], cell[3]

                # Continuation cell (second half of wide char) — show space
                if ch == '' and c > 0 and grid_row[c-1][3] & ATTR_WIDE:
                    cached = self.displayed[r][c]
                    if cached != ('', None, bg, 0):
                        self.displayed[r][c] = ('', None, bg, 0)
                        tid = self.text_items[r][c]
                        self.canvas.itemconfigure(tid, text=' ', fill=self.default_fg,
                                                  font=font_spec)
                    # Background for continuation cell
                    eff_bg = bg
                    if attrs & ATTR_REVERSE:
                        eff_bg = fg or self.default_fg
                    key = (r, c)
                    if eff_bg and eff_bg != self.default_bg:
                        x = c * self.cell_w
                        y = r * self.cell_h
                        if key in self.bg_items:
                            self.canvas.itemconfigure(self.bg_items[key], fill=eff_bg)
                        else:
                            bid = self.canvas.create_rectangle(
                                x, y, x + self.cell_w, y + self.cell_h,
                                fill=eff_bg, outline='', tags='bgr')
                            self.bg_items[key] = bid
                            self.canvas.tag_lower('bgr')
                    elif key in self.bg_items:
                        self.canvas.delete(self.bg_items[key])
                        del self.bg_items[key]
                    continue

                # Resolve defaults
                eff_fg = fg or self.default_fg
                eff_bg = bg  # None means default (canvas bg)
                eff_attrs = attrs

                # Apply reverse
                if eff_attrs & ATTR_REVERSE:
                    eff_fg, eff_bg = (eff_bg or self.default_bg), eff_fg

                # Apply bold color boost
                if eff_attrs & ATTR_BOLD and fg is None and not (eff_attrs & ATTR_REVERSE):
                    eff_fg = '#ffffff'

                # Apply dim
                if eff_attrs & ATTR_DIM and fg is None:
                    eff_fg = '#6b6b7a'

                # Check cache
                cached = self.displayed[r][c]
                if cached == (ch, eff_fg, eff_bg, eff_attrs):
                    continue

                self.displayed[r][c] = (ch, eff_fg, eff_bg, eff_attrs)

                # Choose font
                bold = bool(eff_attrs & ATTR_BOLD)
                italic = bool(eff_attrs & ATTR_ITALIC)
                if bold and italic:
                    f = font_bold_italic
                elif bold:
                    f = font_bold
                elif italic:
                    f = font_italic
                else:
                    f = font_spec

                # Update text item
                tid = self.text_items[r][c]
                self.canvas.itemconfigure(tid, text=ch, fill=eff_fg, font=f)

                # Underline / strikethrough lines
                lkey = (r, c)
                need_line = eff_attrs & (ATTR_UNDERLINE | ATTR_STRIKETHROUGH)
                if need_line:
                    lx1 = c * self.cell_w
                    lx2 = lx1 + self.cell_w
                    if eff_attrs & ATTR_STRIKETHROUGH:
                        ly = r * self.cell_h + self.cell_h // 2
                    else:
                        ly = (r + 1) * self.cell_h - 1
                    if lkey in self.line_items:
                        self.canvas.coords(self.line_items[lkey], lx1, ly, lx2, ly)
                        self.canvas.itemconfigure(self.line_items[lkey], fill=eff_fg)
                    else:
                        lid = self.canvas.create_line(
                            lx1, ly, lx2, ly, fill=eff_fg, tags='decor')
                        self.line_items[lkey] = lid
                elif lkey in self.line_items:
                    self.canvas.delete(self.line_items[lkey])
                    del self.line_items[lkey]

                # Background — wide chars get double-width bg
                key = (r, c)
                bg_w = self.cell_w * 2 if (eff_attrs & ATTR_WIDE) else self.cell_w
                if eff_bg and eff_bg != self.default_bg:
                    x = c * self.cell_w
                    y = r * self.cell_h
                    if key in self.bg_items:
                        self.canvas.itemconfigure(self.bg_items[key], fill=eff_bg)
                        self.canvas.coords(self.bg_items[key], x, y,
                                           x + bg_w, y + self.cell_h)
                    else:
                        bid = self.canvas.create_rectangle(
                            x, y, x + bg_w, y + self.cell_h,
                            fill=eff_bg, outline='', tags='bgr'
                        )
                        self.bg_items[key] = bid
                        self.canvas.tag_lower('bgr')
                elif key in self.bg_items:
                    self.canvas.delete(self.bg_items[key])
                    del self.bg_items[key]

        self._update_cursor()

    def _update_cursor(self):
        """Move cursor rectangle to current position, respecting cursor shape."""
        scr = self.screen
        if not self.cursor_item:
            return
        if scr.cursor_visible and self.cursor_blink_on and self.scroll_offset == 0:
            x = scr.cx * self.cell_w
            y = scr.cy * self.cell_h
            shape = scr.cursor_shape
            # 0,1,2 = block; 3,4 = underline; 5,6 = bar
            if shape in (3, 4):  # underline
                cy_top = y + self.cell_h - 2
                self.canvas.coords(self.cursor_item, x, cy_top,
                                   x + self.cell_w, y + self.cell_h)
            elif shape in (5, 6):  # bar
                self.canvas.coords(self.cursor_item, x, y,
                                   x + 2, y + self.cell_h)
            else:  # block (default)
                self.canvas.coords(self.cursor_item, x, y,
                                   x + self.cell_w, y + self.cell_h)
            self.canvas.itemconfigure(self.cursor_item, state='normal')
            self.canvas.tag_raise('cursor')
            self.canvas.tag_raise('cell')
        else:
            self.canvas.itemconfigure(self.cursor_item, state='hidden')

    # ── Cursor blink ──

    def start_blink(self):
        self._blink_tick()

    def _blink_tick(self):
        self.cursor_blink_on = not self.cursor_blink_on
        self._update_cursor()
        self._blink_id = self.canvas.after(530, self._blink_tick)

    def stop_blink(self):
        if self._blink_id:
            self.canvas.after_cancel(self._blink_id)
            self._blink_id = None

    def reset_blink(self):
        """Reset blink to visible (called on keypress)."""
        self.cursor_blink_on = True
        if self._blink_id:
            self.canvas.after_cancel(self._blink_id)
        self._blink_id = self.canvas.after(530, self._blink_tick)

    # ── Scrollback view ──

    def scroll_up(self, lines=3):
        max_offset = len(self.screen.scrollback)
        self.scroll_offset = min(self.scroll_offset + lines, max_offset)
        if self.scroll_offset > 0:
            self._render_scrollback()

    def scroll_down(self, lines=3):
        self.scroll_offset = max(self.scroll_offset - lines, 0)
        if self.scroll_offset == 0:
            self.screen._mark_all_dirty()
            self.render()
        else:
            self._render_scrollback()

    def snap_to_bottom(self):
        if self.scroll_offset > 0:
            self.scroll_offset = 0
            self.screen._mark_all_dirty()

    def _render_scrollback(self):
        """Render a view that includes scrollback lines."""
        scr = self.screen
        sb = scr.scrollback
        offset = self.scroll_offset

        # Build combined view: scrollback + current grid
        all_lines = sb + scr.grid
        total = len(all_lines)
        # The "viewport bottom" in all_lines is at (total - offset)
        view_bottom = total - offset
        view_top = max(view_bottom - self.rows, 0)

        font_spec = (self.font_family, self.font_size)
        for vr in range(self.rows):
            src_idx = view_top + vr
            if src_idx < 0 or src_idx >= total:
                # blank
                for c in range(self.cols):
                    tid = self.text_items[vr][c]
                    self.canvas.itemconfigure(tid, text=' ', fill=self.default_fg,
                                              font=font_spec)
                    key = (vr, c)
                    if key in self.bg_items:
                        self.canvas.delete(self.bg_items[key])
                        del self.bg_items[key]
                continue

            row_data = all_lines[src_idx]
            for c in range(self.cols):
                if c < len(row_data):
                    cell = row_data[c]
                    ch, fg, bg, attrs = cell[0], cell[1], cell[2], cell[3]
                else:
                    ch, fg, bg, attrs = ' ', None, None, 0

                eff_fg = fg or self.default_fg
                eff_bg = bg
                if attrs & ATTR_REVERSE:
                    eff_fg, eff_bg = (eff_bg or self.default_bg), eff_fg
                if attrs & ATTR_BOLD and fg is None and not (attrs & ATTR_REVERSE):
                    eff_fg = '#ffffff'

                tid = self.text_items[vr][c]
                self.canvas.itemconfigure(tid, text=ch, fill=eff_fg, font=font_spec)

                key = (vr, c)
                if eff_bg and eff_bg != self.default_bg:
                    x = c * self.cell_w
                    y = vr * self.cell_h
                    if key in self.bg_items:
                        self.canvas.itemconfigure(self.bg_items[key], fill=eff_bg)
                    else:
                        bid = self.canvas.create_rectangle(
                            x, y, x + self.cell_w, y + self.cell_h,
                            fill=eff_bg, outline='', tags='bgr'
                        )
                        self.bg_items[key] = bid
                        self.canvas.tag_lower('bgr')
                elif key in self.bg_items:
                    self.canvas.delete(self.bg_items[key])
                    del self.bg_items[key]

        # Hide cursor in scrollback view
        if self.cursor_item:
            self.canvas.itemconfigure(self.cursor_item, state='hidden')

    # ── Selection ──

    def start_selection(self, row, col):
        self.clear_selection()
        self.sel_start = (row, col)
        self.sel_end = (row, col)

    def update_selection(self, row, col):
        if self.sel_start is None:
            return
        self.sel_end = (row, col)
        self._draw_selection()

    def clear_selection(self):
        self.sel_start = None
        self.sel_end = None
        for sid in self.sel_items:
            self.canvas.delete(sid)
        self.sel_items = []

    def get_selection_text(self):
        """Get selected text as a string."""
        if self.sel_start is None or self.sel_end is None:
            return ''
        r1, c1 = self.sel_start
        r2, c2 = self.sel_end
        if (r1, c1) > (r2, c2):
            r1, c1, r2, c2 = r2, c2, r1, c1

        scr = self.screen
        lines = []
        for r in range(r1, r2 + 1):
            if r >= self.rows or r >= len(scr.grid):
                continue
            start_c = c1 if r == r1 else 0
            end_c = c2 if r == r2 else self.cols - 1
            line = ''
            for c in range(start_c, min(end_c + 1, self.cols)):
                if c < len(scr.grid[r]):
                    line += scr.grid[r][c][0]
            lines.append(line.rstrip())
        return '\n'.join(lines)

    def _draw_selection(self):
        for sid in self.sel_items:
            self.canvas.delete(sid)
        self.sel_items = []

        if self.sel_start is None or self.sel_end is None:
            return

        r1, c1 = self.sel_start
        r2, c2 = self.sel_end
        if (r1, c1) > (r2, c2):
            r1, c1, r2, c2 = r2, c2, r1, c1

        sel_color = '#45475a'
        for r in range(r1, r2 + 1):
            sc = c1 if r == r1 else 0
            ec = c2 if r == r2 else self.cols - 1
            x1 = sc * self.cell_w
            y1 = r * self.cell_h
            x2 = (ec + 1) * self.cell_w
            y2 = (r + 1) * self.cell_h
            sid = self.canvas.create_rectangle(
                x1, y1, x2, y2, fill=sel_color, outline='',
                stipple='gray50', tags='sel'
            )
            self.sel_items.append(sid)
        self.canvas.tag_raise('cell')

    def pixel_to_cell(self, x, y):
        """Convert pixel coords to (row, col)."""
        col = max(0, min(x // self.cell_w, self.cols - 1))
        row = max(0, min(y // self.cell_h, self.rows - 1))
        return row, col

    def change_font_size(self, delta):
        """Adjust font size by delta points."""
        new_size = max(8, min(self.font_size + delta, 24))
        if new_size != self.font_size:
            self.font_size = new_size
            self._measure_font()
            self._setup_grid()
