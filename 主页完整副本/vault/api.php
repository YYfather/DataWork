<?php
/**
 * 凭证保险箱 v2 — 多用户 API（SQLite 版）
 * 支持：主账号/子账号、分类级权限、条目 CRUD
 */
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Authorization, Content-Type');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, private');
header('Pragma: no-cache');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(200); exit; }

// ---- 调试日志（带脱敏）----
function vault_log($level, $message) {
    $logDir = defined('DATA_DIR') ? DATA_DIR : __DIR__;
    $logFile = $logDir . '/vault_debug.log';
    $ts = date('Y-m-d H:i:s');
    $message = preg_replace('/\b(password|password_field|token|_auth|Authorization)\b[=:]\s*["\']?[^"\'&\s]{3,}["\'\s&]*/i', '$1=[REDACTED]', $message);
    $message = preg_replace('/Bearer\s+[A-Za-z0-9]+/', 'Bearer [REDACTED]', $message);
    $line = "[{$ts}] [{$level}] {$message}" . PHP_EOL;
    @file_put_contents($logFile, $line, FILE_APPEND | LOCK_EX);
    error_log("[Vault {$level}] {$message}");
}

// ---- 全局错误捕获 ----
set_error_handler(function($severity, $msg, $file, $line) {
    if (!(error_reporting() & $severity)) return;
    $fatal = [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR, E_USER_ERROR, E_RECOVERABLE_ERROR];
    if (in_array($severity, $fatal)) {
        $errInfo = '服务器错误: ' . $msg . ' in ' . basename($file) . ':' . $line;
        vault_log('FATAL', $errInfo);
        http_response_code(500);
        echo json_encode(['error' => $errInfo]);
        exit;
    }
    $map = [E_WARNING => 'WARNING', E_NOTICE => 'NOTICE', E_DEPRECATED => 'DEPRECATED',
            E_USER_WARNING => 'USER_WARNING', E_USER_NOTICE => 'USER_NOTICE',
            E_USER_DEPRECATED => 'USER_DEPRECATED', E_STRICT => 'STRICT'];
    $type = $map[$severity] ?? 'UNKNOWN';
    vault_log($type, "{$msg} in {$file}:{$line}");
    return true;
});

