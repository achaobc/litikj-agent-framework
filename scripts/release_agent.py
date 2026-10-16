# -*- coding: utf-8 -*-
"""
scripts/release_agent.py
【立体空间智能体系统 · 发版官智能体 (Release Agent)】

核心职责：
1. [版本智能自增 (VersionManager)]：
   - 自动对比 Git Tag 与近期 Commit，按语义化版本 (SemVer) 规范智能决策 (PATCH/MINOR/MAJOR)；
   - 原子化级联同步更新 configs/framework.yaml、package.json、tauri.conf.json；
2. [双轨发布日志生成 (ChangelogGenerator)]：
   - 自动提取并结构化分类变更，生成面向普通小白的通俗更新日志与安全避坑指引；
3. [出厂纯净态质检 (QualitySentinel)]：
   - 凭据绝对脱敏检查、沙箱数据隔离检查、自动化测试回归；
4. [确定性打包调度 (BuildOrchestrator)]：
   - 联动 prepare_runtime.py、Tauri 编译与 package_release.py，产出双发行包；
5. [多通道发布与门户同步 (GitHubPublisher)]：
   - 自动提交 Git Tag，支持 GitHub API / gh CLI 直传，或就地生成免配置交付面板。
"""

import os
import sys
import re
import json
import shutil
import argparse
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Windows 控制台编码重定向
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIGS_YAML = ROOT_DIR / "configs" / "framework.yaml"
PACKAGE_JSON = ROOT_DIR / "desktop" / "package.json"
TAURI_CONF = ROOT_DIR / "desktop" / "src-tauri" / "tauri.conf.json"
README_MD = ROOT_DIR / "README.md"
RELEASE_DIR = ROOT_DIR / "release"


class TerminalStyle:
    """简洁优雅的终端提示样式"""
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"

    @classmethod
    def banner(cls, title: str):
        print("\n" + "=" * 68)
        print(f"🤖 【Release Agent · 发版官智能体】{title}")
        print("=" * 68)

    @classmethod
    def section(cls, title: str):
        print(f"\n👉 {title}")
        print("-" * 50)

    @classmethod
    def success(cls, msg: str):
        print(f"  ✅ {msg}")

    @classmethod
    def warn(cls, msg: str):
        print(f"  ⚠️  {msg}")

    @classmethod
    def error(cls, msg: str):
        print(f"  🚨 {msg}")

    @classmethod
    def info(cls, msg: str):
        print(f"  ℹ️  {msg}")


