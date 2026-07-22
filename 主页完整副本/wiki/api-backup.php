<?php
ini_set('display_errors', 0);
/**
 * Wiki 云端备份 API
 *
 * 共享 vault 的 WebDAV 配置，备份 wiki 内容（.md + comments/*.json）
 * WebDAV 子目录：{vault_webdav_url}/wiki-backup/
 *
 * GET  ?action=status           → WebDAV 配置状态
 * GET  ?action=versions         → 列出备份版本
 * GET  ?action=last-sync        → 上次同步时间
 * POST ?action=backup           → 打包并上传
 * POST ?action=restore          → 从最新版本恢复
 * POST ?action=restore-version  → 恢复指定版本
 * POST ?action=set-max-versions → 设置最大版本数
 * GET  ?action=documents        → 自动扫描并列出 Markdown 文档
 */

// 错误处理：确保所有错误都以 JSON 格式返回
error_reporting(E_ALL);
set_error_handler(function($errno, $errstr, $errfile, $errline) {
    // 检查是否被 @ 运算符抑制
    if (!(error_reporting() & $errno)) {
        return false; // 不处理被抑制的错误
    }
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['ok' => false, 'error' => "PHP 错误: $errstr (第 $errline 行)"], JSON_UNESCAPED_UNICODE);
    exit;
});
set_exception_handler(function($e) {
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['ok' => false, 'error' => 'PHP 异常: ' . $e->getMessage()], JSON_UNESCAPED_UNICODE);
    exit;
});
register_shutdown_function(function() {
    $error = error_get_last();
    if (!$error || !in_array($error['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR], true)) return;
    if (headers_sent()) return;
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['ok' => false, 'error' => 'PHP 致命错误: ' . $error['message']], JSON_UNESCAPED_UNICODE);
});

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Authorization, Content-Type');
if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') { http_response_code(200); exit; }

$action = $_GET['action'] ?? $_POST['action'] ?? '';
$wikiRoot = __DIR__; // wiki/ 目录

// ============================================================
//  辅助函数
// ============================================================

function jsonResponse($data) {
    $options = JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT;
    // 某个 Markdown 不是 UTF-8（或读取片段刚好截断多字节字符）时，
    // json_encode() 默认返回 false，最终会形成 HTTP 200 空响应。
    if (defined('JSON_INVALID_UTF8_SUBSTITUTE')) {
        $options |= JSON_INVALID_UTF8_SUBSTITUTE;
    }
    $json = json_encode($data, $options);
    if ($json === false) {
        http_response_code(500);
        $message = function_exists('json_last_error_msg') ? json_last_error_msg() : ('错误码 ' . json_last_error());
        $json = json_encode([
            'ok' => false,
            'error' => 'JSON 编码失败：' . $message . '。请确认 Markdown 文件使用 UTF-8 编码。'
        ], JSON_UNESCAPED_UNICODE);
    }
    echo $json;
    exit;
}

function jsonInput() {
    return json_decode(file_get_contents('php://input'), true) ?? [];
}

function wikiRequireMasterAuth() {
    $auth = '';
    if (function_exists('getallheaders')) {
        $headers = getallheaders();
        $auth = $headers['Authorization'] ?? ($headers['authorization'] ?? '');
    }
    if ($auth === '') $auth = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    if (substr($auth, 0, 7) !== 'Bearer ') {
        http_response_code(401);
        jsonResponse(['ok' => false, 'error' => '请先登录凭证保险箱主账号']);
    }

    $token = trim(substr($auth, 7));
    $dbPath = dirname(__DIR__) . '/vault/vault.db';
    if ($token === '' || !file_exists($dbPath) || !class_exists('SQLite3')) {
        http_response_code(401);
        jsonResponse(['ok' => false, 'error' => '无法验证保险箱会话']);
    }

    try {
        $db = new SQLite3($dbPath, SQLITE3_OPEN_READONLY);
        $stmt = $db->prepare("SELECT u.role FROM users u JOIN sessions s ON s.user_id = u.id
            WHERE s.token = :token AND s.expires_at > datetime('now','localtime') AND u.is_active = 1");
        $stmt->bindValue(':token', $token, SQLITE3_TEXT);
        $user = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
        $db->close();
    } catch (Throwable $e) {
        http_response_code(500);
        jsonResponse(['ok' => false, 'error' => '保险箱会话验证失败']);
    }

    if (!$user) {
        http_response_code(401);
        jsonResponse(['ok' => false, 'error' => '保险箱会话已过期，请重新登录']);
    }
    if (($user['role'] ?? '') !== 'master') {
        http_response_code(403);
        jsonResponse(['ok' => false, 'error' => '仅保险箱主账号可管理 Wiki 云同步']);
    }
}

function wikiAcquireSyncMutationLock() {
    $lockPath = rtrim(sys_get_temp_dir(), '/\\') . DIRECTORY_SEPARATOR . 'wiki-sync-' . sha1(__DIR__) . '.lock';
    $handle = @fopen($lockPath, 'c');
    if ($handle === false) {
        http_response_code(500);
        jsonResponse(['ok' => false, 'error' => '无法创建 Wiki 同步锁']);
    }
    if (!@flock($handle, LOCK_EX | LOCK_NB)) {
        @fclose($handle);
        http_response_code(409);
        jsonResponse(['ok' => false, 'error' => '另一项 Wiki 同步操作正在进行，请稍后重试']);
    }
    return $handle;
}

function wikiRequirePostMethod() {
    if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'POST') {
        http_response_code(405);
        header('Allow: POST');
        jsonResponse(['ok' => false, 'error' => '该同步操作仅允许 POST 请求']);
    }
}

function wikiLog($level, $msg) {
    $logFile = __DIR__ . '/backup-debug.log';
    // 检查目录是否可写，避免权限错误
    if (!is_writable(dirname($logFile))) {
        return;
    }
    // 如果文件已存在，检查文件本身是否可写
    if (file_exists($logFile) && !is_writable($logFile)) {
        return;
    }
    $line = date('Y-m-d H:i:s') . " [$level] $msg\n";
    @file_put_contents($logFile, $line, FILE_APPEND);
}

/**
 * 递归删除目录及其所有内容
 */
function recursiveDelete($dir) {
    if (!is_dir($dir)) return;
    foreach (scandir($dir) as $item) {
        if ($item === '.' || $item === '..') continue;
        $path = $dir . '/' . $item;
        is_dir($path) ? recursiveDelete($path) : @unlink($path);
    }
    @rmdir($dir);
}

function wikiDecryptStoredSecret($db, $stored) {
    if ($stored === '' || strpos($stored, 'enc:v1:') !== 0) return $stored;
    $stmt = $db->prepare("SELECT value FROM settings WHERE key = 'crypto_master_key'");
    $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
    $key = $row && !empty($row['value']) ? base64_decode($row['value'], true) : false;
    $decoded = base64_decode(substr($stored, 7), true);
    if ($key === false || $decoded === false || strlen($decoded) <= 28) return '';
    $iv = substr($decoded, 0, 12);
    $tag = substr($decoded, 12, 16);
    $ciphertext = substr($decoded, 28);
    $plaintext = openssl_decrypt($ciphertext, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
    return $plaintext === false ? '' : $plaintext;
}

/**
 * 从 vault.db 读取 WebDAV 配置
 */
function getWebdavConfig() {
    $dbPath = dirname(__DIR__) . '/vault/vault.db';
    if (!file_exists($dbPath)) {
        return null;
    }
    try {
        $db = new SQLite3($dbPath, SQLITE3_OPEN_READONLY);
        $config = ['url' => '', 'username' => '', 'password' => ''];
        foreach (['webdav_url', 'webdav_username', 'webdav_password'] as $key) {
            $stmt = $db->prepare("SELECT value FROM settings WHERE key = :k");
            $stmt->bindValue(':k', $key, SQLITE3_TEXT);
            $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
            $config[str_replace('webdav_', '', $key)] = $row ? trim($row['value']) : '';
        }
        $config['password'] = wikiDecryptStoredSecret($db, $config['password']);
        $db->close();
        if ($config['url'] && substr($config['url'], -1) !== '/') {
            $config['url'] .= '/';
        }
        return $config;
    } catch (Exception $e) {
        return null;
    }
}

/**
 * 获取 wiki 备份的 WebDAV 目录 URL
 */
function getWikiBackupUrl($config) {
    return $config['url'] . 'wiki-backup/';
}

/**
 * 读取本地版本数配置
 */
function getMaxVersions() {
    $confPath = __DIR__ . '/backup-config.json';
    if (file_exists($confPath)) {
        $conf = json_decode(file_get_contents($confPath), true);
        if ($conf && isset($conf['max_versions'])) {
            return max(1, min(100, (int)$conf['max_versions']));
        }
    }
    return 20; // 默认
}

function saveMaxVersions($n) {
    $confPath = __DIR__ . '/backup-config.json';
    if (file_exists($confPath) && !is_writable($confPath)) return false;
    if (!file_exists($confPath) && !is_writable(dirname($confPath))) return false;
    $conf = [];
    if (file_exists($confPath)) {
        $conf = json_decode(file_get_contents($confPath), true) ?? [];
    }
    $conf['max_versions'] = $n;
    return @file_put_contents($confPath, json_encode($conf, JSON_PRETTY_PRINT)) !== false;
}

function getLastSyncTime() {
    $confPath = __DIR__ . '/backup-config.json';
    if (file_exists($confPath)) {
        $conf = json_decode(file_get_contents($confPath), true);
        return $conf['last_sync'] ?? null;
    }
    return null;
}

function saveLastSyncTime() {
    $confPath = __DIR__ . '/backup-config.json';
    if (file_exists($confPath) && !is_writable($confPath)) {
        wikiLog('ERROR', "saveLastSyncTime: backup-config.json 不可写");
        return false;
    }
    if (!file_exists($confPath) && !is_writable(dirname($confPath))) {
        wikiLog('ERROR', "saveLastSyncTime: wiki 目录不可写，无法创建 backup-config.json");
        return false;
    }
    $conf = [];
    if (file_exists($confPath)) {
        $conf = json_decode(file_get_contents($confPath), true) ?? [];
    }
    $conf['last_sync'] = date('c');
    $ok = @file_put_contents($confPath, json_encode($conf, JSON_PRETTY_PRINT));
    if ($ok === false) {
        wikiLog('ERROR', "saveLastSyncTime: 写入 backup-config.json 失败");
        return false;
    }
    return true;
}

// ============================================================
//  WebDAV 请求封装
// ============================================================

/**
 * 执行单次 WebDAV 请求（内部函数）
 */
function webdavRequestOnce($url, $method, $body, $user, $pass) {
    if (!function_exists('curl_init')) {
        return ['ok' => false, 'error' => '服务器未安装 PHP cURL 扩展', 'code' => 0, 'curl_errno' => 0];
    }
    if (!$url) return ['ok' => false, 'error' => 'URL 为空', 'code' => 0, 'curl_errno' => 0];

    @set_time_limit(120);
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_TIMEOUT        => 90,
        CURLOPT_CONNECTTIMEOUT => 15,
        CURLOPT_USERPWD        => $user . ':' . $pass,
        CURLOPT_USERAGENT      => 'WikiBackup/1.0',
    ]);
    if ($method === 'PUT') {
        curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'PUT');
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'Content-Type: application/json; charset=utf-8',
            'Content-Length: ' . strlen($body),
        ]);
    } elseif ($method === 'PROPFIND') {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'PROPFIND');
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'Depth: 1',
            'Content-Type: application/xml',
        ]);
    } elseif ($method === 'DELETE' || $method === 'MKCOL') {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    }

    $resp = @curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err  = curl_error($ch);
    $errNo = curl_errno($ch);
    curl_close($ch);

    if ($resp === false) {
        $msg = '连接失败';
        if ($errNo === 6)  $msg = '无法解析域名';
        elseif ($errNo === 7)  $msg = '无法连接服务器';
        elseif ($errNo === 28) $msg = '连接超时';
        elseif ($errNo === 35) $msg = 'SSL/TLS 握手失败';
        elseif ($err) $msg = $err;
        return ['ok' => false, 'error' => $msg, 'code' => 0, 'body' => '', 'curl_errno' => $errNo];
    }
    if ($code === 401) return ['ok' => false, 'error' => '认证失败（401）', 'code' => $code, 'body' => $resp, 'curl_errno' => 0];
    if ($code === 403) return ['ok' => false, 'error' => '无权限（403）', 'code' => $code, 'body' => $resp, 'curl_errno' => 0];
    // 404 只对读取不存在资源和幂等删除是正常结果；PUT 的 404 必须视为失败。
    $allowNotFound = $code === 404 && in_array($method, ['GET', 'DELETE'], true);
    if ($code >= 400 && !$allowNotFound) return ['ok' => false, 'error' => 'HTTP ' . $code, 'code' => $code, 'body' => $resp, 'curl_errno' => 0];
    return ['ok' => true, 'code' => $code, 'body' => $resp, 'error' => '', 'curl_errno' => 0];
}

