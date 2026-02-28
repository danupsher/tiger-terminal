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


# ── Unicode drawing support ──
# Instead of relying on Monaco (which lacks many glyphs), we draw
# box-drawing, block elements, braille, and common symbols ourselves
# using canvas primitives.

def _build_box_draw_table():
    """Build lookup for U+2500-U+257F box-drawing characters.
    Returns dict mapping char -> (left, right, up, down).
    Values: 0=none, 1=light, 2=heavy."""
    t = {}
    def bd(cp, l, r, u, d):
        t[chr(cp)] = (l, r, u, d)

    # ── Light lines ──
    bd(0x2500, 1,1,0,0)  # ─
    bd(0x2502, 0,0,1,1)  # │
    bd(0x250C, 0,1,0,1)  # ┌
    bd(0x250E, 0,2,0,2)  # ┎ (heavy right+down)
    bd(0x2510, 1,0,0,1)  # ┐
    bd(0x2512, 2,0,0,2)  # ┒
    bd(0x2514, 0,1,1,0)  # └
    bd(0x2516, 0,2,2,0)  # ┖
    bd(0x2518, 1,0,1,0)  # ┘
    bd(0x251A, 2,0,2,0)  # ┚
    bd(0x251C, 0,1,1,1)  # ├
    bd(0x251E, 0,1,2,1)  # ┞
    bd(0x251F, 0,1,1,2)  # ┟
    bd(0x2520, 0,1,2,2)  # ┠
    bd(0x2521, 0,2,2,1)  # ┡
    bd(0x2522, 0,2,1,2)  # ┢
    bd(0x2524, 1,0,1,1)  # ┤
    bd(0x2526, 1,0,2,1)  # ┦
    bd(0x2527, 1,0,1,2)  # ┧
    bd(0x2528, 1,0,2,2)  # ┨
    bd(0x2529, 2,0,2,1)  # ┩
    bd(0x252A, 2,0,1,2)  # ┪
    bd(0x252C, 1,1,0,1)  # ┬
    bd(0x252E, 2,1,0,1)  # ┮
    bd(0x252F, 2,2,0,1)  # ┯
    bd(0x2530, 1,1,0,2)  # ┰
    bd(0x2531, 2,1,0,2)  # ┱
    bd(0x2532, 1,2,0,2)  # ┲
    bd(0x2534, 1,1,1,0)  # ┴
    bd(0x2536, 2,1,1,0)  # ┶
    bd(0x2537, 2,2,1,0)  # ┷
    bd(0x2538, 1,1,2,0)  # ┸
    bd(0x2539, 2,1,2,0)  # ┹
    bd(0x253A, 1,2,2,0)  # ┺
    bd(0x253C, 1,1,1,1)  # ┼
    bd(0x253E, 2,1,1,1)  # ┾
    bd(0x253F, 2,2,1,1)  # ┿
    bd(0x2540, 1,1,2,1)  # ╀
    bd(0x2541, 1,1,1,2)  # ╁
    bd(0x2542, 1,1,2,2)  # ╂
    bd(0x2543, 2,1,2,1)  # ╃
    bd(0x2544, 1,2,2,1)  # ╄
    bd(0x2545, 2,1,1,2)  # ╅
    bd(0x2546, 1,2,1,2)  # ╆
    bd(0x2547, 2,2,2,1)  # ╇
    bd(0x2548, 2,2,1,2)  # ╈
    bd(0x2549, 2,1,2,2)  # ╉
    bd(0x254A, 1,2,2,2)  # ╊
    bd(0x254B, 2,2,2,2)  # ╋

    # ── Heavy lines ──
    bd(0x2501, 2,2,0,0)  # ━
    bd(0x2503, 0,0,2,2)  # ┃
    bd(0x250F, 0,2,0,2)  # ┏
    bd(0x2511, 2,0,0,1)  # ┑
    bd(0x2513, 2,0,0,2)  # ┓
    bd(0x2515, 0,1,2,0)  # ┕
    bd(0x2517, 0,2,2,0)  # ┗
    bd(0x2519, 1,0,2,0)  # ┙
    bd(0x251B, 2,0,2,0)  # ┛
    bd(0x251D, 0,2,1,1)  # ┝
    bd(0x2523, 0,2,2,2)  # ┣
    bd(0x2525, 2,0,1,1)  # ┥
    bd(0x252B, 2,0,2,2)  # ┫
    bd(0x252D, 1,2,0,1)  # ┭
    bd(0x2533, 2,2,0,2)  # ┳
    bd(0x2535, 1,2,1,0)  # ┵
    bd(0x253B, 2,2,2,0)  # ┻
    bd(0x253D, 1,2,1,1)  # ┽

    # ── Double lines ──
    bd(0x2550, 2,2,0,0)  # ═
    bd(0x2551, 0,0,2,2)  # ║
    bd(0x2552, 0,2,0,1)  # ╒
    bd(0x2553, 0,1,0,2)  # ╓
    bd(0x2554, 0,2,0,2)  # ╔
    bd(0x2555, 2,0,0,1)  # ╕
    bd(0x2556, 1,0,0,2)  # ╖
    bd(0x2557, 2,0,0,2)  # ╗
    bd(0x2558, 0,2,1,0)  # ╘
    bd(0x2559, 0,1,2,0)  # ╙
    bd(0x255A, 0,2,2,0)  # ╚
    bd(0x255B, 2,0,1,0)  # ╛
    bd(0x255C, 1,0,2,0)  # ╜
    bd(0x255D, 2,0,2,0)  # ╝
    bd(0x255E, 0,2,1,1)  # ╞
    bd(0x255F, 0,1,2,2)  # ╟
    bd(0x2560, 0,2,2,2)  # ╠
    bd(0x2561, 2,0,1,1)  # ╡
    bd(0x2562, 1,0,2,2)  # ╢
    bd(0x2563, 2,0,2,2)  # ╣
    bd(0x2564, 2,2,0,1)  # ╤
    bd(0x2565, 1,1,0,2)  # ╥
    bd(0x2566, 2,2,0,2)  # ╦
    bd(0x2567, 2,2,1,0)  # ╧
    bd(0x2568, 1,1,2,0)  # ╨
    bd(0x2569, 2,2,2,0)  # ╩
    bd(0x256A, 2,2,1,1)  # ╪
    bd(0x256B, 1,1,2,2)  # ╫
    bd(0x256C, 2,2,2,2)  # ╬

    # ── Rounded corners ──
    bd(0x256D, 0,1,0,1)  # ╭
    bd(0x256E, 1,0,0,1)  # ╮
    bd(0x256F, 1,0,1,0)  # ╯
    bd(0x2570, 0,1,1,0)  # ╰

    # ── Dashed/dotted (render as solid) ──
    bd(0x2504, 1,1,0,0); bd(0x2505, 2,2,0,0)
    bd(0x2506, 0,0,1,1); bd(0x2507, 0,0,2,2)
    bd(0x2508, 1,1,0,0); bd(0x2509, 2,2,0,0)
    bd(0x250A, 0,0,1,1); bd(0x250B, 0,0,2,2)

    # ── Dashed double-dot ──
    bd(0x254C, 1,1,0,0); bd(0x254D, 2,2,0,0)
    bd(0x254E, 0,0,1,1); bd(0x254F, 0,0,2,2)

    # ── Diagonal (approximate as box) ──
    bd(0x2571, 1,0,0,1)  # ╱ (approx)
    bd(0x2572, 0,1,0,1)  # ╲ (approx)
    bd(0x2573, 1,1,1,1)  # ╳ (approx)

    # ── Single-segment lines U+2574-257F ──
    bd(0x2574, 1,0,0,0)  # ╴ light left
    bd(0x2575, 0,0,1,0)  # ╵ light up
    bd(0x2576, 0,1,0,0)  # ╶ light right
    bd(0x2577, 0,0,0,1)  # ╷ light down
    bd(0x2578, 2,0,0,0)  # ╸ heavy left
    bd(0x2579, 0,0,2,0)  # ╹ heavy up
    bd(0x257A, 0,2,0,0)  # ╺ heavy right
    bd(0x257B, 0,0,0,2)  # ╻ heavy down
    bd(0x257C, 1,2,0,0)  # ╼ light left heavy right
    bd(0x257D, 0,0,1,2)  # ╽ light up heavy down
    bd(0x257E, 2,1,0,0)  # ╾ heavy left light right
    bd(0x257F, 0,0,2,1)  # ╿ heavy up light down

    # ── Missing mixed connectors ──
    bd(0x250D, 0,2,0,1)  # ┍

    return t


