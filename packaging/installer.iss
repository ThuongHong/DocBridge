#define AppName "DocBridge"
#define AppVersion "0.1.0"

[Setup]
AppId={{88C59509-04AA-43DB-A745-659965DE8F60}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\DocBridge
DefaultGroupName=DocBridge
OutputDir=..\dist
OutputBaseFilename=DocBridge-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\DocBridge.exe

[Files]
Source: "..\dist\DocBridge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DocBridge"; Filename: "{app}\DocBridge.exe"

[Run]
Filename: "{app}\DocBridge.exe"; Description: "Mở DocBridge"; Flags: nowait postinstall skipifsilent