/**
 * WebDAV 请求（带自动重试）
 * 对临时性网络错误自动重试最多 2 次（共 3 次尝试）
 */
function webdavRequest($url, $method, $body, $user, $pass) {
    $maxRetries = 2;
    $retryableErrors = [6, 7, 28, 35]; // DNS、连接、超时、SSL 错误可重试
    $lastResult = null;

    for ($attempt = 0; $attempt <= $maxRetries; $attempt++) {
        $result = webdavRequestOnce($url, $method, $body, $user, $pass);

        // 成功或不可重试的错误，直接返回
        if ($result['ok'] || !in_array($result['curl_errno'] ?? 0, $retryableErrors)) {
            if ($attempt > 0) {
                wikiLog('INFO', "WebDAV {$method} 第 {$attempt} 次重试成功");
            }
            return $result;
        }

        $lastResult = $result;
        if ($attempt < $maxRetries) {
            wikiLog('WARN', "WebDAV {$method} 第 " . ($attempt + 1) . " 次尝试失败: {$result['error']}，准备重试...");
            sleep(1 * ($attempt + 1)); // 递增延迟: 1s, 2s
        }
    }

    // 所有重试都失败
    wikiLog('ERROR', "WebDAV {$method} 重试 {$maxRetries} 次后仍失败: {$lastResult['error']}");
    return $lastResult;
}

function webdavMkcol($url, $user, $pass) {
    $result = webdavRequest($url, 'MKCOL', null, $user, $pass);
    return ($result['ok'] || $result['code'] === 405);
}

/**
 * 列出 WebDAV 目录中的 wiki-*.json 文件
 */
