//! Tauri bridge: every command shells out to the Python CLI (`phonecert … --json`)
//! so the desktop app and the terminal share exactly the same core.
use serde_json::Value;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, State};

/// The `phonecert serve` child process (Safari hardware tests), one at a time.
#[derive(Default)]
/// The running `phonecert serve` process and the page address it announced.
struct TestServer(Mutex<Option<(Child, String)>>);

fn kill(server: &TestServer) {
    if let Ok(mut guard) = server.0.lock() {
        if let Some((mut child, _)) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// Where the Python CLI lives. `PHONECERT_BIN` overrides; otherwise the dev layout
/// `<repo>/desktop/src-tauri` → `<repo>/.venv/bin/phonecert`.
fn phonecert_bin() -> PathBuf {
    if let Ok(p) = std::env::var("PHONECERT_BIN") {
        return PathBuf::from(p);
    }
    repo_root().join(".venv/bin/phonecert")
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn run_cli(args: &[&str]) -> Result<Value, String> {
    run_cli_with_input(args, None)
}

/// Like `run_cli`, with `input` written to the command's stdin (used for secrets: arguments show up in `ps`).
fn run_cli_with_input(args: &[&str], input: Option<&str>) -> Result<Value, String> {
    use std::io::Write;
    let bin = phonecert_bin();
    let mut child = Command::new(&bin)
        .args(args)
        .stdin(if input.is_some() { Stdio::piped() } else { Stdio::null() })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("cannot start {}: {e} — run ./setup.sh", bin.display()))?;
    if let (Some(text), Some(mut stdin)) = (input, child.stdin.take()) {
        stdin.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
    }
    let out = child.wait_with_output().map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&out.stdout);
    if !out.status.success() {
        // The CLI prints "❌ <message>" (and a hint line) to stderr on failure.
        let stderr = String::from_utf8_lossy(&out.stderr);
        let msg = stderr
            .lines()
            .map(str::trim)
            .find(|l| !l.is_empty())
            .unwrap_or("unknown error")
            .trim_start_matches("❌ ")
            .to_string();
        return Err(msg);
    }
    serde_json::from_str(stdout.trim()).map_err(|e| format!("bad JSON from phonecert: {e}"))
}

async fn cli(args: &'static [&'static str]) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || run_cli(args))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn devices() -> Result<Value, String> {
    cli(&["devices", "--json"]).await
}

/// Full scan (~15–20 s). Saves the report JSON like the CLI does.
#[tauri::command]
async fn scan() -> Result<Value, String> {
    cli(&["scan", "--json"]).await
}

#[tauri::command]
async fn reports() -> Result<Value, String> {
    cli(&["reports", "--json"]).await
}

/// Move one saved scan to the Trash: `phonecert reports --delete <path> --json` → {"deleted", "reports"}.
#[tauri::command]
async fn delete_report(path: String) -> Result<Value, String> {
    let file = checked_report(&path)?.to_string_lossy().to_string();
    tauri::async_runtime::spawn_blocking(move || run_cli(&["reports", "--delete", &file, "--json"]))
        .await
        .map_err(|e| e.to_string())?
}

/// Move every saved scan to the Trash. The test page is stopped first: its report is going away.
#[tauri::command]
async fn clear_reports(server: State<'_, TestServer>) -> Result<Value, String> {
    kill(&server);
    cli(&["reports", "--clear", "--json"]).await
}

/// Paid IMEI lookup for a saved report: runs `phonecert imei --report <path> --json`,
/// which stores the result in the report, re-runs Trust and prints the updated report.
#[tauri::command]
async fn imei_check(path: String) -> Result<Value, String> {
    let reports_dir = repo_root().join("reports").canonicalize().map_err(|e| e.to_string())?;
    let file = PathBuf::from(&path).canonicalize().map_err(|e| e.to_string())?;
    if !file.starts_with(&reports_dir) {
        return Err("report path outside reports/".into());
    }
    let file_str = file.to_string_lossy().to_string();
    tauri::async_runtime::spawn_blocking(move || {
        run_cli(&["imei", "--report", &file_str, "--json"])
    })
    .await
    .map_err(|e| e.to_string())?
}

fn checked_report(path: &str) -> Result<PathBuf, String> {
    let reports_dir = repo_root().join("reports").canonicalize().map_err(|e| e.to_string())?;
    let file = PathBuf::from(path).canonicalize().map_err(|e| e.to_string())?;
    if !file.starts_with(&reports_dir) {
        return Err("report path outside reports/".into());
    }
    Ok(file)
}