// ---- 加密工具（AES-256-CBC）----
function getEncryptionKey($db) {
    $stmt = $db->prepare("SELECT value FROM settings WHERE key = 'crypto_master_key'");
    $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if ($row && !empty($row['value'])) return base64_decode($row['value']);
    $key = random_bytes(32);
    $stmt = $db->prepare("INSERT OR REPLACE INTO settings (key, value) VALUES ('crypto_master_key', :v)");
    $stmt->bindValue(':v', base64_encode($key), SQLITE3_TEXT);
    $stmt->execute();
    vault_log('CRYPTO', '已生成新的数据加密密钥');
    return $key;
}
function encryptPassword($db, $plaintext) {
    if ($plaintext === '' || $plaintext === null) return '';
    $key = getEncryptionKey($db);
    $iv = random_bytes(12); // GCM 推荐 12 字节
    $tag = '';
    $ciphertext = openssl_encrypt($plaintext, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
    if ($ciphertext === false) { vault_log('CRYPTO', '加密失败'); return $plaintext; }
    return base64_encode($iv . $tag . $ciphertext);
}
function decryptPassword($db, $ciphertext) {
    if ($ciphertext === '' || $ciphertext === null) return '';
    $decoded = @base64_decode($ciphertext, true);
    if ($decoded === false || strlen($decoded) < 16) return $ciphertext;
    $key = getEncryptionKey($db);
    
    // 检测格式：CBC 用 16 字节 IV，GCM 用 12 字节 IV + 16 字节 tag
    if (strlen($decoded) > 28) {
        // 尝试 GCM 解密
        $iv = substr($decoded, 0, 12);
        $tag = substr($decoded, 12, 16);
        $encrypted = substr($decoded, 28);
        $plaintext = openssl_decrypt($encrypted, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
        if ($plaintext !== false) return $plaintext;
    }
    
    // 回退到 CBC 解密（向后兼容）
    $iv = substr($decoded, 0, 16);
    $encrypted = substr($decoded, 16);
    $plaintext = openssl_decrypt($encrypted, 'aes-256-cbc', $key, OPENSSL_RAW_DATA, $iv);
    if ($plaintext === false) return $ciphertext;
    return $plaintext;
}
function encryptSettingSecret($db, $plaintext) {
    if ($plaintext === '' || $plaintext === null) return '';
    $encrypted = encryptPassword($db, $plaintext);
    return $encrypted === $plaintext ? $plaintext : 'enc:v1:' . $encrypted;
}
function decryptSettingSecret($db, $stored) {
    if ($stored === '' || $stored === null) return '';
    if (strpos($stored, 'enc:v1:') !== 0) return $stored;
    $payload = substr($stored, 7);
    $decrypted = decryptPassword($db, $payload);
    return $decrypted === $payload ? '' : $decrypted;
}
function migrateWebdavPasswordEncryption($db) {
    $stmt = $db->prepare("SELECT value FROM settings WHERE key = 'webdav_password'");
    $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    $stored = $row['value'] ?? '';
    if ($stored === '' || strpos($stored, 'enc:v1:') === 0) return;
    $encrypted = encryptSettingSecret($db, $stored);
    if ($encrypted === $stored) {
        vault_log('WEBDAV', 'WebDAV 密码加密迁移失败，保留旧值');
        return;
    }
    $stmt = $db->prepare("UPDATE settings SET value = :value WHERE key = 'webdav_password'");
    $stmt->bindValue(':value', $encrypted, SQLITE3_TEXT);
    $stmt->execute();
    vault_log('WEBDAV', 'WebDAV 密码已迁移为加密存储');
}
function migratePasswordsToEncrypted($db) {
    $rows = $db->query("SELECT id, password_field FROM entries WHERE password_field != ''");
    $count = 0;
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $plain = $r['password_field'];
        $decoded = @base64_decode($plain, true);
        if ($decoded !== false && strlen($decoded) >= 16) continue;
        $encrypted = encryptPassword($db, $plain);
        if ($encrypted !== $plain) {
            $stmt = $db->prepare("UPDATE entries SET password_field = :pwd WHERE id = :id");
            $stmt->bindValue(':pwd', $encrypted, SQLITE3_TEXT);
            $stmt->bindValue(':id', $r['id'], SQLITE3_INTEGER);
            $stmt->execute();
            $count++;
        }
    }
    if ($count > 0) vault_log('CRYPTO', "已迁移 {$count} 条密码为加密存储");
}

// ---- 鉴权工具 ----
function authenticate($db) {
    $auth = '';
    if (function_exists('getallheaders')) {
        $h = getallheaders();
        $auth = $h['Authorization'] ?? $h['authorization'] ?? '';
    }
    if (!$auth) $auth = $_SERVER['HTTP_AUTHORIZATION'] ?? $_POST['_auth'] ?? '';
    if (!$auth) { vault_log('AUTH', '鉴权失败：未提供 Authorization 头'); return null; }
    if (substr($auth, 0, 7) === 'Bearer ') {
        $token = substr($auth, 7);
        $stmt = $db->prepare("SELECT u.* FROM users u JOIN sessions s ON u.id = s.user_id
            WHERE s.token = :token AND s.expires_at > datetime('now','localtime') AND u.is_active = 1");
        $stmt->bindValue(':token', $token, SQLITE3_TEXT);
        $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
        return $row ?: null;
    }
    return null;
}
function requireMaster($user) {
    if ($user['role'] !== 'master') { http_response_code(403); echo json_encode(['error' => '仅主账号可执行此操作']); exit; }
}
function jsonInput() {
    $body = file_get_contents('php://input');
    if (!$body && isset($_POST['_body'])) $body = $_POST['_body'];
    return json_decode($body, true) ?? [];
}
function validateUsername($username) {
    if (!preg_match('/^[A-Za-z0-9_.@-]{2,32}$/', $username)) {
        http_response_code(400); echo json_encode(['error' => '用户名需为 2-32 位，可包含字母、数字、点、下划线、@ 或短横线']); exit;
    }
}
function validatePassword($password) {
    $errors = [];
    if (strlen($password) < 8) {
        $errors[] = '密码至少8位';
    }
    if (!preg_match('/[A-Z]/', $password)) {
        $errors[] = '需包含大写字母';
    }
    if (!preg_match('/[a-z]/', $password)) {
        $errors[] = '需包含小写字母';
    }
    if (!preg_match('/[0-9]/', $password)) {
        $errors[] = '需包含数字';
    }
    if (!empty($errors)) {
        http_response_code(400);
        echo json_encode(['error' => implode('，', $errors)]);
        exit;
    }
}
function recordLoginAttempt($db, $ip) {
    $stmt = $db->prepare("SELECT id, attempts, first_attempt FROM login_attempts WHERE ip = :ip");
    $stmt->bindValue(':ip', $ip, SQLITE3_TEXT);
    $existing = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if ($existing) {
        if ((time() - strtotime($existing['first_attempt'])) > 300) {
            $stmt = $db->prepare("UPDATE login_attempts SET attempts = 1, first_attempt = datetime('now','localtime'), blocked_until = NULL WHERE id = :id");
        } else {
            $stmt = $db->prepare("UPDATE login_attempts SET attempts = attempts + 1 WHERE id = :id");
        }
        $stmt->bindValue(':id', $existing['id'], SQLITE3_INTEGER);
    } else {
        $stmt = $db->prepare("INSERT INTO login_attempts (ip, attempts) VALUES (:ip, 1)");
        $stmt->bindValue(':ip', $ip, SQLITE3_TEXT);
    }
    $stmt->execute();
}

// ---- 数据库辅助函数 ----
function migrateColumns($db) {
    $cols = [];
    $res = $db->query("PRAGMA table_info(users)");
    if ($res === false) return; // 表不存在或数据库不可写，跳过迁移
    while ($r = $res->fetchArray(SQLITE3_ASSOC)) $cols[$r['name']] = true;
    $additions = ['last_login'=>'ALTER TABLE users ADD COLUMN last_login DATETIME DEFAULT NULL','login_count'=>'ALTER TABLE users ADD COLUMN login_count INTEGER DEFAULT 0','display_name'=>"ALTER TABLE users ADD COLUMN display_name TEXT DEFAULT ''"];
    foreach ($additions as $col => $sql) { if (!isset($cols[$col])) $db->exec($sql); }
    $entryCols = [];
    $res = $db->query("PRAGMA table_info(entries)");
    if ($res === false) return;
    while ($r = $res->fetchArray(SQLITE3_ASSOC)) $entryCols[$r['name']] = true;
    if (!isset($entryCols['sort_order'])) { $db->exec("ALTER TABLE entries ADD COLUMN sort_order INTEGER DEFAULT 0"); $db->exec("UPDATE entries SET sort_order = id WHERE sort_order IS NULL OR sort_order = 0"); }
    if (!isset($entryCols['icon'])) { $db->exec("ALTER TABLE entries ADD COLUMN icon TEXT DEFAULT ''"); }
}
function migrateFromJson($db) {
    $jsonPath = __DIR__ . '/_vault_data.json';
    $oldPath2 = DATA_DIR . '/_vault_data.json';
    if (!file_exists($jsonPath) && file_exists($oldPath2)) $jsonPath = $oldPath2;
    if (!file_exists($jsonPath)) return;
    $cnt = $db->querySingle("SELECT COUNT(*) FROM categories");
    if ($cnt > 0) return;
    $raw = @file_get_contents($jsonPath);
    $data = json_decode($raw, true);
    if (!$data || !isset($data['categories'])) return;
    $db->exec('BEGIN');
    try {
        foreach ($data['categories'] as $cat) {
            $stmt = $db->prepare("INSERT INTO categories (name, icon, sort_order) VALUES (:name, :icon, :order)");
            $stmt->bindValue(':name', $cat['name'] ?? '未命名', SQLITE3_TEXT);
            $stmt->bindValue(':icon', $cat['icon'] ?? '🔑', SQLITE3_TEXT);
            $stmt->bindValue(':order', $cat['sort_order'] ?? 0, SQLITE3_INTEGER);
            $stmt->execute();
            $catId = $db->lastInsertRowID();
            foreach ($cat['entries'] ?? [] as $entry) {
                $encryptedPwd = encryptPassword($db, $entry['password'] ?? '');
                $stmt = $db->prepare("INSERT INTO entries (category_id, title, username_field, password_field, url, notes, updated_at) VALUES (:cid, :title, :uname, :pwd, :url, :notes, :ts)");
                $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
                $stmt->bindValue(':title', $entry['title'] ?? '', SQLITE3_TEXT);
                $stmt->bindValue(':uname', $entry['username'] ?? '', SQLITE3_TEXT);
                $stmt->bindValue(':pwd', $encryptedPwd, SQLITE3_TEXT);
                $stmt->bindValue(':url', $entry['url'] ?? '', SQLITE3_TEXT);
                $stmt->bindValue(':notes', $entry['notes'] ?? '', SQLITE3_TEXT);
                $stmt->bindValue(':ts', $data['updatedAt'] ?? date('c'), SQLITE3_TEXT);
                $stmt->execute();
            }
        }
        $db->exec('COMMIT');
        rename($jsonPath, $jsonPath . '.migrated');
    } catch (Exception $e) { $db->exec('ROLLBACK'); }
}
function initDB($db) {
    $db->exec("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,display_name TEXT DEFAULT '',role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('master','user')),is_active INTEGER DEFAULT 1,last_login DATETIME DEFAULT NULL,login_count INTEGER DEFAULT 0,created_at DATETIME DEFAULT (datetime('now','localtime')))");
    $db->exec("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires_at DATETIME NOT NULL,FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)");
    $db->exec("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,icon TEXT DEFAULT '🔑',sort_order INTEGER DEFAULT 0,created_at DATETIME DEFAULT (datetime('now','localtime')))");
    $db->exec("CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT,category_id INTEGER NOT NULL,title TEXT NOT NULL,username_field TEXT DEFAULT '',password_field TEXT DEFAULT '',url TEXT DEFAULT '',notes TEXT DEFAULT '',created_by INTEGER,sort_order INTEGER DEFAULT 0,updated_at DATETIME DEFAULT (datetime('now','localtime')),FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE)");
    $db->exec("CREATE TABLE IF NOT EXISTS category_permissions (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,category_id INTEGER NOT NULL,can_read INTEGER DEFAULT 1,can_write INTEGER DEFAULT 0,UNIQUE(user_id,category_id),FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE)");
    $db->exec("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)");
    $db->exec("CREATE TABLE IF NOT EXISTS entry_permissions (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,entry_id INTEGER NOT NULL,can_view INTEGER DEFAULT 1,UNIQUE(user_id,entry_id),FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE)");
    $db->exec("CREATE TABLE IF NOT EXISTS proposals (id INTEGER PRIMARY KEY AUTOINCREMENT,proposal_type TEXT NOT NULL DEFAULT 'create' CHECK(proposal_type IN ('create','update','report')),title TEXT NOT NULL,category_id INTEGER,target_entry_id INTEGER DEFAULT NULL,entry_data TEXT NOT NULL DEFAULT '{}',icon TEXT DEFAULT '🔒',reason TEXT DEFAULT '',status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),created_by INTEGER NOT NULL,reviewed_by INTEGER DEFAULT NULL,review_comment TEXT DEFAULT '',created_at DATETIME DEFAULT (datetime('now','localtime')),reviewed_at DATETIME DEFAULT NULL,FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,FOREIGN KEY (target_entry_id) REFERENCES entries(id) ON DELETE SET NULL,FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL)");
    $db->exec("CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status)"); $db->exec("CREATE INDEX IF NOT EXISTS idx_proposals_creator ON proposals(created_by)"); $db->exec("CREATE INDEX IF NOT EXISTS idx_proposals_category ON proposals(category_id)");
    $db->exec("CREATE TABLE IF NOT EXISTS review_notifications (id INTEGER PRIMARY KEY AUTOINCREMENT,proposal_id INTEGER NOT NULL,user_id INTEGER NOT NULL,type TEXT NOT NULL DEFAULT 'submitted',is_read INTEGER DEFAULT 0,created_at DATETIME DEFAULT (datetime('now','localtime')),FOREIGN KEY (proposal_id) REFERENCES proposals(id) ON DELETE CASCADE,FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)");
    $db->exec("CREATE INDEX IF NOT EXISTS idx_review_notif_user ON review_notifications(user_id, is_read)");
    $db->exec("CREATE TABLE IF NOT EXISTS login_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT,ip TEXT NOT NULL,attempts INTEGER DEFAULT 1,first_attempt DATETIME DEFAULT (datetime('now','localtime')),blocked_until DATETIME DEFAULT NULL)");
    $db->exec("CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts(ip)");
    $db->exec("DELETE FROM login_attempts WHERE blocked_until IS NOT NULL AND blocked_until < datetime('now','localtime')");
    $db->exec("DELETE FROM login_attempts WHERE blocked_until IS NULL AND first_attempt < datetime('now','localtime','-24 hours')");
    migrateColumns($db);
    migrateFromJson($db);
    migratePasswordsToEncrypted($db);
    migrateWebdavPasswordEncryption($db);
}

try {

// ---- 数据目录 ----
// 自动检测：优先使用本文件所在目录（与 api.php 同目录的 vault.db）
$dataDir = __DIR__;
define('DATA_DIR', $dataDir);
$dbPath = DATA_DIR . '/vault.db';
try {
    $db = new SQLite3($dbPath);
} catch (Exception $e) {
    vault_log('FATAL', '数据库创建失败: ' . $e->getMessage() . ' (路径: ' . $dbPath . ')');
    http_response_code(500); echo json_encode(['error' => '数据库创建失败: ' . $e->getMessage() . ' (路径: ' . $dbPath . ')']); exit;
}
$db->busyTimeout(5000);
$db->exec('PRAGMA journal_mode=WAL');
$db->exec('PRAGMA foreign_keys=ON');

initDB($db);

// ---- CORS 动态白名单 ----
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
$stmt = $db->prepare("SELECT value FROM settings WHERE key = 'cors_allowed_origins'");
$row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
$allowedOrigins = $row ? array_filter(array_map('trim', explode(',', $row['value']))) : [];
if (empty($allowedOrigins)) { header('Access-Control-Allow-Origin: ' . ($origin ?: '*')); }
else { $matchedOrigin = in_array($origin, $allowedOrigins) ? $origin : $allowedOrigins[0]; header('Access-Control-Allow-Origin: ' . $matchedOrigin); }
header('Access-Control-Allow-Credentials: true');

$action = $_GET['action'] ?? $_POST['action'] ?? '';
vault_log('INFO', '请求 action=' . ($action ?: '(空)') . ' method=' . $_SERVER['REQUEST_METHOD'] . ' ip=' . ($_SERVER['REMOTE_ADDR'] ?? '?'));

// ---- 无需鉴权的路由 ----
if ($action === 'ping')     { echo json_encode(['ok' => true, 'time' => date('c')]); exit; }
if ($action === 'setup')    { handleSetup($db); exit; }
if ($action === 'login')    { handleLogin($db); exit; }

if ($action === 'list-users') {
    $rows = $db->query("SELECT id, username, display_name FROM users WHERE is_active = 1 ORDER BY role DESC, id ASC");
    $users = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) { $users[] = ['id'=>(int)$r['id'],'username'=>$r['username'],'display_name'=>$r['display_name']]; }
    echo json_encode(['ok' => true, 'users' => $users]); exit;
}

$user = authenticate($db);
if (!$user) { http_response_code(401); echo json_encode(['error' => '未登录或会话已过期']); exit; }

switch ($action) {
    case 'me':              handleMe($user); break;
    case 'logout':          handleLogout($db, $user); break;
    case 'get-categories':  handleGetCategories($db, $user); break;
    case 'add-category':    requireMaster($user); handleAddCategory($db); break;
    case 'rename-category': requireMaster($user); handleRenameCategory($db); break;
    case 'delete-category': requireMaster($user); handleDeleteCategory($db); break;
    case 'reorder-categories': requireMaster($user); handleReorderCategories($db); break;
    case 'get-entries':     handleGetEntries($db, $user); break;
    case 'add-entry':       handleAddEntry($db, $user); break;
    case 'edit-entry':      handleEditEntry($db, $user); break;
    case 'delete-entry':    handleDeleteEntry($db, $user); break;
    case 'reorder-entries': handleReorderEntries($db, $user); break;
    case 'get-users':       requireMaster($user); handleGetUsers($db); break;
    case 'add-user':        requireMaster($user); handleAddUser($db); break;
    case 'toggle-user':     requireMaster($user); handleToggleUser($db); break;
    case 'update-user':     requireMaster($user); handleUpdateUser($db); break;
    case 'delete-user':     requireMaster($user); handleDeleteUser($db); break;
    case 'get-stats':       requireMaster($user); handleGetStats($db); break;
    case 'reset-user-pwd':  requireMaster($user); handleResetUserPwd($db); break;
    case 'change-my-pwd':   handleChangeMyPwd($db, $user); break;
    case 'get-permissions': requireMaster($user); handleGetPermissions($db); break;
    case 'set-permissions': requireMaster($user); handleSetPermissions($db); break;
    case 'get-entry-perms': requireMaster($user); handleGetEntryPerms($db); break;
    case 'set-entry-perms': requireMaster($user); handleSetEntryPerms($db); break;
    case 'get-user-detail': requireMaster($user); handleGetUserDetail($db); break;
    case 'export-data':     requireMaster($user); handleExportData($db); break;
    case 'import-data':     requireMaster($user); handleImportData($db); break;
    case 'webdav-config':       requireMaster($user); handleWebdavConfig($db); break;
    case 'webdav-config-save':  requireMaster($user); handleWebdavConfigSave($db); break;
    case 'webdav-test':         requireMaster($user); handleWebdavTest($db); break;
    case 'webdav-save':         requireMaster($user); handleWebdavSave($db); break;
    case 'webdav-load':         requireMaster($user); handleWebdavLoad($db); break;
    case 'webdav-load-version': requireMaster($user); handleWebdavLoadVersion($db); break;
    case 'webdav-versions':     requireMaster($user); handleWebdavVersions($db); break;
    case 'webdav-last-sync':    requireMaster($user); handleWebdavLastSync($db); break;
    case 'webdav-cloud-latest': requireMaster($user); handleWebdavCloudLatest($db); break;
    case 'debug-log':       requireMaster($user); handleDebugLog(); break;
    case 'get-my-proposals':    handleGetMyProposals($db, $user); break;
    case 'get-pending-reviews': requireMaster($user); handleGetPendingReviews($db); break;
    case 'get-proposal-detail': handleGetProposalDetail($db, $user); break;
    case 'create-proposal':     handleCreateProposal($db, $user); break;
    case 'update-proposal':     handleUpdateProposal($db, $user); break;
    case 'delete-proposal':     handleDeleteProposal($db, $user); break;
    case 'review-proposal':     requireMaster($user); handleReviewProposal($db, $user); break;
    case 'get-notifications':   handleGetNotifications($db, $user); break;
    case 'mark-notification-read': handleMarkNotificationRead($db, $user); break;
    case 'serverchan-config':       requireMaster($user); handleServerChanConfig($db); break;
    case 'serverchan-config-save':  requireMaster($user); handleServerChanConfigSave($db); break;
    case 'serverchan-test':         requireMaster($user); handleServerChanTest($db); break;
    case 'verify-password':         handleVerifyPassword($db, $user); break;
    default: http_response_code(400); echo json_encode(['error' => '未知操作: ' . $action]);
}
} catch (Throwable $e) {
    vault_log('FATAL', '未捕获异常 action=' . ($action ?? '?') . ': ' . $e->getMessage() . ' in ' . $e->getFile() . ':' . $e->getLine());
    http_response_code(500); echo json_encode(['error' => '服务器异常: ' . $e->getMessage()]);
}


// ==================== 设置 / 登录 / 登出 ====================
function handleSetup($db) {
    $input = jsonInput();
    $username = trim($input['username'] ?? '');
    $password = $input['password'] ?? '';
    if (!$username || !$password) { http_response_code(400); echo json_encode(['error' => '请输入用户名和密码']); exit; }
    validateUsername($username);
    validatePassword($password);
    // 检查是否已有主账号
    $hasMaster = $db->querySingle("SELECT COUNT(*) FROM users WHERE role='master'");
    if ($hasMaster) { http_response_code(403); echo json_encode(['error' => '主账号已存在']); exit; }
    $hash = password_hash($password, PASSWORD_DEFAULT);
    $stmt = $db->prepare("INSERT INTO users (username, password_hash, display_name, role) VALUES (:uname, :hash, :dname, 'master')");
    $stmt->bindValue(':uname', $username, SQLITE3_TEXT);
    $stmt->bindValue(':hash', $hash, SQLITE3_TEXT);
    $stmt->bindValue(':dname', $username, SQLITE3_TEXT);
    $stmt->execute();
    // 自动创建默认分类
    $masterId = $db->lastInsertRowID();
    $defaultCats = [['个人', '👤'], ['工作', '💼'], ['社交', '📱'], ['金融', '💰'], ['其他', '📝']];
    foreach ($defaultCats as $i => $c) {
        $stmt = $db->prepare("INSERT INTO categories (name, icon, sort_order) VALUES (:name, :icon, :order)");
        $stmt->bindValue(':name', $c[0], SQLITE3_TEXT);
        $stmt->bindValue(':icon', $c[1], SQLITE3_TEXT);
        $stmt->bindValue(':order', $i, SQLITE3_INTEGER);
        $stmt->execute();
    }
    // 主账号拥有所有权限
    $cats = $db->query("SELECT id FROM categories");
    while ($c = $cats->fetchArray(SQLITE3_ASSOC)) {
        $stmt = $db->prepare("INSERT OR IGNORE INTO category_permissions (user_id, category_id, can_read, can_write) VALUES (:uid, :cid, 1, 1)");
        $stmt->bindValue(':uid', $masterId, SQLITE3_INTEGER);
        $stmt->bindValue(':cid', $c['id'], SQLITE3_INTEGER);
        $stmt->execute();
    }
    echo json_encode(['ok' => true, 'msg' => '主账号创建成功']);
}

function handleLogin($db) {
    // ---- 登录频率限制（单 IP 5 分钟内最多 10 次，超限封锁 15 分钟）----
    $clientIp = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
    $stmt = $db->prepare("SELECT * FROM login_attempts WHERE ip = :ip");
    $stmt->bindValue(':ip', $clientIp, SQLITE3_TEXT);
    $attempt = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if ($attempt && !empty($attempt['blocked_until'])) {
        if (strtotime($attempt['blocked_until']) > time()) {
            $waitMin = ceil((strtotime($attempt['blocked_until']) - time()) / 60);
            http_response_code(429);
            echo json_encode(['error' => "登录尝试太频繁，请 {$waitMin} 分钟后重试"]);
            exit;
        }
        // 封锁已过期，重置
        $stmt = $db->prepare("DELETE FROM login_attempts WHERE id = :id");
        $stmt->bindValue(':id', $attempt['id'], SQLITE3_INTEGER);
        $stmt->execute();
        $attempt = null;
    }
    if ($attempt && $attempt['attempts'] >= 10 && (time() - strtotime($attempt['first_attempt'])) < 300) {
        // 封锁 15 分钟
        $stmt = $db->prepare("UPDATE login_attempts SET blocked_until = datetime('now','localtime','+15 minutes') WHERE id = :id");
        $stmt->bindValue(':id', $attempt['id'], SQLITE3_INTEGER);
        $stmt->execute();
        http_response_code(429);
        echo json_encode(['error' => '登录尝试太频繁，请 15 分钟后重试']);
        exit;
    }

    $input = jsonInput();
    $username = trim($input['username'] ?? '');
    $password = $input['password'] ?? '';
    // 仅接受明确的布尔真值，避免请求体中的字符串 "false" 被 !empty()
    // 误判为七天会话。
    $rememberValue = $input['remember'] ?? false;
    $remember = $rememberValue === true || $rememberValue === 1 ||
        $rememberValue === '1' || $rememberValue === 'true' || $rememberValue === 'on';
    if (!$username || !$password) { http_response_code(400); echo json_encode(['error' => '请输入用户名和密码']); exit; }
    $stmt = $db->prepare("SELECT * FROM users WHERE username = :uname AND is_active = 1");
    $stmt->bindValue(':uname', $username, SQLITE3_TEXT);
    $user = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if (!$user || !password_verify($password, $user['password_hash'])) {
        // 记录失败尝试
        recordLoginAttempt($db, $clientIp);
        http_response_code(401); echo json_encode(['error' => '用户名或密码错误']); exit;
    }
    // 登录成功，清除该 IP 的尝试记录
    $stmt = $db->prepare("DELETE FROM login_attempts WHERE ip = :ip");
    $stmt->bindValue(':ip', $clientIp, SQLITE3_TEXT);
    $stmt->execute();
    // 清理过期会话（每次登录时顺带清理）
    $db->exec("DELETE FROM sessions WHERE expires_at < datetime('now','localtime')");
    $token = bin2hex(random_bytes(32));
    $ttl = $remember ? '+7 days' : '+2 hours';
    $expiresAt = $db->querySingle("SELECT datetime('now','localtime','{$ttl}')");
    $stmt = $db->prepare("INSERT INTO sessions (token, user_id, expires_at) VALUES (:token, :uid, :expires)");
    $stmt->bindValue(':token', $token, SQLITE3_TEXT);
    $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
    $stmt->bindValue(':expires', $expiresAt, SQLITE3_TEXT);
    $stmt->execute();
    // 更新登录统计
    $stmt = $db->prepare("UPDATE users SET last_login = datetime('now','localtime'), login_count = login_count + 1 WHERE id = :id");
    $stmt->bindValue(':id', $user['id'], SQLITE3_INTEGER);
    $stmt->execute();
    echo json_encode(['ok' => true, 'token' => $token, 'expires_at' => $expiresAt, 'remember' => $remember, 'user' => [
        'id' => $user['id'],
        'username' => $user['username'],
        'display_name' => $user['display_name'],
        'role' => $user['role']
    ]]);
}

function handleMe($user) {
    echo json_encode(['ok' => true, 'user' => [
        'id' => $user['id'],
        'username' => $user['username'],
        'display_name' => $user['display_name'],
        'role' => $user['role']
    ]]);
}

function handleLogout($db, $user) {
    $auth = '';
    if (function_exists('getallheaders')) {
        $h = getallheaders();
        $auth = $h['Authorization'] ?? $h['authorization'] ?? '';
    }
    if (substr($auth, 0, 7) === 'Bearer ') {
        $token = substr($auth, 7);
        $stmt = $db->prepare("DELETE FROM sessions WHERE token = :token");
        $stmt->bindValue(':token', $token, SQLITE3_TEXT);
        $stmt->execute();
    }
    echo json_encode(['ok' => true, 'msg' => '已登出']);
}

// ==================== 分类管理 ====================
function handleGetCategories($db, $user) {
    if ($user['role'] === 'master') {
        $rows = $db->query("SELECT * FROM categories ORDER BY sort_order ASC, id ASC");
    } else {
        $stmt = $db->prepare("SELECT c.*, cp.can_read, cp.can_write FROM categories c
            JOIN category_permissions cp ON c.id = cp.category_id
            WHERE cp.user_id = :uid AND cp.can_read = 1
            ORDER BY c.sort_order ASC, c.id ASC");
        $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
        $rows = $stmt->execute();
    }
    $cats = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $cats[] = [
            'id' => (int)$r['id'],
            'name' => $r['name'],
            'icon' => $r['icon'],
            'sort_order' => (int)$r['sort_order'],
            'can_read' => isset($r['can_read']) ? (bool)$r['can_read'] : true,
            'can_write' => isset($r['can_write']) ? (bool)$r['can_write'] : true,
        ];
    }
    echo json_encode(['ok' => true, 'categories' => $cats]);
}

function handleAddCategory($db) {
    $input = jsonInput();
    $name = trim($input['name'] ?? '');
    if (!$name) { http_response_code(400); echo json_encode(['error' => '请输入分类名称']); exit; }
    $icon = $input['icon'] ?? '🔑';
    $stmt = $db->prepare("INSERT INTO categories (name, icon) VALUES (:name, :icon)");
    $stmt->bindValue(':name', $name, SQLITE3_TEXT);
    $stmt->bindValue(':icon', $icon, SQLITE3_TEXT);
    $stmt->execute();
    $id = $db->lastInsertRowID();
    // 新分类对所有用户默认无权限（主账号之后手动分配）
    echo json_encode(['ok' => true, 'category' => ['id' => $id, 'name' => $name, 'icon' => $icon]]);
}

function handleRenameCategory($db) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    $name = trim($input['name'] ?? '');
    $icon = $input['icon'] ?? null;
    if (!$id || !$name) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    if ($icon !== null) {
        $stmt = $db->prepare("UPDATE categories SET name=:name, icon=:icon WHERE id=:id");
        $stmt->bindValue(':icon', $icon, SQLITE3_TEXT);
    } else {
        $stmt = $db->prepare("UPDATE categories SET name=:name WHERE id=:id");
    }
    $stmt->bindValue(':name', $name, SQLITE3_TEXT);
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    echo json_encode(['ok' => true]);
}

