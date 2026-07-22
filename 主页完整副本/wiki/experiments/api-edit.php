<?php
/**
 * 实验记录编辑 API
 */

// PHP 7.x 兼容：str_starts_with / str_ends_with polyfill
if (!function_exists('str_starts_with')) {
    function str_starts_with(string $haystack, string $needle): bool {
        return strncmp($haystack, $needle, strlen($needle)) === 0;
    }
}
if (!function_exists('str_ends_with')) {
    function str_ends_with(string $haystack, string $needle): bool {
        return $needle === '' || substr($haystack, -strlen($needle)) === $needle;
    }
}

// 错误处理：确保所有错误都以 JSON 格式返回
error_reporting(E_ALL);
set_error_handler(function($errno, $errstr, $errfile, $errline) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => "PHP Error: $errstr in $errfile:$errline"], JSON_UNESCAPED_UNICODE);
    exit;
});
set_exception_handler(function($e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Exception: ' . $e->getMessage()], JSON_UNESCAPED_UNICODE);
    exit;
});

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(200); exit; }

$action = $_GET['action'] ?? $_POST['action'] ?? '';
$experimentsRoot = __DIR__;

// ── 辅助函数 ──

function jsonResponse($data, $code = 200) {
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

/**
 * 安全检查：确保路径在 experiments/ 目录内
 */
function safePath($relPath, $root) {
    $relPath = str_replace('\\', '/', $relPath);
    $relPath = preg_replace('#/+#', '/', $relPath);
    $relPath = trim($relPath, '/');
    if (!$relPath) return null;
    $full = realpath($root . '/' . $relPath);
    if (!$full) return null;
    $rootReal = realpath($root);
    if (!str_starts_with($full, $rootReal)) return null;
    // 禁止访问隐藏目录和特殊文件
    $parts = explode('/', $relPath);
    foreach ($parts as $p) {
        if ($p[0] === '.') return null;
    }
    return $full;
}

/**
 * 解析 frontmatter
 */
function parseFrontmatter($content) {
    $fm = [];
    if (preg_match('/^---\s*\n(.*?)\n---\s*\n/s', $content, $m)) {
        $lines = explode("\n", $m[1]);
        foreach ($lines as $line) {
            $line = trim($line);
            if ($line === '' || $line[0] === '#') continue;
            if (preg_match('/^(\w+):\s*(.+)$/', $line, $p)) {
                $key = $p[1];
                $val = trim($p[2]);
                if ($key === 'tags') {
                    if (str_starts_with($val, '[')) {
                        $parsed = json_decode($val, true);
                        $val = is_array($parsed) ? $parsed : [$val];
                    } else {
                        $val = array_map('trim', explode(',', $val));
                    }
                } elseif ($key === 'pinned') {
                    $val = ($val === 'true' || $val === 'yes');
                }
                $fm[$key] = $val;
            }
        }
    }
    return $fm;
}

/**
 * 生成 frontmatter 字符串
 */
function buildFrontmatter($meta) {
    $lines = ['---'];
    if (isset($meta['title']))   $lines[] = 'title: ' . $meta['title'];
    if (isset($meta['titleEn'])) $lines[] = 'titleEn: ' . $meta['titleEn'];
    if (isset($meta['summary']))   $lines[] = 'summary: ' . $meta['summary'];
    if (isset($meta['summaryEn'])) $lines[] = 'summaryEn: ' . $meta['summaryEn'];
    if (isset($meta['tags'])) {
        $lines[] = 'tags: [' . implode(', ', $meta['tags']) . ']';
    }
    if (isset($meta['status'])) $lines[] = 'status: ' . $meta['status'];
    if (isset($meta['pinned'])) $lines[] = 'pinned: ' . ($meta['pinned'] ? 'true' : 'false');
    $lines[] = '---';
    return implode("\n", $lines);
}

// ============================================================
//  路由
// ============================================================

switch ($action) {

    // ── 读取实验内容 ──
    case 'read':
        $path = $_GET['path'] ?? '';
        $lang = $_GET['lang'] ?? 'zh';
        $suffix = ($lang === 'en') ? '.md' : '.zh.md';

        if (!$path) jsonResponse(['error' => '缺少 path 参数'], 400);

        $fullPath = safePath($path . $suffix, $experimentsRoot);
        if (!$fullPath || !file_exists($fullPath)) {
            // 尝试不带后缀的原始路径
            $fullPath = safePath($path, $experimentsRoot);
            if (!$fullPath || !file_exists($fullPath)) {
                jsonResponse(['error' => '文件不存在: ' . $path], 404);
            }
        }

        $content = file_get_contents($fullPath);
        $fm = parseFrontmatter($content);
        jsonResponse([
            'ok'       => true,
            'content'  => $content,
            'frontmatter' => $fm,
            'path'     => basename($fullPath),
        ]);
        break;

    // ── 保存实验内容 ──
    case 'save':
        $input = json_decode(file_get_contents('php://input'), true);
        $path    = $input['path'] ?? '';
        $lang    = $input['lang'] ?? 'zh';
        $content = $input['content'] ?? '';
        $suffix  = ($lang === 'en') ? '.md' : '.zh.md';

        if (!$path) jsonResponse(['error' => '缺少 path'], 400);
        if (!$content) jsonResponse(['error' => '内容不能为空'], 400);

        $fullPath = safePath($path . $suffix, $experimentsRoot);
        if (!$fullPath) {
            $fullPath = safePath($path, $experimentsRoot);
            if (!$fullPath) jsonResponse(['error' => '无效路径: ' . $path], 400);
        }

        // 验证 frontmatter
        $fm = parseFrontmatter($content);
        if (empty($fm['title'])) {
            jsonResponse(['error' => 'frontmatter 必须包含 title 字段'], 400);
        }

        // 自动备份（保留最近 5 个）
        if (file_exists($fullPath)) {
            $backupDir = dirname($fullPath) . '/.backup';
            if (!is_dir($backupDir)) @mkdir($backupDir, 0755, true);
            $backupName = basename($fullPath, '.md') . '.' . date('Ymd-His') . '.md';
            @copy($fullPath, $backupDir . '/' . $backupName);
            // 清理旧备份
            $backups = glob($backupDir . '/*.md');
            if (count($backups) > 5) {
                usort($backups, function($a, $b) { return filemtime($a) - filemtime($b); });
                $toDelete = array_slice($backups, 0, count($backups) - 5);
                array_map('unlink', $toDelete);
            }
        }

        // 写入文件（统一换行符为 LF）
        $content = str_replace("\r\n", "\n", $content);
        if (substr($content, -1) !== "\n") $content .= "\n";
        file_put_contents($fullPath, $content);

        jsonResponse(['ok' => true, 'saved' => basename($fullPath)]);
        break;

    // ── 新建实验 ──
    case 'create':
        $input   = json_decode(file_get_contents('php://input'), true);
        $project = trim($input['project'] ?? '');
        $date    = $input['date'] ?? date('Y-m-d');
        $id      = trim($input['id'] ?? '');
        $templateId = $input['template'] ?? 'standard';

        if (!$project) jsonResponse(['error' => '请选择项目'], 400);
        if (!$id) jsonResponse(['error' => '请输入实验标识（英文slug）'], 400);

        // 验证项目名和 ID 格式
        if (!preg_match('/^[\x{4e00}-\x{9fff}a-zA-Z0-9\-_]+$/u', $project)) {
            jsonResponse(['error' => '项目名包含非法字符'], 400);
        }
        if (!preg_match('/^[a-z0-9\-]+$/', $id)) {
            jsonResponse(['error' => '实验标识只能包含小写字母、数字和连字符'], 400);
        }
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $date)) {
            jsonResponse(['error' => '日期格式应为 YYYY-MM-DD'], 400);
        }

        $projectDir = $experimentsRoot . '/' . $project;
        if (!is_dir($projectDir)) {
            @mkdir($projectDir, 0755, true);
        }

        $fileId = $date . '-' . $id;
        $zhPath = $projectDir . '/' . $fileId . '.zh.md';
        $enPath = $projectDir . '/' . $fileId . '.md';

        if (file_exists($zhPath) || file_exists($enPath)) {
            jsonResponse(['error' => '实验已存在: ' . $fileId], 409);
        }

        // 读取模板
        $tplDir = $experimentsRoot . '/templates';
        $tplFile = $tplDir . '/' . $templateId . '.md';
        if (!file_exists($tplFile)) {
            $tplFile = $tplDir . '/standard.md';
        }
        $tplContent = file_exists($tplFile) ? file_get_contents($tplFile) : "# 实验标题\n\n**日期**：{$date}\n**项目**：{$project}\n\n## 实验目的\n\n## 实验方法\n\n## 实验结果\n\n## 结论\n";

        // 替换模板中的日期和项目占位符
        $tplContent = str_replace(['YYYY-MM-DD', '{{date}}'], $date, $tplContent);
        $tplContent = str_replace(['{{project}}'], $project, $tplContent);

        // 写入中文版
        file_put_contents($zhPath, $tplContent);
        // 写入英文版（用英文 frontmatter）
        $enTpl = str_replace(
            ['title: 实验标题', 'summary: 实验简介（中文）'],
            ['title: Experiment Title', 'summary: Experiment summary'],
            $tplContent
        );
        file_put_contents($enPath, $enTpl);

        jsonResponse([
            'ok'   => true,
            'id'   => $fileId,
            'path' => $project . '/' . $fileId,
        ], 201);
        break;

    // ── 列出项目目录（含实验数量）──
    case 'list-projects':
        $dirs = glob($experimentsRoot . '/*', GLOB_ONLYDIR);
        $projects = [];
        foreach ($dirs as $d) {
            $name = basename($d);
            if ($name[0] === '.' || $name === 'comments' || $name === 'templates') continue;
            // 统计该目录下的实验数量
            $count = 0;
            $experiments_list = [];
            $files = glob($d . '/*.md');
            foreach ($files as $f) {
                $bn = basename($f);
                if ($bn === 'template.md' || $bn === 'templates.json') continue;
                if (str_starts_with($bn, '.')) continue;
                $count++;
                $id = preg_match('/\.zh\.md$/', $bn) ? substr($bn, 0, -6) : substr($bn, 0, -3);
                $experiments_list[] = $id;
            }
            $projects[] = [
                'name'        => $name,
                'count'       => $count,
                'experiments' => array_values(array_unique($experiments_list)),
            ];
        }
        usort($projects, function($a, $b) { return strcmp($a['name'], $b['name']); });
        jsonResponse(['ok' => true, 'projects' => $projects]);
        break;

    // ── 新建项目 ──
    case 'create-project':
        $input = json_decode(file_get_contents('php://input'), true);
        $name = trim($input['name'] ?? '');
        if (!$name) jsonResponse(['error' => '项目名不能为空'], 400);
        if (!preg_match('/^[\x{4e00}-\x{9fff}a-zA-Z0-9\-_ ]+$/u', $name)) {
            jsonResponse(['error' => '项目名包含非法字符'], 400);
        }
        $dir = $experimentsRoot . '/' . $name;
        if (is_dir($dir)) jsonResponse(['error' => '项目已存在'], 409);
        if (!mkdir($dir, 0755, true)) {
            jsonResponse(['error' => '创建目录失败，请检查权限'], 500);
        }
        jsonResponse(['ok' => true, 'name' => $name], 201);
        break;

    // ── 删除项目 ──
    case 'delete-project':
        $input = json_decode(file_get_contents('php://input'), true);
        $name = trim($input['name'] ?? '');
        if (!$name) jsonResponse(['error' => '项目名不能为空'], 400);
        $dir = $experimentsRoot . '/' . $name;
        if (!is_dir($dir)) jsonResponse(['error' => '项目不存在'], 404);
        // 检查是否有实验
        $files = glob($dir . '/*.md');
        $realFiles = array_filter($files, function($f) {
            $bn = basename($f);
            return $bn !== 'template.md' && !str_starts_with($bn, '.');
        });
        if (count($realFiles) > 0) {
            $ids = [];
            foreach ($realFiles as $f) {
                $bn = basename($f);
                $id = preg_match('/\.zh\.md$/', $bn) ? substr($bn, 0, -6) : substr($bn, 0, -3);
                $ids[] = $id;
            }
            $ids = array_values(array_unique($ids));
            jsonResponse([
                'ok'         => false,
                'error'      => '项目下还有 ' . count($ids) . ' 条实验记录，无法删除',
                'experiments' => $ids,
            ], 409);
        }
        // 删除空目录
        rmdir($dir);
        jsonResponse(['ok' => true]);
        break;

    // ── 重命名项目 ──
    case 'rename-project':
        $input = json_decode(file_get_contents('php://input'), true);
        $oldName = trim($input['oldName'] ?? '');
        $newName = trim($input['newName'] ?? '');
        if (!$oldName || !$newName) jsonResponse(['error' => '缺少参数'], 400);
        if ($oldName === $newName) jsonResponse(['ok' => true]);
        if (!preg_match('/^[\x{4e00}-\x{9fff}a-zA-Z0-9\-_ ]+$/u', $newName)) {
            jsonResponse(['error' => '新项目名包含非法字符'], 400);
        }
        $oldDir = $experimentsRoot . '/' . $oldName;
        $newDir = $experimentsRoot . '/' . $newName;
        if (!is_dir($oldDir)) jsonResponse(['error' => '原项目不存在'], 404);
        if (is_dir($newDir)) jsonResponse(['error' => '目标项目名已存在'], 409);
        rename($oldDir, $newDir);
        jsonResponse(['ok' => true, 'name' => $newName]);
        break;

    // ── 列出模板 ──
    case 'list-templates':
        $tplDir = $experimentsRoot . '/templates';
        $jsonFile = $tplDir . '/templates.json';
        $templates = [];
        if (file_exists($jsonFile)) {
            $raw = file_get_contents($jsonFile);
            // Strip BOM if present
            if (str_starts_with($raw, "\xEF\xBB\xBF")) $raw = substr($raw, 3);
            $templates = json_decode($raw, true) ?: [];
        }
        // Fallback: scan directory if JSON missing or empty
        if (empty($templates) && is_dir($tplDir)) {
            $files = glob($tplDir . '/*.md');
            foreach ($files as $f) {
                $name = basename($f, '.md');
                $templates[] = [
                    'id'          => $name,
                    'name'        => $name,
                    'nameEn'      => $name,
                    'description' => '',
                    'file'        => $name . '.md',
                ];
            }
        }
        jsonResponse(['ok' => true, 'templates' => $templates]);
        break;

    // ── 获取模板内容 ──
    case 'get-template':
        $id = $_GET['id'] ?? 'standard';
        if (!preg_match('/^[a-z\-]+$/', $id)) {
            jsonResponse(['error' => '无效的模板 ID'], 400);
        }
        $tplFile = $experimentsRoot . '/templates/' . $id . '.md';
        if (!file_exists($tplFile)) {
            $tplFile = $experimentsRoot . '/template.md';
        }
        if (!file_exists($tplFile)) {
            jsonResponse(['error' => '模板不存在'], 404);
        }
        jsonResponse(['ok' => true, 'content' => file_get_contents($tplFile)]);
        break;

    // ── 删除实验条目 ──
    case 'delete-experiment':
        $input = json_decode(file_get_contents('php://input'), true);
        $path = trim($input['path'] ?? '');
        if (!$path) jsonResponse(['error' => '缺少 path 参数'], 400);

        // 安全检查：手动验证路径，不用 safePath（因为路径没有扩展名）
        $path = str_replace('\\', '/', $path);
        $path = preg_replace('#/+#', '/', $path);
        $path = trim($path, '/');
        if (!$path || str_contains($path, '..')) jsonResponse(['error' => '无效路径'], 400);
        $parts = explode('/', $path);
        foreach ($parts as $p) {
            if ($p === '' || $p[0] === '.') jsonResponse(['error' => '无效路径'], 400);
        }

        $deleted = [];
        $rootReal = realpath($experimentsRoot);

        // 删除中文版
        $zh = $experimentsRoot . '/' . $path . '.zh.md';
        $zhReal = realpath($zh);
        if ($zhReal && str_starts_with($zhReal, $rootReal)) {
            unlink($zhReal);
            $deleted[] = basename($zhReal);
        }
        // 删除英文版
        $en = $experimentsRoot . '/' . $path . '.md';
        $enReal = realpath($en);
        if ($enReal && str_starts_with($enReal, $rootReal)) {
            unlink($enReal);
            $deleted[] = basename($enReal);
        }
        // 删除相关评论 JSON
        $id = basename($path);
        $commentFile = $experimentsRoot . '/comments/' . $id . '.json';
        if (file_exists($commentFile)) {
            unlink($commentFile);
            $deleted[] = basename($commentFile);
        }

        if (empty($deleted)) jsonResponse(['error' => '文件不存在: ' . $path], 404);
        jsonResponse(['ok' => true, 'deleted' => $deleted]);
        break;

    // ── 默认 ──
    default:
        jsonResponse(['error' => '未知操作: ' . $action, 'actions' => [
            'read', 'save', 'create', 'list-projects', 'list-templates', 'get-template'
        ]], 400);
}
