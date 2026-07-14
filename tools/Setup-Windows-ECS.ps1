# Run this script in an elevated PowerShell session on the Windows Server ECS.
# It configures VMS at C:\VMS behind nginx on port 80.

[CmdletBinding()]
param(
    [string]$VmsRoot = "C:\VMS",
    [string]$NginxVersion = "1.30.3",
    [string]$NginxRoot = "C:\nginx",
    [string]$DomainName = "visitor-eric.cn",
    [string]$PublicIp = "39.101.122.245",
    [switch]$SkipDatabaseSetup
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Please run PowerShell as Administrator."
    }
}

function Convert-SecureStringToPlainText([Security.SecureString]$SecureValue) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Escape-MySqlLiteral([string]$Value) {
    $Value.Replace("\", "\\").Replace("'", "''")
}

function Find-CommandPath([string[]]$Names) {
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    return $null
}

function Find-MySqlExe {
    $fromPath = Find-CommandPath @("mysql.exe", "mysql")
    if ($fromPath) { return $fromPath }

    $candidates = @(
        "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
        "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
        "C:\Program Files\MariaDB 11.4\bin\mysql.exe",
        "C:\Program Files\MariaDB 10.11\bin\mysql.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }

    $matches = Get-ChildItem "C:\Program Files\MySQL" -Recurse -Filter mysql.exe -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($matches) { return $matches.FullName }

    return $null
}

function Download-File([string]$Url, [string]$Destination) {
    Write-Host "Downloading $Url"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
}

Assert-Administrator

if (-not (Test-Path $VmsRoot)) {
    throw "VMS root not found: $VmsRoot"
}
if (-not (Test-Path (Join-Path $VmsRoot "server.py"))) {
    throw "server.py not found under $VmsRoot"
}
if (-not (Test-Path (Join-Path $VmsRoot "requirements.txt"))) {
    throw "requirements.txt not found under $VmsRoot"
}

New-Item -ItemType Directory -Force -Path (Join-Path $VmsRoot "logs") | Out-Null
New-Item -ItemType Directory -Force -Path "C:\vms-install" | Out-Null

$python = Find-CommandPath @("py.exe", "python.exe", "python")
if (-not $python) {
    throw "Python was not found. Install Python 3 first, then rerun this script."
}

$venvPython = Join-Path $VmsRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating Python virtual environment..."
    if ((Split-Path $python -Leaf) -ieq "py.exe") {
        & $python -3 -m venv (Join-Path $VmsRoot ".venv")
    }
    else {
        & $python -m venv (Join-Path $VmsRoot ".venv")
    }
}

Write-Host "Installing Python dependencies..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $VmsRoot "requirements.txt")

$envPath = Join-Path $VmsRoot ".env"
$existingPassword = ""
if (Test-Path $envPath) {
    $passwordLine = Get-Content $envPath | Where-Object { $_ -match "^VMS_MYSQL_PASSWORD=" } | Select-Object -First 1
    if ($passwordLine) {
        $existingPassword = $passwordLine.Substring("VMS_MYSQL_PASSWORD=".Length)
    }
}

if ($existingPassword) {
    $vmsDbPassword = $existingPassword
    Write-Host "Using existing VMS_MYSQL_PASSWORD from $envPath"
}
else {
    $vmsDbPassword = Convert-SecureStringToPlainText (Read-Host "Enter password to set for MySQL user vms_user" -AsSecureString)
}

@"
PORT=18088
VMS_MYSQL_HOST=127.0.0.1
VMS_MYSQL_PORT=3306
VMS_MYSQL_DATABASE=vms
VMS_MYSQL_USER=vms_user
VMS_MYSQL_PASSWORD=$vmsDbPassword
VMS_MYSQL_CHARSET=utf8mb4
"@ | Set-Content -Path $envPath -Encoding UTF8

if (-not $SkipDatabaseSetup) {
    $mysql = Find-MySqlExe
    if (-not $mysql) {
        throw "mysql.exe was not found. Rerun with -SkipDatabaseSetup if the vms database/user already exists."
    }

    $rootPassword = Convert-SecureStringToPlainText (Read-Host "Enter MySQL root password" -AsSecureString)
    $escapedVmsPassword = Escape-MySqlLiteral $vmsDbPassword
    $sqlPath = "C:\vms-install\vms-db-setup.sql"
    @"
CREATE DATABASE IF NOT EXISTS vms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'vms_user'@'127.0.0.1' IDENTIFIED BY '$escapedVmsPassword';
ALTER USER 'vms_user'@'127.0.0.1' IDENTIFIED BY '$escapedVmsPassword';
CREATE USER IF NOT EXISTS 'vms_user'@'localhost' IDENTIFIED BY '$escapedVmsPassword';
ALTER USER 'vms_user'@'localhost' IDENTIFIED BY '$escapedVmsPassword';
GRANT ALL PRIVILEGES ON vms.* TO 'vms_user'@'127.0.0.1';
GRANT ALL PRIVILEGES ON vms.* TO 'vms_user'@'localhost';
FLUSH PRIVILEGES;
"@ | Set-Content -Path $sqlPath -Encoding ASCII

    Write-Host "Creating/updating MySQL database and local user..."
    & $mysql -h 127.0.0.1 -uroot "-p$rootPassword" "--default-character-set=utf8mb4" -e "source $($sqlPath.Replace('\','/'))"
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL database setup failed. Check the MySQL root password, or create the vms database/user manually and rerun with -SkipDatabaseSetup."
    }
}

