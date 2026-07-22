<?php
/**
 * 实验记录自动索引 API
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

error_reporting(E_ALL);
set_error_handler(function($errno, $errstr, $errfile, $errline) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => "PHP Error: $errstr in $errfile:$errline"], JSON_UNESCAPED_UNICODE);
    exit;
});

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');

$root = __DIR__;
$experiments = [];  // keyed by id

// 获取所有子目录（排除隐藏目录）
$dirs = glob($root . '/*', GLOB_ONLYDIR);

foreach ($dirs as $dir) {
    $project = basename($dir);
    // 跳过特殊目录
    if ($project === 'templates' || $project === 'comments' || $project[0] === '.') continue;
    $files = glob($dir . '/*.md');
    sort($files);

    foreach ($files as $file) {
        $basename = basename($file);
        if ($basename === 'template.md') continue;

        // 判断中英文
        $isZh = (str_ends_with($basename, '.zh.md'));
        $id = $isZh ? substr($basename, 0, -6) : substr($basename, 0, -3);

        // 从文件名提取日期和标题
        $date = '';
        $fallbackTitle = $id;
        if (preg_match('/^(\d{4}-\d{2}-\d{2})[-_]?(.+)$/', $id, $m)) {
            $date = $m[1];
            $fallbackTitle = str_replace(['-', '_'], ' ', $m[2]);
        }

        // 读取 frontmatter
        $content = file_get_contents($file);
        $fm = parseFrontmatter($content);

        // 合并到统一条目
        $relPath = $project . '/' . $id;
        if (!isset($experiments[$id])) {
            $experiments[$id] = [
                'id'      => $id,
                'date'    => $date,
                'project' => $project,
                'path'    => $relPath,
                'title'   => '',
                'titleEn' => '',
                'summary' => '',
                'summaryEn' => '',
                'tags'    => [],
                'status'  => '',
                'pinned'  => false,
            ];
        }

        $e = &$experiments[$id];

        if ($isZh) {
            $e['status']  = $fm['status']  ?? '';
            $e['title']   = $fm['title']   ?? $fallbackTitle;
            $e['summary'] = $fm['summary'] ?? '';
            if (isset($fm['tags']))   $e['tags']   = $fm['tags'];
            if (isset($fm['pinned'])) $e['pinned'] = (bool)$fm['pinned'];
        } else {
            $e['titleEn']   = $fm['titleEn']   ?? $fm['title']   ?? $fallbackTitle;
            $e['summaryEn'] = $fm['summaryEn'] ?? $fm['summary'] ?? '';
            if (isset($fm['tags'])   && empty($e['tags']))   $e['tags']   = $fm['tags'];
            if (isset($fm['pinned']) && empty($e['pinned'])) $e['pinned'] = (bool)$fm['pinned'];
        }
    }
}

// 填补缺失的中文标题/概要（仅上传 .md 文件时有用）
foreach ($experiments as &$e) {
    if (empty($e['title']) && !empty($e['titleEn'])) {
        $e['title'] = $e['titleEn'];
    }
    if (empty($e['status'])) {
        $e['status'] = '待分析';  // 未标注状态的默认值
    }
}
unset($e);

// 按日期降序排列
$result = array_values($experiments);
usort($result, function ($a, $b) {
    return strcmp($b['date'], $a['date']);
});

echo json_encode($result, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);


// ---------- 辅助函数 ----------

function parseFrontmatter(string $content): array {
    $fm = [];
    if (preg_match('/^---\s*\n(.*?)\n---\s*\n/s', $content, $m)) {
        $lines = explode("\n", $m[1]);
        foreach ($lines as $line) {
            $line = trim($line);
            if ($line === '') continue;
            if (preg_match('/^(\w+):\s*(.+)$/', $line, $p)) {
                $key  = $p[1];
                $val  = trim($p[2]);
                switch ($key) {
                    case 'tags':
                        // YAML 数组格式: [tag1, tag2, ...]
                        if (str_starts_with($val, '[')) {
                            $parsed = json_decode($val, true);
                            $val = is_array($parsed) ? $parsed : [$val];
                        } else {
                            $val = [$val];
                        }
                        break;
                    case 'pinned':
                        $val = ($val === 'true' || $val === 'yes');
                        break;
                }
                $fm[$key] = $val;
            }
        }
    }
    return $fm;
}
