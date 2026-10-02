; Veröffentlichung ohne Admin-Rechte. Der vollständige Ordner-Build wird benötigt.
#define MyAppName "Emulator Hub"
#define MyAppExeName "EmulatorHub.exe"
#define MyAppDir AddBackslash(SourcePath) + "..\dist\EmulatorHub"
; Direkter ISCC-Aufruf: Version aus der zentral erzeugten Windows-EXE übernehmen.
#ifndef MyAppVersion
  #define MyAppVersion GetStringFileInfo(MyAppDir + "\" + MyAppExeName, "ProductVersion")
#endif
#if MyAppVersion == ""
  #error "Bitte zuerst build.ps1 ausführen; die Anwendungsversion fehlt."
#endif

[Setup]
AppId={{6DA074B0-870E-43C9-96B9-0510803FB9AE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\EmulatorHub
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\Output
OutputBaseFilename=EmulatorHub-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Zusätzliche Verknüpfungen:"; Flags: unchecked

[Files]
Source: "{#MyAppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} starten"; Flags: nowait postinstall skipifsilent

; Kein [UninstallDelete]: Eigene Spiele und Daten bleiben bei der Deinstallation erhalten.