def _build_block_table():
    """Build lookup for U+2580-U+259F block elements.
    Returns dict mapping char -> drawing spec."""
    t = {}
    # Lower blocks: ▁▂▃▄▅▆▇█
    for i in range(8):
        t[chr(0x2581 + i)] = ('bottom', (i + 1) / 8.0)
    t['▀'] = ('top', 0.5)      # ▀ upper half
    t['▄'] = ('bottom', 0.5)   # ▄ lower half (already in loop but explicit)
    t['█'] = ('bottom', 1.0)   # █ full block
    t['▌'] = ('left', 0.5)     # ▌ left half
    t['▐'] = ('right', 0.5)    # ▐ right half
    # Left blocks: ▉▊▋▌▍▎▏
    t['▉'] = ('left', 7/8)
    t['▊'] = ('left', 6/8)
    t['▋'] = ('left', 5/8)
    # 258C already done
    t['▍'] = ('left', 3/8)
    t['▎'] = ('left', 2/8)
    t['▏'] = ('left', 1/8)
    # Right blocks
    t['▐'] = ('right', 0.5)
    # Shade characters
    t['░'] = ('shade', 0.25)  # ░ light shade
    t['▒'] = ('shade', 0.5)   # ▒ medium shade
    t['▓'] = ('shade', 0.75)  # ▓ dark shade
    # Quadrant block characters U+2596-U+259F
    # Each is a tuple of which quadrants are filled: (UL, UR, LL, LR)
    t['\u2596'] = ('quadrant', (0,0,1,0))  # ▖ lower left
    t['\u2597'] = ('quadrant', (0,0,0,1))  # ▗ lower right
    t['\u2598'] = ('quadrant', (1,0,0,0))  # ▘ upper left
    t['\u2599'] = ('quadrant', (1,0,1,1))  # ▙ UL+LL+LR
    t['\u259A'] = ('quadrant', (1,0,0,1))  # ▚ UL+LR
    t['\u259B'] = ('quadrant', (1,1,1,0))  # ▛ UL+UR+LL
    t['\u259C'] = ('quadrant', (1,1,0,1))  # ▜ UL+UR+LR
    t['\u259D'] = ('quadrant', (0,1,0,0))  # ▝ upper right
    t['\u259E'] = ('quadrant', (0,1,1,0))  # ▞ UR+LL
    t['\u259F'] = ('quadrant', (0,1,1,1))  # ▟ UR+LL+LR
    return t


def _build_braille_table():
    """Braille patterns U+2800-U+28FF.
    Each of 256 patterns is a combination of 8 dots in a 2x4 grid.
    Returns dict mapping char -> list of (col, row) dot positions."""
    t = {}
    # Dot positions (col 0-1, row 0-3):
    # Bit 0: (0,0)  Bit 3: (1,0)
    # Bit 1: (0,1)  Bit 4: (1,1)
    # Bit 2: (0,2)  Bit 5: (1,2)
    # Bit 6: (0,3)  Bit 7: (1,3)
    dot_map = [
        (0, 0), (0, 1), (0, 2),  # bits 0,1,2
        (1, 0), (1, 1), (1, 2),  # bits 3,4,5
        (0, 3), (1, 3),          # bits 6,7
    ]
    for offset in range(256):
        dots = []
        for bit, (col, row) in enumerate(dot_map):
            if offset & (1 << bit):
                dots.append((col, row))
        t[chr(0x2800 + offset)] = dots
    return t


