; Inno Setup script pra AdvBox Export.
; Compilado pelo CI: iscc /DAppVersion=X.Y.Z packaging/windows/AdvBoxExport.iss
;
; Gera AdvBoxExport-Setup.exe que:
;   - Instala em "Program Files\AdvBoxExport" (no admin) ou "%LocalAppData%\Programs\AdvBoxExport" (no user)
;   - Cria atalho no Menu Iniciar (vai aparecer na busca do Windows)
;   - Opcional: atalho na Área de Trabalho
;   - Registra em "Adicionar/Remover Programas" com uninstaller
;   - Ícone no .exe via icon embutido pelo PyInstaller + SetupIconFile do installer

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "AdvBox Export"
#define AppPublisher "Zé Estevão (zecarioco)"
#define AppExeName "AdvBoxExport.exe"

[Setup]
; AppId é um GUID único pro app — não muda entre versões.
AppId={{8F4A1B2C-3D5E-4F67-8A90-1B2C3D4E5F60}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/zecarioco/advbox-export
AppSupportURL=https://github.com/zecarioco/advbox-export/issues
AppUpdatesURL=https://github.com/zecarioco/advbox-export/releases

; Instala em %LocalAppData% (não pede admin) ou Program Files (com admin)
DefaultDirName={autopf}\AdvBoxExport
DefaultGroupName=AdvBox Export
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Saída do compilador
OutputDir=..\..\
OutputBaseFilename=AdvBoxExport-Setup
SetupIconFile=..\icons\AdvBoxExport.ico
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller gera dist\AdvBoxExport\ — copia tudo recursivamente
Source: "..\..\dist\AdvBoxExport\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
