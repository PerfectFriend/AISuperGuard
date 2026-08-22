import win32serviceutil
import win32service
import win32event
import servicemanager
import sys
import os
import traceback

class SuperGuardService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SuperGuardAlarm"
    _svc_display_name_ = "SuperGuard Alarm Bot"
    _svc_description_ = "SuperGuard Alarm - Video surveillance with YOLO detection and Telegram control"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = True

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_running = False

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()

    def main(self):
        # Add project to path
        sys.path.insert(0, r"C:\SuperGuard")
        
        # Change to project directory
        os.chdir(r"C:\SuperGuard")
        
        try:
            from superguard.main import main
            main()
        except Exception as e:
            # Log the error to Windows Event Log
            error_msg = f"SuperGuard service crashed: {e}\n{traceback.format_exc()}"
            servicemanager.LogErrorMsg(error_msg)
            # Restart after delay
            import time
            time.sleep(10)
            if self.is_running:
                self.main()

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SuperGuardService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SuperGuardService)