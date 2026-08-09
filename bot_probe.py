import sys, os
sys.path.insert(0, r'C:\SuperGuard')
print('probe: before import', flush=True)
import superguard.main
print('probe: imported, calling main()', flush=True)
superguard.main.main()