function webdavListFiles($dirUrl, $user, $pass) {
    // 先尝试 PROPFIND（更可靠）
    $result = webdavRequest($dirUrl, 'PROPFIND', null, $user, $pass);
    if ($result['ok'] && $result['code'] >= 200 && $result['code'] < 300) {
        $body = $result['body'];
        $files = [];
        // 尝试多种 XML 格式：<d:href>, <D:href>, <href>, <ns1:href> 等
        if (preg_match_all('/<[^>:]*:href>[^<]*?(wiki-\d{8}_\d{6}\.json)<\/[^>:]*:href>/i', $body, $m)) {
            $files = $m[1];
        }
        if (empty($files) && preg_match_all('/<href>[^<]*?(wiki-\d{8}_\d{6}\.json)<\/href>/i', $body, $m)) {
            $files = $m[1];
        }
        // href="..." 属性格式
        if (empty($files) && preg_match_all('/href="[^"]*?(wiki-\d{8}_\d{6}\.json)"/i', $body, $m)) {
            $files = $m[1];
        }
        // 最后兜底：任何位置出现的文件名
        if (empty($files) && preg_match_all('/(wiki-\d{8}_\d{6}\.json)/', $body, $m)) {
            $files = $m[1];
        }
        if (empty($files) && !empty($body)) {
            wikiLog('WARN', 'PROPFIND 响应未匹配到文件名，响应片段: ' . substr($body, 0, 500));
        }
        return array_unique($files);
    }

    // 回退到 GET 目录列表
    $result = webdavRequest($dirUrl, 'GET', null, $user, $pass);
    if (!$result['ok']) {
        wikiLog('WARN', 'webdavListFiles 回退 GET 也失败: ' . ($result['error'] ?: 'HTTP ' . $result['code']));
        return [];
    }
    $files = [];
    if (preg_match_all('/href="[^"]*?(wiki-\d{8}_\d{6}\.json)"/i', $result['body'], $m)) {
        $files = $m[1];
    }
    if (empty($files) && preg_match_all('/(wiki-\d{8}_\d{6}\.json)/', $result['body'], $m)) {
        $files = $m[1];
    }
    return array_unique($files);
}

// ============================================================
//  Wiki 内容打包 / 解包
// ============================================================

function wikiNormalizeManagedPath($path) {
    if (!is_string($path) || $path === '' || strpos($path, "\0") !== false) return null;
    $path = str_replace('\\', '/', $path);
    if ($path[0] === '/' || preg_match('/^[A-Za-z]:/', $path)) return null;
    $segments = explode('/', $path);
    foreach ($segments as $segment) {
        if ($segment === '' || $segment === '.' || $segment === '..') return null;
    }
    return implode('/', $segments);
}

function wikiIsManagedBackupPath($path) {
    $path = wikiNormalizeManagedPath($path);
    if ($path === null) return false;
    if (preg_match('/\.md$/i', $path)) return true;
    if ($path === 'experiments/templates/templates.json') return true;
    return preg_match('#(^|/)comments/[^/]+\.json$#i', $path) === 1;
}

/**
 * 递归扫描 wiki/ 下需要备份的文件
 * 包含：.md、.zh.md、comments/*.json
 * 排除：.html、.php、.db、.log、.json（非 comments 目录）
 */
function scanWikiFiles($dir, $prefix = '') {
    $files = [];
    $items = @scandir($dir);
    if ($items === false) throw new RuntimeException('无法读取 Wiki 目录: ' . $dir);
    foreach ($items as $item) {
        if ($item === '.' || $item === '..') continue;
        $fullPath = $dir . '/' . $item;
        $relPath = $prefix ? $prefix . '/' . $item : $item;

        if (is_link($fullPath)) {
            continue;
        } elseif (is_dir($fullPath)) {
            // 跳过隐藏目录
            if ($item[0] === '.') continue;
            $files = array_merge($files, scanWikiFiles($fullPath, $relPath));
        } else {
            // 判断是否需要备份
            $ext = strtolower(pathinfo($item, PATHINFO_EXTENSION));
            if ($ext === 'md') {
                $files[$relPath] = $fullPath;
            } elseif ($ext === 'json' && wikiIsManagedBackupPath($relPath)) {
                $files[$relPath] = $fullPath;
            }
        }
    }
    return $files;
}

/**
 * 打包 wiki 内容为 JSON
 */
function exportWikiJson($wikiRoot) {
    $files = scanWikiFiles($wikiRoot);
    $data = ['files' => []];
    foreach ($files as $relPath => $fullPath) {
        $content = file_get_contents($fullPath);
        if ($content === false) throw new RuntimeException('无法读取 Wiki 文件: ' . $relPath);
        $data['files'][$relPath] = $content;
    }
    if (empty($data['files'])) throw new RuntimeException('Wiki 中没有可备份的文件');
    $payload = [
        'version'      => 2,
        'type'         => 'wiki-backup',
        'exportedAt'   => date('c'),
        'fileCount'    => count($data['files']),
        'files'        => $data['files'],
    ];
    $options = JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT;
    if (defined('JSON_INVALID_UTF8_SUBSTITUTE')) $options |= JSON_INVALID_UTF8_SUBSTITUTE;
    $json = json_encode($payload, $options);
    if ($json === false) {
        $message = function_exists('json_last_error_msg') ? json_last_error_msg() : ('错误码 ' . json_last_error());
        throw new RuntimeException('Wiki 备份 JSON 编码失败：' . $message . '。请将 Markdown 保存为 UTF-8。');
    }
    return $json;
}

/**
 * 从 JSON 恢复文件到 wiki/
 * 支持原子性恢复：先备份原文件，失败时可回滚
 */
function wikiPathHasSymlink($root, $relativePath) {
    $current = rtrim($root, '/\\');
    $segments = explode('/', $relativePath);
    foreach ($segments as $segment) {
        $current .= DIRECTORY_SEPARATOR . $segment;
        if (is_link($current)) return true;
    }
    return false;
}

function wikiEnsureParentDirectories($root, $relativePath, &$createdDirectories) {
    $directory = dirname($relativePath);
    if ($directory === '.' || $directory === '') return;
    $current = rtrim($root, '/\\');
    foreach (explode('/', $directory) as $segment) {
        $current .= DIRECTORY_SEPARATOR . $segment;
        if (is_link($current)) throw new RuntimeException('路径包含符号链接: ' . $relativePath);
        if (file_exists($current)) {
            if (!is_dir($current)) throw new RuntimeException('父路径不是目录: ' . $relativePath);
            continue;
        }
        if (!@mkdir($current, 0755)) throw new RuntimeException('无法创建目录: ' . $current);
        $createdDirectories[] = $current;
    }
}