/// Start the Safari test server. With a report path: attach to that scan. Without one (no cable):
/// `--new --label …` creates a tests-only report. Returns the ready line {"url", "port", "report", "secure"}.
#[tauri::command]
async fn start_tests(path: Option<String>, open: bool, https: bool, label: Option<String>,
                     server: State<'_, TestServer>) -> Result<Value, String> {
    kill(&server);
    let mut args: Vec<String> = vec!["serve".into()];
    match path.as_deref().filter(|p| !p.is_empty()) {
        Some(p) => {
            let file = checked_report(p)?;
            args.push("--report".into());
            args.push(file.to_string_lossy().to_string());
        }
        None => {
            args.push("--new".into());
            if let Some(l) = label.filter(|l| !l.trim().is_empty()) {
                args.push("--label".into());
                args.push(l);
            }
        }
    }
    if open {
        args.push("--open".into());
    }
    if https {
        args.push("--https".into());
    }
    let log_path = repo_root().join("reports").join(".webtests.log");
    let log = std::fs::OpenOptions::new().create(true).append(true).open(&log_path)
        .map_err(|e| format!("cannot open {}: {e}", log_path.display()))?;
    let mut child = Command::new(phonecert_bin())
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::from(log))
        .spawn()
        .map_err(|e| format!("cannot start test server: {e}"))?;
    // Until the child is stored in `server`, nothing else can stop it: kill it on every early return.
    let ready_line = (|| -> Result<(BufReader<std::process::ChildStdout>, Value), String> {
        let stdout = child.stdout.take().ok_or("no stdout")?;
        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        reader.read_line(&mut line).map_err(|e| e.to_string())?;
        let ready = serde_json::from_str(line.trim()).map_err(|e| format!("bad ready line {line:?}: {e}"))?;
        Ok((reader, ready))
    })();
    let (reader, ready): (_, Value) = match ready_line {
        Ok(v) => v,
        Err(e) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e);
        }
    };
    // Keep reading the event lines so the pipe never fills up and blocks the server; copy them to the log.
    let log_path2 = log_path.clone();
    std::thread::spawn(move || {
        use std::io::Write;
        let mut log = std::fs::OpenOptions::new().append(true).open(&log_path2).ok();
        for l in reader.lines().map_while(Result::ok) {
            if let Some(f) = log.as_mut() {
                let _ = writeln!(f, "{l}");
            }
        }
    });
    let url = ready.get("url").and_then(Value::as_str).unwrap_or_default().to_string();
    *server.0.lock().map_err(|e| e.to_string())? = Some((child, url));
    Ok(ready)
}

#[tauri::command]
async fn stop_tests(server: State<'_, TestServer>) -> Result<(), String> {
    kill(&server);
    Ok(())
}

/// Open the running test page in Safari on the cabled phone: `phonecert open <url> --json` → {"ok", "detail"}.
/// The address comes from this app's own server state; the frontend cannot supply one.
#[tauri::command]
async fn open_on_phone(server: State<'_, TestServer>) -> Result<Value, String> {
    let url = match &*server.0.lock().map_err(|e| e.to_string())? {
        Some((_, url)) if !url.is_empty() => url.clone(),
        _ => return Err("the test page is not running".into()),
    };
    tauri::async_runtime::spawn_blocking(move || run_cli(&["open", &url, "--json"]))
        .await
        .map_err(|e| e.to_string())?
}

/// Record a manual checklist result: `phonecert tests --report <path> --name … --status … --json`.
#[tauri::command]
async fn set_manual_test(path: String, name: String, status: String, note: Option<String>) -> Result<Value, String> {
    let file = checked_report(&path)?.to_string_lossy().to_string();
    tauri::async_runtime::spawn_blocking(move || {
        let mut args = vec!["tests", "--report", &file, "--name", &name, "--status", &status, "--json"];
        let note_val;
        if let Some(n) = note.as_deref() {
            note_val = n.to_string();
            args.push("--note");
            args.push(&note_val);
        }
        run_cli(&args)
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Re-run Trust for a saved scan after the settings changed, so the "Run check" button appears: `phonecert trust`.
#[tauri::command]
async fn refresh_trust(path: String) -> Result<Value, String> {
    let file = checked_report(&path)?.to_string_lossy().to_string();
    tauri::async_runtime::spawn_blocking(move || run_cli(&["trust", "--report", &file, "--json"]))
        .await
        .map_err(|e| e.to_string())?
}

/// Settings screen: `phonecert settings --json` → {"fields", "provider", "services"}. Saved keys are never returned.
#[tauri::command]
async fn get_settings() -> Result<Value, String> {
    cli(&["settings", "--json"]).await
}

/// Save changed settings. The values go to the CLI over stdin, not as arguments.
#[tauri::command]
async fn save_settings(changes: serde_json::Map<String, Value>) -> Result<Value, String> {
    let body = Value::Object(changes).to_string();
    tauri::async_runtime::spawn_blocking(move || run_cli_with_input(&["settings", "--set", "--json"], Some(&body)))
        .await
        .map_err(|e| e.to_string())?
}

/// Ask the provider whether the saved key works (free account call) → settings plus {"check": {"ok", "detail"}}.
#[tauri::command]
async fn check_provider() -> Result<Value, String> {
    cli(&["settings", "--check", "--json"]).await
}

/// Load one saved report. Only files inside <repo>/reports are allowed.
#[tauri::command]
async fn read_report(path: String) -> Result<Value, String> {
    let reports_dir = repo_root()
        .join("reports")
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let file = PathBuf::from(&path).canonicalize().map_err(|e| e.to_string())?;
    if !file.starts_with(&reports_dir) {
        return Err("report path outside reports/".into());
    }
    let text = std::fs::read_to_string(&file).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(TestServer::default())
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                kill(&window.state::<TestServer>());
            }
        })
        .invoke_handler(tauri::generate_handler![devices, scan, reports, read_report, imei_check,
                                                 start_tests, stop_tests, set_manual_test, open_on_phone,
                                                 delete_report, clear_reports,
                                                 get_settings, save_settings, check_provider, refresh_trust])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
