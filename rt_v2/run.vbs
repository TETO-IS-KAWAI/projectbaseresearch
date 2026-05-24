Set objShell = CreateObject("WScript.Shell")
objShell.Run "python.exe """ & CreateObject("WScript.FileSystemObject").GetAbsolutePathName(".") & "\main_app.py""", 0
