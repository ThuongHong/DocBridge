#define AppName "Converter"
#define AppVersion "0.1.0"

[Setup]
AppId={{88C59509-04AA-43DB-A745-659965DE8F60}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Converter
DefaultGroupName=Converter
OutputDir=..\dist
OutputBaseFilename=Converter-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\Converter.exe

[Files]
Source: "..\dist\Converter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Converter"; Filename: "{app}\Converter.exe"

[Run]
Filename: "{app}\Converter.exe"; Description: "Mở Converter"; Flags: nowait postinstall skipifsilent
