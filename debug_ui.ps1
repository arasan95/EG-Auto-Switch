
Add-Type @"
    using System;
    using System.Runtime.InteropServices;
    using System.Collections.Generic;
    using System.Text;

    public class Win32 {
        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool EnumChildWindows(IntPtr window, EnumWindowProc callback, IntPtr lParam);

        public delegate bool EnumWindowProc(IntPtr hWnd, IntPtr lParam);

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        public static extern int GetClassName(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);

        [DllImport("user32.dll")]
        public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

        public struct RECT {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        public static List<string> children = new List<string>();

        public static bool EnumWindow(IntPtr hWnd, IntPtr lParam) {
            StringBuilder sbTitle = new StringBuilder(256);
            GetWindowText(hWnd, sbTitle, 256);
            StringBuilder sbClass = new StringBuilder(256);
            GetClassName(hWnd, sbClass, 256);
            
            RECT r;
            GetWindowRect(hWnd, out r);

            children.Add(string.Format("Handle: {0}, Title: '{1}', Class: '{2}', Rect: [{3},{4}, {5},{6}]", 
                hWnd, sbTitle.ToString(), sbClass.ToString(), r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top));
            return true;
        }
    }
"@

$processName = "elecomui"
$proc = Get-Process -Name $processName -ErrorAction SilentlyContinue

if (-not $proc) {
    Write-Host "Process '$processName' not found."
    exit
}

$hWnd = $proc.MainWindowHandle
Write-Host "Main Window Handle: $hWnd"

[Win32]::children.Clear()
$cb = [Win32+EnumWindowProc] { param($h, $l) return [Win32]::EnumWindow($h, $l) }
[Win32]::EnumChildWindows($hWnd, $cb, [IntPtr]::Zero) | Out-Null

if ([Win32]::children.Count -eq 0) {
    Write-Host "No child windows found. The UI might be drawn directly on the main window (WPF/Qt/etc) or coordinates are strictly relative to main."
}
else {
    Write-Host "Child Windows Found:"
    [Win32]::children | ForEach-Object { Write-Host $_ }
}