_BOX_DRAW = _build_box_draw_table()
_BLOCKS = _build_block_table()
_BRAILLE = _build_braille_table()

# Simple symbol replacements: chars we draw as basic shapes
# Maps char -> drawing type
_SYMBOLS = {}
# Bullets
for ch in '•‣●⬤':  # • ‣ ● ⬤
    _SYMBOLS[ch] = 'filled_circle'
for ch in '○◯◦':  # ○ ◯ ◦
    _SYMBOLS[ch] = 'circle'
# Triangles / arrows (draw as filled triangles)
for ch in '▶►▸‣➤':  # ▶ ► ▸ ‣ ➤
    _SYMBOLS[ch] = 'tri_right'
for ch in '◀◄◂':  # ◀ ◄ ◂
    _SYMBOLS[ch] = 'tri_left'
for ch in '▲▴':  # ▲ ▴
    _SYMBOLS[ch] = 'tri_up'
for ch in '▼▾':  # ▼ ▾
    _SYMBOLS[ch] = 'tri_down'
# Squares
for ch in '■▪◾':  # ■ ▪ ◾
    _SYMBOLS[ch] = 'filled_square'
for ch in '□▫◽◻':  # □ ▫ ◽ ☐
    _SYMBOLS[ch] = 'square'
# Diamonds
_SYMBOLS['◆'] = 'filled_diamond'  # ◆
_SYMBOLS['◇'] = 'diamond'  # ◇
# Checkmarks and crosses
_SYMBOLS['✓'] = 'checkmark'  # ✓
_SYMBOLS['✔'] = 'checkmark'  # ✔
_SYMBOLS['✕'] = 'cross'     # ✕
_SYMBOLS['✖'] = 'cross'     # ✖
_SYMBOLS['✗'] = 'cross'     # ✗
_SYMBOLS['✘'] = 'cross'     # ✘
# Arrows
_SYMBOLS['←'] = 'arrow_left'   # ←
_SYMBOLS['↑'] = 'arrow_up'     # ↑
_SYMBOLS['→'] = 'arrow_right'  # →
_SYMBOLS['↓'] = 'arrow_down'   # ↓
# Powerline
_SYMBOLS[''] = 'tri_right'   # branch
_SYMBOLS[''] = 'filled_square'  # lock
_SYMBOLS[''] = 'filled_square'  # column
_SYMBOLS[''] = 'tri_right'   # right arrow solid
_SYMBOLS[''] = 'tri_right'   # right arrow line
_SYMBOLS[''] = 'tri_left'    # left arrow solid
_SYMBOLS[''] = 'tri_left'    # left arrow line
# Stars
_SYMBOLS['★'] = 'filled_diamond'  # ★
_SYMBOLS['☆'] = 'diamond'         # ☆
# Ellipsis
_SYMBOLS['…'] = 'ellipsis'  # …
# Ballot boxes (used by Claude Code for checkboxes)
_SYMBOLS['\u2610'] = 'square'          # ☐ ballot box
_SYMBOLS['\u2612'] = 'cross_in_square' # ☒ ballot box with X
# Angle brackets
_SYMBOLS['\u276F'] = 'angle_right'     # ❯ heavy right-pointing angle
_SYMBOLS['\u276E'] = 'angle_left'      # ❮ heavy left-pointing angle
# More geometric shapes
_SYMBOLS['\u25C9'] = 'bullseye'  # ◉ fisheye
_SYMBOLS['\u25CA'] = 'diamond'   # ◊ lozenge
_SYMBOLS['\u25CE'] = 'bullseye'  # ◎ bullseye
_SYMBOLS['\u25CC'] = 'circle'    # ◌ dotted circle
_SYMBOLS['\u25B5'] = 'tri_up'    # ▵ white up triangle
_SYMBOLS['\u25BF'] = 'tri_down'  # ▿ white down triangle
_SYMBOLS['\u25B9'] = 'tri_right' # ▹ white right triangle
_SYMBOLS['\u25C3'] = 'tri_left'  # ◃ white left triangle
_SYMBOLS['\u25B3'] = 'tri_up'    # △ white up triangle
_SYMBOLS['\u25BD'] = 'tri_down'  # ▽ white down triangle
# Warning/misc
_SYMBOLS['\u26A0'] = 'tri_up'    # ⚠ warning sign
_SYMBOLS['\u2758'] = 'vbar'      # ❘ light vertical bar
# Hamburger menu
_SYMBOLS['\u2630'] = 'hamburger' # ☰ trigram
# More geometric shapes Claude Code uses
_SYMBOLS['\u25AD'] = 'square'          # ▭ white rectangle
_SYMBOLS['\u25AE'] = 'filled_square'   # ▮ filled rectangle
_SYMBOLS['\u25B1'] = 'square'          # ▱ white parallelogram
_SYMBOLS['\u25D0'] = 'filled_circle'   # ◐ half circle
_SYMBOLS['\u25D1'] = 'filled_circle'   # ◑ half circle
_SYMBOLS['\u25D2'] = 'filled_circle'   # ◒ half circle
_SYMBOLS['\u25D3'] = 'filled_circle'   # ◓ half circle
_SYMBOLS['\u25EC'] = 'tri_up'          # ◬ triangle with dot
_SYMBOLS['\u25F8'] = 'tri_up'          # ◸ upper left triangle
_SYMBOLS['\u25F9'] = 'tri_up'          # ◹ upper right triangle
_SYMBOLS['\u25FA'] = 'tri_down'        # ◺ lower left triangle
_SYMBOLS['\u25FC'] = 'filled_square'   # ◼ black medium square
# Card suits
_SYMBOLS['\u2660'] = 'filled_diamond'  # ♠ spade
_SYMBOLS['\u2663'] = 'filled_diamond'  # ♣ club
_SYMBOLS['\u2665'] = 'filled_circle'   # ♥ heart
_SYMBOLS['\u2666'] = 'filled_diamond'  # ♦ diamond
# Music notes (draw as filled circle with stem)
_SYMBOLS['\u266A'] = 'filled_circle'   # ♪
_SYMBOLS['\u266B'] = 'filled_circle'   # ♫
# Misc symbols
_SYMBOLS['\u260E'] = 'filled_square'   # ☎ phone
_SYMBOLS['\u263A'] = 'circle'          # ☺ smiley
_SYMBOLS['\u2640'] = 'circle'          # ♀ female
_SYMBOLS['\u2642'] = 'circle'          # ♂ male
# Emoji-style (draw as their base shape)
_SYMBOLS['\u2705'] = 'checkmark'       # ✅ check mark
_SYMBOLS['\u274C'] = 'cross'           # ❌ cross mark
# Ornamental
_SYMBOLS['\u2720'] = 'cross'           # ✠ maltese cross
_SYMBOLS['\u2722'] = 'filled_diamond'  # ✢ star
_SYMBOLS['\u2733'] = 'cross'           # ✳ asterisk
_SYMBOLS['\u2736'] = 'filled_diamond'  # ✶ star
_SYMBOLS['\u273B'] = 'cross'           # ✻ teardrop asterisk
_SYMBOLS['\u273D'] = 'cross'           # ✽ heavy teardrop asterisk
# Brackets
_SYMBOLS['\u2772'] = 'angle_left'      # ❲ light tortoise shell bracket
_SYMBOLS['\u2773'] = 'angle_right'     # ❳ light tortoise shell bracket
# Single-quote angle brackets (General Punctuation — outside geometric range)
# Media control triangles (U+23F4-23F9)
_SYMBOLS['\u23F4'] = 'tri_left'        # ⏴ reverse/rewind
_SYMBOLS['\u23F5'] = 'tri_right'       # ⏵ play/forward
_SYMBOLS['\u23F6'] = 'tri_up'          # ⏶ increase
_SYMBOLS['\u23F7'] = 'tri_down'        # ⏷ decrease
_SYMBOLS['\u23F8'] = 'vbar'            # ⏸ pause (two bars)
_SYMBOLS['\u23F9'] = 'filled_square'   # ⏹ stop
_SYMBOLS['\u23FA'] = 'filled_circle'   # ⏺ record
_SYMBOLS['\u203A'] = 'angle_right'     # › single right-pointing angle quotation mark
_SYMBOLS['\u2039'] = 'angle_left'      # ‹ single left-pointing angle quotation mark
_SYMBOLS['\u00BB'] = 'angle_right'     # » right-pointing double angle quotation mark
_SYMBOLS['\u00AB'] = 'angle_left'      # « left-pointing double angle quotation mark
# Letterlike symbols
_SYMBOLS['\u2139'] = 'circle'          # ℹ information source
# Hexagons (draw as filled diamond)
_SYMBOLS['\u2B22'] = 'filled_diamond'  # ⬢ black hexagon
_SYMBOLS['\u2B23'] = 'diamond'         # ⬣ white hexagon
# Ticks/crosses in various forms (Dingbats range)
_SYMBOLS['\u2713'] = 'checkmark'       # ✓ check mark
_SYMBOLS['\u2717'] = 'cross'           # ✗ ballot X
_SYMBOLS['\u2718'] = 'cross'           # ✘ heavy ballot X
_SYMBOLS['\u2714'] = 'checkmark'       # ✔ heavy check mark
# Circled letters (Claude Code uses ⓧ and Ⓘ)
_SYMBOLS['\u24E7'] = 'cross_in_square' # ⓧ circled latin small letter x
_SYMBOLS['\u24D8'] = 'circle'          # ⓘ circled latin small letter i
# Double exclamation
_SYMBOLS['\u203C'] = 'vbar'            # ‼ double exclamation mark
# Bullet operator
_SYMBOLS['\u2219'] = 'filled_circle'   # ∙ bullet operator
# Misc math operators that might appear
_SYMBOLS['\u2261'] = 'hamburger'       # ≡ identical to (used as hamburger fallback)

