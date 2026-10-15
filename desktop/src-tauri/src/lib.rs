// ========================================================
// desktop/src-tauri/src/lib.rs
// 立体空间智能体系统 · Tauri 2.0 Rust 原生中枢与 Sidecar 进程守护器
// ========================================================

use std::fs::{create_dir_all, OpenOptions};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use tauri::{
    menu::{MenuBuilder, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, RunEvent, WindowEvent,
};

struct SidecarState {
    #[allow(dead_code)]
    child: Arc<Mutex<Option<Child>>>,
}

/// 智能自适应寻找项目物理根目录
fn find_project_root() -> PathBuf {
    // 1. 优先检查 exe 所在目录及其 resources 伴生目录 (生产安装包与便携包)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            if exe_dir.join("apps/server/headless_server.py").exists() {
                return exe_dir.to_path_buf();
            }
            if exe_dir.join("resources/apps/server/headless_server.py").exists() {
                return exe_dir.join("resources");
            }

            // 沿着 exe 所在路径逐级向上探测项目根目录 (兼容 target/debug/ 或 target/release/ 下调试)
            let mut cur = exe_dir;
            while let Some(parent) = cur.parent() {
                if parent.join("apps/server/headless_server.py").exists() {
                    return parent.to_path_buf();
                }
                cur = parent;
            }
        }
    }

    // 2. 检查当前运行工作目录
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.join("apps/server/headless_server.py").exists() {
            return cwd;
        }
        if let Some(parent) = cwd.parent() {
            if parent.join("apps/server/headless_server.py").exists() {
                return parent.to_path_buf();
            }
        }
    }

    // 3. 开发环境备用绝对根路径
    if let Ok(env_root) = std::env::var("AGENTOS_ROOT") {
        let p = PathBuf::from(env_root);
        if p.join("apps/server/headless_server.py").exists() {
            return p;
        }
    }

    PathBuf::from(".")
}

/// 深度解析真实 python.exe 物理路径（优先锁定内嵌便携环境，彻底实现 0 环境依赖）
fn resolve_python_runner(root: &Path) -> (String, Vec<String>) {
    #[cfg(windows)]
    {
        // 🌟 优先级 1（最高）：项目或 exe 同级内嵌便携式 Python 运行时 (runtime/python.exe)
        let embedded_python = root.join("runtime").join("python.exe");
        if embedded_python.is_file() {
            println!("⚡ [Tauri] 锁定内嵌便携式 Python 运行时: {}", embedded_python.display());
            return (embedded_python.to_string_lossy().to_string(), Vec::new());
        }

        // 备选检查：如果当前 exe 旁边有 runtime
        if let Ok(exe) = std::env::current_exe() {
            if let Some(exe_dir) = exe.parent() {
                let candidate = exe_dir.join("runtime").join("python.exe");
                if candidate.is_file() {
                    println!("⚡ [Tauri] 锁定 exe 伴生内嵌 Python 运行时: {}", candidate.display());
                    return (candidate.to_string_lossy().to_string(), Vec::new());
                }
            }
        }

        // 🌟 优先级 2：开发环境本地虚拟环境 (.venv/Scripts/python.exe)
        let venv_python = root.join(".venv").join("Scripts").join("python.exe");
        if venv_python.is_file() {
            println!("🔧 [Tauri] 锁定本地虚拟环境 Python: {}", venv_python.display());
            return (venv_python.to_string_lossy().to_string(), Vec::new());
        }

        // 🌟 优先级 3：扫描 pyenv-win 版本库中的真实 python.exe
        if let Ok(userprofile) = std::env::var("USERPROFILE") {
            let pyenv_versions = PathBuf::from(&userprofile).join(".pyenv").join("pyenv-win").join("versions");
            if pyenv_versions.is_dir() {
                if let Ok(entries) = std::fs::read_dir(&pyenv_versions) {
                    for entry in entries.flatten() {
                        let exe_path = entry.path().join("python.exe");
                        if exe_path.is_file() {
                            return (exe_path.to_string_lossy().to_string(), Vec::new());
                        }
                    }
                }
            }
        }

        // 🌟 优先级 4：检查常见系统 Python 安装路径
        for candidate in &[
            r"C:\Python312\python.exe",
            r"C:\Python311\python.exe",
            r"C:\Python310\python.exe",
            r"C:\Program Files\Python312\python.exe",
            r"C:\Program Files\Python311\python.exe",
            r"C:\Program Files\Python310\python.exe",
        ] {
            if Path::new(candidate).exists() {
                return (candidate.to_string(), Vec::new());
            }
        }

        // 🌟 优先级 5：兜底回退为 cmd.exe /c python (由 Windows 命令解释器天然分流 .bat)
        ("cmd.exe".to_string(), vec!["/c".to_string(), "python".to_string()])
    }

    #[cfg(not(windows))]
    {
        // 非 Windows 优先检查内嵌，再回退 python3
        let embedded = root.join("runtime").join("bin").join("python3");
        if embedded.is_file() {
            (embedded.to_string_lossy().to_string(), Vec::new())
        } else {
            ("python3".to_string(), Vec::new())
        }
    }
}

