# 打包离线部署包。在有网的构建机上运行，产物拷进内网。
#
#   .\deploy\make-bundle.ps1
#   .\deploy\make-bundle.ps1 -Tag v1.0 -SkipBuild
#
# 存在的意义不只是省事：要传哪些文件这件事写在这里，就不会和 DEPLOY.md
# 各说各话。加了新的部署文件就往 $Files 里加一行。

[CmdletBinding()]
param(
    # 镜像 tag，同时也是包名的一部分。
    [string]$Tag = "latest",
    # 已经构建过就跳过，只重新打包。
    [switch]$SkipBuild,
    [string]$OutDir = "dist"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$images = @("report-agent-gateway:$Tag", "report-agent-backend:$Tag")

# 要随包带走的文件。源码不在其中 —— 已经构建进镜像了，内网不需要也不应该
# 重新构建（那边没有网，装不了依赖）。
$Files = @(
    "docker-compose.yml",
    "DEPLOY.md",
    "deploy/env.example",
    "deploy/nginx-modules/README.md",
    "deploy/nginx-modules/their-tool.conf.example",
    "deploy/jdbc/README.md"
)

if (-not $SkipBuild) {
    Write-Host "==> 构建镜像" -ForegroundColor Cyan
    docker build -t "report-agent-gateway:$Tag" ./frontend
    if ($LASTEXITCODE -ne 0) { throw "网关镜像构建失败" }
    docker build -t "report-agent-backend:$Tag" ./backend
    if ($LASTEXITCODE -ne 0) { throw "后端镜像构建失败" }
}

foreach ($img in $images) {
    docker image inspect $img *> $null
    if ($LASTEXITCODE -ne 0) { throw "镜像不存在：$img（去掉 -SkipBuild 重跑）" }
}

$stage = Join-Path $OutDir "report-agent-$Tag"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
# 解析成绝对路径：后面要用它的长度从 FullName 里截出相对路径，相对路径在这里
# 会把偏移算错，截出半截目录名。
$stage = (Resolve-Path $stage).Path

Write-Host "==> 导出镜像（几分钟，1GB 以上）" -ForegroundColor Cyan
$tar = Join-Path $stage "images.tar"
docker save -o $tar @images
if ($LASTEXITCODE -ne 0) { throw "docker save 失败" }

# 压缩率大概 4 倍，跨网传输值得等这一下。
#
# 必须是「tar 本身的 gzip」，不是「装着 tar 的 tar 包再 gzip」。
# `tar -czf x.tar.gz images.tar` 产出的是后者，docker load 会报
# "unrecognized image format" —— 而且要等搬到内网才会发现。
# 这里走 .NET 的 GZipStream，不依赖构建机上有没有 gzip.exe。
Write-Host "==> 压缩" -ForegroundColor Cyan
$gzPath = "$tar.gz"
$in = [System.IO.File]::OpenRead($tar)
try {
    $out = [System.IO.File]::Create($gzPath)
    try {
        $gz = New-Object System.IO.Compression.GZipStream(
            $out, [System.IO.Compression.CompressionLevel]::Optimal)
        try { $in.CopyTo($gz) } finally { $gz.Dispose() }
    } finally { $out.Dispose() }
} finally { $in.Dispose() }
Remove-Item $tar -Force

# 自检：确认压出来的确实是 docker load 认得的格式。
# 这一步存在是因为它真的挡住过一次 —— 双层打包的包在构建机上看着一切正常，
# 要搬到内网、解开、load 的时候才报 "unrecognized image format"。那时候再修
# 就是一次跨网往返。
Write-Host "==> 自检" -ForegroundColor Cyan
$fs = [System.IO.File]::OpenRead($gzPath)
try {
    $magic = New-Object byte[] 2
    $fs.Read($magic, 0, 2) | Out-Null
    if ($magic[0] -ne 0x1f -or $magic[1] -ne 0x8b) { throw "$gzPath 不是 gzip 格式" }
    $fs.Position = 0
    $gz = New-Object System.IO.Compression.GZipStream(
        $fs, [System.IO.Compression.CompressionMode]::Decompress)
    try {
        # tar 头的前 100 字节是第一个成员的文件名。
        $hdr = New-Object byte[] 100
        $gz.Read($hdr, 0, 100) | Out-Null
        $first = ([System.Text.Encoding]::ASCII.GetString($hdr) -split "`0")[0]
        if ($first -like "*.tar") {
            throw "打成了套娃：解开后第一个成员是 '$first'，docker load 需要的是镜像 tar 本身"
        }
        Write-Host "    ok，首个成员：$first"
    } finally { $gz.Dispose() }
} finally { $fs.Dispose() }

Write-Host "==> 复制部署文件" -ForegroundColor Cyan
foreach ($f in $Files) {
    if (-not (Test-Path $f)) { throw "缺少文件：$f" }
    $dest = Join-Path $stage $f
    New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
    Copy-Item $f $dest
}

# 驱动 jar 是厂商授权的，仓库里没有。内网自己有就不用带。
$jars = Get-ChildItem "deploy/jdbc/*.jar" -ErrorAction SilentlyContinue
if ($jars) {
    Copy-Item $jars.FullName (Join-Path $stage "deploy/jdbc/")
    Write-Host "    带上了 $($jars.Count) 个 JDBC 驱动 jar"
}

# .env 刻意不带：里面是真实密码和 API key，应当由部署人员在内网现场填。
@"
离线部署包 —— report-agent ($Tag)

  1. docker load -i images.tar.gz
  2. cp deploy/env.example .env   然后填真实值
  3. docker compose up -d
  4. curl http://localhost/healthz

完整说明见 DEPLOY.md。

注意：本包不含 .env。数据库密码、AUTH_SECRET、LLM 网关地址由部署人员
现场填写，不要从外网机器拷贝过来。
"@ | Out-File (Join-Path $stage "README.txt") -Encoding utf8

$size = "{0:N0} MB" -f ((Get-ChildItem $stage -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host ""
Write-Host "==> 完成：$stage（$size）" -ForegroundColor Green
Get-ChildItem $stage -Recurse -File | ForEach-Object {
    "    " + $_.FullName.Substring($stage.Length + 1)
}
