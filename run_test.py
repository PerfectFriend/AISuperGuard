import sys
sys.path.insert(0, r'C:\SuperGuard')

import traceback
try:
    from superguard.main import main
    main()
except Exception as e:
    traceback.print_exc()
    input("Press Enter to exit...")