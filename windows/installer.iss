; Daf for Windows: an installer for one person, which needs no administrator.
; It copies what dotnet publish made (build\Daf) to %LOCALAPPDATA%\Programs\Daf, puts Daf
; in the Start menu, and lets daf:// links open it. Made by windows\build.ps1 and the
; Windows workflow:
;
;   iscc /DVersion=0.1.0 windows\installer.iss
;
; Uninstalling leaves the settings, the sign-in and the copy for no connection in
; %LOCALAPPDATA%\Daf, and takes Daf out of the apps that open at sign-in.

#ifndef Version
  #define Version "0.0.0"
#endif
#ifndef Source
  #define Source "..\build\Daf"
#endif

[Setup]
AppId={{9C4E2B7A-3F51-4D8E-A6B0-1E7D5C2F8A43}
AppName=Daf
AppVersion={#Version}
AppVerName=Daf {#Version}
AppPublisher=franz-rosenzweig
AppPublisherURL=https://github.com/franz-rosenzweig/daf
AppSupportURL=https://github.com/franz-rosenzweig/daf/blob/master/docs/windows.md
DefaultDirName={localappdata}\Programs\Daf
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\build\out
OutputBaseFilename=Daf-{#Version}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#Source}\Assets\Daf.ico
UninstallDisplayIcon={app}\Daf.exe
UninstallDisplayName=Daf
CloseApplications=yes

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Daf"; Filename: "{app}\Daf.exe"
Name: "{autodesktop}\Daf"; Filename: "{app}\Daf.exe"; Tasks: desktopicon

[Registry]
; daf://save?url=... and daf://go/review open Daf (the app says the same at each start)
Root: HKCU; Subkey: "Software\Classes\daf"; ValueType: string; ValueName: ""; ValueData: "URL:Daf"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\daf"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\daf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\Daf.exe"",0"
Root: HKCU; Subkey: "Software\Classes\daf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Daf.exe"" ""%1"""
; Settings > Open Daf when you sign in writes this; uninstalling takes it away
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Daf"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Daf.exe"; Description: "{cm:LaunchProgram,Daf}"; Flags: nowait postinstall skipifsilent