function restoreWikiFiles($wikiRoot, $jsonStr) {
    $data = json_decode($jsonStr, true);
    if (!is_array($data)) {
        $jsonErr = function_exists('json_last_error_msg') ? json_last_error_msg() : ('错误码 ' . json_last_error());
        return ['ok' => false, 'error' => "JSON 解析失败: {$jsonErr}（文件可能已截断或损坏）"];
    }
    $backupVersion = (int)($data['version'] ?? 0);
    if (($data['type'] ?? '') !== 'wiki-backup' || !in_array($backupVersion, [1, 2], true) ||
        !isset($data['files']) || !is_array($data['files']) || empty($data['files'])) {
        return ['ok' => false, 'error' => '备份文件格式或版本无效'];
    }
    if (isset($data['fileCount']) && (int)$data['fileCount'] !== count($data['files'])) {
        return ['ok' => false, 'error' => '备份文件数量校验失败'];
    }

    $realRoot = realpath($wikiRoot);
    if ($realRoot === false || !is_writable($realRoot)) {
        return ['ok' => false, 'error' => 'Wiki 目录不存在或不可写'];
    }

    $incoming = [];
    foreach ($data['files'] as $relPath => $content) {
        $normalized = wikiNormalizeManagedPath($relPath);
        if ($normalized === null || !wikiIsManagedBackupPath($normalized) || !is_string($content)) {
            return ['ok' => false, 'error' => '备份包含不允许的路径或内容: ' . (string)$relPath];
        }
        if (wikiPathHasSymlink($realRoot, $normalized)) {
            return ['ok' => false, 'error' => '备份目标路径包含符号链接: ' . $normalized];
        }
        $incoming[$normalized] = $content;
    }

    // 镜像恢复：快照中不存在的受管文件也会删除，但同样先纳入回滚备份。
    $localFiles = scanWikiFiles($realRoot);
    $extraPaths = array_values(array_diff(array_keys($localFiles), array_keys($incoming)));
    // v1 快照尚未包含模板索引，恢复旧快照时不得误删当前模板配置。
    if ($backupVersion === 1 && !array_key_exists('experiments/templates/templates.json', $incoming)) {
        $extraPaths = array_values(array_diff($extraPaths, ['experiments/templates/templates.json']));
    }
    $affectedPaths = array_values(array_unique(array_merge(array_keys($incoming), $extraPaths)));
    $backupDir = $realRoot . DIRECTORY_SEPARATOR . '.restore-backup-' . date('YmdHis') . '-' . bin2hex(random_bytes(4));
    if (!@mkdir($backupDir, 0700)) {
        return ['ok' => false, 'error' => '无法创建恢复回滚目录，已中止且未修改文件'];
    }

    $backups = [];
    $createdFiles = [];
    $createdDirectories = [];
    $restored = 0;
    $removed = 0;

    try {
        // 在任何覆盖或删除前，先完整备份所有现有目标。
        foreach ($affectedPaths as $relPath) {
            $fullPath = $realRoot . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relPath);
            if (!file_exists($fullPath)) continue;
            $backupPath = $backupDir . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relPath);
            $dummyDirectories = [];
            wikiEnsureParentDirectories($backupDir, $relPath, $dummyDirectories);
            if (!@copy($fullPath, $backupPath)) throw new RuntimeException('无法创建文件回滚副本: ' . $relPath);
            $backups[$relPath] = $backupPath;
        }

        foreach ($incoming as $relPath => $content) {
            $fullPath = $realRoot . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relPath);
            if (is_link($fullPath)) throw new RuntimeException('拒绝写入符号链接: ' . $relPath);
            $existed = file_exists($fullPath);
            wikiEnsureParentDirectories($realRoot, $relPath, $createdDirectories);
            if (@file_put_contents($fullPath, $content, LOCK_EX) === false) {
                throw new RuntimeException('写入失败: ' . $relPath);
            }
            if (!$existed) $createdFiles[] = $fullPath;
            $restored++;
        }

        foreach ($extraPaths as $relPath) {
            $fullPath = $realRoot . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relPath);
            if (file_exists($fullPath) && !@unlink($fullPath)) throw new RuntimeException('删除旧文件失败: ' . $relPath);
            if (!file_exists($fullPath)) $removed++;
        }
    } catch (Throwable $e) {
        foreach ($createdFiles as $createdFile) {
            if (file_exists($createdFile)) @unlink($createdFile);
        }
        foreach ($backups as $relPath => $backupPath) {
            $originalPath = $realRoot . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relPath);
            @copy($backupPath, $originalPath);
        }
        usort($createdDirectories, function($a, $b) { return strlen($b) <=> strlen($a); });
        foreach ($createdDirectories as $directory) {
            if (is_dir($directory)) @rmdir($directory);
        }
        recursiveDelete($backupDir);
        wikiLog('ERROR', '恢复失败并已回滚: ' . $e->getMessage());
        return [
            'ok' => false,
            'error' => '恢复失败，所有修改已回滚: ' . $e->getMessage(),
            'restored' => 0,
            'removed' => 0,
            'total' => count($incoming)
        ];
    }

    recursiveDelete($backupDir);
    return [
        'ok' => true,
        'restored' => $restored,
        'removed' => $removed,
        'total' => count($incoming),
        'errors' => []
    ];
}

// ============================================================
//  Markdown 文档自动发现（仅供 action=documents 使用）
// ============================================================

/**
 * 解析 Markdown 顶部的简易 YAML Front Matter。
 * 无需额外安装 YAML 扩展，支持本系统使用的单行键值元数据。
 */
function wikiDocsParseFrontMatter($content) {
    $meta = [];
    if (!preg_match('/\A---\s*\R(.*?)\R---\s*(?:\R|\z)/s', $content, $match)) {
        return $meta;
    }

    $lines = preg_split('/\R/', $match[1]);
    if ($lines === false) return $meta;

    foreach ($lines as $line) {
        if (!preg_match('/^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$/', trim($line), $parts)) {
            continue;
        }
        $value = trim($parts[2]);
        if (strlen($value) >= 2) {
            $first = $value[0];
            $last = $value[strlen($value) - 1];
            if (($first === '"' && $last === '"') || ($first === "'" && $last === "'")) {
                $value = substr($value, 1, -1);
            }
        }
        $meta[strtolower($parts[1])] = $value;
    }
    return $meta;
}

function wikiDocsStripFrontMatter($content) {
    $result = preg_replace('/\A---\s*\R.*?\R---\s*(?:\R|\z)/s', '', $content, 1);
    return $result === null ? $content : $result;
}

function wikiDocsCleanMarkdownText($text) {
    $result = preg_replace('/!\[([^\]]*)\]\([^)]*\)/', '$1', $text);
    if ($result !== null) $text = $result;
    $result = preg_replace('/\[([^\]]+)\]\([^)]*\)/', '$1', $text);
    if ($result !== null) $text = $result;
    $result = preg_replace('/[`*_~>#|]/', '', $text);
    if ($result !== null) $text = $result;
    $result = preg_replace('/\s+/u', ' ', trim($text));
    return $result === null ? trim($text) : $result;
}

function wikiDocsNormalizeUtf8($content, &$encodingIssue) {
    $encodingIssue = false;
    $content = preg_replace('/^\xEF\xBB\xBF/', '', $content) ?? $content;
    if (preg_match('//u', $content) === 1) return $content;

    $encodingIssue = true;
    $utf8Only = function_exists('iconv') ? @iconv('UTF-8', 'UTF-8//IGNORE', $content) : false;
    $retainedRatio = ($utf8Only !== false && strlen($content) > 0) ? strlen($utf8Only) / strlen($content) : 0;

    // 大部分字节都不是 UTF-8 时，才按旧中文编码转换；少量坏字节视为混合损坏，
    // 避免把原本正确的 UTF-8 中文再次错误转码。
    if ($retainedRatio < 0.75) {
        $legacyEncodings = ['GB18030', 'GBK', 'BIG-5'];
        foreach ($legacyEncodings as $encoding) {
            $converted = false;
            if (function_exists('mb_convert_encoding')) {
                $converted = @mb_convert_encoding($content, 'UTF-8', $encoding);
            } elseif (function_exists('iconv')) {
                $converted = @iconv($encoding, 'UTF-8//IGNORE', $content);
            }
            if (is_string($converted) && $converted !== '' && preg_match('//u', $converted) === 1) {
                $encodingIssue = false;
                return $converted;
            }
        }
    }

    if (is_string($utf8Only)) return $utf8Only;
    // 极少数没有 iconv/mbstring 的环境：保留 ASCII，摘要随后会显示编码提示。
    return preg_replace('/[^\x00-\x7F]/', '', $content) ?? '';
}

function wikiDocsUnicodeLength($value) {
    if (function_exists('mb_strlen')) {
        return mb_strlen($value, 'UTF-8');
    }
    $count = preg_match_all('/./us', $value, $matches);
    return $count === false ? strlen($value) : $count;
}

function wikiDocsUnicodeSubstring($value, $start, $length) {
    if (function_exists('mb_substr')) {
        return mb_substr($value, $start, $length, 'UTF-8');
    }
    $characters = preg_split('//u', $value, -1, PREG_SPLIT_NO_EMPTY);
    if ($characters === false) {
        return substr($value, $start, $length);
    }
    return implode('', array_slice($characters, $start, $length));
}

