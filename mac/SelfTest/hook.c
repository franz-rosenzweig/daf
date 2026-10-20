// Linked into the self-test build only (see selftest.sh). Runs before main and
// asks the harness to start once the app has finished launching, so the app's
// own sources need no test hook.
extern void selftest_install(void);
__attribute__((constructor)) static void selftest_hook(void) { selftest_install(); }
