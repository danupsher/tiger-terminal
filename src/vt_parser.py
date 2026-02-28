"""
VT100/xterm byte-at-a-time state machine parser.
Calls handler methods on a Screen object for each action.
"""

# States
GROUND = 0
ESCAPE = 1
ESCAPE_INTERMEDIATE = 2
CSI_ENTRY = 3
CSI_PARAM = 4
CSI_INTERMEDIATE = 5
OSC_STRING = 6
DCS_PASSTHROUGH = 7
UTF8 = 8

class VTParser:
    def __init__(self, screen):
        self.screen = screen
        self.state = GROUND
        self._params = ''
        self._intermediate = ''
        self._osc_data = bytearray()
        self._private = ''
        # UTF-8 decode state
        self._utf8_buf = bytearray()
        self._utf8_remaining = 0

    def feed(self, data):
        """Process raw bytes from the PTY."""
        if isinstance(data, str):
            data = data.encode('utf-8')
        for byte in data:
            self._process_byte(byte)

    def _process_byte(self, b):
        # Handle UTF-8 continuation bytes (only in GROUND state)
        if self._utf8_remaining > 0 and self.state == GROUND:
            if 0x80 <= b <= 0xBF:
                self._utf8_buf.append(b)
                self._utf8_remaining -= 1
                if self._utf8_remaining == 0:
                    try:
                        ch = bytes(self._utf8_buf).decode('utf-8')
                        self.screen.print_char(ch)
                    except UnicodeDecodeError:
                        self.screen.print_char('?')
                    self._utf8_buf.clear()
                return
            else:
                # Invalid continuation — discard and reprocess
                self._utf8_buf.clear()
                self._utf8_remaining = 0

        # ESC is handled specially: dispatch OSC/DCS first if active
        if b == 0x1B:
            if self.state == OSC_STRING:
                self._osc_finish()
            elif self.state == DCS_PASSTHROUGH:
                pass  # DCS has no dispatch
            self.state = ESCAPE
            self._params = ''
            self._intermediate = ''
            self._private = ''
            return

        # C0 controls (except in OSC/DCS where bytes are data)
        if self.state != OSC_STRING and self.state != DCS_PASSTHROUGH:
            if b == 0x07:  # BEL
                self.screen.execute(b)
                return
            if b == 0x08:  # BS
                self.screen.execute(b)
                return
            if b == 0x09:  # HT
                self.screen.execute(b)
                return
            if b == 0x0A or b == 0x0B or b == 0x0C:  # LF, VT, FF
                self.screen.execute(0x0A)
                return
            if b == 0x0D:  # CR
                self.screen.execute(b)
                return
            if b == 0x0E or b == 0x0F:  # SO/SI (charset switch, ignore)
                return

        if self.state == GROUND:
            self._ground(b)
        elif self.state == ESCAPE:
            self._escape(b)
        elif self.state == ESCAPE_INTERMEDIATE:
            self._escape_intermediate(b)
        elif self.state == CSI_ENTRY:
            self._csi_entry(b)
        elif self.state == CSI_PARAM:
            self._csi_param(b)
        elif self.state == CSI_INTERMEDIATE:
            self._csi_intermediate(b)
        elif self.state == OSC_STRING:
            self._osc_string(b)
        elif self.state == DCS_PASSTHROUGH:
            self._dcs_passthrough(b)

    def _ground(self, b):
        if b < 0x20:
            return  # unhandled C0
        if b == 0x7F:
            return  # DEL
        # UTF-8 lead byte detection
        if b >= 0xC0:
            if b < 0xE0:
                self._utf8_remaining = 1
            elif b < 0xF0:
                self._utf8_remaining = 2
            elif b < 0xF8:
                self._utf8_remaining = 3
            else:
                return  # invalid
            self._utf8_buf = bytearray([b])
            return
        # ASCII printable
        self.screen.print_char(chr(b))

    def _escape(self, b):
        if b == 0x5B:  # [  → CSI
            self.state = CSI_ENTRY
            self._params = ''
            self._intermediate = ''
            self._private = ''
            return
        if b == 0x5D:  # ]  → OSC
            self.state = OSC_STRING
            self._osc_data = bytearray()
            return
        if b == 0x50:  # P  → DCS
            self.state = DCS_PASSTHROUGH
            return
        if b == 0x58 or b == 0x5E or b == 0x5F:  # X, ^, _ — ignored strings
            self.state = OSC_STRING  # consume until ST
            self._osc_data = bytearray()
            return
        if 0x20 <= b <= 0x2F:  # intermediate
            self._intermediate = chr(b)
            self.state = ESCAPE_INTERMEDIATE
            return
        # Final byte — dispatch ESC sequence
        self.screen.esc_dispatch(self._intermediate, chr(b))
        self.state = GROUND

    def _escape_intermediate(self, b):
        if 0x20 <= b <= 0x2F:
            self._intermediate += chr(b)
            return
        if 0x30 <= b <= 0x7E:
            self.screen.esc_dispatch(self._intermediate, chr(b))
            self.state = GROUND
            return
        self.state = GROUND  # error

    def _csi_entry(self, b):
        if b == 0x3F or b == 0x3E or b == 0x21:  # ?, >, !
            self._private = chr(b)
            self.state = CSI_PARAM
            return
        # Fall through to CSI_PARAM
        self.state = CSI_PARAM
        self._csi_param(b)

    def _csi_param(self, b):
        if 0x30 <= b <= 0x3B:  # 0-9, ;, :
            self._params += chr(b)
            return
        if 0x20 <= b <= 0x2F:  # intermediate
            self._intermediate += chr(b)
            self.state = CSI_INTERMEDIATE
            return
        if 0x40 <= b <= 0x7E:  # final
            self._dispatch_csi(chr(b))
            self.state = GROUND
            return
        if b == 0x3F or b == 0x3E:  # late private marker
            self._private = chr(b)
            return
        self.state = GROUND  # error

    def _csi_intermediate(self, b):
        if 0x20 <= b <= 0x2F:
            self._intermediate += chr(b)
            return
        if 0x40 <= b <= 0x7E:
            self._dispatch_csi(chr(b))
            self.state = GROUND
            return
        self.state = GROUND

    def _dispatch_csi(self, final):
        params = []
        if self._params:
            for p in self._params.split(';'):
                if p == '':
                    params.append(0)
                else:
                    try:
                        params.append(int(p))
                    except ValueError:
                        params.append(0)
        self.screen.csi_dispatch(params, self._intermediate, final, self._private)

    def _osc_finish(self):
        """Decode accumulated OSC bytes as UTF-8 and dispatch."""
        try:
            data = bytes(self._osc_data).decode('utf-8')
        except UnicodeDecodeError:
            data = bytes(self._osc_data).decode('latin-1')
        self.screen.osc_dispatch(data)

    def _osc_string(self, b):
        if b == 0x07:  # BEL terminates OSC
            self._osc_finish()
            self.state = GROUND
            return
        # In UTF-8 mode, do NOT treat 0x9C as ST — it's a valid
        # continuation byte in multi-byte sequences.
        # ESC-based ST (\e\\) is handled in _process_byte.
        self._osc_data.append(b)

    def _dcs_passthrough(self, b):
        # ESC terminator handled in _process_byte
        self.state = GROUND
