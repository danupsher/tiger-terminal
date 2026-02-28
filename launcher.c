/* TigerTerm launcher — Mach-O PPC binary for .app bundle.
   Resolves bundle path, sets PYTHONHOME relative to bundle,
   and execs the bundled Python with the terminal app script.
   Drops -psn_* args injected by Finder on launch. */

#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <libgen.h>

int main(int argc, char *argv[]) {
    char exe_dir[1024];
    char python_path[1024];
    char script_path[1024];
    char pythonhome[1024];
    char terminal_dir[1024];
    char cwd[512];
    char *dir;
    char *args[3];

    /* Find our own directory (Contents/MacOS/) */
    if (strlen(argv[0]) > 0 && argv[0][0] == '/') {
        /* Absolute path — use directly */
        snprintf(exe_dir, sizeof(exe_dir), "%s", argv[0]);
    } else {
        /* Relative — prepend cwd */
        if (getcwd(cwd, sizeof(cwd)) == NULL) {
            _exit(1);
        }
        snprintf(exe_dir, sizeof(exe_dir), "%s/%s", cwd, argv[0]);
    }

    /* Strip executable name to get directory */
    dir = dirname(exe_dir);

    /* Build paths relative to Contents/MacOS/ */
    snprintf(python_path, sizeof(python_path), "%s/python3.13", dir);
    snprintf(script_path, sizeof(script_path), "%s/terminal/terminal_app.py", dir);
    snprintf(pythonhome, sizeof(pythonhome), "%s", dir);
    snprintf(terminal_dir, sizeof(terminal_dir), "%s/terminal", dir);

    /* Set environment */
    setenv("PYTHONHOME", pythonhome, 1);
    setenv("TIGERTERM_BUNDLE", "1", 1);

    /* Change to the terminal source directory so relative imports work */
    chdir(terminal_dir);

    /* Exec Python with script */
    args[0] = python_path;
    args[1] = script_path;
    args[2] = NULL;
    execv(python_path, args);

    /* If exec fails, print error and exit */
    perror("TigerTerm: exec failed");
    _exit(1);
}
