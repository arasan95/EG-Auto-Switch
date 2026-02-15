param (
    [Parameter(Mandatory = $true)]
    [ValidateSet(1, 2, 3)]
    [int]$Profile
)

# Admin check
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Warning: Script is NOT running as Administrator." -ForegroundColor Yellow
    Write-Host "For UIA to interact with admin processes, this script MUST run as Admin." -ForegroundColor Yellow
}

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$processName = "elecomui"
$proc = Get-Process -Name $processName -ErrorAction SilentlyContinue

if (-not $proc) {
    Write-Host "Error: Process '$processName' not found." -ForegroundColor Red
    exit 1
}

try {
    # Get Root Element (Window)
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
    if (-not $root) {
        throw "Could not get AutomationElement from window handle."
    }

    # Find the ListBox that contains profiles
    # Based on inspection: Class: ListBox
    $condList = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "ListBox")
    $listBox = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condList)

    if (-not $listBox) {
        throw "Could not find profile ListBox."
    }

    # Find all ListItems (Profiles)
    $condItem = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "ListBoxItem")
    $items = $listBox.FindAll([System.Windows.Automation.TreeScope]::Children, $condItem)

    Write-Host "Found $($items.Count) profiles." -ForegroundColor Cyan

    $index = $Profile - 1
    if ($index -ge $items.Count) {
        throw "Profile $Profile not found (Only $($items.Count) items detected)."
    }

    $targetItem = $items[$index]
    Write-Host "Target Profile Item: $($targetItem.Current.Name)" -ForegroundColor Green

    # Find the Invoke-able Button inside the ListItem
    # The button name might be the profile name (e.g. "Default", "LoL")
    $condButton = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
    $buttons = $targetItem.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condButton)

    $invokableButton = $null

    foreach ($btn in $buttons) {
        # Check if it supports InvokePattern
        if ($btn.GetSupportedPatterns() -contains [System.Windows.Automation.InvokePattern]::Pattern) {
            $invokableButton = $btn
            break
        }
    }

    if (-not $invokableButton) {
        throw "Could not find a clickable button inside the profile item."
    }

    Write-Host "Clicking button: '$($invokableButton.Current.Name)'" -ForegroundColor Yellow
    
    $invoke = $invokableButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $invoke.Invoke()

    Write-Host "Successfully switched to Profile $Profile." -ForegroundColor Green

}
catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}