def _is_custom_drawn(ch):
    """Check if a character should be custom-drawn."""
    if ch in _BOX_DRAW or ch in _BLOCKS or ch in _BRAILLE or ch in _SYMBOLS:
        return True
    # Fallback: any char in ranges Monaco can't render
    cp = ord(ch)
    if 0x25A0 <= cp <= 0x25FF:  # geometric shapes
        return True
    if 0x2600 <= cp <= 0x27BF:  # misc symbols, dingbats
        return True
    if 0x2B00 <= cp <= 0x2BFF:  # misc symbols and arrows
        return True
    if 0x2900 <= cp <= 0x297F:  # supplemental arrows
        return True
    if 0x2980 <= cp <= 0x29FF:  # misc math symbols
        return True
    if 0x2190 <= cp <= 0x21FF:  # arrows
        return True
    if 0x2300 <= cp <= 0x23FF:  # misc technical (media controls etc)
        return True
    return False


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
        # Box-drawing canvas items
        self.box_items = {}  # (row, col) -> [item_ids]

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
        self._scroll_render_id = None  # throttle timer for scroll rendering

        # Ring buffer scroll state
        self._ring_top = 0  # cumulative pixel offset applied to canvas items
        self._last_scroll_offset = None  # previous scroll_offset (None = not in scrollback)

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
        self.canvas.delete('box')
        self._ring_top = 0
        self._last_scroll_offset = None
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
                    anchor='nw', fill=self.default_fg,
                    tags=('cell', 'r%d' % r)
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
                        bkey = (r, c)
                        if bkey in self.box_items:
                            for bid in self.box_items[bkey]:
                                self.canvas.delete(bid)
                            del self.box_items[bkey]
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
                                fill=eff_bg, outline='',
                                tags=('bgr', 'r%d' % r))
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

                # Custom-drawn Unicode characters
                bkey = (r, c)
                if _is_custom_drawn(ch):
                    tid = self.text_items[r][c]
                    self.canvas.itemconfigure(tid, text='')
                    self._draw_custom_char(r, c, ch, eff_fg, eff_bg)
                else:
                    if bkey in self.box_items:
                        for bid in self.box_items[bkey]:
                            self.canvas.delete(bid)
                        del self.box_items[bkey]
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
                            lx1, ly, lx2, ly, fill=eff_fg,
                            tags=('decor', 'r%d' % r))
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
                            fill=eff_bg, outline='',
                            tags=('bgr', 'r%d' % r)
                        )
                        self.bg_items[key] = bid
                        self.canvas.tag_lower('bgr')
                elif key in self.bg_items:
                    self.canvas.delete(self.bg_items[key])
                    del self.bg_items[key]

        self._update_cursor()

    def _draw_custom_char(self, r, c, ch, fg, bg):
        """Draw a custom Unicode character using canvas primitives."""
        key = (r, c)
        if key in self.box_items:
            for bid in self.box_items[key]:
                self.canvas.delete(bid)

        cw = self.cell_w
        ch_ = self.cell_h
        x = c * cw
        y = r * ch_
        mx = x + cw // 2
        my = y + ch_ // 2
        items = []
        cv = self.canvas

        if ch in _BOX_DRAW:
            left, right, up, down = _BOX_DRAW[ch]
            if left:
                w = 2 if left == 2 else 1
                items.append(cv.create_line(x, my, mx + 1, my, fill=fg, width=w))
            if right:
                w = 2 if right == 2 else 1
                items.append(cv.create_line(mx, my, x + cw, my, fill=fg, width=w))
            if up:
                w = 2 if up == 2 else 1
                items.append(cv.create_line(mx, y, mx, my + 1, fill=fg, width=w))
            if down:
                w = 2 if down == 2 else 1
                items.append(cv.create_line(mx, my, mx, y + ch_, fill=fg, width=w))

        elif ch in _BLOCKS:
            kind, frac = _BLOCKS[ch]
            if kind == 'bottom':
                h = int(ch_ * frac)
                items.append(cv.create_rectangle(x, y + ch_ - h, x + cw, y + ch_,
                             fill=fg, outline=''))
            elif kind == 'top':
                h = int(ch_ * frac)
                items.append(cv.create_rectangle(x, y, x + cw, y + h,
                             fill=fg, outline=''))
            elif kind == 'left':
                w = int(cw * frac)
                items.append(cv.create_rectangle(x, y, x + w, y + ch_,
                             fill=fg, outline=''))
            elif kind == 'right':
                w = int(cw * frac)
                items.append(cv.create_rectangle(x + cw - w, y, x + cw, y + ch_,
                             fill=fg, outline=''))
            elif kind == 'shade':
                # Draw shade as a semi-dense pattern of dots
                step = max(2, int(4 - frac * 3))
                for dy in range(0, ch_, step):
                    for dx in range(0, cw, step):
                        items.append(cv.create_rectangle(
                            x + dx, y + dy, x + dx + 1, y + dy + 1,
                            fill=fg, outline=''))
            elif kind == 'quadrant':
                ul, ur, ll, lr = frac
                hw = cw // 2
                hh = ch_ // 2
                if ul:
                    items.append(cv.create_rectangle(x, y, x + hw, y + hh,
                                 fill=fg, outline=''))
                if ur:
                    items.append(cv.create_rectangle(x + hw, y, x + cw, y + hh,
                                 fill=fg, outline=''))
                if ll:
                    items.append(cv.create_rectangle(x, y + hh, x + hw, y + ch_,
                                 fill=fg, outline=''))
                if lr:
                    items.append(cv.create_rectangle(x + hw, y + hh, x + cw, y + ch_,
                                 fill=fg, outline=''))

        elif ch in _BRAILLE:
            dots = _BRAILLE[ch]
            # 2 columns, 4 rows of dots within the cell
            dot_w = cw / 4
            dot_h = ch_ / 8
            pad_x = cw / 4
            pad_y = ch_ / 8
            for col, row in dots:
                dx = x + pad_x + col * (cw - 2 * pad_x)
                dy = y + pad_y + row * (ch_ - 2 * pad_y) / 3
                r2 = max(1, min(dot_w, dot_h) * 0.4)
                items.append(cv.create_oval(
                    dx - r2, dy - r2, dx + r2, dy + r2,
                    fill=fg, outline=''))

        elif ch in _SYMBOLS:
            kind = _SYMBOLS[ch]
            m = min(cw, ch_)
            pad = m // 5

            if kind == 'filled_circle':
                r2 = m // 2 - pad
                items.append(cv.create_oval(mx-r2, my-r2, mx+r2, my+r2,
                             fill=fg, outline=''))
            elif kind == 'circle':
                r2 = m // 2 - pad
                items.append(cv.create_oval(mx-r2, my-r2, mx+r2, my+r2,
                             fill='', outline=fg))
            elif kind == 'tri_right':
                items.append(cv.create_polygon(
                    x+pad, y+pad, x+cw-pad, my, x+pad, y+ch_-pad,
                    fill=fg, outline=''))
            elif kind == 'tri_left':
                items.append(cv.create_polygon(
                    x+cw-pad, y+pad, x+pad, my, x+cw-pad, y+ch_-pad,
                    fill=fg, outline=''))
            elif kind == 'tri_up':
                items.append(cv.create_polygon(
                    mx, y+pad, x+cw-pad, y+ch_-pad, x+pad, y+ch_-pad,
                    fill=fg, outline=''))
            elif kind == 'tri_down':
                items.append(cv.create_polygon(
                    x+pad, y+pad, x+cw-pad, y+pad, mx, y+ch_-pad,
                    fill=fg, outline=''))
            elif kind == 'filled_square':
                items.append(cv.create_rectangle(
                    x+pad, y+pad, x+cw-pad, y+ch_-pad,
                    fill=fg, outline=''))
            elif kind == 'square':
                items.append(cv.create_rectangle(
                    x+pad, y+pad, x+cw-pad, y+ch_-pad,
                    fill='', outline=fg))
            elif kind == 'filled_diamond':
                items.append(cv.create_polygon(
                    mx, y+pad, x+cw-pad, my, mx, y+ch_-pad, x+pad, my,
                    fill=fg, outline=''))
            elif kind == 'diamond':
                items.append(cv.create_polygon(
                    mx, y+pad, x+cw-pad, my, mx, y+ch_-pad, x+pad, my,
                    fill='', outline=fg))
            elif kind == 'checkmark':
                items.append(cv.create_line(
                    x+pad, my, mx-1, y+ch_-pad-1, fill=fg, width=2))
                items.append(cv.create_line(
                    mx-1, y+ch_-pad-1, x+cw-pad, y+pad+1, fill=fg, width=2))
            elif kind == 'cross':
                items.append(cv.create_line(
                    x+pad, y+pad, x+cw-pad, y+ch_-pad, fill=fg, width=2))
                items.append(cv.create_line(
                    x+cw-pad, y+pad, x+pad, y+ch_-pad, fill=fg, width=2))
            elif kind == 'arrow_right':
                items.append(cv.create_line(x+pad, my, x+cw-pad, my, fill=fg, width=1))
                items.append(cv.create_line(
                    mx+1, y+pad+2, x+cw-pad, my, fill=fg, width=1))
                items.append(cv.create_line(
                    mx+1, y+ch_-pad-2, x+cw-pad, my, fill=fg, width=1))
            elif kind == 'arrow_left':
                items.append(cv.create_line(x+pad, my, x+cw-pad, my, fill=fg, width=1))
                items.append(cv.create_line(
                    x+pad, my, mx-1, y+pad+2, fill=fg, width=1))
                items.append(cv.create_line(
                    x+pad, my, mx-1, y+ch_-pad-2, fill=fg, width=1))
            elif kind == 'arrow_up':
                items.append(cv.create_line(mx, y+pad, mx, y+ch_-pad, fill=fg, width=1))
                items.append(cv.create_line(
                    mx, y+pad, x+pad+2, my-1, fill=fg, width=1))
                items.append(cv.create_line(
                    mx, y+pad, x+cw-pad-2, my-1, fill=fg, width=1))
            elif kind == 'arrow_down':
                items.append(cv.create_line(mx, y+pad, mx, y+ch_-pad, fill=fg, width=1))
                items.append(cv.create_line(
                    mx, y+ch_-pad, x+pad+2, my+1, fill=fg, width=1))
                items.append(cv.create_line(
                    mx, y+ch_-pad, x+cw-pad-2, my+1, fill=fg, width=1))
            elif kind == 'ellipsis':
                dot_r = max(1, m // 8)
                for dx_off in [-cw//3, 0, cw//3]:
                    cx = mx + dx_off
                    items.append(cv.create_oval(
                        cx-dot_r, my+ch_//6-dot_r, cx+dot_r, my+ch_//6+dot_r,
                        fill=fg, outline=''))
            elif kind == 'cross_in_square':
                items.append(cv.create_rectangle(
                    x+pad, y+pad, x+cw-pad, y+ch_-pad,
                    fill='', outline=fg))
                items.append(cv.create_line(
                    x+pad+1, y+pad+1, x+cw-pad-1, y+ch_-pad-1, fill=fg, width=1))
                items.append(cv.create_line(
                    x+cw-pad-1, y+pad+1, x+pad+1, y+ch_-pad-1, fill=fg, width=1))
            elif kind == 'angle_right':
                items.append(cv.create_line(
                    x+pad, y+pad+2, x+cw-pad, my, fill=fg, width=2))
                items.append(cv.create_line(
                    x+cw-pad, my, x+pad, y+ch_-pad-2, fill=fg, width=2))
            elif kind == 'angle_left':
                items.append(cv.create_line(
                    x+cw-pad, y+pad+2, x+pad, my, fill=fg, width=2))
                items.append(cv.create_line(
                    x+pad, my, x+cw-pad, y+ch_-pad-2, fill=fg, width=2))
            elif kind == 'bullseye':
                r2 = m // 2 - pad
                r3 = max(1, r2 // 2)
                items.append(cv.create_oval(mx-r2, my-r2, mx+r2, my+r2,
                             fill='', outline=fg))
                items.append(cv.create_oval(mx-r3, my-r3, mx+r3, my+r3,
                             fill=fg, outline=''))
            elif kind == 'vbar':
                items.append(cv.create_line(mx, y+pad, mx, y+ch_-pad,
                             fill=fg, width=1))
            elif kind == 'hamburger':
                for dy_off in [-ch_//4, 0, ch_//4]:
                    items.append(cv.create_line(
                        x+pad, my+dy_off, x+cw-pad, my+dy_off,
                        fill=fg, width=1))

        if not items:
            # Fallback: draw a small dot for any unhandled custom char
            dot_r = max(1, min(cw, ch_) // 6)
            items.append(cv.create_oval(mx-dot_r, my-dot_r, mx+dot_r, my+dot_r,
                         fill=fg, outline=''))

        self.box_items[key] = items
        row_tag = 'r%d' % r
        for item in items:
            cv.addtag_withtag('box', item)
            cv.addtag_withtag(row_tag, item)
        # Ensure custom items render above background rectangles
        if self.bg_items:
            for item in items:
                try:
                    self.canvas.tag_raise(item, 'bgr')
                except Exception:
                    pass

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

    def _reset_ring_positions(self):
        """Reposition all canvas items back to their natural row positions."""
        if self._ring_top == 0:
            return
        cv = self.canvas
        cell_h = self.cell_h
        for r in range(self.rows):
            natural_y = r * cell_h
            # Get current position of first text item in this row
            tid = self.text_items[r][0]
            coords = cv.coords(tid)
            if coords:
                current_y = coords[1]
                dy = natural_y - current_y
                if dy != 0:
                    cv.move('r%d' % r, 0, dy)
        self._ring_top = 0
        self._last_scroll_offset = None

    def scroll_up(self, lines=3):
        max_offset = len(self.screen.scrollback)
        self.scroll_offset = min(self.scroll_offset + lines, max_offset)
        if self.scroll_offset > 0:
            self._schedule_scroll_render()

    def scroll_down(self, lines=3):
        self.scroll_offset = max(self.scroll_offset - lines, 0)
        if self.scroll_offset == 0:
            self._cancel_scroll_render()
            self._reset_ring_positions()
            for r in range(self.rows):
                for c in range(self.cols):
                    self.displayed[r][c] = None
            self.screen._mark_all_dirty()
            self.render()
        else:
            self._schedule_scroll_render()

    def _schedule_scroll_render(self):
        """Coalesce rapid scroll events — render at most every 40ms."""
        if self._scroll_render_id is None:
            self._scroll_render_id = self.canvas.after(
                40, self._do_scroll_render)

    def _cancel_scroll_render(self):
        if self._scroll_render_id is not None:
            self.canvas.after_cancel(self._scroll_render_id)
            self._scroll_render_id = None

    def _do_scroll_render(self):
        self._scroll_render_id = None
        if self.scroll_offset <= 0:
            return
        scr = self.screen
        sb_len = len(scr.scrollback)
        grid_len = len(scr.grid)
        total = sb_len + grid_len
        view_top = max(total - self.scroll_offset - self.rows, 0)

        if self._last_scroll_offset is None:
            # First scroll into scrollback — full render
            self._render_scrollback()
            self._last_scroll_offset = self.scroll_offset
            self._last_view_top = view_top
            return

        prev_view_top = self._last_view_top
        delta = prev_view_top - view_top  # positive = scrolled up, negative = scrolled down

        if delta == 0:
            return

        if abs(delta) >= self.rows:
            # Large jump — full render fallback
            self._render_scrollback()
            self._last_scroll_offset = self.scroll_offset
            self._last_view_top = view_top
            return

        self._render_scrollback_ring(delta, view_top, total, sb_len)
        self._last_scroll_offset = self.scroll_offset
        self._last_view_top = view_top

    def _render_scrollback_ring(self, delta, view_top, total, sb_len):
        """Ring buffer scroll: bulk-move existing items, render only new rows."""
        cv = self.canvas
        scr = self.screen
        sb = scr.scrollback
        rows = self.rows
        cell_h = self.cell_h
        cell_w = self.cell_w
        font_spec = (self.font_family, self.font_size)
        default_fg = self.default_fg
        default_bg = self.default_bg
        displayed = self.displayed

        # Pixel shift for the delta
        dy = delta * cell_h

        # 1. Bulk move ALL tagged items
        cv.move('cell', 0, dy)
        cv.move('bgr', 0, dy)
        cv.move('decor', 0, dy)
        cv.move('box', 0, dy)
        if self.cursor_item:
            cv.move('cursor', 0, dy)
        self._ring_top += dy

        # 2. Identify recycled rows — rows that moved off-screen
        #    and need to wrap around to the other end
        if delta > 0:
            # Scrolled up: bottom rows moved off-screen below, wrap to top
            # New content appears at top (rows 0..delta-1)
            recycled = list(range(rows - delta, rows))
            new_rows = list(range(0, delta))
        else:
            # Scrolled down: top rows moved off-screen above, wrap to bottom
            # New content appears at bottom (rows rows+delta..rows-1)
            recycled = list(range(0, -delta))
            new_rows = list(range(rows + delta, rows))

        # 3. Reposition recycled rows to their new screen positions
        for i, old_r in enumerate(recycled):
            target_r = new_rows[i]
            target_y = target_r * cell_h
            # Get current y of this row's first text item
            coords = cv.coords(self.text_items[old_r][0])
            if coords:
                current_y = coords[1]
                wrap_dy = target_y - current_y
                if wrap_dy != 0:
                    cv.move('r%d' % old_r, 0, wrap_dy)

        # 4. Clean up old items on recycled rows and render new content
        for i, old_r in enumerate(recycled):
            target_r = new_rows[i]
            src_idx = view_top + target_r

            # Clean bg_items, line_items, box_items for this visual row
            for c in range(self.cols):
                bkey = (old_r, c)
                if bkey in self.bg_items:
                    cv.delete(self.bg_items[bkey])
                    del self.bg_items[bkey]
                if bkey in self.line_items:
                    cv.delete(self.line_items[bkey])
                    del self.line_items[bkey]
                if bkey in self.box_items:
                    for bid in self.box_items[bkey]:
                        cv.delete(bid)
                    del self.box_items[bkey]

            # Render new content on this row
            if src_idx < 0 or src_idx >= total:
                for c in range(self.cols):
                    cache_key = (' ', default_fg, None, 0)
                    displayed[old_r][c] = cache_key
                    cv.itemconfigure(self.text_items[old_r][c],
                                     text=' ', fill=default_fg, font=font_spec)
                continue

            if src_idx < sb_len:
                row_data = sb[src_idx]
            else:
                row_data = scr.grid[src_idx - sb_len]
            row_len = len(row_data)

            for c in range(self.cols):
                if c < row_len:
                    cell = row_data[c]
                    ch, fg, bg, attrs = cell[0], cell[1], cell[2], cell[3]
                else:
                    ch, fg, bg, attrs = ' ', None, None, 0

                eff_fg = fg or default_fg
                eff_bg = bg
                if attrs & ATTR_REVERSE:
                    eff_fg, eff_bg = (eff_bg or default_bg), eff_fg
                if attrs & ATTR_BOLD and fg is None and not (attrs & ATTR_REVERSE):
                    eff_fg = '#ffffff'

                displayed[old_r][c] = (ch, eff_fg, eff_bg, attrs)

                # Render text or custom-drawn char
                if _is_custom_drawn(ch):
                    cv.itemconfigure(self.text_items[old_r][c], text='')
                    self._draw_custom_char(old_r, c, ch, eff_fg, eff_bg)
                else:
                    cv.itemconfigure(self.text_items[old_r][c],
                                     text=ch, fill=eff_fg, font=font_spec)

                # Render background
                bkey = (old_r, c)
                if eff_bg and eff_bg != default_bg:
                    x = c * cell_w
                    y = target_r * cell_h
                    bid = cv.create_rectangle(
                        x, y, x + cell_w, y + cell_h,
                        fill=eff_bg, outline='',
                        tags=('bgr', 'r%d' % old_r)
                    )
                    self.bg_items[bkey] = bid
                    cv.tag_lower('bgr')

        # Also reposition non-recycled rows' display cache mapping
        # (the text_items grid indices stay the same — they track visual rows)

        # Hide cursor in scrollback view
        if self.cursor_item:
            cv.itemconfigure(self.cursor_item, state='hidden')

    def snap_to_bottom(self):
        if self.scroll_offset > 0:
            self.scroll_offset = 0
            self._cancel_scroll_render()
            self._reset_ring_positions()
            for r in range(self.rows):
                for c in range(self.cols):
                    self.displayed[r][c] = None
            self.screen._mark_all_dirty()

    def _render_scrollback(self):
        """Render scrollback view. Skips custom char drawing for speed
        and uses display cache to skip unchanged cells."""
        self._reset_ring_positions()
        scr = self.screen
        sb = scr.scrollback
        offset = self.scroll_offset
        sb_len = len(sb)
        grid_len = len(scr.grid)
        total = sb_len + grid_len
        view_bottom = total - offset
        view_top = max(view_bottom - self.rows, 0)

        font_spec = (self.font_family, self.font_size)
        displayed = self.displayed
        default_fg = self.default_fg
        default_bg = self.default_bg

        for vr in range(self.rows):
            src_idx = view_top + vr
            if src_idx < 0 or src_idx >= total:
                for c in range(self.cols):
                    cache_key = (' ', default_fg, None, 0)
                    if displayed[vr][c] == cache_key:
                        continue
                    displayed[vr][c] = cache_key
                    self.canvas.itemconfigure(self.text_items[vr][c],
                                              text=' ', fill=default_fg, font=font_spec)
                    bkey = (vr, c)
                    if bkey in self.box_items:
                        for bid in self.box_items[bkey]:
                            self.canvas.delete(bid)
                        del self.box_items[bkey]
                    if bkey in self.bg_items:
                        self.canvas.delete(self.bg_items[bkey])
                        del self.bg_items[bkey]
                continue

            # Index into scrollback or grid without concatenating lists
            if src_idx < sb_len:
                row_data = sb[src_idx]
            else:
                row_data = scr.grid[src_idx - sb_len]
            row_len = len(row_data)

            for c in range(self.cols):
                if c < row_len:
                    cell = row_data[c]
                    ch, fg, bg, attrs = cell[0], cell[1], cell[2], cell[3]
                else:
                    ch, fg, bg, attrs = ' ', None, None, 0

                eff_fg = fg or default_fg
                eff_bg = bg
                if attrs & ATTR_REVERSE:
                    eff_fg, eff_bg = (eff_bg or default_bg), eff_fg
                if attrs & ATTR_BOLD and fg is None and not (attrs & ATTR_REVERSE):
                    eff_fg = '#ffffff'

                cache_key = (ch, eff_fg, eff_bg, attrs)
                if displayed[vr][c] == cache_key:
                    continue
                displayed[vr][c] = cache_key

                # Clean up any box-drawing items from previous render
                bkey = (vr, c)
                if bkey in self.box_items:
                    for bid in self.box_items[bkey]:
                        self.canvas.delete(bid)
                    del self.box_items[bkey]

                # Custom-drawn chars or text
                if _is_custom_drawn(ch):
                    self.canvas.itemconfigure(self.text_items[vr][c], text='')
                    self._draw_custom_char(vr, c, ch, eff_fg, eff_bg)
                else:
                    self.canvas.itemconfigure(self.text_items[vr][c],
                                              text=ch, fill=eff_fg, font=font_spec)

                if eff_bg and eff_bg != default_bg:
                    x = c * self.cell_w
                    y = vr * self.cell_h
                    if bkey in self.bg_items:
                        self.canvas.itemconfigure(self.bg_items[bkey], fill=eff_bg)
                    else:
                        bid = self.canvas.create_rectangle(
                            x, y, x + self.cell_w, y + self.cell_h,
                            fill=eff_bg, outline='',
                            tags=('bgr', 'r%d' % vr)
                        )
                        self.bg_items[bkey] = bid
                        self.canvas.tag_lower('bgr')
                elif bkey in self.bg_items:
                    self.canvas.delete(self.bg_items[bkey])
                    del self.bg_items[bkey]

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