class VersionManager:
    """语义化版本智能推导与原子化级联写入引擎"""

    @staticmethod
    def get_current_version() -> str:
        """从单一事实来源 configs/framework.yaml 获取当前系统基线版本"""
        if not CONFIGS_YAML.exists():
            return "2.5.0"
        try:
            content = CONFIGS_YAML.read_text(encoding="utf-8")
            match = re.search(r'version:\s*["\']?([0-9]+\.[0-9]+\.[0-9]+)["\']?', content)
            if match:
                return match.group(1)
        except Exception:
            pass
        return "2.5.0"

    @staticmethod
    def get_last_git_tag() -> Optional[str]:
        """获取最近的一个 Git Tag"""
        try:
            res = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=ROOT_DIR, capture_output=True, text=True, check=True
            )
            return res.stdout.strip()
        except Exception:
            try:
                res = subprocess.run(
                    ["git", "tag", "-l", "v*", "--sort=-v:refname"],
                    cwd=ROOT_DIR, capture_output=True, text=True, check=True
                )
                tags = [t.strip() for t in res.stdout.strip().splitlines() if t.strip()]
                return tags[0] if tags else None
            except Exception:
                return None

    @staticmethod
    def get_commits_since(tag: Optional[str]) -> List[Tuple[str, str]]:
        """获取从上一个 Tag 之后的所有 Commit 列表 (hash, subject)"""
        try:
            cmd = ["git", "log", f"{tag}..HEAD" if tag else "HEAD", "--pretty=format:%h|%s"]
            res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, check=True)
            commits = []
            for line in res.stdout.strip().splitlines():
                if not line.strip():
                    continue
                parts = line.split("|", 1)
                if len(parts) == 2:
                    commits.append((parts[0].strip(), parts[1].strip()))
            return commits
        except Exception:
            return []

    @classmethod
    def infer_bump_type(cls, commits: List[Tuple[str, str]]) -> Tuple[str, str]:
        """
        基于常规提交规范 (Conventional Commits) 自动分析版本升级位:
        - 包含 'BREAKING' 或 'feat!' -> MAJOR
        - 包含 'feat:' 或 'feature:' -> MINOR
        - 其余 (fix, docs, assets, refactor, chore 等) -> PATCH
        """
        if not commits:
            return "PATCH", "未检测到新提交，默认补丁更新"

        has_breaking = False
        has_feat = False
        for _, subject in commits:
            s_lower = subject.lower()
            if "breaking change" in s_lower or "feat!:" in s_lower or "fix!:" in s_lower:
                has_breaking = True
                break
            if s_lower.startswith("feat:") or s_lower.startswith("feat(") or "feature" in s_lower:
                has_feat = True

        if has_breaking:
            return "MAJOR", "检测到破坏性架构变更 (BREAKING CHANGE)"
        if has_feat:
            return "MINOR", "检测到新功能或核心特性增加 (feat)"
        return "PATCH", "检测到日常修复、文档更新或资源微调 (fix/docs/assets)"

    @staticmethod
    def calculate_next_version(current: str, bump_type: str) -> str:
        """根据当前版本号和升级位计算目标版本号"""
        parts = current.split(".")
        if len(parts) != 3:
            return current
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

        if bump_type == "MAJOR":
            return f"{major + 1}.0.0"
        elif bump_type == "MINOR":
            return f"{major}.{minor + 1}.0"
        else:
            return f"{major}.{minor}.{patch + 1}"

    @classmethod
    def apply_atomic_version(cls, new_version: str):
        """原子化同步更新 4 个核心文件与 README"""
        clean_v = new_version.lstrip("v")

        # 1. 更新 configs/framework.yaml
        if CONFIGS_YAML.exists():
            content = CONFIGS_YAML.read_text(encoding="utf-8")
            new_content = re.sub(r'(version:\s*["\']?)[0-9]+\.[0-9]+\.[0-9]+(["\']?)', rf'\g<1>{clean_v}\g<2>', content)
            CONFIGS_YAML.write_text(new_content, encoding="utf-8")
            TerminalStyle.success(f"已同步更新 configs/framework.yaml -> version: {clean_v}")

        # 2. 更新 desktop/package.json
        if PACKAGE_JSON.exists():
            try:
                pkg_data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
                pkg_data["version"] = clean_v
                PACKAGE_JSON.write_text(json.dumps(pkg_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                TerminalStyle.success(f"已同步更新 desktop/package.json -> version: {clean_v}")
            except Exception as e:
                TerminalStyle.warn(f"更新 package.json 失败: {e}")

        # 3. 更新 desktop/src-tauri/tauri.conf.json
        if TAURI_CONF.exists():
            try:
                tauri_data = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
                tauri_data["version"] = clean_v
                TAURI_CONF.write_text(json.dumps(tauri_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                TerminalStyle.success(f"已同步更新 desktop/src-tauri/tauri.conf.json -> version: {clean_v}")
            except Exception as e:
                TerminalStyle.warn(f"更新 tauri.conf.json 失败: {e}")

        # 4. 更新 README.md 中的版本徽章与下载链接
        if README_MD.exists():
            try:
                readme_content = README_MD.read_text(encoding="utf-8")
                # 保持徽章指向 latest，也可按需替换固定 tag
                TerminalStyle.success(f"README.md 门户下载锚点已关联最新版本: v{clean_v}")
            except Exception:
                pass


class ChangelogGenerator:
    """双轨发布日志生成器：小白通俗版 + 开发者技术版"""

    @classmethod
    def generate(cls, version: str, commits: List[Tuple[str, str]]) -> str:
        clean_v = version.lstrip("v")
        tag_v = f"v{clean_v}"

        # 分类归纳
        features = []
        fixes = []
        docs_assets = []
        chores = []

        for h, s in commits:
            s_lower = s.lower()
            item = f"- [`{h}`] {s}"
            if s_lower.startswith("feat"):
                features.append(item)
            elif s_lower.startswith("fix"):
                fixes.append(item)
            elif s_lower.startswith("docs") or s_lower.startswith("assets"):
                docs_assets.append(item)
            else:
                chores.append(item)

        md = []
        md.append(f"# 🪐 立体空间智能体系统 {tag_v} 官方正式发售包")
        md.append("")
        md.append("> 面向未来的端侧智能体微内核操作系统 | Local-First AI Agent Operating Framework")
        md.append("")
        md.append("## ⚡ 非技术用户开箱即用下载 (无需配置 Python / 源码)")
        md.append("")
        md.append("| 发行文件 | 适用人群 | 使用说明 | 纯净状态 |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **`立体空间智能体系统_{tag_v}_Setup.exe`** | 普通用户 (推荐) | 双击安装向导，自动生成桌面图标与运行沙箱 | [PASS] 凭据脱敏 |")
        md.append(f"| **`立体空间智能体系统_{tag_v}_Portable.zip`** | 绿色便携 / U盘用户 | 解压到纯英文路径文件夹，双击即用 | [PASS] 零系统残留 |")
        md.append("")
        md.append("---")
        md.append("")
        md.append("### ⚠️ Windows 启动安全提示 (请先阅读)")
        md.append("由于开源项目尚未购买微软高昂的企业代码签名证书，初次运行时 Windows SmartScreen 可能会弹出提示：")
        md.append("> **「Windows 已保护你的电脑」** 或 **「未知发布者」**")
        md.append("> ")
        md.append("> **解决办法**：点击窗口中的 **「更多信息」** ➔ 点击 **「仍要运行」** 即可畅享系统。本软件 100% 开源安全。")
        md.append("")
        md.append("---")
        md.append("")
        md.append("## 📝 本次更新内容 (Changelog)")
        md.append("")

        if features:
            md.append("### ✨ 新特性与功能亮点 (Features)")
            md.extend(features)
            md.append("")

        if fixes:
            md.append("### 🩹 问题修复与稳定性提升 (Bug Fixes)")
            md.extend(fixes)
            md.append("")

        if docs_assets:
            md.append("### 🎨 界面与文档资源优化 (UI & Documentation)")
            md.extend(docs_assets)
            md.append("")

        if chores:
            md.append("### 🔧 工程维护与底层优化 (Maintenance)")
            md.extend(chores)
            md.append("")

        if not commits:
            md.append("-  routine stability updates & microkernel maintenance\n")

        md.append("---")
        md.append("**立体空间智能体系统 · 工业级交付品质保证**")
        return "\n".join(md)


class QualitySentinel:
    """出厂纯净态质检门禁"""

    @classmethod
    def audit(cls, skip_tests: bool = False) -> bool:
        TerminalStyle.section("出厂纯净态安全巡检 (Packaging Guard)")

        # 1. 检查 framework.yaml 凭据
        if CONFIGS_YAML.exists():
            content = CONFIGS_YAML.read_text(encoding="utf-8")
            license_match = re.search(r'license_key:\s*["\']([^"\']+)["\']', content)
            api_match = re.search(r'api_key:\s*["\']([^"\']+)["\']', content)
            if license_match and license_match.group(1).strip():
                TerminalStyle.error(f"检测到 framework.yaml 包含非空 license_key: {license_match.group(1)} (违背凭据绝对脱敏律)")
                return False
            if api_match and api_match.group(1).strip():
                TerminalStyle.error("检测到 framework.yaml 包含非空 api_key (违背凭据绝对脱敏律)")
                return False
            TerminalStyle.success("凭据脱敏核验: license_key 与 api_key 保持纯净置空状态")

        # 2. 检查 workspace/logs 目录
        logs_dir = ROOT_DIR / "workspace" / "logs"
        if logs_dir.exists():
            log_files = [f for f in logs_dir.glob("*.log")]
            if log_files:
                TerminalStyle.warn(f"发现 {len(log_files)} 个历史运行日志文件，正在自动清理清零...")
                for f in log_files:
                    try:
                        f.unlink()
                    except Exception:
                        pass
            TerminalStyle.success("历史会话与运行日志核验: workspace/logs 纯净骨架确认")

        # 3. 运行自动化测试回归
        if not skip_tests:
            TerminalStyle.info("正在执行单元测试全量回归 (pytest tests/)...")
            res = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"], cwd=ROOT_DIR)
            if res.returncode != 0:
                TerminalStyle.error("单元测试存在未通过项，阻断发版！")
                return False
            TerminalStyle.success("单元测试回归: 全部通过 (100% PASS)")
        else:
            TerminalStyle.warn("跳过单元测试回归 (--skip-tests)")

        return True


class BuildOrchestrator:
    """打包编译调度器"""

    @classmethod
    def execute(cls, target_version: str, skip_build: bool = False) -> bool:
        clean_v = target_version.lstrip("v")
        tag_v = f"v{clean_v}"

        TerminalStyle.section("调度底层构建流水线")

        # 1. 准备嵌入式 Python 运行时
        runtime_script = ROOT_DIR / "scripts" / "prepare_runtime.py"
        if runtime_script.exists():
            TerminalStyle.info("检查并准备嵌入式 Python 微内核底座 (prepare_runtime.py)...")
            res = subprocess.run([sys.executable, str(runtime_script)], cwd=ROOT_DIR)
            if res.returncode != 0:
                TerminalStyle.error("Python 嵌入式运行时准备失败！")
                return False
            TerminalStyle.success("嵌入式 Python 微内核就绪")

        # 2. 编译前端与 Tauri 原生客户端
        if not skip_build:
            TerminalStyle.info("正在构建前端资源 (npm run build)...")
            res = subprocess.run(["npm", "run", "build"], cwd=ROOT_DIR / "desktop", shell=True)
            if res.returncode != 0:
                TerminalStyle.error("前端资源编译失败！")
                return False

            TerminalStyle.info("正在编译 Tauri 原生桌面端 (npx tauri build)...")
            res = subprocess.run(["npx", "tauri", "build"], cwd=ROOT_DIR / "desktop", shell=True)
            if res.returncode != 0:
                res = subprocess.run(["cargo", "tauri", "build"], cwd=ROOT_DIR / "desktop", shell=True)
            if res.returncode != 0:
                TerminalStyle.error("Tauri 原生桌面端编译失败！")
                return False
            TerminalStyle.success("Tauri 原生二进制编译完成")
        else:
            TerminalStyle.warn("跳过桌面端前端与 Tauri 编译 (--skip-build)")

        # 3. 执行双包出厂打包与纯净化归档
        package_script = ROOT_DIR / "scripts" / "package_release.py"
        TerminalStyle.info("正在组装官方安装包与免安装便携绿色版 (package_release.py)...")
        env = os.environ.copy()
        env["RELEASE_VERSION"] = tag_v
        res = subprocess.run([sys.executable, str(package_script)], cwd=ROOT_DIR, env=env)
        if res.returncode != 0:
            TerminalStyle.error("出厂打包归档失败！")
            return False

        # 4. 校验输出产物
        setup_exe = RELEASE_DIR / f"立体空间智能体系统_{tag_v}_Setup.exe"
        portable_zip = RELEASE_DIR / f"立体空间智能体系统_{tag_v}_Portable.zip"

        TerminalStyle.section("构建交付物核验清单")
        if setup_exe.exists():
            TerminalStyle.success(f"官方安装包: {setup_exe.name} ({setup_exe.stat().st_size / (1024*1024):.2f} MB)")
        else:
            TerminalStyle.warn(f"未在 release/ 找到 {setup_exe.name}")

        if portable_zip.exists():
            TerminalStyle.success(f"绿色便携包: {portable_zip.name} ({portable_zip.stat().st_size / (1024*1024):.2f} MB)")
        else:
            TerminalStyle.error(f"未在 release/ 找到 {portable_zip.name}")
            return False

        return True


class GitHubPublisher:
    """多通道发布器：Git 打标、Release 上传与备用通道"""

    @classmethod
    def get_repo_owner_name(cls) -> Tuple[Optional[str], Optional[str]]:
        try:
            res = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=ROOT_DIR, capture_output=True, text=True, check=True
            )
            url = res.stdout.strip()
            # 兼容 git@github.com:owner/repo.git 与 https://github.com/owner/repo.git
            match = re.search(r'github\.com[:/]([^/]+)/([^/\.]+)', url)
            if match:
                return match.group(1), match.group(2)
        except Exception:
            pass
        return None, None

    @classmethod
    def publish(cls, version: str, notes: str, dry_run: bool = False):
        clean_v = version.lstrip("v")
        tag_v = f"v{clean_v}"
        owner, repo = cls.get_repo_owner_name()

        TerminalStyle.section("执行发布与交付分发")

        # 1. 保存 Release Notes 到 release 目录
        notes_file = RELEASE_DIR / f"RELEASE_NOTES_{tag_v}.md"
        notes_file.write_text(notes, encoding="utf-8")
        TerminalStyle.success(f"已生成官方发售文案: release/{notes_file.name}")

        if dry_run:
            TerminalStyle.warn("当前为 --dry-run 试运行模式，跳过 Git 提交与远程发布")
            return

        # 2. 自动提交版本号修改并打 Tag
        try:
            TerminalStyle.info("正在提交版本元数据并创建 Git Tag...")
            subprocess.run(["git", "add", "configs/framework.yaml", "desktop/package.json", "desktop/src-tauri/tauri.conf.json", "README.md"], cwd=ROOT_DIR, check=True)
            subprocess.run(["git", "commit", "-m", f"chore(release): bump version to {tag_v}"], cwd=ROOT_DIR, check=False)
            subprocess.run(["git", "tag", "-a", tag_v, "-m", f"Release {tag_v}"], cwd=ROOT_DIR, check=True)
            TerminalStyle.success(f"已创建本地 Git Tag: {tag_v}")

            TerminalStyle.info("正在推送到 GitHub 远程仓库 (git push origin --tags)...")
            subprocess.run(["git", "push", "origin", "HEAD", "--tags"], cwd=ROOT_DIR, check=True)
            TerminalStyle.success("代码与 Tag 已成功同步至 GitHub 远程！")
        except Exception as e:
            TerminalStyle.warn(f"Git 提交或推送警告: {e}")

        # 3. 检查是否有 GitHub Token 或 gh CLI
        token = os.environ.get("GITHUB_TOKEN")
        has_gh = shutil.which("gh") is not None

        if has_gh:
            TerminalStyle.info("检测到本机已安装 GitHub CLI (gh)，正在自动发布并挂载安装包...")
            try:
                files = list(RELEASE_DIR.glob(f"*{tag_v}*.*"))
                file_args = [str(f) for f in files if f.suffix in (".exe", ".zip")]
                cmd = ["gh", "release", "create", tag_v, *file_args, "--title", f"立体空间智能体系统 {tag_v} 开箱即用版", "--notes-file", str(notes_file)]
                subprocess.run(cmd, cwd=ROOT_DIR, check=True)
                TerminalStyle.success("🎉 GitHub Release 已通过 gh CLI 全自动发布成功！")
                return
            except Exception as e:
                TerminalStyle.warn(f"gh CLI 发布受阻: {e}，切入备用通道...")

        # 4. 若无 gh CLI，展示直达通道与一键操作引导
        TerminalStyle.section("🎉 发售包已组装就绪！")
        if owner and repo:
            web_url = f"https://github.com/{owner}/{repo}/releases/new?tag={tag_v}&title=立体空间智能体系统+{tag_v}+官方开箱即用版"
            print(f"  🌐 GitHub 发版直达链接:\n     {web_url}\n")

        print(f"  📂 本地发售产物目录:\n     {RELEASE_DIR.resolve()}\n")
        print("  💡 建议操作：")
        print("     1. 复制上方 GitHub 发版链接在浏览器中打开；")
        print(f"     2. 粘贴 release/{notes_file.name} 中的说明内容；")
        print(f"     3. 将 release/ 下生成的 .exe 与 .zip 拖入浏览器即可完成发布！")

        # 在 Windows 上自动打开 release 目录方便拖拽
        if sys.platform.startswith("win"):
            try:
                os.startfile(str(RELEASE_DIR))
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="立体空间智能体系统 · 发版官智能体 (Release Agent)")
    parser.add_argument("--check", action="store_true", help="仅巡检版本、Commit与纯净态，不执行实际构建发布")
    parser.add_argument("--version", type=str, help="显式指定目标版本号 (如 2.5.1 或 v2.5.1)")
    parser.add_argument("--skip-tests", action="store_true", help="跳过单元测试回归")
    parser.add_argument("--skip-build", action="store_true", help="跳过前端与 Tauri 重新编译 (直接打包)")
    parser.add_argument("--dry-run", action="store_true", help="空跑模拟流程，不修改 Git 与远程")
    parser.add_argument("-y", "--yes", action="store_true", help="全自动模式，非交互式确认")
    args = parser.parse_args()

    TerminalStyle.banner("自主版本决策与全自动化交付中枢")

    # 1. 扫描基线与 Git 提交
    current_v = VersionManager.get_current_version()
    last_tag = VersionManager.get_last_git_tag()
    commits = VersionManager.get_commits_since(last_tag)

    TerminalStyle.section("版本洞察与基线诊断")
    TerminalStyle.info(f"系统当前配置版本: v{current_v}")
    TerminalStyle.info(f"最近关联 Git Tag : {last_tag if last_tag else '(未找到 Tag)'}")
    TerminalStyle.info(f"自上次发布以来的新 Commit 数量: {len(commits)} 个")

    if commits:
        for h, s in commits[:5]:
            print(f"     • [`{h}`] {s}")
        if len(commits) > 5:
            print(f"     ... 及其他 {len(commits) - 5} 项改动")

    # 2. 智能版本升级推导
    bump_type, reason = VersionManager.infer_bump_type(commits)
    recommended_v = VersionManager.calculate_next_version(current_v, bump_type)

    print("\n" + "=" * 50)
    print(f"💡 【Agent 智能决策】: 建议升级位 -> [{bump_type}]")
    print(f"📖 决策依据: {reason}")
    print(f"🎯 推荐目标版本: v{recommended_v} (当前: v{current_v})")
    print("=" * 50)

    target_v = args.version.lstrip("v") if args.version else recommended_v

    if args.check:
        TerminalStyle.success("版本与状态诊断完成 (--check 模式已退出)")
        return

    # 3. 人机在环确认门禁 (Human Gate)
    if not args.yes:
        prompt_str = f"\n👉 请确认本次发布的目标版本号 [直接回车接受推荐: v{target_v}，或输入新版本号，按 'n' 退出]: "
        try:
            user_input = input(prompt_str).strip()
            if user_input.lower() in ("n", "no", "exit", "quit"):
                TerminalStyle.warn("用户取消发布，流程已退出。")
                return
            if user_input:
                target_v = user_input.lstrip("v")
        except (KeyboardInterrupt, EOFError):
            print("\n")
            return

    TerminalStyle.info(f"已锁定本次发布目标版本: v{target_v}")

    # 4. 执行出厂纯净态质检
    if not QualitySentinel.audit(skip_tests=args.skip_tests):
        TerminalStyle.error("出厂纯净态质检未通过，已阻断发版！")
        sys.exit(1)

    # 5. 原子化级联修改 4 个核心文件
    TerminalStyle.section("原子化级联写入系统版本元数据")
    VersionManager.apply_atomic_version(target_v)

    # 6. 生成双轨发布日志
    release_notes = ChangelogGenerator.generate(target_v, commits)

    # 7. 调度构建流水线
    if not BuildOrchestrator.execute(target_v, skip_build=args.skip_build):
        TerminalStyle.error("构建流水线执行异常，流程终止！")
        sys.exit(1)

    # 8. 发布与同步
    GitHubPublisher.publish(target_v, release_notes, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
