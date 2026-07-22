<?php
/**
 * 消息队列 API — 获取所有实验的评论，按时间倒序
 *
 * GET /api-messages.php → 返回所有评论（含所属实验 id）
 */

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');

$commentsDir = __DIR__ . '/comments';
$all = [];

if (!is_dir($commentsDir)) {
    echo json_encode([], JSON_UNESCAPED_UNICODE);
    exit;
}

$files = glob($commentsDir . '/*.json');
sort($files);

foreach ($files as $file) {
    $expId = basename($file, '.json');
    $comments = json_decode(file_get_contents($file), true) ?: [];
    foreach ($comments as $c) {
        $c['expId'] = $expId;
        $all[] = $c;
    }
}

// 按时间倒序
usort($all, function ($a, $b) {
    return strcmp($b['createdAt'], $a['createdAt']);
});

echo json_encode($all, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
