# build_release.ps1
# 在 Developer PowerShell for VS 2022 环境中，对工程执行 CMake 配置、构建、安装。
# 脚本结束时会明确提示成功或失败，并以退出码 0 / 1 返回结果。
#
# 运行方式（在任意 PowerShell 中执行）：
#   powershell -ExecutionPolicy Bypass -File .\Script\build_release.ps1
# 也可以直接双击同目录下的 build_release.bat（cmd 方式，效果相同）。

$ErrorActionPreference = 'Stop'

try {
    # 1. 通过 vswhere 自动定位 VS 2022（兼容 Community / Professional / Enterprise）
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path $vswhere)) {
        throw '未找到 vswhere.exe，请确认已安装 Visual Studio 2022（含"使用 C++ 的桌面开发"工作负载）。'
    }
    $vsInstallPath = & $vswhere -latest -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath | Select-Object -First 1
    if (-not $vsInstallPath) {
        throw '未找到安装 C++ 工具的 Visual Studio 2022。'
    }
    Write-Host "使用 Visual Studio: $vsInstallPath"

    # 2. 进入 VS 2022 开发者环境（等价于打开 Developer PowerShell for VS 2022）
    $devShellModule = Join-Path $vsInstallPath 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll'
    Import-Module $devShellModule
    Enter-VsDevShell -VsInstallPath $vsInstallPath -SkipAutomaticLocation -DevCmdArguments '-arch=x64'

    # 3. 切换到工程根目录（本脚本位于 Script 子目录下）
    Set-Location (Join-Path $PSScriptRoot '..')
    Write-Host "当前目录: $(Get-Location)"

    # 4. 依次执行三条 cmake 指令
    $configureArgs = @(
        '-S', '.',
        '-B', 'cmake-build-release',
        '-G', 'Visual Studio 17 2022',
        '-A', 'x64',
        '-DCMAKE_BUILD_TYPE=Release',
        '-DENABLE_CGNS_MODULE=OFF',
        '-DENABLE_QT_MODULE=OFF'
    )

    Write-Host "`n[1/3] cmake -S . -B cmake-build-release -G `"Visual Studio 17 2022`" -A x64 -DCMAKE_BUILD_TYPE=Release -DENABLE_CGNS_MODULE=OFF -DENABLE_QT_MODULE=OFF"
    & cmake @configureArgs
    if ($LASTEXITCODE -ne 0) { throw "cmake 配置失败（退出码 $LASTEXITCODE）" }

    # 关闭 MSBuild 文件跟踪（/p:TrackFileAccess=false）：
    # 本机 Tracker.exe 会随机以堆损坏(0xc0000374)崩溃并把 cl.exe 挂起，导致构建“卡住”。
    # 关闭后构建不再依赖 Tracker.exe，可稳定完成。
    Write-Host "`n[2/3] cmake --build cmake-build-release --config Release -- /p:TrackFileAccess=false"
    & cmake --build cmake-build-release --config Release -- /p:TrackFileAccess=false
    if ($LASTEXITCODE -ne 0) { throw "cmake 构建失败（退出码 $LASTEXITCODE）" }

    Write-Host "`n[3/3] cmake --install cmake-build-release --config Release"
    & cmake --install cmake-build-release --config Release
    if ($LASTEXITCODE -ne 0) { throw "cmake 安装失败（退出码 $LASTEXITCODE）" }

    Write-Host "`n[结果] 成功：配置、构建、安装全部完成。" -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "`n[结果] 失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
