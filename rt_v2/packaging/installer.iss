; ─────────────────────────────────────────────────────────────
;  HI 21cm 전파망원경 — Windows 설치 파일 (Inno Setup 6)
;
;  직접 돌리기보다 packaging\make_release.py 가 버전을 넘겨 컴파일한다:
;     ISCC.exe /DAppVersion=2.0.0 /DSourceDir=...\dist\RWA_HI21cm /DOutputDir=...\dist\release installer.iss
;
;  · 기본은 관리자 권한 없이 '내 계정에만' 설치 (%LOCALAPPDATA%\Programs)
;    설치 첫 화면에서 '모든 사용자(Program Files)' 를 고를 수도 있다.
;  · 사용자 데이터(%APPDATA%\RWA_HI21cm: 설정·프로젝트)는 제거해도 남긴다.
; ─────────────────────────────────────────────────────────────

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\RWA_HI21cm"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\release"
#endif

#define AppName      "HI 21cm 전파망원경"
#define AppNameEn    "HI 21cm Radio Telescope"
#define AppExe       "RWA_HI21cm.exe"
#define AppPublisher "Team RWA (SASA 10th)"
#define AppURL       "https://github.com/TETO-IS-KAWAI/projectbaseresearch"

[Setup]
; AppId 는 절대 바꾸지 말 것 (바꾸면 업그레이드가 아니라 별도 프로그램으로 설치됨)
AppId={{54EEB592-12FE-4CE8-85A7-D73C18A243E9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
AppCopyright=© 2026 Team RWA · MIT License
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppNameEn}
VersionInfoDescription={#AppName} 설치 프로그램

DefaultDirName={autopf}\RWA HI21cm
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

LicenseFile=..\..\LICENSE
SetupIconFile=..\assets\icons\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
WizardStyle=modern
WizardSizePercent=110

OutputDir={#OutputDir}
OutputBaseFilename=RWA_HI21cm-{#AppVersion}-setup
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; 업그레이드할 때 실행 중인 앱을 닫는다
CloseApplications=force
RestartApplications=no

[Languages]
Name: "korean";  MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
korean.DesktopIcon=바탕화면에 바로가기 만들기
english.DesktopIcon=Create a desktop shortcut
korean.LaunchApp={#AppName} 실행
english.LaunchApp=Launch {#AppNameEn}
korean.Notices=오픈소스 고지
english.Notices=Open-source notices

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; Flags: unchecked

[InstallDelete]
; 예전 버전의 파일이 섞이지 않도록 프로그램 폴더 안의 번들을 비우고 새로 깐다
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "{#AppNameEn}"
Name: "{autoprograms}\{#AppName} — {cm:Notices}"; Filename: "{app}\licenses\THIRD_PARTY_NOTICES.txt"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 앱이 실행 중 만든 캐시만 지운다. 설정·프로젝트(%APPDATA%\RWA_HI21cm)는 남긴다.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
