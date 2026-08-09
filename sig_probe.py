import sys, os, signal, faulthandler, threading
sys.path.insert(0, r'C:\SuperGuard')
faulthandler.enable()
def log_sig(signum, frame):
    print(f'SIGNAL {signum} received!', flush=True)
    faulthandler.dump_traceback()
for s in [signal.SIGINT, signal.SIGTERM, signal.SIGABRT]:
    try: signal.signal(s, log_sig)
    except Exception: pass
print('probe: handlers installed, importing...', flush=True)
from superguard.main import main
print('probe: calling main()', flush=True)
main()