function handleDeleteCategory($db) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    $stmt = $db->prepare("DELETE FROM entries WHERE category_id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    $stmt = $db->prepare("DELETE FROM category_permissions WHERE category_id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    $stmt = $db->prepare("DELETE FROM categories WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    echo json_encode(['ok' => true]);
}

function handleReorderCategories($db) {
    $input = jsonInput();
    $ids = $input['ids'] ?? [];
    if (!is_array($ids)) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    $db->exec('BEGIN');
    foreach ($ids as $i => $id) {
        $stmt = $db->prepare("UPDATE categories SET sort_order = :order WHERE id = :id");
        $stmt->bindValue(':order', $i, SQLITE3_INTEGER);
        $stmt->bindValue(':id', (int)$id, SQLITE3_INTEGER);
        $stmt->execute();
    }
    $db->exec('COMMIT');
    echo json_encode(['ok' => true]);
}

// ==================== 条目管理 ====================
function handleGetEntries($db, $user) {
    $catId = (int)($_GET['category_id'] ?? 0);
    if (!$catId) { http_response_code(400); echo json_encode(['error' => '缺少 category_id']); exit; }
    // 检查权限
    if (!checkCategoryAccess($db, $user, $catId, 'read')) return;

    // 获取被条目级权限隐藏的 entry ID 列表（仅子账号受限）
    $hiddenIds = [];
    if ($user['role'] !== 'master') {
        $stmt = $db->prepare("SELECT entry_id FROM entry_permissions WHERE user_id = :uid AND can_view = 0
            AND entry_id IN (SELECT id FROM entries WHERE category_id = :cid)");
        $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
        $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
        $hRows = $stmt->execute();
        while ($hr = $hRows->fetchArray(SQLITE3_ASSOC)) {
            $hiddenIds[(int)$hr['entry_id']] = true;
        }
    }

    $stmt = $db->prepare("SELECT * FROM entries WHERE category_id = :cid ORDER BY sort_order ASC, updated_at DESC, id ASC");
    $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
    $rows = $stmt->execute();
    $entries = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $eid = (int)$r['id'];
        // 子账号：跳过被隐藏的条目
        if (isset($hiddenIds[$eid])) continue;
        $entries[] = [
            'id' => $eid,
            'category_id' => (int)$r['category_id'],
            'title' => $r['title'],
            'icon' => $r['icon'] ?? '',
            'username' => $r['username_field'],
            'password' => decryptPassword($db, $r['password_field']),
            'url' => $r['url'],
            'notes' => $r['notes'],
            'sort_order' => (int)($r['sort_order'] ?? 0),
            'updated_at' => $r['updated_at'],
        ];
    }
    $writeAccess = checkCategoryAccess($db, $user, $catId, 'write', false);
    echo json_encode(['ok' => true, 'entries' => $entries, 'can_write' => $writeAccess]);
}

function handleAddEntry($db, $user) {
    $input = jsonInput();
    $catId = (int)($input['category_id'] ?? 0);
    if (!checkCategoryAccess($db, $user, $catId, 'write')) return;
    $nextOrder = (int)$db->querySingle("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM entries WHERE category_id = " . (int)$catId);
    $stmt = $db->prepare("INSERT INTO entries (category_id, title, icon, username_field, password_field, url, notes, created_by, sort_order)
        VALUES (:cid, :title, :icon, :uname, :pwd, :url, :notes, :uid, :order)");
    $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
    $stmt->bindValue(':title', $input['title'] ?? '', SQLITE3_TEXT);
    $stmt->bindValue(':icon', $input['icon'] ?? '', SQLITE3_TEXT);
    $stmt->bindValue(':uname', $input['username'] ?? '', SQLITE3_TEXT);
    $encryptedPwd = encryptPassword($db, $input['password'] ?? '');
    $stmt->bindValue(':pwd', $encryptedPwd, SQLITE3_TEXT);
    $stmt->bindValue(':url', $input['url'] ?? '', SQLITE3_TEXT);
    $stmt->bindValue(':notes', $input['notes'] ?? '', SQLITE3_TEXT);
    $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
    $stmt->bindValue(':order', $nextOrder, SQLITE3_INTEGER);
    $stmt->execute();
    echo json_encode(['ok' => true, 'id' => $db->lastInsertRowID()]);
}

function handleEditEntry($db, $user) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    // 检查条目所在分类的写权限
    $stmt = $db->prepare("SELECT category_id FROM entries WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $catId = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    $catId = $catId ? $catId['category_id'] : null;
    if (!$catId) { http_response_code(404); echo json_encode(['error' => '条目不存在']); exit; }
    if (!checkCategoryAccess($db, $user, $catId, 'write')) return;
    $stmt = $db->prepare("UPDATE entries SET title=:title, icon=:icon, username_field=:uname, password_field=:pwd, url=:url, notes=:notes,
        updated_at=datetime('now','localtime') WHERE id=:id");
    $stmt->bindValue(':title', $input['title'] ?? '', SQLITE3_TEXT);
    $stmt->bindValue(':icon', $input['icon'] ?? '', SQLITE3_TEXT);
    $stmt->bindValue(':uname', $input['username'] ?? '', SQLITE3_TEXT);
    $encryptedPwd = encryptPassword($db, $input['password'] ?? '');
    $stmt->bindValue(':pwd', $encryptedPwd, SQLITE3_TEXT);
    $stmt->bindValue(':url', $input['url'] ?? '', SQLITE3_TEXT);
    $stmt->bindValue(':notes', $input['notes'] ?? '', SQLITE3_TEXT);
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    echo json_encode(['ok' => true]);
}

function handleReorderEntries($db, $user) {
    $input = jsonInput();
    $catId = (int)($input['category_id'] ?? 0);
    $ids = $input['ids'] ?? [];
    if (!$catId || !is_array($ids)) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    if (!checkCategoryAccess($db, $user, $catId, 'write')) return;

    $valid = [];
    $stmt = $db->prepare("SELECT id FROM entries WHERE category_id = :cid");
    $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
    $rows = $stmt->execute();
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) $valid[(int)$r['id']] = true;

    $db->exec('BEGIN');
    try {
        $stmt = $db->prepare("UPDATE entries SET sort_order = :order, updated_at = updated_at WHERE id = :id AND category_id = :cid");
        $order = 0;
        foreach ($ids as $id) {
            $id = (int)$id;
            if (!isset($valid[$id])) continue;
            $stmt->bindValue(':order', $order++, SQLITE3_INTEGER);
            $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
            $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
            $stmt->execute();
        }
        $db->exec('COMMIT');
        echo json_encode(['ok' => true]);
    } catch (Exception $e) {
        $db->exec('ROLLBACK');
        http_response_code(500);
        echo json_encode(['error' => '排序保存失败: ' . $e->getMessage()]);
    }
}

function handleDeleteEntry($db, $user) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    $stmt = $db->prepare("SELECT category_id FROM entries WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $catId = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    $catId = $catId ? $catId['category_id'] : null;
    if (!$catId) { http_response_code(404); echo json_encode(['error' => '条目不存在']); exit; }
    if (!checkCategoryAccess($db, $user, $catId, 'write')) return;
    $stmt = $db->prepare("DELETE FROM entries WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    echo json_encode(['ok' => true]);
}

// ==================== 用户管理 ====================
function handleGetUsers($db) {
    $rows = $db->query("SELECT u.id, u.username, u.display_name, u.role, u.is_active, u.last_login, u.login_count, u.created_at,
        (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id AND s.expires_at > datetime('now','localtime')) AS active_sessions,
        (SELECT COUNT(*) FROM category_permissions cp WHERE cp.user_id = u.id AND cp.can_read = 1) AS readable_categories,
        (SELECT COUNT(*) FROM category_permissions cp WHERE cp.user_id = u.id AND cp.can_write = 1) AS writable_categories
        FROM users u ORDER BY u.role DESC, u.is_active DESC, u.id ASC");
    $users = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $users[] = [
            'id' => (int)$r['id'],
            'username' => $r['username'],
            'display_name' => $r['display_name'],
            'role' => $r['role'],
            'is_active' => (bool)$r['is_active'],
            'last_login' => $r['last_login'],
            'login_count' => (int)($r['login_count'] ?? 0),
            'created_at' => $r['created_at'],
            'active_sessions' => (int)($r['active_sessions'] ?? 0),
            'readable_categories' => (int)($r['readable_categories'] ?? 0),
            'writable_categories' => (int)($r['writable_categories'] ?? 0),
        ];
    }
    echo json_encode(['ok' => true, 'users' => $users]);
}

function handleUpdateUser($db) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    $stmt = $db->prepare("SELECT role FROM users WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $role = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    $role = $role ? $role['role'] : null;
    if ($role === 'master' && ($input['role'] ?? '') !== 'master') {
        http_response_code(403); echo json_encode(['error' => '不能修改主账号']); exit;
    }
    $fields = [];
    $params = [];
    if (isset($input['display_name'])) { $fields[] = 'display_name = :dname'; $params[':dname'] = trim($input['display_name']); }
    if (!empty($fields)) {
        $sql = "UPDATE users SET " . implode(', ', $fields) . " WHERE id = :id";
        $stmt = $db->prepare($sql);
        $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
        foreach ($params as $k => $v) $stmt->bindValue($k, $v, SQLITE3_TEXT);
        $stmt->execute();
    }
    echo json_encode(['ok' => true]);
}

function handleDeleteUser($db) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    $stmt = $db->prepare("SELECT role FROM users WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $role = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    $role = $role ? $role['role'] : null;
    if ($role === 'master') { http_response_code(403); echo json_encode(['error' => '不能删除主账号']); exit; }
    $stmt = $db->prepare("DELETE FROM sessions WHERE user_id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    $stmt = $db->prepare("DELETE FROM category_permissions WHERE user_id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    $stmt = $db->prepare("DELETE FROM users WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    echo json_encode(['ok' => true]);
}

function handleGetStats($db) {
    $totalUsers = $db->querySingle("SELECT COUNT(*) FROM users");
    $activeUsers = $db->querySingle("SELECT COUNT(*) FROM users WHERE is_active = 1");
    $totalCats = $db->querySingle("SELECT COUNT(*) FROM categories");
    $totalEntries = $db->querySingle("SELECT COUNT(*) FROM entries");
    $totalSessions = $db->querySingle("SELECT COUNT(*) FROM sessions WHERE expires_at > datetime('now','localtime')");
    $dbSize = 0;
    $dbPath = DATA_DIR . '/vault.db';
    if (file_exists($dbPath)) $dbSize = @filesize($dbPath);
    echo json_encode(['ok' => true, 'stats' => [
        'total_users' => (int)$totalUsers,
        'active_users' => (int)$activeUsers,
        'total_categories' => (int)$totalCats,
        'total_entries' => (int)$totalEntries,
        'active_sessions' => (int)$totalSessions,
        'db_size' => $dbSize,
    ]]);
}

function handleAddUser($db) {
    $input = jsonInput();
    $username = trim($input['username'] ?? '');
    $password = $input['password'] ?? '';
    if (!$username || !$password) { http_response_code(400); echo json_encode(['error' => '请输入用户名和密码']); exit; }
    validateUsername($username);
    validatePassword($password);
    // 检查重名
    $stmt = $db->prepare("SELECT COUNT(*) FROM users WHERE username = :uname");
    $stmt->bindValue(':uname', $username, SQLITE3_TEXT);
    $exists = $stmt->execute()->fetchArray(SQLITE3_NUM)[0];
    if ($exists) { http_response_code(409); echo json_encode(['error' => '用户名已存在']); exit; }
    $hash = password_hash($password, PASSWORD_DEFAULT);
    $stmt = $db->prepare("INSERT INTO users (username, password_hash, display_name, role) VALUES (:uname, :hash, :dname, 'user')");
    $stmt->bindValue(':uname', $username, SQLITE3_TEXT);
    $stmt->bindValue(':hash', $hash, SQLITE3_TEXT);
    $stmt->bindValue(':dname', $username, SQLITE3_TEXT);
    $stmt->execute();
    echo json_encode(['ok' => true, 'id' => $db->lastInsertRowID()]);
}

function handleToggleUser($db) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    $stmt = $db->prepare("SELECT role FROM users WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $role = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    $role = $role ? $role['role'] : null;
    if ($role === 'master') { http_response_code(403); echo json_encode(['error' => '不能禁用主账号']); exit; }
    $stmt = $db->prepare("UPDATE users SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    $isActive = (int)$db->querySingle("SELECT is_active FROM users WHERE id = " . (int)$id);
    if (!$isActive) {
        $stmt = $db->prepare("DELETE FROM sessions WHERE user_id = :id");
        $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
        $stmt->execute();
    }
    echo json_encode(['ok' => true]);
}

function handleResetUserPwd($db) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    $password = $input['password'] ?? '';
    if (!$id || !$password) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    validatePassword($password);
    $stmt = $db->prepare("SELECT role FROM users WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $role = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    $role = $role ? $role['role'] : null;
    if ($role === 'master') { http_response_code(403); echo json_encode(['error' => '不能修改主账号密码']); exit; }
    $hash = password_hash($password, PASSWORD_DEFAULT);
    $stmt = $db->prepare("UPDATE users SET password_hash = :hash WHERE id = :id");
    $stmt->bindValue(':hash', $hash, SQLITE3_TEXT);
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    $stmt = $db->prepare("DELETE FROM sessions WHERE user_id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    echo json_encode(['ok' => true]);
}

// ---- 子账号改密 ----
function handleChangeMyPwd($db, $user) {
    $input = jsonInput();
    $oldPwd = $input['old_password'] ?? '';
    $newPwd = $input['new_password'] ?? '';
    if (!$oldPwd || !$newPwd) { http_response_code(400); echo json_encode(['error' => '请输入旧密码和新密码']); exit; }
    validatePassword($newPwd);
    // 验证旧密码
    $stmt = $db->prepare("SELECT password_hash FROM users WHERE id = :id");
    $stmt->bindValue(':id', $user['id'], SQLITE3_INTEGER);
    $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if (!$row || !password_verify($oldPwd, $row['password_hash'])) {
        http_response_code(403); echo json_encode(['error' => '旧密码不正确']); exit;
    }
    $hash = password_hash($newPwd, PASSWORD_DEFAULT);
    $stmt = $db->prepare("UPDATE users SET password_hash = :hash WHERE id = :id");
    $stmt->bindValue(':hash', $hash, SQLITE3_TEXT);
    $stmt->bindValue(':id', $user['id'], SQLITE3_INTEGER);
    $stmt->execute();
    // 密码修改后清除该用户的所有会话，强制重新登录
    $stmt = $db->prepare("DELETE FROM sessions WHERE user_id = :uid");
    $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
    $stmt->execute();
    vault_log('AUTH', '用户 ' . $user['username'] . ' 修改密码，已清除所有会话');
    echo json_encode(['ok' => true, 'msg' => '密码已修改，请重新登录']);
}

// ==================== 权限管理 ====================
function handleGetPermissions($db) {
    $rows = $db->query("SELECT * FROM category_permissions ORDER BY user_id, category_id");
    $perms = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $key = $r['user_id'] . '-' . $r['category_id'];
        $perms[] = [
            'user_id' => (int)$r['user_id'],
            'category_id' => (int)$r['category_id'],
            'can_read' => (bool)$r['can_read'],
            'can_write' => (bool)$r['can_write'],
        ];
    }
    echo json_encode(['ok' => true, 'permissions' => $perms]);
}

function handleSetPermissions($db) {
    $input = jsonInput();
    $userId = (int)($input['user_id'] ?? 0);
    $permissions = $input['permissions'] ?? []; // [{category_id, can_read, can_write}]
    if (!$userId || !is_array($permissions)) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    $db->exec('BEGIN');
    $stmt = $db->prepare("DELETE FROM category_permissions WHERE user_id = :uid");
    $stmt->bindValue(':uid', $userId, SQLITE3_INTEGER);
    $stmt->execute();
    foreach ($permissions as $p) {
        $catId = (int)($p['category_id'] ?? 0);
        if (!$catId) continue;
        $read = ($p['can_read'] ?? true) ? 1 : 0;
        $write = ($p['can_write'] ?? false) ? 1 : 0;
        $stmt = $db->prepare("INSERT INTO category_permissions (user_id, category_id, can_read, can_write) VALUES (:uid, :cid, :r, :w)");
        $stmt->bindValue(':uid', $userId, SQLITE3_INTEGER);
        $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
        $stmt->bindValue(':r', $read, SQLITE3_INTEGER);
        $stmt->bindValue(':w', $write, SQLITE3_INTEGER);
        $stmt->execute();
    }
    $db->exec('COMMIT');
    echo json_encode(['ok' => true]);
}

// ==================== 条目级可见性管理 ====================
function handleGetEntryPerms($db) {
    $userId = (int)($_GET['user_id'] ?? 0);
    $catId = (int)($_GET['category_id'] ?? 0);
    if (!$userId || !$catId) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    // 获取该分类下所有条目
        $stmt = $db->prepare("SELECT id, title FROM entries WHERE category_id = :cid ORDER BY sort_order ASC, updated_at DESC, id ASC");
    $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
    $rows = $stmt->execute();
    $entries = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $entries[] = ['id' => (int)$r['id'], 'title' => $r['title']];
    }
    // 获取该用户在该分类下的条目权限
    $stmt = $db->prepare("SELECT ep.entry_id, ep.can_view FROM entry_permissions ep
        JOIN entries e ON ep.entry_id = e.id WHERE ep.user_id = :uid AND e.category_id = :cid");
    $stmt->bindValue(':uid', $userId, SQLITE3_INTEGER);
    $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
    $rows = $stmt->execute();
    $perms = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $perms[(int)$r['entry_id']] = (bool)$r['can_view'];
    }
    echo json_encode(['ok' => true, 'entries' => $entries, 'permissions' => $perms]);
}

function handleSetEntryPerms($db) {
    $input = jsonInput();
    $userId = (int)($input['user_id'] ?? 0);
    $catId = (int)($input['category_id'] ?? 0);
    $visibleIds = $input['visible_entry_ids'] ?? [];
    if (!$userId || !$catId || !is_array($visibleIds)) { http_response_code(400); echo json_encode(['error' => '参数不完整']); exit; }
    $db->exec('BEGIN');
    try {
        // 清除该用户在该分类下所有条目的旧权限
        $stmt = $db->prepare("DELETE FROM entry_permissions WHERE user_id = :uid AND entry_id IN (SELECT id FROM entries WHERE category_id = :cid)");
        $stmt->bindValue(':uid', $userId, SQLITE3_INTEGER);
        $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
        $stmt->execute();
        // 如果 visibleIds 为空，表示全部可见（默认行为），不需要插入记录
        // 如果有指定 ID，只有这些 ID 可见
        if (!empty($visibleIds)) {
            // 获取该分类下所有条目 ID
            $stmt = $db->prepare("SELECT id FROM entries WHERE category_id = :cid");
            $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
            $rows = $stmt->execute();
            $allIds = [];
            while ($r = $rows->fetchArray(SQLITE3_ASSOC)) $allIds[] = (int)$r['id'];
            $visibleSet = array_flip(array_map(function($v) { return (int)$v; }, $visibleIds));
            $stmt = $db->prepare("INSERT INTO entry_permissions (user_id, entry_id, can_view) VALUES (:uid, :eid, :v)");
            foreach ($allIds as $eid) {
                $canView = isset($visibleSet[$eid]) ? 1 : 0;
                $stmt->bindValue(':uid', $userId, SQLITE3_INTEGER);
                $stmt->bindValue(':eid', $eid, SQLITE3_INTEGER);
                $stmt->bindValue(':v', $canView, SQLITE3_INTEGER);
                $stmt->execute();
            }
        }
        $db->exec('COMMIT');
        echo json_encode(['ok' => true]);
    } catch (Exception $e) {
        $db->exec('ROLLBACK');
        http_response_code(500);
        echo json_encode(['error' => '保存失败: ' . $e->getMessage()]);
    }
}

// ==================== 用户详情（权限摘要）====================
function handleGetUserDetail($db) {
    $userId = (int)($_GET['user_id'] ?? 0);
    if (!$userId) { http_response_code(400); echo json_encode(['error' => '缺少 user_id']); exit; }
    // 用户基本信息
    $stmt = $db->prepare("SELECT id, username, display_name, role, is_active, last_login, login_count, created_at FROM users WHERE id = :id");
    $stmt->bindValue(':id', $userId, SQLITE3_INTEGER);
    $user = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if (!$user) { http_response_code(404); echo json_encode(['error' => '用户不存在']); exit; }
    // 分类权限
    $stmt = $db->prepare("SELECT cp.*, c.name AS cat_name, c.icon AS cat_icon FROM category_permissions cp
        JOIN categories c ON cp.category_id = c.id WHERE cp.user_id = :uid ORDER BY c.sort_order ASC, c.id ASC");
    $stmt->bindValue(':uid', $userId, SQLITE3_INTEGER);
    $rows = $stmt->execute();
    $catPerms = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $catPerms[] = [
            'category_id' => (int)$r['category_id'],
            'cat_name' => $r['cat_name'],
            'cat_icon' => $r['cat_icon'],
            'can_read' => (bool)$r['can_read'],
            'can_write' => (bool)$r['can_write'],
        ];
    }
    // 条目可见性摘要（每个分类的可见/隐藏条目数）
    $stmt = $db->prepare("SELECT e.category_id, c.name AS cat_name,
        COUNT(e.id) AS total,
        SUM(CASE WHEN ep.can_view = 0 THEN 1 ELSE 0 END) AS hidden
        FROM entries e
        JOIN categories c ON e.category_id = c.id
        LEFT JOIN entry_permissions ep ON ep.entry_id = e.id AND ep.user_id = :uid
        WHERE e.category_id IN (SELECT category_id FROM category_permissions WHERE user_id = :uid2 AND can_read = 1)
        GROUP BY e.category_id");
    $stmt->bindValue(':uid', $userId, SQLITE3_INTEGER);
    $stmt->bindValue(':uid2', $userId, SQLITE3_INTEGER);
    $rows = $stmt->execute();
    $entrySummary = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $entrySummary[] = [
            'category_id' => (int)$r['category_id'],
            'cat_name' => $r['cat_name'],
            'total' => (int)$r['total'],
            'hidden' => (int)($r['hidden'] ?? 0),
            'visible' => (int)$r['total'] - (int)($r['hidden'] ?? 0),
        ];
    }
    echo json_encode([
        'ok' => true,
        'user' => [
            'id' => (int)$user['id'],
            'username' => $user['username'],
            'display_name' => $user['display_name'],
            'role' => $user['role'],
            'is_active' => (bool)$user['is_active'],
            'last_login' => $user['last_login'],
            'login_count' => (int)($user['login_count'] ?? 0),
            'created_at' => $user['created_at'],
        ],
        'category_permissions' => $catPerms,
        'entry_summary' => $entrySummary,
    ]);
}

// ==================== 数据导出 / 导入 ====================
function handleExportData($db) {
    $json = exportDataJson($db);
    // 包装 ok 字段供前端使用
    $data = json_decode($json, true);
    $data['ok'] = true;
    echo json_encode($data);
}

function handleImportData($db) {
    $input = jsonInput();
    // 支持新版格式 { version: 2, data: { categories: [...] } }
    // 和旧版格式 { categories: [...] }
    $data = $input['data'] ?? $input;
    if (!isset($data['categories']) || !is_array($data['categories'])) {
        http_response_code(400);
        echo json_encode(['error' => '数据格式不正确，缺少 categories 字段']);
        exit;
    }
    $db->exec('BEGIN');
    try {
        // 清空现有数据（按外键依赖顺序）
        $db->exec('DELETE FROM review_notifications');
        $db->exec('DELETE FROM proposals');
        $db->exec('DELETE FROM entry_permissions');
        $db->exec('DELETE FROM entries');
        $db->exec('DELETE FROM category_permissions');
        $db->exec('DELETE FROM categories');
        // 导入
        foreach ($data['categories'] as $cat) {
            // 兼容旧版 label 字段（旧版用 label，新版用 name）
            $catName = $cat['name'] ?? $cat['label'] ?? '未命名';
            $stmt = $db->prepare("INSERT INTO categories (name, icon, sort_order) VALUES (:name, :icon, :order)");
            $stmt->bindValue(':name', $catName, SQLITE3_TEXT);
            $stmt->bindValue(':icon', $cat['icon'] ?? '🔑', SQLITE3_TEXT);
            $stmt->bindValue(':order', (int)($cat['sort_order'] ?? 0), SQLITE3_INTEGER);
            $stmt->execute();
            $catId = $db->lastInsertRowID();
            foreach ($cat['entries'] ?? [] as $entryIndex => $entry) {
                // 兼容旧版：扁平字段 vs fields 数组
                $title = $entry['label'] ?? $entry['title'] ?? '';
                $username = $entry['username'] ?? '';
                $password = $entry['password'] ?? '';
                $url = $entry['url'] ?? '';
                $notes = $entry['notes'] ?? '';
                // 旧版格式有 fields 数组
                $fields = $entry['fields'] ?? null;
                if (is_array($fields) && count($fields) > 0) {
                    $saveFields = [];
                    foreach ($fields as $f) {
                        $k = $f['key'] ?? '';
                        $v = $f['value'] ?? '';
                        $t = $f['type'] ?? 'text';
                        $saveFields[] = ['key' => $k, 'value' => $v, 'type' => $t];
                        // 自动提取用户名（第一个 text 或含邮箱/账号的字段）
                        if (!$username && ($t === 'text' || preg_match('/邮箱|账号|ID|user/i', $k))) {
                            $username = $v;
                        } elseif (!$password && ($t === 'password' || !empty($f['sensitive']))) {
                            $password = $v;
                        } elseif (!$url && ($t === 'url' || preg_match('/^https?:\/\//', $v))) {
                            $url = $v;
                        }
                    }
                    // 把字段数组存入 notes（前端可直接解析）
                    $notes = json_encode($saveFields, JSON_UNESCAPED_UNICODE);
                }
                // 导入时加密密码存储
                $encryptedPwd = encryptPassword($db, $password);
                $stmt = $db->prepare("INSERT INTO entries (category_id, title, username_field, password_field, url, notes, sort_order)
                    VALUES (:cid, :title, :uname, :pwd, :url, :notes, :order)");
                $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
                $stmt->bindValue(':title', $title, SQLITE3_TEXT);
                $stmt->bindValue(':uname', $username, SQLITE3_TEXT);
                $stmt->bindValue(':pwd', $encryptedPwd, SQLITE3_TEXT);
                $stmt->bindValue(':url', $url, SQLITE3_TEXT);
                $stmt->bindValue(':notes', $notes, SQLITE3_TEXT);
                $stmt->bindValue(':order', (int)($entry['sort_order'] ?? $entryIndex), SQLITE3_INTEGER);
                $stmt->execute();
            }
        }
        // 为主账号重新赋予所有分类权限
        $masterId = $db->querySingle("SELECT id FROM users WHERE role = 'master' LIMIT 1");
        if ($masterId) {
            $cats = $db->query("SELECT id FROM categories");
            while ($c = $cats->fetchArray(SQLITE3_ASSOC)) {
                $stmt = $db->prepare("INSERT OR IGNORE INTO category_permissions (user_id, category_id, can_read, can_write) VALUES (:uid, :cid, 1, 1)");
                $stmt->bindValue(':uid', $masterId, SQLITE3_INTEGER);
                $stmt->bindValue(':cid', $c['id'], SQLITE3_INTEGER);
                $stmt->execute();
            }
        }
        $db->exec('COMMIT');
        // 导入成功后更新本地同步时间戳，避免重复提示云端同步
        $syncTime = ($input['exportedAt'] ?? $data['exportedAt'] ?? null) ?: date('c');
        $stmt = $db->prepare("INSERT OR REPLACE INTO settings (key, value) VALUES ('webdav_last_sync', :v)");
        $stmt->bindValue(':v', $syncTime, SQLITE3_TEXT);
        $stmt->execute();
        echo json_encode(['ok' => true, 'msg' => '导入成功']);
    } catch (Exception $e) {
        $db->exec('ROLLBACK');
        http_response_code(500);
        echo json_encode(['error' => '导入失败: ' . $e->getMessage()]);
    }
}

// ==================== WebDAV 云同步 ====================

// 从 settings 表读取 WebDAV 配置
function getWebdavConfig($db) {
    $keys = ['webdav_url', 'webdav_username', 'webdav_password'];
    $config = ['url' => '', 'username' => '', 'password' => ''];
    foreach ($keys as $k) {
        $stmt = $db->prepare("SELECT value FROM settings WHERE key = :k");
        $stmt->bindValue(':k', $k, SQLITE3_TEXT);
        $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
        $config[str_replace('webdav_', '', $k)] = $row ? trim($row['value']) : '';
    }
    $config['password'] = decryptSettingSecret($db, $config['password']);
    // 确保 URL 以 / 结尾（目录路径）
    if ($config['url'] && substr($config['url'], -1) !== '/') {
        $config['url'] .= '/';
    }
    return $config;
}

// 获取当前配置（不返回密码明文）
function handleWebdavConfig($db) {
    $config = getWebdavConfig($db);
    echo json_encode([
        'ok' => true,
        'url' => $config['url'],
        'username' => $config['username'],
        'has_password' => !empty($config['password']),
    ]);
}

// 保存 WebDAV 配置
function handleWebdavConfigSave($db) {
    $input = jsonInput();
    $fields = [
        'webdav_url'      => trim($input['url'] ?? ''),
        'webdav_username'  => trim($input['username'] ?? ''),
    ];
    // URL 自动补全结尾 /
    if ($fields['webdav_url'] && substr($fields['webdav_url'], -1) !== '/') {
        $fields['webdav_url'] .= '/';
    }
    foreach ($fields as $key => $val) {
        $stmt = $db->prepare("INSERT OR REPLACE INTO settings (key, value) VALUES (:k, :v)");
        $stmt->bindValue(':k', $key, SQLITE3_TEXT);
        $stmt->bindValue(':v', $val, SQLITE3_TEXT);
        $stmt->execute();
    }
    if (isset($input['password']) && $input['password'] !== '') {
        $stmt = $db->prepare("INSERT OR REPLACE INTO settings (key, value) VALUES (:k, :v)");
        $stmt->bindValue(':k', 'webdav_password', SQLITE3_TEXT);
        $stmt->bindValue(':v', encryptSettingSecret($db, $input['password']), SQLITE3_TEXT);
        $stmt->execute();
    }
    vault_log('WEBDAV', '配置已保存: url=' . $fields['webdav_url']);
    echo json_encode(['ok' => true]);
}

// 创建目录（忽略 405=已存在）
function webdavMkcol($url, $user, $pass) {
    $result = webdavRequest($url, 'MKCOL', null, $user, $pass);
    return ($result['ok'] || $result['code'] === 405);
}

// 测试连接：创建目录 + 写入测试文件
function handleWebdavTest($db) {
    $config = getWebdavConfig($db);
    if (!$config['url']) {
        echo json_encode(['ok' => false, 'error' => '请先填写 WebDAV 地址']);
        return;
    }
    if (!webdavMkcol($config['url'], $config['username'], $config['password'])) {
        echo json_encode(['ok' => false, 'error' => '无法创建目录，请检查地址和权限']);
        return;
    }
    $testFile = $config['url'] . '_vault_test_.json';
    $result = webdavRequest($testFile, 'PUT', '{"test":true}', $config['username'], $config['password']);
    if ($result['ok']) {
        webdavRequest($testFile, 'DELETE', null, $config['username'], $config['password']);
        vault_log('WEBDAV', '连接测试成功: 目录可写');
        echo json_encode(['ok' => true, 'msg' => '连接成功，目录可写入']);
    } else {
        vault_log('WEBDAV', '连接测试失败: ' . $result['error']);
        echo json_encode(['ok' => false, 'error' => $result['error'], 'code' => $result['code']]);
    }
}

// 导出数据为 JSON
function exportDataJson($db) {
    $cats = $db->query("SELECT * FROM categories ORDER BY sort_order ASC, id ASC");
    $categories = [];
    while ($c = $cats->fetchArray(SQLITE3_ASSOC)) {
        $stmt = $db->prepare("SELECT * FROM entries WHERE category_id = :cid ORDER BY sort_order ASC, updated_at DESC, id ASC");
        $stmt->bindValue(':cid', $c['id'], SQLITE3_INTEGER);
        $rows = $stmt->execute();
        $entries = [];
        while ($e = $rows->fetchArray(SQLITE3_ASSOC)) {
            $entries[] = [
                'title' => $e['title'], 'username' => $e['username_field'],
                'password' => decryptPassword($db, $e['password_field']), 'url' => $e['url'], 'notes' => $e['notes'], 'sort_order' => (int)($e['sort_order'] ?? 0),
            ];
        }
        $categories[] = ['name' => $c['name'], 'icon' => $c['icon'], 'sort_order' => (int)$c['sort_order'], 'entries' => $entries];
    }
    return json_encode(['version' => 2, 'exportedAt' => date('c'), 'data' => ['categories' => $categories]], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
}

// 上传：创建目录 → 写入时间戳文件 → 清理旧版本（保留最新 10 个）
function handleWebdavSave($db) {
    @set_time_limit(90);
    $config = getWebdavConfig($db);
    if (!$config['url']) {
        echo json_encode(['ok' => false, 'error' => '请先配置 WebDAV 地址']);
        return;
    }
    $json = exportDataJson($db);
    $ts = date('Ymd_His');
    $fileName = 'vault-' . $ts . '.json';
    $fileUrl = $config['url'] . $fileName;
    vault_log('WEBDAV', '上传: ' . strlen($json) . ' bytes → ' . $fileUrl);

    webdavMkcol($config['url'], $config['username'], $config['password']);

    $result = webdavRequest($fileUrl, 'PUT', $json, $config['username'], $config['password']);
    if (!$result['ok']) {
        vault_log('WEBDAV', '上传失败: ' . $result['error'] . ' HTTP=' . $result['code']);
        http_response_code(502);
        echo json_encode(['ok' => false, 'error' => $result['error'], 'code' => $result['code']]);
        return;
    }
    vault_log('WEBDAV', '上传成功: ' . $fileName . ' HTTP=' . $result['code']);

    // 清理旧版本（保留最新 10 个）
    $files = webdavListFiles($config['url'], $config['username'], $config['password']);
    rsort($files);
    if (count($files) > 10) {
        foreach (array_slice($files, 10) as $old) {
            vault_log('WEBDAV', '清理旧版本: ' . $old);
            webdavRequest($config['url'] . $old, 'DELETE', null, $config['username'], $config['password']);
        }
    }

    $stmt = $db->prepare("INSERT OR REPLACE INTO settings (key, value) VALUES ('webdav_last_sync', :v)");
    $stmt->bindValue(':v', date('c'), SQLITE3_TEXT);
    $stmt->execute();
    echo json_encode(['ok' => true, 'msg' => '已上传: ' . $fileName, 'size' => strlen($json)]);
}

// 解析目录列表，提取 vault-*.json 文件名
function webdavListFiles($dirUrl, $user, $pass) {
    $result = webdavRequest($dirUrl, 'GET', null, $user, $pass);
    if (!$result['ok']) return [];
    $body = $result['body'];
    $files = [];
    if (preg_match_all('/href="(vault-\d{8}_\d{6}\.json)"/i', $body, $m)) {
        $files = $m[1];
    }
    return $files;
}

// 下载：列出目录 → 取最新文件 → GET
function handleWebdavLoad($db) {
    @set_time_limit(90);
    $config = getWebdavConfig($db);
    if (!$config['url']) {
        echo json_encode(['ok' => false, 'error' => '请先配置 WebDAV 地址']);
        return;
    }
    $files = webdavListFiles($config['url'], $config['username'], $config['password']);
    if (empty($files)) {
        echo json_encode(['ok' => true, 'data' => null, 'msg' => 'WebDAV 暂无备份文件']);
        return;
    }
    rsort($files);
    $latest = $files[0];
    $fileUrl = $config['url'] . $latest;
    vault_log('WEBDAV', '下载最新: ' . $latest);

    $result = webdavRequest($fileUrl, 'GET', null, $config['username'], $config['password']);
    if ($result['ok'] && $result['code'] >= 200 && $result['code'] < 300) {
        $data = json_decode($result['body'], true);
        if (!$data) {
            http_response_code(400);
            echo json_encode(['error' => '备份文件 JSON 解析失败']);
            return;
        }
        vault_log('WEBDAV', '下载成功: ' . $latest . ' HTTP=' . $result['code']);
        echo json_encode(['ok' => true, 'data' => $data]);
    } else {
        http_response_code(502);
        echo json_encode(['ok' => false, 'error' => $result['error'] ?: ('HTTP ' . $result['code']), 'code' => $result['code']]);
    }
}

// 列出最近版本
function handleWebdavVersions($db) {
    $config = getWebdavConfig($db);
    if (!$config['url']) {
        echo json_encode(['ok' => true, 'versions' => []]);
        return;
    }
    $files = webdavListFiles($config['url'], $config['username'], $config['password']);
    rsort($files);
    $versions = [];
    foreach (array_slice($files, 0, 10) as $name) {
        // 从 vault-YYYYMMDD_HHMMSS.json 解析时间
        $ts = substr($name, 6, 15); // YYYYMMDD_HHMMSS
        $dt = DateTime::createFromFormat('Ymd_His', $ts);
        $versions[] = [
            'name' => $name,
            'time' => $dt ? $dt->format('c') : $ts,
        ];
    }
    echo json_encode(['ok' => true, 'versions' => $versions]);
}

// 下载指定版本
function handleWebdavLoadVersion($db) {
    $input = jsonInput();
    $name = $input['name'] ?? '';
    if (!$name || !preg_match('/^vault-\d{8}_\d{6}\.json$/', $name)) {
        http_response_code(400);
        echo json_encode(['error' => '无效的版本文件名']);
        return;
    }
    $config = getWebdavConfig($db);
    $fileUrl = $config['url'] . $name;
    vault_log('WEBDAV', '下载指定版本: ' . $name);
    $result = webdavRequest($fileUrl, 'GET', null, $config['username'], $config['password']);
    if ($result['ok'] && $result['code'] >= 200 && $result['code'] < 300) {
        $data = json_decode($result['body'], true);
        if (!$data) { http_response_code(400); echo json_encode(['error' => '备份文件 JSON 解析失败']); return; }
        echo json_encode(['ok' => true, 'data' => $data]);
    } else {
        http_response_code(502);
        echo json_encode(['ok' => false, 'error' => $result['error'] ?: ('HTTP ' . $result['code'])]);
    }
}

// HTTP 请求工具
function webdavRequest($url, $method, $body, $user, $pass) {
    if (!function_exists('curl_init')) {
        return ['ok' => false, 'error' => '服务器未安装 PHP cURL 扩展', 'code' => 0];
    }
    if (!$url) return ['ok' => false, 'error' => 'URL 为空', 'code' => 0];

    @set_time_limit(90);
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_TIMEOUT        => 60,
        CURLOPT_CONNECTTIMEOUT => 15,
        CURLOPT_USERPWD        => $user . ':' . $pass,
        CURLOPT_USERAGENT      => 'VaultWebDAV/3.0',
    ]);
    if ($method === 'PUT') {
        curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'PUT');
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'Content-Type: application/json; charset=utf-8',
            'Content-Length: ' . strlen($body),
        ]);
    } elseif ($method === 'DELETE' || $method === 'MKCOL') {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    }

    $resp = @curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err  = curl_error($ch);
    $errNo = curl_errno($ch);
    $time = round(curl_getinfo($ch, CURLINFO_TOTAL_TIME), 2);
    curl_close($ch);

    if ($resp === false) {
        $msg = '连接失败';
        if ($errNo === 6)  $msg = '无法解析域名';
        elseif ($errNo === 7)  $msg = '无法连接服务器';
        elseif ($errNo === 28) $msg = '连接超时';
        elseif ($errNo === 35) $msg = 'SSL/TLS 握手失败';
        elseif ($err) $msg = $err;
        vault_log('WEBDAV', "请求失败: {$msg} ({$errNo}), 耗时={$time}s");
        return ['ok' => false, 'error' => $msg, 'code' => 0, 'body' => ''];
    }
    vault_log('WEBDAV', "{$method} {$code}, 耗时={$time}s" . ($err ? ", err={$err}" : ''));
    if ($code === 401) return ['ok' => false, 'error' => '认证失败（401）', 'code' => $code, 'body' => $resp];
    if ($code === 403) return ['ok' => false, 'error' => '无权限（403）',   'code' => $code, 'body' => $resp];
    if ($code >= 400) return ['ok' => false, 'error' => 'HTTP ' . $code,     'code' => $code, 'body' => $resp];
    return ['ok' => true, 'code' => $code, 'body' => $resp, 'error' => ''];
}

function handleWebdavLastSync($db) {
    $stmt = $db->prepare("SELECT value FROM settings WHERE key = 'webdav_last_sync'");
    $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    echo json_encode(['ok' => true, 'time' => $row ? $row['value'] : null]);
}

// 快速查询云端最新备份的时间戳（不下载完整数据）
function handleWebdavCloudLatest($db) {
    $config = getWebdavConfig($db);
    if (!$config['url']) {
        echo json_encode(['ok' => true, 'configured' => false]);
        return;
    }
    $files = webdavListFiles($config['url'], $config['username'], $config['password']);
    if (empty($files)) {
        echo json_encode(['ok' => true, 'configured' => true, 'latest' => null]);
        return;
    }
    rsort($files);
    $latest = $files[0]; // vault-YYYYMMDD_HHMMSS.json
    $time = null;
    if (preg_match('/vault-(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json/', $latest, $m)) {
        $time = $m[1] . '-' . $m[2] . '-' . $m[3] . 'T' . $m[4] . ':' . $m[5] . ':' . $m[6];
    }
    echo json_encode(['ok' => true, 'configured' => true, 'latest' => $latest, 'time' => $time]);
}

// ==================== 权限检查工具 ====================
function checkCategoryAccess($db, $user, $catId, $mode = 'read', $exitOnDeny = true) {
    if ($user['role'] === 'master') return true;
    $stmt = $db->prepare("SELECT can_read, can_write FROM category_permissions WHERE user_id = :uid AND category_id = :cid");
    $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
    $stmt->bindValue(':cid', $catId, SQLITE3_INTEGER);
    $perm = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if (!$perm) $hasAccess = false;
    elseif ($mode === 'read') $hasAccess = (bool)$perm['can_read'];
    else $hasAccess = (bool)$perm['can_write'];
    if (!$hasAccess && $exitOnDeny) {
        http_response_code(403);
        echo json_encode(['error' => '无权限']);
        exit;
    }
    return $hasAccess;
}

// ==================== 调试日志查看 ====================
function handleDebugLog() {
    $logDir = defined('DATA_DIR') ? DATA_DIR : __DIR__;
    $logFile = $logDir . '/vault_debug.log';
    $lines = $_GET['lines'] ?? 100;
    $lines = max(10, min(500, (int)$lines));
    if (!file_exists($logFile)) {
        echo json_encode(['ok' => true, 'log' => '(日志文件尚未创建)', 'path' => $logFile]);
        return;
    }
    $content = @file_get_contents($logFile);
    if ($content === false) {
        echo json_encode(['ok' => false, 'error' => '无法读取日志文件', 'path' => $logFile]);
        return;
    }
    $allLines = explode("\n", rtrim($content));
    $recent = array_slice($allLines, -$lines);
    echo json_encode([
        'ok' => true,
        'path' => $logFile,
        'size' => strlen($content),
        'log' => implode("\n", $recent),
    ]);
}

// ==================== 提交审核系统 ====================

function formatProposal($r) {
    $data = json_decode($r['entry_data'] ?? '{}', true) ?: [];
    return [
        'id'              => (int)$r['id'],
        'proposal_type'   => $r['proposal_type'],
        'title'           => $r['title'],
        'category_id'     => $r['category_id'] ? (int)$r['category_id'] : null,
        'target_entry_id' => $r['target_entry_id'] ? (int)$r['target_entry_id'] : null,
        'entry_data'      => $data,
        'icon'            => $r['icon'] ?? '🔐',
        'reason'          => $r['reason'] ?? '',
        'status'          => $r['status'],
        'created_by'      => (int)$r['created_by'],
        'reviewed_by'     => $r['reviewed_by'] ? (int)$r['reviewed_by'] : null,
        'review_comment'  => $r['review_comment'] ?? '',
        'created_at'      => $r['created_at'],
        'reviewed_at'     => $r['reviewed_at'],
        'category_name'   => $r['category_name'] ?? null,
        'creator_name'    => $r['creator_name'] ?? null,
    ];
}

function handleGetMyProposals($db, $user) {
    $status = $_GET['status'] ?? 'all';
    $sql = "SELECT p.*, c.name AS category_name, u.display_name AS creator_name
            FROM proposals p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN users u ON p.created_by = u.id
            WHERE p.created_by = :uid";
    $params = [':uid' => $user['id']];
    if ($status !== 'all') {
        $sql .= " AND p.status = :status";
        $params[':status'] = $status;
    }
    $sql .= " ORDER BY p.created_at DESC";
    $stmt = $db->prepare($sql);
    foreach ($params as $k => $v) {
        $stmt->bindValue($k, $v, SQLITE3_TEXT);
    }
    $rows = $stmt->execute();
    $proposals = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $proposals[] = formatProposal($r);
    }
    echo json_encode(['ok' => true, 'proposals' => $proposals]);
}

function handleGetPendingReviews($db) {
    $type = $_GET['type'] ?? 'all';
    $status = $_GET['status'] ?? 'pending';
    $sql = "SELECT p.*, c.name AS category_name, u.display_name AS creator_name
            FROM proposals p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN users u ON p.created_by = u.id
            WHERE 1=1";
    $params = [];
    if ($type !== 'all') {
        $sql .= " AND p.proposal_type = :type";
        $params[':type'] = $type;
    }
    if ($status !== 'all') {
        $sql .= " AND p.status = :status";
        $params[':status'] = $status;
    }
    $sql .= " ORDER BY CASE WHEN p.status = 'pending' THEN 0 ELSE 1 END, p.created_at DESC";
    $stmt = $db->prepare($sql);
    foreach ($params as $k => $v) {
        $stmt->bindValue($k, $v, SQLITE3_TEXT);
    }
    $rows = $stmt->execute();
    $proposals = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $proposals[] = formatProposal($r);
    }
    echo json_encode(['ok' => true, 'proposals' => $proposals]);
}