function wikiDocsUnicodeLower($value) {
    return function_exists('mb_strtolower') ? mb_strtolower($value, 'UTF-8') : strtolower($value);
}

function wikiDocsUnicodeContains($haystack, $needle) {
    if (function_exists('mb_strpos')) {
        return mb_strpos($haystack, $needle, 0, 'UTF-8') !== false;
    }
    return strpos($haystack, $needle) !== false;
}

function wikiDocsBoolValue($value) {
    return in_array(strtolower(trim((string)$value)), ['1', 'true', 'yes', 'on'], true);
}

function wikiDocsDetectLanguage($body, $meta) {
    $declared = strtolower(trim((string)($meta['lang'] ?? ($meta['language'] ?? ''))));
    if (in_array($declared, ['zh', 'zh-cn', 'zh-hans', 'cn', 'chinese'], true)) return 'zh';
    if (in_array($declared, ['en', 'en-us', 'en-gb', 'english'], true)) return 'en';

    // 忽略代码块后比较正文中的中英文字符，避免 Python/命令示例干扰判断。
    $sample = preg_replace('/```[\s\S]*?```|~~~[\s\S]*?~~~/u', ' ', $body);
    if ($sample === null) $sample = $body;
    $cjk = preg_match_all('/[\x{3400}-\x{4DBF}\x{4E00}-\x{9FFF}]/u', $sample, $unused);
    $latin = preg_match_all('/[A-Za-z]/', $sample, $unusedLatin);
    $cjk = $cjk === false ? 0 : $cjk;
    $latin = $latin === false ? 0 : $latin;
    return ($cjk >= 4 && ($latin === 0 || ($cjk / max(1, $latin)) >= 0.08)) ? 'zh' : 'en';
}

function wikiDocsDefaultIcon($title, $page) {
    $haystack = wikiDocsUnicodeLower($title . ' ' . $page);
    $map = [
        'git' => '🔧', 'python' => '🐍', '数据' => '📊', 'data' => '📊',
        '光合' => '🌿', 'par' => '☀️', 'lai' => '🍃', '冠层' => '🌳',
        '实验' => '🧪', '指南' => '📘', '教程' => '📘', 'manual' => '📘'
    ];
    foreach ($map as $needle => $icon) {
        if (wikiDocsUnicodeContains($haystack, $needle)) {
            return $icon;
        }
    }
    return '📄';
}

/**
 * 提取标题、摘要和 Front Matter。
 * 为避免大文件占用过多内存，最多读取前 128 KiB。
 */
function wikiDocsInspectMarkdown($path, $fallbackTitle) {
    $handle = @fopen($path, 'rb');
    $content = $handle ? (string)fread($handle, 131072) : '';
    if (is_resource($handle)) fclose($handle);

    $encodingIssue = false;
    $content = wikiDocsNormalizeUtf8($content, $encodingIssue);
    $meta = wikiDocsParseFrontMatter($content);
    $body = wikiDocsStripFrontMatter($content);

    $title = trim($meta['title'] ?? '');
    if ($title === '' && preg_match('/^#\s+(.+)$/mu', $body, $match)) {
        $title = wikiDocsCleanMarkdownText($match[1]);
    }
    if ($title === '') {
        $title = str_replace(['-', '_'], ' ', $fallbackTitle);
    }

    $description = trim($meta['description'] ?? ($meta['summary'] ?? ($meta['desc'] ?? '')));
    // 优先使用开头引用块中明确标注的摘要字段。这样没有 Front Matter 的新文档
    // 也能得到干净摘要，而不会把“推荐叶室、版本、注意事项”等多行元数据拼在一起。
    if ($description === '' && preg_match('/^>\s*\*\*(?:适用对象|摘要|简介|概述|用途|Purpose|Summary|Introduction)\*\*\s*[:：]\s*(.+)$/miu', $body, $summaryMatch)) {
        $description = wikiDocsCleanMarkdownText($summaryMatch[1]);
    }
    if ($description === '') {
        $lines = preg_split('/\R/', $body);
        if ($lines === false) $lines = [];
        $paragraph = [];
        $insideFence = false;
        foreach ($lines as $line) {
            $trimmed = trim($line);
            if (preg_match('/^(```|~~~)/', $trimmed)) {
                $insideFence = !$insideFence;
                continue;
            }
            if ($insideFence || $trimmed === '' || preg_match('/^(#{1,6}\s|[-*+]\s|\d+\.\s|<!--|\||[-*_]{3,}\s*$)/', $trimmed)) {
                if (!empty($paragraph)) break;
                continue;
            }
            // 文档常把 Purpose / 适用对象写在开头引用块中；它正适合作为卡片摘要。
            $trimmed = preg_replace('/^>\s*/', '', $trimmed) ?? $trimmed;
            $paragraph[] = $trimmed;
            if (wikiDocsUnicodeLength(implode(' ', $paragraph)) >= 120) break;
        }
        $description = wikiDocsCleanMarkdownText(implode(' ', $paragraph));
    }
    if (wikiDocsUnicodeLength($description) > 140) {
        $description = wikiDocsUnicodeSubstring($description, 0, 137) . '…';
    }
    if ($description === '') $description = 'Markdown 文档';

    return [
        'meta' => $meta,
        'title' => $title,
        'description' => $description,
        'language' => wikiDocsDetectLanguage($body, $meta),
        'encoding_warning' => $encodingIssue
    ];
}

/**
 * 扫描 wiki 根目录及普通子目录中的 Markdown 文件，并合并语言版本。
 * Example.md / Example.zh.md / Example.en.md 会作为同一页面返回。
 * 同时兼容用户上传时常见的 Example_zh.md、Example-en.md 等命名。
 */
