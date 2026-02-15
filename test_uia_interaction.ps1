param (
    [Parameter(Mandatory = $true)]
    [ValidateSet(1, 2, 3)]
    [int]$Profile
)

# Admin check
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Warning: Script is NOT running as Administrator." -ForegroundColor Yellow
}

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$processName = "elecomui"
$proc = Get-Process -Name $processName -ErrorAction SilentlyContinue

if (-not $proc) {
    Write-Host "Error: Process '$processName' not found." -ForegroundColor Red
    exit 1
}

$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)

# Find Profile ListBox
$condList = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "ListBox")
$listBox = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condList)

if (-not $listBox) {
    Write-Host "Error: Profile ListBox not found." -ForegroundColor Red
    exit
}

# Find all Profile Items
$condItem = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "ListBoxItem")
$items = $listBox.FindAll([System.Windows.Automation.TreeScope]::Children, $condItem)

$index = $Profile - 1
if ($index -ge $items.Count) {
    Write-Host "Error: Profile $Profile not found."
    exit
}

$targetItem = $items[$index]
Write-Host "Reaching Profile $Profile Item: '$($targetItem.Current.Name)'" -ForegroundColor Cyan

# TEST 1: Try to SELECT the list item directly
Write-Host "`n[TEST 1] Trying 'SelectionItem.Select()' on the item itself..." -ForegroundColor Yellow
try {
    if ($targetItem.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)) {
        $sel = $targetItem.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        $sel.Select()
        Write-Host "  -> Select() called successfully." -ForegroundColor Green
    }
    else {
        Write-Host "  -> SelectionItemPattern not supported." -ForegroundColor DarkGray
    }
}
catch {
    Write-Host "  -> Failed: $_" -ForegroundColor Red
}

Start-Sleep -Seconds 1

# TEST 2: Try to INVOKE every button inside the item
Write-Host "`n[TEST 2] Looking for buttons inside the item to Invoke..." -ForegroundColor Yellow
$condButton = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
$buttons = $targetItem.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condButton)

foreach ($btn in $buttons) {
    $btnName = $btn.Current.Name
    Write-Host "  Found Button: '$btnName'"
    
    try {
        if ($btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)) {
            $inv = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            $inv.Invoke()
            Write-Host "    -> Invoke() called on '$btnName'." -ForegroundColor Green
        }
        else {
            Write-Host "    -> InvokePattern not supported." -ForegroundColor DarkGray
        }
    }
    catch {
        Write-Host "    -> Failed to invoke: $_" -ForegroundColor Red
    }
    
    Start-Sleep -Milliseconds 500
}

Write-Host "`n--------------------------------------------------"
Write-Host "Test finished. Did the profile change at any point?" -ForegroundColor Magenta