function handleGetProposalDetail($db, $user) {
    $id = (int)($_GET['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error' => '缺少提案ID']); exit; }
    $stmt = $db->prepare("SELECT p.*, c.name AS category_name, u.display_name AS creator_name
            FROM proposals p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN users u ON p.created_by = u.id
            WHERE p.id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $r = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if (!$r) { http_response_code(404); echo json_encode(['error' => '提案不存在']); exit; }
    if ($user['role'] !== 'master' && (int)$r['created_by'] !== $user['id']) {
        http_response_code(403); echo json_encode(['error' => '无权查看此提案']); exit;
    }
    echo json_encode(['ok' => true, 'proposal' => formatProposal($r)]);
}

function handleCreateProposal($db, $user) {
    $input = jsonInput();
    $type = $input['proposal_type'] ?? '';
    if (!in_array($type, ['create','update','report'])) {
        http_response_code(400); echo json_encode(['error' => '无效的提案类型']); exit;
    }
    $title = trim($input['title'] ?? '');
    if (!$title) { http_response_code(400); echo json_encode(['error' => '标题不能为空']); exit; }

    $categoryId = (int)($input['category_id'] ?? 0);
    $targetEntryId = (int)($input['target_entry_id'] ?? 0);

    if ($type === 'create') {
        // 创建新条目：需要分类读权限（提案会经过审核）
        if (!$categoryId) { http_response_code(400); echo json_encode(['error' => '缺少分类ID']); exit; }
        if (!checkCategoryAccess($db, $user, $categoryId, 'read', false)) {
            http_response_code(403); echo json_encode(['error' => '无权限访问该分类']); exit;
        }
    } elseif (in_array($type, ['update','report'])) {
        if (!$targetEntryId) {
            http_response_code(400); echo json_encode(['error' => '缺少目标条目ID']); exit;
        }
        $ce = $db->prepare("SELECT category_id FROM entries WHERE id = :id");
        $ce->bindValue(':id', $targetEntryId, SQLITE3_INTEGER);
        $cr = $ce->execute()->fetchArray(SQLITE3_ASSOC);
        if (!$cr) { http_response_code(404); echo json_encode(['error' => '目标条目不存在']); exit; }
        if (!checkCategoryAccess($db, $user, $cr['category_id'], 'read', false)) {
            http_response_code(403); echo json_encode(['error' => '无权访问目标条目']); exit;
        }
        if (!$categoryId) $categoryId = (int)$cr['category_id'];
    }

    $entryData = $input['entry_data'] ?? '{}';
    if (is_array($entryData)) $entryData = json_encode($entryData, JSON_UNESCAPED_UNICODE);
    $icon = $input['icon'] ?? '🔐';
    $reason = trim($input['reason'] ?? '');

    $stmt = $db->prepare("INSERT INTO proposals (proposal_type, title, category_id, target_entry_id, entry_data, icon, reason, created_by)
            VALUES (:type, :title, :cid, :teid, :edata, :icon, :reason, :uid)");
    $stmt->bindValue(':type', $type, SQLITE3_TEXT);
    $stmt->bindValue(':title', $title, SQLITE3_TEXT);
    $stmt->bindValue(':cid', $categoryId ?: null, SQLITE3_INTEGER);
    $stmt->bindValue(':teid', $targetEntryId ?: null, SQLITE3_INTEGER);
    $stmt->bindValue(':edata', $entryData, SQLITE3_TEXT);
    $stmt->bindValue(':icon', $icon, SQLITE3_TEXT);
    $stmt->bindValue(':reason', $reason, SQLITE3_TEXT);
    $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
    $stmt->execute();
    $newId = $db->lastInsertRowID();

    // 通知主账号
    $masters = $db->query("SELECT id FROM users WHERE role = 'master' AND is_active = 1");
    while ($m = $masters->fetchArray(SQLITE3_ASSOC)) {
        $n = $db->prepare("INSERT INTO review_notifications (proposal_id, user_id, type) VALUES (:pid, :uid, 'submitted')");
        $n->bindValue(':pid', $newId, SQLITE3_INTEGER);
        $n->bindValue(':uid', (int)$m['id'], SQLITE3_INTEGER);
        $n->execute();
    }

    $typeLabel = ['create' => '新条目', 'update' => '修改建议', 'report' => '问题上报'][$type] ?? $type;
    vault_log('PROPOSAL', "用户 {$user['username']} 提交{$typeLabel}: {$title} (ID={$newId})");

    // 推送 Server酱 通知给主账号
    $scTitle = "🔒 凭证保险箱 · 新提案待审核";
    $scDesp = "来自你的**个人网页凭证保险箱**，有一条新的提交等待审核：\n\n"
            . "---\n\n"
            . "**提案类型**: {$typeLabel}\n\n"
            . "**提交者**: {$user['display_name']}\n\n"
            . "**条目标题**: {$title}\n\n"
            . ($reason ? "**提交说明**: {$reason}\n\n" : '')
            . "---\n\n"
            . "> 请登录凭证保险箱审核处理";
    notifyServerChan($db, $scTitle, $scDesp);

    echo json_encode(['ok' => true, 'id' => $newId]);
}

function handleUpdateProposal($db, $user) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error' => '缺少提案ID']); exit; }
    $stmt = $db->prepare("SELECT * FROM proposals WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $r = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if (!$r) { http_response_code(404); echo json_encode(['error' => '提案不存在']); exit; }
    if ((int)$r['created_by'] !== $user['id']) { http_response_code(403); echo json_encode(['error' => '只能编辑自己的提案']); exit; }
    if ($r['status'] !== 'pending') { http_response_code(400); echo json_encode(['error' => '只能编辑待审核的提案']); exit; }

    $fields = [];
    if (!empty($input['title'])) $fields['title'] = $input['title'];
    if (!empty($input['reason'])) $fields['reason'] = $input['reason'];
    if (isset($input['entry_data'])) {
        $ed = $input['entry_data'];
        $fields['entry_data'] = is_array($ed) ? json_encode($ed, JSON_UNESCAPED_UNICODE) : $ed;
    }
    if (!empty($input['icon'])) $fields['icon'] = $input['icon'];

    if (empty($fields)) { echo json_encode(['ok' => true]); exit; }

    $setParts = [];
    $bindings = [];
    foreach ($fields as $k => $v) {
        $setParts[] = "$k = :$k";
        $bindings[":$k"] = $v;
    }
    $bindings[':id'] = $id;
    $sql = "UPDATE proposals SET " . implode(', ', $setParts) . " WHERE id = :id";
    $stmt = $db->prepare($sql);
    foreach ($bindings as $k => $v) {
        $stmt->bindValue($k, $v, SQLITE3_TEXT);
    }
    $stmt->execute();
    echo json_encode(['ok' => true]);
}

function handleDeleteProposal($db, $user) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error' => '缺少提案ID']); exit; }
    $stmt = $db->prepare("SELECT * FROM proposals WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $r = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if (!$r) { http_response_code(404); echo json_encode(['error' => '提案不存在']); exit; }
    if ((int)$r['created_by'] !== $user['id']) { http_response_code(403); echo json_encode(['error' => '只能删除自己的提案']); exit; }
    if ($r['status'] !== 'pending') { http_response_code(400); echo json_encode(['error' => '只能删除待审核的提案']); exit; }
    $stmt = $db->prepare("DELETE FROM proposals WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $stmt->execute();
    echo json_encode(['ok' => true]);
}

function handleReviewProposal($db, $user) {
    $input = jsonInput();
    $id = (int)($input['proposal_id'] ?? 0);
    $action = $input['action'] ?? '';
    $comment = trim($input['review_comment'] ?? '');

    if (!$id || !in_array($action, ['approve','reject'])) {
        http_response_code(400); echo json_encode(['error' => '参数错误']); exit;
    }

    $stmt = $db->prepare("SELECT * FROM proposals WHERE id = :id");
    $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
    $proposal = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if (!$proposal) { http_response_code(404); echo json_encode(['error' => '提案不存在']); exit; }
    if ($proposal['status'] !== 'pending') { http_response_code(400); echo json_encode(['error' => '该提案已处理']); exit; }

    $newStatus = $action === 'approve' ? 'approved' : 'rejected';

    if ($action === 'approve') {
        $db->exec('BEGIN');
        try {
            // 根据提案类型执行自动合并
            $entryData = json_decode($proposal['entry_data'], true) ?: [];
            $fields = $entryData['fields'] ?? [];
            $icon = $proposal['icon'] ?? '🔐';

            if ($proposal['proposal_type'] === 'create') {
                // 创建新条目
                $eStmt = $db->prepare("INSERT INTO entries (category_id, title, username_field, password_field, url, notes, created_by)
                        VALUES (:cid, :title, :uname, :pwd, :url, :notes, :cb)");
                $uname = ''; $pwd = ''; $url = ''; $notes = '';
                foreach ($fields as $f) {
                    $key = strtolower(trim($f['key'] ?? ''));
                    $val = $f['value'] ?? '';
                    if ($key === '用户名' || $key === 'username' || $key === '账号') $uname = $val;
                    elseif ($key === '密码' || $key === 'password') $pwd = $val;
                    elseif ($key === '链接' || $key === 'url' || $key === '网址') $url = $val;
                    elseif ($key === '备注' || $key === 'notes') $notes = $val;
                    else { if ($notes) $notes .= "\n"; $notes .= ($f['key'] ?? '') . ': ' . $val; }
                }
                $eStmt->bindValue(':cid', $proposal['category_id'], SQLITE3_INTEGER);
                $eStmt->bindValue(':title', $proposal['title'], SQLITE3_TEXT);
                $eStmt->bindValue(':uname', $uname, SQLITE3_TEXT);
                $eStmt->bindValue(':pwd', encryptPassword($db, $pwd), SQLITE3_TEXT);
                $eStmt->bindValue(':url', $url, SQLITE3_TEXT);
                $eStmt->bindValue(':notes', $notes, SQLITE3_TEXT);
                $eStmt->bindValue(':cb', $proposal['created_by'], SQLITE3_INTEGER);
                $eStmt->execute();
            } elseif ($proposal['proposal_type'] === 'update' && $proposal['target_entry_id']) {
                // 修改已有条目
                $setParts = [];
                $bindings = [];
                foreach ($fields as $f) {
                    $key = strtolower(trim($f['key'] ?? ''));
                    $val = $f['value'] ?? '';
                    if ($key === '标题' || $key === 'title') { $setParts[] = 'title = :title'; $bindings[':title'] = $val; }
                    elseif ($key === '用户名' || $key === 'username' || $key === '账号') { $setParts[] = 'username_field = :uname'; $bindings[':uname'] = $val; }
                    elseif ($key === '密码' || $key === 'password') { $setParts[] = 'password_field = :pwd'; $bindings[':pwd'] = encryptPassword($db, $val); }
                    elseif ($key === '链接' || $key === 'url' || $key === '网址') { $setParts[] = 'url = :url'; $bindings[':url'] = $val; }
                    elseif ($key === '备注' || $key === 'notes') { $setParts[] = 'notes = :notes'; $bindings[':notes'] = $val; }
                }
                if (!empty($setParts)) {
                    $setParts[] = "updated_at = datetime('now','localtime')";
                    $bindings[':eid'] = (int)$proposal['target_entry_id'];
                    $sql = "UPDATE entries SET " . implode(', ', $setParts) . " WHERE id = :eid";
                    $uStmt = $db->prepare($sql);
                    foreach ($bindings as $k => $v) {
                        $uStmt->bindValue($k, $v, SQLITE3_TEXT);
                    }
                    $uStmt->execute();
                }
            }
            // report 类型：仅标记为已处理，不修改数据

            // 更新提案状态
            $upStmt = $db->prepare("UPDATE proposals SET status = :status, reviewed_by = :rb, review_comment = :rc, reviewed_at = datetime('now','localtime') WHERE id = :id");
            $upStmt->bindValue(':status', $newStatus, SQLITE3_TEXT);
            $upStmt->bindValue(':rb', $user['id'], SQLITE3_INTEGER);
            $upStmt->bindValue(':rc', $comment, SQLITE3_TEXT);
            $upStmt->bindValue(':id', $id, SQLITE3_INTEGER);
            $upStmt->execute();

            $db->exec('COMMIT');
        } catch (Exception $e) {
            $db->exec('ROLLBACK');
            vault_log('PROPOSAL', '审核合并失败: ' . $e->getMessage());
            http_response_code(500);
            echo json_encode(['error' => '合并失败: ' . $e->getMessage()]);
            exit;
        }
    } else {
        // 驳回
        $upStmt = $db->prepare("UPDATE proposals SET status = :status, reviewed_by = :rb, review_comment = :rc, reviewed_at = datetime('now','localtime') WHERE id = :id");
        $upStmt->bindValue(':status', $newStatus, SQLITE3_TEXT);
        $upStmt->bindValue(':rb', $user['id'], SQLITE3_INTEGER);
        $upStmt->bindValue(':rc', $comment, SQLITE3_TEXT);
        $upStmt->bindValue(':id', $id, SQLITE3_INTEGER);
        $upStmt->execute();
    }

    // 通知提案创建者
    $nStmt = $db->prepare("INSERT INTO review_notifications (proposal_id, user_id, type) VALUES (:pid, :uid, :type)");
    $nStmt->bindValue(':pid', $id, SQLITE3_INTEGER);
    $nStmt->bindValue(':uid', (int)$proposal['created_by'], SQLITE3_INTEGER);
    $nStmt->bindValue(':type', $newStatus, SQLITE3_TEXT);
    $nStmt->execute();

    $typeLabel = ['create' => '新条目', 'update' => '修改建议', 'report' => '问题上报'][$proposal['proposal_type']] ?? '';
    $actionLabel = $action === 'approve' ? '批准' : '驳回';
    vault_log('PROPOSAL', "主账号 {$user['username']} {$actionLabel} 提案 #{$id} ({$typeLabel}): {$proposal['title']}");

    // 推送 Server酱 通知给提案者
    $scEmoji = $action === 'approve' ? '✅' : '❌';
    $scTitle = "🔒 凭证保险箱 · 提案已{$actionLabel}";
    $scDesp = "来自你的**个人网页凭证保险箱**，你提交的提案已被处理：\n\n"
            . "---\n\n"
            . "**提案类型**: {$typeLabel}\n\n"
            . "**条目标题**: {$proposal['title']}\n\n"
            . "**审核结果**: {$scEmoji} 已{$actionLabel}\n\n"
            . ($comment ? "**审核意见**: {$comment}\n\n" : '')
            . "---";
    notifyServerChan($db, $scTitle, $scDesp);

    echo json_encode(['ok' => true, 'action' => $action]);
}

function handleGetNotifications($db, $user) {
    $unreadOnly = isset($_GET['unread']) && $_GET['unread'] === '1';
    $sql = "SELECT n.*, p.title AS proposal_title, p.proposal_type
            FROM review_notifications n
            LEFT JOIN proposals p ON n.proposal_id = p.id
            WHERE n.user_id = :uid";
    if ($unreadOnly) $sql .= " AND n.is_read = 0";
    $sql .= " ORDER BY n.created_at DESC LIMIT 50";
    $stmt = $db->prepare($sql);
    $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
    $rows = $stmt->execute();
    $notifications = [];
    while ($r = $rows->fetchArray(SQLITE3_ASSOC)) {
        $notifications[] = [
            'id' => (int)$r['id'],
            'proposal_id' => (int)$r['proposal_id'],
            'type' => $r['type'],
            'is_read' => (bool)$r['is_read'],
            'created_at' => $r['created_at'],
            'proposal_title' => $r['proposal_title'] ?? '',
            'proposal_type' => $r['proposal_type'] ?? '',
        ];
    }
    $stmt = $db->prepare("SELECT COUNT(*) FROM review_notifications WHERE user_id = :uid AND is_read = 0");
    $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
    $unreadCount = $stmt->execute()->fetchArray(SQLITE3_NUM)[0];
    echo json_encode(['ok' => true, 'notifications' => $notifications, 'unread_count' => (int)$unreadCount]);
}

function handleMarkNotificationRead($db, $user) {
    $input = jsonInput();
    $id = (int)($input['id'] ?? 0);
    if ($id) {
        $stmt = $db->prepare("UPDATE review_notifications SET is_read = 1 WHERE id = :id AND user_id = :uid");
        $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
        $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
        $stmt->execute();
    } else {
        // 标记全部已读
        $stmt = $db->prepare("UPDATE review_notifications SET is_read = 1 WHERE user_id = :uid AND is_read = 0");
        $stmt->bindValue(':uid', $user['id'], SQLITE3_INTEGER);
        $stmt->execute();
    }
    echo json_encode(['ok' => true]);
}

// ==================== Server酱推送 ====================

function getServerChanKey($db) {
    $stmt = $db->prepare("SELECT value FROM settings WHERE key = 'serverchan_sendkey'");
    $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    return $row ? trim($row['value']) : '';
}

function handleServerChanConfig($db) {
    $key = getServerChanKey($db);
    echo json_encode(['ok' => true, 'has_key' => !empty($key)]);
}

function handleServerChanConfigSave($db) {
    $input = jsonInput();
    $key = trim($input['sendkey'] ?? '');
    $stmt = $db->prepare("INSERT OR REPLACE INTO settings (key, value) VALUES ('serverchan_sendkey', :v)");
    $stmt->bindValue(':v', $key, SQLITE3_TEXT);
    $stmt->execute();
    vault_log('SERVERCHAN', 'SendKey 已' . ($key ? '更新' : '清除'));
    echo json_encode(['ok' => true]);
}

function handleServerChanTest($db) {
    $key = getServerChanKey($db);
    if (!$key) { echo json_encode(['ok' => false, 'error' => '请先配置 SendKey']); return; }
    $result = serverChanSend($key, '🔒 凭证保险箱 · 推送测试', '来自你的**个人网页凭证保险箱**，Server酱推送配置成功！后续有新提案或审核结果时，会自动推送通知到这里。');
    if ($result['ok']) {
        echo json_encode(['ok' => true, 'msg' => '推送成功，请检查微信']);
    } else {
        echo json_encode(['ok' => false, 'error' => $result['error']]);
    }
}

/**
 * 调用 Server酱 API 发送推送通知
 *
 * @param string $sendKey Server酱 SendKey
 * @param string $title   通知标题
 * @param string $desp    通知内容（支持 Markdown）
 * @return array ['ok' => bool, 'error' => string]
 */
function serverChanSend($sendKey, $title, $desp = '') {
    if (!$sendKey) return ['ok' => false, 'error' => 'SendKey 未配置'];
    if (!function_exists('curl_init')) return ['ok' => false, 'error' => '服务器未安装 cURL'];

    $url = 'https://sctapi.ftqq.com/' . $sendKey . '.send';
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => http_build_query(['title' => $title, 'desp' => $desp]),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_CONNECTTIMEOUT => 5,
        CURLOPT_SSL_VERIFYPEER => true,
    ]);
    $resp = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err  = curl_error($ch);
    curl_close($ch);

    if ($resp === false) {
        vault_log('SERVERCHAN', "推送失败: {$err}");
        return ['ok' => false, 'error' => '连接失败: ' . $err];
    }

    $data = json_decode($resp, true);
    // Server酱 Turbo 返回 code=0 表示成功
    if ($code >= 200 && $code < 300 && isset($data['code']) && $data['code'] === 0) {
        vault_log('SERVERCHAN', "推送成功: {$title}");
        return ['ok' => true];
    }

    $errMsg = $data['message'] ?? $data['errmsg'] ?? "HTTP {$code}";
    vault_log('SERVERCHAN', "推送失败: {$errMsg}");
    return ['ok' => false, 'error' => $errMsg];
}

/**
 * 异步发送 Server酱 通知（不阻塞主请求）
 * 在提案创建/审核时调用
 */
function notifyServerChan($db, $title, $desp) {
    $key = getServerChanKey($db);
    if (!$key) return;
    // 非阻塞：忽略返回值
    serverChanSend($key, $title, $desp);
}

// ==================== 锁屏密码验证 ====================
function handleVerifyPassword($db, $user) {
    $input = jsonInput();
    $password = $input['password'] ?? '';
    if (!$password) { http_response_code(400); echo json_encode(['error' => '请输入密码']); exit; }
    $stmt = $db->prepare("SELECT password_hash FROM users WHERE id = :id");
    $stmt->bindValue(':id', $user['id'], SQLITE3_INTEGER);
    $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    if (!$row || !password_verify($password, $row['password_hash'])) {
        http_response_code(401);
        echo json_encode(['ok' => false, 'error' => '密码错误']);
        exit;
    }
    echo json_encode(['ok' => true]);
}
