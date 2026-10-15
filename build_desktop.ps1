# -*- coding: utf-8 -*-
# ========================================================
# 👑 立体空间智能体系统 · 商业级全流程复合打包流水线
# ========================================================
$ErrorActionPreference = 'Stop'

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   👑 立体空间智能体系统 · Tauri 2.0 商业级全流程构建流水线   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. 确保 Rust 工具链就绪
$cargoBin = "$env:USERPROFILE\.cargo\bin"
if (Test-Path "$cargoBin\cargo.exe") {
    $env:PATH = "$cargoBin;$env:PATH"
}

Write-Host "`n🔍 [步骤 1/4] 校验基础编译器与开发环境..." -ForegroundColor Yellow
& node --version
& cargo --version
& python --version

# 2. 准备嵌入式 Python 运行时与微内核巡检
Write-Host "`n🪐 [步骤 2/4] 准备/校验嵌入式 Python 运行时 (Zero-Config Runtime)..." -ForegroundColor Yellow
& python scripts\prepare_runtime.py
if (-not (Test-Path "runtime\python.exe")) {
    Write-Host "❌ 嵌入式运行时准备失败，未找到 runtime\python.exe" -ForegroundColor Red
    exit 1
}

Write-Host "🔍 执行嵌入式微内核独立巡检..." -ForegroundColor Gray
& .\runtime\python.exe run.py diagnose
Write-Host "✅ 嵌入式运行时独立巡检 100% 通过！" -ForegroundColor Green

Write-Host "📦 预构建官方卡带库 (.skill / .agent / .flow)..." -ForegroundColor Gray
& python scripts\build_skill_capsules.py
& python scripts\build_agent_capsules.py
& python scripts\build_workflow_capsules.py

# 3. 编译前端工程与 Tauri 桌面端
Write-Host "`n📦 [步骤 3/4] 编译 Vue 3 前端并构建 Tauri 2.0 原生二进制..." -ForegroundColor Yellow
Push-Location "desktop"
try {
    npm run build
    npx tauri build
} finally {
    Pop-Location
}

# 4. 组装归档双发布矩阵
Write-Host "`n🎉 [步骤 4/4] 组装并归档发行物矩阵..." -ForegroundColor Yellow
& python scripts\package_release.py

Write-Host "`n✨ 全流程自动化构建与归档大获成功！" -ForegroundColor Cyan