function wikiDocsDiscover($root) {
    $realRoot = realpath($root);
    if ($realRoot === false) {
        return ['ok' => false, 'error' => '无法确定文档目录'];
    }

    $excludedDirectories = [
        '.git', '.github', '.idea', '.vscode',
        'vendor', 'node_modules', 'experiments',
        'backup', 'backups', 'backu', 'cache', 'tmp'
    ];
    $documents = [];

    try {
        $directory = new RecursiveDirectoryIterator($realRoot, FilesystemIterator::SKIP_DOTS);
        $filter = new RecursiveCallbackFilterIterator(
            $directory,
            function($current) use ($excludedDirectories) {
                $name = $current->getFilename();
                if ($current->isDir()) {
                    return !in_array($name, $excludedDirectories, true) && substr($name, 0, 1) !== '.';
                }
                return !$current->isLink();
            }
        );
        $iterator = new RecursiveIteratorIterator($filter);
    } catch (Exception $e) {
        return ['ok' => false, 'error' => '无法扫描文档目录: ' . $e->getMessage()];
    }

    foreach ($iterator as $file) {
        if (!($file instanceof SplFileInfo) || !$file->isFile()) continue;

        $filename = $file->getFilename();
        if (substr($filename, 0, 1) === '.' || substr($filename, 0, 1) === '_') continue;
        if (!preg_match('/\.md$/i', $filename)) continue;

        $absolute = $file->getRealPath();
        if ($absolute === false || strpos($absolute, $realRoot . DIRECTORY_SEPARATOR) !== 0) continue;

        $relative = str_replace(DIRECTORY_SEPARATOR, '/', substr($absolute, strlen($realRoot) + 1));
        $relativeWithoutExtension = preg_replace('/\.md$/i', '', $relative) ?? $relative;
        $language = null;
        $explicitLanguage = false;
        $page = $relativeWithoutExtension;
        // 支持点号、下划线和连字符三种语言后缀，上传后无需重命名：
        // Example.zh.md / Example_zh.md / Example-zh.md（英文同理）。
        if (preg_match('/(?:\.|_|-)(zh(?:-cn)?|en)$/i', $relativeWithoutExtension, $languageMatch)) {
            $language = stripos($languageMatch[1], 'zh') === 0 ? 'zh' : 'en';
            $explicitLanguage = true;
            $page = substr($relativeWithoutExtension, 0, -strlen($languageMatch[0]));
        }

        // 与 viewer.html 的路径安全规则保持一致。
        $segments = explode('/', $page);
        $unsafe = $page === '' || strpos($page, '\\') !== false || preg_match('/[\x00-\x1F<>:"|?*#]/u', $page);
        foreach ($segments as $segment) {
            if ($segment === '' || $segment === '.' || $segment === '..') {
                $unsafe = true;
                break;
            }
        }
        if ($unsafe) continue;

        $info = wikiDocsInspectMarkdown($absolute, basename($page));
        if (wikiDocsBoolValue($info['meta']['hidden'] ?? null)) continue;
        if ($language === null) $language = $info['language'];

        if (!isset($documents[$page])) {
            $documents[$page] = ['page' => $page, 'versions' => [], 'mtime' => 0];
        }
        // 显式语言后缀优先于内容推断出的同语言 .md。
        if (isset($documents[$page]['versions'][$language]) &&
            !empty($documents[$page]['versions'][$language]['explicit']) && !$explicitLanguage) {
            continue;
        }
        $documents[$page]['versions'][$language] = [
            'path' => $relative,
            'meta' => $info['meta'],
            'title' => $info['title'],
            'description' => $info['description'],
            'encoding_warning' => $info['encoding_warning'],
            'explicit' => $explicitLanguage,
            'mtime' => $file->getMTime()
        ];
        $documents[$page]['mtime'] = max($documents[$page]['mtime'], $file->getMTime());
    }

    $result = [];
    foreach ($documents as $page => $document) {
        $versions = $document['versions'];
        $primary = $versions['zh'] ?? ($versions['en'] ?? null);
        if ($primary === null) continue;

        $meta = $primary['meta'];
        $folder = dirname($page);
        $defaultCategory = ($folder === '.' || $folder === '')
            ? '学习文档'
            : str_replace(['-', '_', '/'], [' ', ' ', ' · '], $folder);

        $title = trim((string)($meta['title'] ?? $primary['title']));
        $description = trim((string)($meta['description'] ?? ($meta['summary'] ?? ($meta['desc'] ?? $primary['description']))));
        $category = trim((string)($meta['category'] ?? $defaultCategory));
        $icon = trim((string)($meta['icon'] ?? ''));
        $tag = trim((string)($meta['tag'] ?? ''));
        $order = is_numeric($meta['order'] ?? null) ? (int)$meta['order'] : 9999;

        $languages = [];
        $versionPaths = [];
        $titles = [];
        $descriptions = [];
        $encodingWarnings = [];
        foreach (['zh', 'en'] as $versionLanguage) {
            if (!isset($versions[$versionLanguage])) continue;
            $languages[] = $versionLanguage;
            $versionPaths[$versionLanguage] = $versions[$versionLanguage]['path'];
            $titles[$versionLanguage] = $versions[$versionLanguage]['title'];
            $descriptions[$versionLanguage] = $versions[$versionLanguage]['description'];
            if (!empty($versions[$versionLanguage]['encoding_warning'])) $encodingWarnings[] = $versionLanguage;
        }

        $result[] = [
            'page' => $page,
            'title' => $title,
            'description' => $description,
            'category' => $category !== '' ? $category : '学习文档',
            'icon' => $icon !== '' ? $icon : wikiDocsDefaultIcon($title, $page),
            'tag' => $tag,
            'order' => $order,
            'languages' => $languages,
            'versions' => $versionPaths,
            'titles' => $titles,
            'descriptions' => $descriptions,
            'encoding_warnings' => $encodingWarnings,
            'modified_at' => gmdate('c', (int)$document['mtime'])
        ];
    }

    usort($result, function($a, $b) {
        $category = strnatcasecmp($a['category'], $b['category']);
        if ($category !== 0) return $category;
        if ($a['order'] !== $b['order']) return $a['order'] <=> $b['order'];
        return strnatcasecmp($a['title'], $b['title']);
    });

    return [
        'ok' => true,
        'documents' => $result,
        'count' => count($result),
        'generated_at' => gmdate('c')
    ];
}

// ============================================================
//  路由
// ============================================================

// 文档索引保持公开；所有涉及本地状态或 WebDAV 的操作均要求主账号会话。
if ($action !== 'documents') wikiRequireMasterAuth();
$syncMutationLock = null;
if (in_array($action, ['backup', 'restore', 'restore-version', 'set-max-versions'], true)) {
    wikiRequirePostMethod();
    $syncMutationLock = wikiAcquireSyncMutationLock();
}

