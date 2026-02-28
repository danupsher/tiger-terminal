"""
PTY shell backend. Forks a real shell behind a PTY,
streams output via a callback, and accepts input.
"""
import os, pty, fcntl, termios, struct, signal, select, threading

class PTYShell:
    def __init__(self, on_output, shell=None, cols=80, rows=24):
        self.on_output = on_output
        self.cols = cols
        self.rows = rows
        self._shell = shell or os.environ.get('SHELL', '/bin/bash')
        self._master_fd = None
        self._pid = None
        self._reader = None
        self._alive = False

    @property
    def is_alive(self):
        if self._alive and self._pid:
            try:
                pid, status = os.waitpid(self._pid, os.WNOHANG)
                if pid != 0:
                    self._alive = False
            except ChildProcessError:
                self._alive = False
        return self._alive

    def start(self):
        env = dict(os.environ)
        env['TERM'] = 'xterm-256color'
        env['COLORTERM'] = 'truecolor'
        env['COLUMNS'] = str(self.cols)
        env['LINES'] = str(self.rows)
        env['LANG'] = 'en_US.UTF-8'
        env['LC_ALL'] = 'en_US.UTF-8'

        pid, master_fd = pty.fork()
        if pid == 0:
            # Start shell in user's home, not inside the .app bundle
            try:
                os.chdir(os.path.expanduser('~'))
            except OSError:
                pass
            self._set_winsize_fd(0, self.rows, self.cols)
            os.execve(self._shell, [self._shell, '--login'], env)
            os._exit(1)

        self._pid = pid
        self._master_fd = master_fd
        self._alive = True
        self._set_winsize_fd(master_fd, self.rows, self.cols)

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _set_winsize_fd(self, fd, rows, cols):
        try:
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

    def resize(self, rows, cols):
        self.rows, self.cols = rows, cols
        if self._master_fd:
            self._set_winsize_fd(self._master_fd, rows, cols)
            if self._pid:
                try:
                    os.kill(self._pid, signal.SIGWINCH)
                except Exception:
                    pass

    def _read_loop(self):
        while self._alive:
            try:
                r, _, _ = select.select([self._master_fd], [], [], 0.05)
                if r:
                    data = os.read(self._master_fd, 16384)
                    if data:
                        self.on_output(data)
                    else:
                        break
            except OSError:
                break
        self._alive = False

    def write(self, data):
        if self._master_fd and self._alive:
            if isinstance(data, str):
                data = data.encode('utf-8', errors='replace')
            try:
                os.write(self._master_fd, data)
            except OSError:
                pass

    def stop(self):
        self._alive = False
        if self._pid:
            try:
                os.kill(self._pid, signal.SIGHUP)
            except Exception:
                pass
        if self._master_fd:
            try:
                os.close(self._master_fd)
            except Exception:
                pass
