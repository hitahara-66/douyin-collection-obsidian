# 注册 / 移除「抖音收藏 → Obsidian」每周自动同步的 Windows 计划任务
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File register-scheduled-task.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File register-scheduled-task.ps1 -Days Wednesday,Friday -At 21:00
#   powershell -NoProfile -ExecutionPolicy Bypass -File register-scheduled-task.ps1 -Remove
param(
    [string]$ToolRoot = (Join-Path $PSScriptRoot '..\..\..'),
    [string[]]$Days = @('Wednesday', 'Sunday'),
    [string]$At = '19:30',
    [string]$TaskName = 'DouyinToObsidian-Sync',
    [switch]$Remove
)
$ErrorActionPreference = 'Stop'
$ToolRoot = [IO.Path]::GetFullPath($ToolRoot)

if ($Remove) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "已移除计划任务: $TaskName"
    } else {
        Write-Host "计划任务不存在: $TaskName"
    }
    return
}

$wrapper = Join-Path $ToolRoot '定时同步.cmd'
if (-not (Test-Path -LiteralPath $wrapper)) {
    throw "找不到 $wrapper。请确认 -ToolRoot 指向工具根目录（含 定时同步.cmd 的目录）。"
}
$venv = Join-Path $ToolRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv)) {
    Write-Warning "未找到 .venv：请先在工具目录运行 准备.cmd，否则任务会失败。"
}

$action = New-ScheduledTaskAction -Execute $wrapper -WorkingDirectory $ToolRoot
$triggers = foreach ($day in $Days) {
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek $day -At $At
}
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME) -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Principal $principal `
    -Description ("每周自动同步抖音收藏 / 稍后再看到本地 Obsidian 库（{0} {1}）" -f ($Days -join '、'), $At) `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
Write-Host "已注册计划任务: $TaskName"
Write-Host ("  触发时间: " + ($Days -join '、') + " " + $At)
Write-Host ("  下次运行: " + $info.NextRunTime)
Write-Host ("  运行入口: " + $wrapper)
Write-Host "  日志文件: $(Join-Path $ToolRoot 'data\logs\scheduled.log')"
