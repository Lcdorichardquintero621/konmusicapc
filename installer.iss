[Setup]
AppName=KonMusic
AppVersion=1.0.0
AppPublisher=KonMusic
DefaultDirName={autopf}\KonMusic
DefaultGroupName=KonMusic
OutputDir=installer_out
OutputBaseFilename=KonMusic_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\KonMusic.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "dist\KonMusic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\KonMusic"; Filename: "{app}\KonMusic.exe"
Name: "{autodesktop}\KonMusic"; Filename: "{app}\KonMusic.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KonMusic.exe"; Description: "Abrir KonMusic"; Flags: nowait postinstall skipifsilent
