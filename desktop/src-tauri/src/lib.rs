use std::sync::Mutex;
use tauri::{Manager, WindowEvent};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct SidecarState(Mutex<Option<CommandChild>>);

#[cfg(target_os = "windows")]
fn stop_sidecar(child: CommandChild) {
    let pid = child.pid().to_string();
    let tree_stopped = std::process::Command::new("taskkill")
        .args(["/PID", &pid, "/T", "/F"])
        .status()
        .is_ok_and(|status| status.success());
    if !tree_stopped {
        let _ = child.kill();
    }
}

#[cfg(not(target_os = "windows"))]
fn stop_sidecar(child: CommandChild) {
    let _ = child.kill();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState(Mutex::new(None)))
        .setup(|app| {
            let command = app
                .shell()
                .sidecar("datawork-sidecar")?
                .args(["--host", "127.0.0.1", "--port", "8765", "--no-browser"]);
            let (_events, child) = command.spawn()?;
            *app.state::<SidecarState>().0.lock().expect("sidecar state poisoned") = Some(child);
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::Destroyed) {
                if let Some(child) = window
                    .app_handle()
                    .state::<SidecarState>()
                    .0
                    .lock()
                    .expect("sidecar state poisoned")
                    .take()
                {
                    stop_sidecar(child);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running DataWork desktop application");
}