switch ($action) {

    // ── 自动扫描 Markdown 文档 ──
    // 独立 action，不改变任何原有备份/恢复接口及其返回结构。
    case 'documents':
        header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
        header('X-Content-Type-Options: nosniff');
        jsonResponse(wikiDocsDiscover($wikiRoot));
        break;

    // ── WebDAV 状态 ──
    case 'status':
        $config = getWebdavConfig();
        if (!$config) {
            jsonResponse(['ok' => false, 'configured' => false, 'error' => '无法读取 vault 数据库，请先配置凭证保险箱的 WebDAV']);
        }
        $hasConfig = !empty($config['url']) && !empty($config['username']);
        jsonResponse([
            'ok'           => true,
            'configured'   => $hasConfig,
            'url'          => $config['url'] ? preg_replace('/\/\/[^@]+@/', '//***@', $config['url']) : '',
            'username'     => $config['username'],
            'max_versions' => getMaxVersions(),
            'last_sync'    => getLastSyncTime(),
        ]);
        break;

    // ── 版本列表 ──
    case 'versions':
        $config = getWebdavConfig();
        if (!$config || empty($config['url'])) {
            jsonResponse(['ok' => true, 'versions' => []]);
        }
        $backupUrl = getWikiBackupUrl($config);
        $files = webdavListFiles($backupUrl, $config['username'], $config['password']);
        rsort($files);
        $versions = [];
        foreach ($files as $name) {
            $ts = substr($name, 5, 15); // YYYYMMDD_HHMMSS
            $dt = DateTime::createFromFormat('Ymd_His', $ts);
            $versions[] = [
                'name' => $name,
                'time' => $dt ? $dt->format('c') : $ts,
            ];
        }
        jsonResponse(['ok' => true, 'versions' => $versions, 'max_versions' => getMaxVersions()]);
        break;

    // ── 上次同步时间 ──
    case 'last-sync':
        jsonResponse(['ok' => true, 'time' => getLastSyncTime()]);
        break;

    // ── 云端最新版本（快速查询，不下载完整数据）──
    case 'cloud-latest':
        $config = getWebdavConfig();
        if (!$config || empty($config['url'])) {
            jsonResponse(['ok' => true, 'configured' => false]);
        }
        $backupUrl = getWikiBackupUrl($config);
        $files = webdavListFiles($backupUrl, $config['username'], $config['password']);
        if (empty($files)) {
            jsonResponse(['ok' => true, 'configured' => true, 'latest' => null, 'time' => null]);
        }
        rsort($files);
        $latest = $files[0];
        $time = null;
        if (preg_match('/wiki-(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json/', $latest, $m)) {
            $time = $m[1] . '-' . $m[2] . '-' . $m[3] . 'T' . $m[4] . ':' . $m[5] . ':' . $m[6];
        }
        jsonResponse(['ok' => true, 'configured' => true, 'latest' => $latest, 'time' => $time]);
        break;

    // ── 检查本地是否有未同步的变更 ──
    case 'check-local':
        $lastSync = getLastSyncTime();
        $lastSyncTs = $lastSync ? strtotime($lastSync) : 0;
        // 扫描所有 wiki 文件，找到最新修改时间
        $wikiFiles = scanWikiFiles($wikiRoot);
        $latestMtime = 0;
        $changedFiles = [];
        foreach ($wikiFiles as $relPath => $fullPath) {
            $mtime = filemtime($fullPath);
            if ($mtime > $latestMtime) {
                $latestMtime = $mtime;
            }
            // 收集在 last_sync 之后修改的文件（留 2 秒宽容度，防止 restore 时文件写入与 saveLastSyncTime 的时序偏差）
            if ($mtime > $lastSyncTs + 2) {
                $changedFiles[] = $relPath;
            }
        }
        $hasChanges = $latestMtime > 0 && ($lastSyncTs === 0 || $latestMtime > $lastSyncTs + 2);
        jsonResponse([
            'ok'            => true,
            'last_sync'     => $lastSync,
            'last_modified' => $latestMtime > 0 ? date('c', $latestMtime) : null,
            'has_changes'   => $hasChanges,
            'changed_count' => count($changedFiles),
            // 只返回前 10 个变更文件，避免响应过大
            'changed_files' => array_slice($changedFiles, 0, 10),
        ]);
        break;

    // ── 云端综合状态（供前端一键获取）──
    case 'cloud-status':
        $config = getWebdavConfig();
        $configured = $config && !empty($config['url']) && !empty($config['username']);
        $lastSync = getLastSyncTime();
        $cloudTime = null;
        $cloudLatest = null;
        $versionCount = 0;

        if ($configured) {
            $backupUrl = getWikiBackupUrl($config);
            $files = webdavListFiles($backupUrl, $config['username'], $config['password']);
            if (!empty($files)) {
                rsort($files);
                $versionCount = count($files);
                $cloudLatest = $files[0];
                if (preg_match('/wiki-(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json/', $cloudLatest, $m)) {
                    $cloudTime = $m[1] . '-' . $m[2] . '-' . $m[3] . 'T' . $m[4] . ':' . $m[5] . ':' . $m[6];
                }
            }
        }

        // 检查本地变更
        $lastSyncTs = $lastSync ? strtotime($lastSync) : 0;
        $wikiFiles = scanWikiFiles($wikiRoot);
        $latestMtime = 0;
        foreach ($wikiFiles as $fullPath) {
            $mtime = filemtime($fullPath);
            if ($mtime > $latestMtime) $latestMtime = $mtime;
        }
        $hasLocalChanges = $latestMtime > 0 && ($lastSyncTs === 0 || $latestMtime > $lastSyncTs + 2);

        // 判断云端是否比本地新
        $cloudIsNewer = false;
        if ($cloudTime && $lastSyncTs > 0) {
            $cloudTs = strtotime($cloudTime);
            $cloudIsNewer = $cloudTs > $lastSyncTs;
        }

        jsonResponse([
            'ok'              => true,
            'configured'      => $configured,
            'last_sync'       => $lastSync,
            'cloud_time'      => $cloudTime,
            'cloud_latest'    => $cloudLatest,
            'cloud_versions'  => $versionCount,
            'has_local_changes' => $hasLocalChanges,
            'cloud_is_newer'  => $cloudIsNewer,
            'local_last_modified' => $latestMtime > 0 ? date('c', $latestMtime) : null,
            'max_versions'    => getMaxVersions(),
            'username'        => $configured ? $config['username'] : null,
        ]);
        break;

    // ── 备份上传 ──
    case 'backup':
        $config = getWebdavConfig();
        if (!$config || empty($config['url'])) {
            jsonResponse(['ok' => false, 'error' => '请先在凭证保险箱中配置 WebDAV']);
        }

        $backupUrl = getWikiBackupUrl($config);

        // 确保目录存在
        if (!webdavMkcol($backupUrl, $config['username'], $config['password'])) {
            jsonResponse(['ok' => false, 'error' => '无法创建 WebDAV 备份目录']);
        }

        // 打包
        try {
            $json = exportWikiJson($wikiRoot);
        } catch (Throwable $e) {
            http_response_code(422);
            jsonResponse(['ok' => false, 'error' => $e->getMessage()]);
        }
        $ts = date('Ymd_His');
        $fileName = 'wiki-' . $ts . '.json';
        $fileUrl = $backupUrl . $fileName;

        wikiLog('INFO', "备份上传: {$fileName}, " . strlen($json) . " bytes");

        // 上传
        $result = webdavRequest($fileUrl, 'PUT', $json, $config['username'], $config['password']);
        if (!$result['ok']) {
            wikiLog('ERROR', "上传失败: " . $result['error']);
            jsonResponse(['ok' => false, 'error' => '上传失败: ' . $result['error']]);
        }

        // 验证上传完整性：GET 请求检查文件是否存在且大小匹配
        $expectedSize = strlen($json);
        $verify = webdavRequest($fileUrl, 'GET', null, $config['username'], $config['password']);
        if (!$verify['ok'] || ($verify['code'] ?? 0) >= 400) {
            webdavRequest($fileUrl, 'DELETE', null, $config['username'], $config['password']);
            wikiLog('ERROR', "上传后验证失败：无法读取已上传文件");
            jsonResponse(['ok' => false, 'error' => '上传后无法读取云端文件，未记录为同步成功']);
        } else {
            $actualSize = strlen($verify['body']);
            if ($actualSize !== $expectedSize) {
                webdavRequest($fileUrl, 'DELETE', null, $config['username'], $config['password']);
                wikiLog('ERROR', "上传后验证失败：文件大小不匹配 (期望 {$expectedSize}, 实际 {$actualSize})");
                jsonResponse(['ok' => false, 'error' => "上传验证失败：文件大小不匹配 (期望 {$expectedSize} 字节, 实际 {$actualSize} 字节)"]);
            }
            $verifyJson = json_decode($verify['body'], true);
            if (!is_array($verifyJson) || ($verifyJson['type'] ?? '') !== 'wiki-backup' ||
                (int)($verifyJson['version'] ?? 0) !== 2 || !isset($verifyJson['files']) ||
                !hash_equals(hash('sha256', $json), hash('sha256', $verify['body']))) {
                webdavRequest($fileUrl, 'DELETE', null, $config['username'], $config['password']);
                wikiLog('ERROR', "上传后验证失败：服务器上的文件 JSON 格式损坏");
                jsonResponse(['ok' => false, 'error' => '上传验证失败：服务器上的备份文件损坏']);
            }
            wikiLog('INFO', "上传验证通过: {$fileName}, {$actualSize} bytes");
        }

        // 清理旧版本
        $maxVersions = getMaxVersions();
        $files = webdavListFiles($backupUrl, $config['username'], $config['password']);
        rsort($files);
        $deleted = [];
        $cleanupErrors = [];
        if (count($files) > $maxVersions) {
            foreach (array_slice($files, $maxVersions) as $old) {
                $deleteResult = webdavRequest($backupUrl . $old, 'DELETE', null, $config['username'], $config['password']);
                if ($deleteResult['ok']) {
                    $deleted[] = $old;
                    wikiLog('INFO', "清理旧版本: {$old}");
                } else {
                    $cleanupErrors[] = $old;
                    wikiLog('WARN', "旧版本删除失败: {$old} ({$deleteResult['error']})");
                }
            }
        }

        $syncSaved = saveLastSyncTime();

        $resp = [
            'ok'       => true,
            'msg'      => '已上传: ' . $fileName,
            'file'     => $fileName,
            'size'     => strlen($json),
            'deleted'  => $deleted,
            'time'     => date('c'),
        ];
        if (!$syncSaved) {
            $resp['warning'] = '备份已上传，但本地同步记录保存失败（文件权限不足）';
        }
        if (!empty($cleanupErrors)) {
            $cleanupWarning = '有 ' . count($cleanupErrors) . ' 个旧版本清理失败';
            $resp['warning'] = isset($resp['warning']) ? ($resp['warning'] . '；' . $cleanupWarning) : $cleanupWarning;
            $resp['cleanup_failed'] = $cleanupErrors;
        }
        jsonResponse($resp);
        break;

    // ── 从最新版本恢复 ──
    case 'restore':
        $config = getWebdavConfig();
        if (!$config || empty($config['url'])) {
            jsonResponse(['ok' => false, 'error' => '请先在凭证保险箱中配置 WebDAV']);
        }

        $backupUrl = getWikiBackupUrl($config);
        $files = webdavListFiles($backupUrl, $config['username'], $config['password']);
        if (empty($files)) {
            jsonResponse(['ok' => false, 'error' => 'WebDAV 上没有备份文件']);
        }
        rsort($files);
        $latest = $files[0];
        $fileUrl = $backupUrl . $latest;

        wikiLog('INFO', "恢复最新版本: {$latest}");

        $result = webdavRequest($fileUrl, 'GET', null, $config['username'], $config['password']);
        if (!$result['ok'] || $result['code'] >= 400) {
            jsonResponse(['ok' => false, 'error' => '下载失败: ' . ($result['error'] ?: 'HTTP ' . $result['code'])]);
        }

        // 下载完整性检查
        if (empty($result['body'])) {
            wikiLog('ERROR', "下载失败：响应内容为空");
            jsonResponse(['ok' => false, 'error' => '下载失败：服务器返回空内容']);
        }
        wikiLog('INFO', "下载完成: {$latest}, " . strlen($result['body']) . " bytes");

        $restoreResult = restoreWikiFiles($wikiRoot, $result['body']);
        $restoreResult['version'] = $latest;
        // 从文件名提取版本时间
        if (preg_match('/wiki-(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json/', $latest, $m)) {
            $restoreResult['time'] = $m[1] . '-' . $m[2] . '-' . $m[3] . 'T' . $m[4] . ':' . $m[5] . ':' . $m[6];
        }
        if (!empty($restoreResult['ok'])) {
            $syncSaved = saveLastSyncTime();
            if (!$syncSaved) {
                $restoreResult['warning'] = '文件已恢复，但本地同步记录保存失败（文件权限不足）';
            }
        }
        jsonResponse($restoreResult);
        break;

    // ── 恢复指定版本 ──
    case 'restore-version':
        $input = jsonInput();
        $name = $input['name'] ?? '';
        if (!$name || !preg_match('/^wiki-\d{8}_\d{6}\.json$/', $name)) {
            jsonResponse(['ok' => false, 'error' => '无效的版本文件名']);
        }

        $config = getWebdavConfig();
        if (!$config || empty($config['url'])) {
            jsonResponse(['ok' => false, 'error' => '请先在凭证保险箱中配置 WebDAV']);
        }

        $backupUrl = getWikiBackupUrl($config);
        $fileUrl = $backupUrl . $name;

        wikiLog('INFO', "恢复指定版本: {$name}");

        $result = webdavRequest($fileUrl, 'GET', null, $config['username'], $config['password']);
        if (!$result['ok'] || $result['code'] >= 400) {
            jsonResponse(['ok' => false, 'error' => '下载失败: ' . ($result['error'] ?: 'HTTP ' . $result['code'])]);
        }

        // 下载完整性检查
        if (empty($result['body'])) {
            wikiLog('ERROR', "下载失败：响应内容为空");
            jsonResponse(['ok' => false, 'error' => '下载失败：服务器返回空内容']);
        }
        wikiLog('INFO', "下载完成: {$name}, " . strlen($result['body']) . " bytes");

        $restoreResult = restoreWikiFiles($wikiRoot, $result['body']);
        $restoreResult['version'] = $name;
        // 从文件名提取版本时间
        if (preg_match('/wiki-(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json/', $name, $m)) {
            $restoreResult['time'] = $m[1] . '-' . $m[2] . '-' . $m[3] . 'T' . $m[4] . ':' . $m[5] . ':' . $m[6];
        }
        if (!empty($restoreResult['ok'])) {
            $syncSaved2 = saveLastSyncTime();
            if (!$syncSaved2) {
                $restoreResult['warning'] = '文件已恢复，但本地同步记录保存失败（文件权限不足）';
            }
        }
        jsonResponse($restoreResult);
    case 'set-max-versions':
        $input = jsonInput();
        $n = (int)($input['max_versions'] ?? 20);
        if ($n < 1 || $n > 100) {
            jsonResponse(['ok' => false, 'error' => '版本数需在 1-100 之间']);
        }
        $oldMax = getMaxVersions();
        // 如果减少了版本数，立即清理多余版本
        $deleted = [];
        $settingsSaved = false;
        if ($n < $oldMax) {
            $config = getWebdavConfig();
            if ($config && !empty($config['url'])) {
                $backupUrl = getWikiBackupUrl($config);
                $files = webdavListFiles($backupUrl, $config['username'], $config['password']);
                rsort($files);
                if (count($files) > $n) {
                    $toDelete = array_slice($files, $n);
                    $confirm = $input['confirm_delete'] ?? false;
                    if (!$confirm) {
                        // 返回需要删除的列表，让前端确认
                        jsonResponse([
                            'ok'              => true,
                            'max_versions'    => $n,
                            'previous_max'    => $oldMax,
                            'needs_confirm'   => true,
                            'current_count'   => count($files),
                            'will_delete'     => $toDelete,
                            'msg'             => "当前有 " . count($files) . " 个版本，设置保留 {$n} 个将删除 " . count($toDelete) . " 个旧版本",
                        ]);
                    }
                    if (!saveMaxVersions($n)) {
                        http_response_code(500);
                        jsonResponse(['ok' => false, 'error' => '版本设置保存失败，未删除任何云端版本']);
                    }
                    $settingsSaved = true;
                    $failedDeletes = [];
                    foreach ($toDelete as $old) {
                        $deleteResult = webdavRequest($backupUrl . $old, 'DELETE', null, $config['username'], $config['password']);
                        if ($deleteResult['ok']) {
                            $deleted[] = $old;
                            wikiLog('INFO', "版本数变更清理: {$old}");
                        } else {
                            $failedDeletes[] = $old;
                            wikiLog('WARN', "版本数变更清理失败: {$old}");
                        }
                    }
                }
            }
        }

        if (!$settingsSaved && !saveMaxVersions($n)) {
            http_response_code(500);
            jsonResponse(['ok' => false, 'error' => '版本设置保存失败，请检查 Wiki 目录权限']);
        }
        $versionResponse = [
            'ok'           => true,
            'max_versions' => $n,
            'deleted'      => $deleted,
            'msg'          => "版本数已设置为 {$n}" . ($deleted ? "，已删除 " . count($deleted) . " 个旧版本" : ""),
        ];
        if (!empty($failedDeletes ?? [])) {
            $versionResponse['warning'] = '有 ' . count($failedDeletes) . ' 个旧版本删除失败';
            $versionResponse['cleanup_failed'] = $failedDeletes;
        }
        jsonResponse($versionResponse);
        break;

    default:
        http_response_code(400);
        jsonResponse(['error' => '未知操作: ' . $action]);
}
