
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$processName = "elecomui"
$proc = Get-Process -Name $processName -ErrorAction SilentlyContinue

if (-not $proc) {
    Write-Host "Process '$processName' not found."
    exit
}

Write-Host "Inspecting UI Automation elements for '$processName'..." -ForegroundColor Cyan

try {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
    if (-not $root) {
        Write-Host "Could not get AutomationElement from window handle."
        exit
    }

    Write-Host "Root Element: $($root.Current.Name) ($($root.Current.ControlType.ProgrammaticName))"

    # Function to recursively dump elements
    function Dump-Elements($element, $indent) {
        $className = ""
        try { $className = $element.Current.ClassName } catch {}
        
        $name = ""
        try { $name = $element.Current.Name } catch {}
        
        $controlType = ""
        try { $controlType = $element.Current.ControlType.ProgrammaticName } catch {}

        Write-Host "$indent [$controlType] '$name' (Class: $className)"

        $patterns = $element.GetSupportedPatterns()
        if ($patterns) {
            foreach ($p in $patterns) {
                Write-Host "$indent   - Pattern: $($p.ProgrammaticName)" -ForegroundColor DarkGray
            }
        }

        # Find children
        $condition = [System.Windows.Automation.Condition]::TrueCondition
        $children = $element.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)

        foreach ($child in $children) {
            Dump-Elements $child "$indent  "
        }
    }

    Dump-Elements $root ""

}
catch {
    Write-Host "Error accessing UIA: $_" -ForegroundColor Red
}