$nginxZip = "C:\vms-install\nginx-$NginxVersion.zip"
$nginxUrl = "https://nginx.org/download/nginx-$NginxVersion.zip"
if (-not (Test-Path $nginxZip)) {
    Download-File $nginxUrl $nginxZip
}

$nginxExtract = "C:\vms-install\nginx-extract"
if (Test-Path $nginxExtract) { Remove-Item $nginxExtract -Recurse -Force }
Expand-Archive -Path $nginxZip -DestinationPath $nginxExtract -Force
$extractedNginxRoot = Join-Path $nginxExtract "nginx-$NginxVersion"
if (-not (Test-Path $extractedNginxRoot)) {
    throw "Unexpected nginx archive layout."
}

if (-not (Test-Path $NginxRoot)) {
    New-Item -ItemType Directory -Force -Path $NginxRoot | Out-Null
}
Copy-Item -Path (Join-Path $extractedNginxRoot "*") -Destination $NginxRoot -Recurse -Force

$nginxConf = @"
worker_processes  1;

events {
    worker_connections  1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout 65;
    client_max_body_size 20m;

    server {
        listen 80 default_server;
        server_name $DomainName www.$DomainName $PublicIp _;

        location / {
            proxy_pass http://127.0.0.1:18088;
            proxy_http_version 1.1;
            proxy_set_header Host `$host;
            proxy_set_header X-Real-IP `$remote_addr;
            proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto `$scheme;
            proxy_read_timeout 300;
        }
    }
}
"@
$nginxConf | Set-Content -Path (Join-Path $NginxRoot "conf\nginx.conf") -Encoding ASCII

Write-Host "Creating startup scripts and scheduled tasks..."
$vmsStart = Join-Path $VmsRoot "Start-VMS.ps1"
@"
Set-Location '$VmsRoot'
`$env:PORT='18088'
`$env:VMS_MYSQL_HOST='127.0.0.1'
`$env:VMS_MYSQL_PORT='3306'
`$env:VMS_MYSQL_DATABASE='vms'
`$env:VMS_MYSQL_USER='vms_user'
`$env:VMS_MYSQL_PASSWORD='$($vmsDbPassword.Replace("'","''"))'
`$env:VMS_MYSQL_CHARSET='utf8mb4'
& '$venvPython' '$VmsRoot\server.py' *> '$VmsRoot\logs\vms-task.log'
"@ | Set-Content -Path $vmsStart -Encoding UTF8

$nginxStart = Join-Path $NginxRoot "Start-Nginx.ps1"
@"
Set-Location '$NginxRoot'
& '$NginxRoot\nginx.exe'
"@ | Set-Content -Path $nginxStart -Encoding UTF8

foreach ($taskName in @("VMS", "VMS-Nginx")) {
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
}

$vmsAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$vmsStart`""
$nginxAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$nginxStart`""
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "VMS" -Action $vmsAction -Trigger $startupTrigger -Principal $taskPrincipal -Settings $taskSettings | Out-Null
Register-ScheduledTask -TaskName "VMS-Nginx" -Action $nginxAction -Trigger $startupTrigger -Principal $taskPrincipal -Settings $taskSettings | Out-Null

Write-Host "Adding Windows Firewall rules for 80/443..."
foreach ($rule in @(
    @{ Name = "VMS HTTP 80"; Port = 80 },
    @{ Name = "VMS HTTPS 443"; Port = 443 }
)) {
    if (-not (Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $rule.Port | Out-Null
    }
}

$nginxExe = Join-Path $NginxRoot "nginx.exe"
Write-Host "Testing nginx configuration..."
Push-Location $NginxRoot
try {
    & $nginxExe -t
}
finally {
    Pop-Location
}

Write-Host "Starting services..."
Start-ScheduledTask -TaskName "VMS"
Start-Sleep -Seconds 4
Start-ScheduledTask -TaskName "VMS-Nginx"
Start-Sleep -Seconds 2

Write-Host "Verifying local backend..."
$backend = Invoke-WebRequest -Uri "http://127.0.0.1:18088/api/config" -UseBasicParsing -TimeoutSec 10
Write-Host "Backend status: $($backend.StatusCode)"

Write-Host "Verifying nginx reverse proxy..."
$web = Invoke-WebRequest -Uri "http://127.0.0.1/web/" -UseBasicParsing -TimeoutSec 10
Write-Host "Web status through nginx: $($web.StatusCode)"

Write-Host ""
Write-Host "Done. Test from your PC: http://$PublicIp/web/"
Write-Host "After ICP filing and DNS are ready, configure HTTPS for https://$DomainName/"
