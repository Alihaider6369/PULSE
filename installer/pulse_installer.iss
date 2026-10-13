; Script generated for Inno Setup 6
; PULSE Desktop Application Windows Installer

#define MyAppName "PULSE"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "PULSE Posture"
#define MyAppURL "http://127.0.0.1:8000"
#define MyAppExeName "PULSE.exe"

[Setup]
; Basic Application Info
AppId={{9C52A55B-F124-4B2E-89EA-8BFAEF68812A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Packaging and Output
OutputDir=..\dist_installer
OutputBaseFilename=PULSE_Setup_v{#MyAppVersion}
SetupIconFile=..\desktop_app\resources\pulse.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Architecture
ArchitecturesInstallIn64BitMode=x64compatible

; Privileges
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Visual presentation
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=PULSE — AI Desk Posture Awareness Application
VersionInfoCopyright=Copyright (C) 2026 PULSE Posture
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copy all files from PyInstaller dist/PULSE directory
Source: "..\dist\PULSE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\resources\pulse.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\resources\pulse.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
