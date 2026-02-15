Add-Type @"
    using System;
    using System.Runtime.InteropServices;
    using System.Drawing;

    public struct POINT {
        public int X;
        public int Y;
    }

    public class Win32 {
        [DllImport("user32.dll")]
        public static extern bool GetCursorPos(out POINT lpPoint);

        [DllImport("user32.dll")]
        public static extern bool ScreenToClient(IntPtr hWnd, ref POINT lpPoint);

        [DllImport("user32.dll")]
        public static extern IntPtr GetForegroundWindow();

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll")]
        public static extern int GetWindowThreadProcessId(IntPtr hWnd, out int lpdwProcessId);
    }
"@

function Get-Info {
    $point = New-Object POINT
    [Win32]::GetCursorPos([ref] $point) | Out-Null
    
    $hWnd = [Win32]::GetForegroundWindow()
    if ($hWnd -eq 0) { return }

    $pidVar = 0
    [Win32]::GetWindowThreadProcessId($hWnd, [ref] $pidVar) | Out-Null
    
    try {
        $proc = Get-Process -Id $pidVar -ErrorAction Stop
    }
    catch {
        return
    }

    # Only show info if the active window is EG Tool (elecomui)
    if ($proc.ProcessName -ne "elecomui") {
        return
    }

    $sb = New-Object System.Text.StringBuilder(256)
    [Win32]::GetWindowText($hWnd, $sb, $sb.Capacity) | Out-Null
    
    $screenPoint = $point
    [Win32]::ScreenToClient($hWnd, [ref] $point) | Out-Null
    
    Write-Host "`n------------------------" -ForegroundColor Cyan
    Write-Host "Window  : '$($sb.ToString())' (PID: $pidVar)"
    Write-Host "Coords  : X=$($point.X), Y=$($point.Y)" -ForegroundColor Green
    Write-Host "------------------------"
}

Write-Host "Monitoring for 'elecomui' active window..." -ForegroundColor Cyan
Write-Host "1. Switch to the EG Tool window."
Write-Host "2. Hover over the button."
Write-Host "3. Wait for the log to update (updates every 2 seconds)."
Write-Host "Press Ctrl+C to stop."

while ($true) {
    Get-Info
    Start-Sleep -Seconds 2
}
