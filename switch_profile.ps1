param (
    [Parameter(Mandatory = $false)]
    [ValidateSet(1, 2, 3)]
    [int]$Profile
)

Add-Type @"
    using System;
    using System.Runtime.InteropServices;

    public class Win32 {

        [DllImport("user32.dll")]
        public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, int dwExtraInfo);

        [DllImport("user32.dll")]
        public static extern bool GetCursorPos(out POINT lpPoint);

        public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
        public const uint MOUSEEVENTF_LEFTUP = 0x0004;
    }
"@

# Check for Admin privileges
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Warning: Script is NOT running as Administrator." -ForegroundColor Yellow
    Write-Host "If EG Tool runs as Admin, this script MUST also run as Admin to work." -ForegroundColor Yellow
}

$coords = @{
    1 = @{ X = 170; Y = 216 }
    2 = @{ X = 157; Y = 260 }
    3 = @{ X = 160; Y = 312 }
}

if (-not $Profile) {
    Write-Host "Please specify -Profile <1|2|3>" -ForegroundColor Red
    exit
}

$pIdx = [int]$Profile
if (-not $coords.ContainsKey($pIdx)) {
    Write-Host "Invalid Profile ID. Use 1, 2, or 3." -ForegroundColor Red
    exit
}
$target = $coords[$pIdx]

# Find Window
$processName = "elecomui"
$proc = Get-Process -Name $processName -ErrorAction SilentlyContinue

if (-not $proc) {
    Write-Host "Error: Process '$processName' not found. Is EG Tool running?" -ForegroundColor Red
    exit 1
}

$hWnd = $proc.MainWindowHandle
if ($hWnd -eq [IntPtr]::Zero) {
    $hWnd = [Win32]::FindWindow($null, "EG Tool")
}

if ($hWnd -eq [IntPtr]::Zero) {
    Write-Host "Error: Could not find window handle." -ForegroundColor Red
    exit 1
}

Write-Host "Target: Profile $Profile ($($target.X), $($target.Y))" -ForegroundColor Cyan

# --- PHYSICAL INPUT STRATEGY ---

# 1. Save current mouse position and active window
$originalPos = New-Object POINT
[Win32]::GetCursorPos([ref]$originalPos) | Out-Null
$hPrev = [Win32]::GetForegroundWindow()

# 2. Calculate Screen Coordinates for target
$screenTarget = New-Object POINT
$screenTarget.X = $target.X
$screenTarget.Y = $target.Y
[Win32]::ClientToScreen($hWnd, [ref]$screenTarget) | Out-Null

# 3. Activate Window
if ([Win32]::IsIconic($hWnd)) {
    [Win32]::ShowWindow($hWnd, [Win32]::SW_RESTORE)
}
else {
    [Win32]::ShowWindow($hWnd, [Win32]::SW_SHOW)
}
[Win32]::SetForegroundWindow($hWnd) | Out-Null
Start-Sleep -Milliseconds 300 # Give it time to render

# 4. Move Mouse Physically
[Win32]::SetCursorPos($screenTarget.X, $screenTarget.Y) | Out-Null
Start-Sleep -Milliseconds 50

# 5. Click Physically
[Win32]::mouse_event([Win32]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
Start-Sleep -Milliseconds 50
[Win32]::mouse_event([Win32]::MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
Start-Sleep -Milliseconds 50

# 6. Restore Mouse and Window
[Win32]::ShowWindow($hWnd, [Win32]::SW_MINIMIZE) | Out-Null
if ($hPrev -ne [IntPtr]::Zero -and $hPrev -ne $hWnd) {
    [Win32]::SetForegroundWindow($hPrev) | Out-Null
}
[Win32]::SetCursorPos($originalPos.X, $originalPos.Y) | Out-Null

Write-Host "Done." -ForegroundColor Green