#[tauri::command]
fn get_session_token() -> String {
    let root = find_project_root();
    let token_path = root.join("workspace").join("data").join(".session_token");
    if let Ok(t) = std::fs::read_to_string(&token_path) {
        let tr = t.trim().to_string();
        if !tr.is_empty() {
            return tr;
        }
    }
    std::env::var("LITIKJ_API_TOKEN").unwrap_or_default()
}

/// 🛡️ 生成高熵 CSPRNG 会话凭据，优先依托 Python secrets 原语 (SEC-VULN-05)
fn generate_strong_token(python_program: &str) -> String {
    #[cfg(windows)]
    const CREATE_NO_WINDOW: u32 = 0x08000000;

    let mut cmd = Command::new(python_program);
    cmd.args(["-c", "import secrets; print(secrets.token_hex(32))"]);
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    if let Ok(output) = cmd.output() {
        if output.status.success() {
            if let Ok(tok) = String::from_utf8(output.stdout) {
                let trimmed = tok.trim().to_string();
                if trimmed.len() == 64 {
                    return trimmed;
                }
            }
        }
    }

    // 备用多源强熵回退：纳秒时间戳 + 进程ID + 堆指针内存地址混合扰动
    let p1 = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos();
    let p2 = std::process::id() as u128;
    let dummy = Box::new(42);
    let p3 = (&*dummy as *const i32 as usize) as u128;
    format!("{:032x}{:032x}", p1 ^ (p3 << 32), p2 ^ p3)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // 🛡️ [便携沙箱数据隔离] 在 Windows 下重定向 WebView2 数据存储目录至工作区沙箱，彻底杜绝跨机/跨实例全局污染
    #[cfg(windows)]
    {
        if std::env::var_os("WEBVIEW2_USER_DATA_FOLDER").is_none() {
            let root = find_project_root();
            let webview_data = root.join("workspace").join("data").join("webview");
            let _ = create_dir_all(&webview_data);
            let path_str = webview_data.to_string_lossy().to_string();
            let clean_path = path_str.strip_prefix(r"\\?\").unwrap_or(&path_str);
            unsafe {
                std::env::set_var("WEBVIEW2_USER_DATA_FOLDER", clean_path);
            }
            println!("🛡️ [Tauri] WebView2 绿色便携沙箱数据目录已挂载: {}", clean_path);
        }
    }

    let sidecar_child = Arc::new(Mutex::new(None));
    let sidecar_child_clone = Arc::clone(&sidecar_child);

    tauri::Builder::default()
        .manage(SidecarState {
            child: Arc::clone(&sidecar_child),
        })
        .invoke_handler(tauri::generate_handler![get_session_token])
        .setup(move |app| {
            let root = find_project_root();
            println!("📁 [Tauri] 锁定项目根目录: {}", root.display());

            // 1. 创建右下角系统托盘菜单
            let show_i = MenuItem::with_id(app, "show", "👑 打开智能体工作台", true, None::<&str>)?;
            let hide_i = MenuItem::with_id(app, "hide", "⬇️ 最小化到托盘", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "🚪 退出系统", true, None::<&str>)?;
            let menu = MenuBuilder::new(app)
                .item(&show_i)
                .item(&hide_i)
                .separator()
                .item(&quit_i)
                .build()?;

            // 2. 托盘图标绑定默认图标与左右键点击事件
            if let Some(default_icon) = app.default_window_icon() {
                let _tray = TrayIconBuilder::with_id("main")
                    .icon(default_icon.clone())
                    .tooltip("立体空间智能体系统 (Litikj Agent OS)")
                    .menu(&menu)
                    .show_menu_on_left_click(false)
                    .on_menu_event(|app, event| {
                        match event.id.as_ref() {
                            "show" => {
                                if let Some(window) = app.get_webview_window("main") {
                                    let _ = window.show();
                                    let _ = window.unminimize();
                                    let _ = window.set_focus();
                                }
                            }
                            "hide" => {
                                if let Some(window) = app.get_webview_window("main") {
                                    let _ = window.hide();
                                }
                            }
                            "quit" => {
                                app.exit(0);
                            }
                            _ => {}
                        }
                    })
                    .on_tray_icon_event(|tray, event| {
                        if let TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        } = event
                        {
                            let app = tray.app_handle();
                            if let Some(window) = app.get_webview_window("main") {
                                if window.is_visible().unwrap_or(false) {
                                    let _ = window.hide();
                                } else {
                                    let _ = window.show();
                                    let _ = window.unminimize();
                                    let _ = window.set_focus();
                                }
                            }
                        }
                    })
                    .build(app)?;
            }

            // 3. 检查是否为开机自启动唤醒 (--autostart / --minimized / --silent)
            let is_autostart = std::env::args().any(|arg| {
                arg == "--autostart" || arg == "--minimized" || arg == "--silent"
            });
            if is_autostart {
                println!("🌙 [Tauri] 开机自启静默唤醒，窗口自动最小化至系统托盘常驻");
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.hide();
                }
            }

            // 确保 workspace/logs 目录就绪 (若主目录无写权限，安全回退至系统临时目录，杜绝权限异常中断)
            let logs_dir = if create_dir_all(root.join("workspace").join("logs")).is_ok() {
                root.join("workspace").join("logs")
            } else {
                let fallback = std::env::temp_dir().join("litikj_agent_os").join("logs");
                let _ = create_dir_all(&fallback);
                fallback
            };
            let log_file_path = logs_dir.join("sidecar.log");

            // 在 Windows 下配置静默标志，杜绝任何控制台黑框弹出
            #[cfg(windows)]
            const CREATE_NO_WINDOW: u32 = 0x08000000;

            #[cfg(windows)]
            {
                // 启动前先清理可能存在的孤儿僵尸 Python 进程，杜绝端口冲突与旧进程代码缓存 (SEC-VULN-09: 严格限定仅清理 python 进程)
                let _ = Command::new("powershell")
                    .args(["-NoProfile", "-Command", "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 0 } | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($p -and ($p.ProcessName -like '*python*' -or $p.Path -like '*python*')) { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"])
                    .creation_flags(CREATE_NO_WINDOW)
                    .status();
            }

            let (program, prefix_args) = resolve_python_runner(&root);
            println!("🐍 [Tauri] 选定 Python 引擎核心: {}", program);

            let server_script = root.join("apps").join("server").join("headless_server.py");

            let token_path = root.join("workspace").join("data").join(".session_token");
            let session_token = if let Ok(t) = std::fs::read_to_string(&token_path) {
                let tr = t.trim().to_string();
                if !tr.is_empty() {
                    tr
                } else {
                    let new_tok = generate_strong_token(&program);
                    let _ = std::fs::write(&token_path, &new_tok);
                    new_tok
                }
            } else {
                let _ = create_dir_all(root.join("workspace").join("data"));
                let new_tok = generate_strong_token(&program);
                let _ = std::fs::write(&token_path, &new_tok);
                new_tok
            };

            let mut cmd = Command::new(&program);
            cmd.current_dir(&root);
            for arg in &prefix_args {
                cmd.arg(arg);
            }
            cmd.arg(&server_script);
            cmd.args(["--port", "8765", "--host", "127.0.0.1", "--token", &session_token]);
            cmd.env("LITIKJ_API_TOKEN", &session_token);
            cmd.env("PYTHONPATH", &root);
            cmd.env("PYTHONIOENCODING", "utf-8");
            cmd.env("PYTHONUTF8", "1");

            // 日志重定向至 workspace/logs/sidecar.log
            if let Ok(file) = OpenOptions::new().create(true).append(true).open(&log_file_path) {
                if let Ok(err_file) = file.try_clone() {
                    cmd.stdout(Stdio::from(file));
                    cmd.stderr(Stdio::from(err_file));
                }
            }

            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                cmd.creation_flags(CREATE_NO_WINDOW);
            }

            match cmd.spawn() {
                Ok(child) => {
                    println!("🚀 [Tauri] Python AI 微内核已作为 Sidecar 伴生拉起 (PID: {})", child.id());
                    let mut lock = sidecar_child_clone.lock().unwrap();
                    *lock = Some(child);
                }
                Err(err) => {
                    eprintln!("⚠️ [Tauri] 拉起 Python 伴生引擎提示: {}", err);
                }
            }

            if let Some(win) = app.get_webview_window("main") {
                use tauri::Listener;
                let token_clone = session_token.clone();
                let win_clone = win.clone();
                win.listen("tauri://page-loaded", move |_| {
                    let _ = win_clone.eval(&format!("window.__LITIKJ_API_TOKEN__ = '{}';", token_clone));
                });
                let _ = win.eval(&format!("window.__LITIKJ_API_TOKEN__ = '{}';", session_token));
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // 点击右上角关闭按钮时，隐藏至右下角系统托盘，不退出应用
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(move |_app_handle, event| {
            if let RunEvent::Exit = event {
                // 当主应用退出（如托盘菜单选择“退出系统”）时，安全释放 Python 伴生微内核
                let mut lock = sidecar_child.lock().unwrap();
                if let Some(mut child) = lock.take() {
                    println!("🛑 [Tauri] 正在安全释放 Python AI 微内核伴生引擎...");
                    let _ = child.kill();
                }
            }
        });
}
