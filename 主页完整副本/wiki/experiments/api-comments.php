<?php
/**
 * 实验评论 API
 *
 * GET  /api-comments.php?id=xxx   → 返回该实验的所有评论
 * POST /api-comments.php?id=xxx   → 新增一条评论
 *
 * 评论存储在 experiments/comments/{id}.json
 */

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');

$id = $_REQUEST['id'] ?? '';
if (!$id || !preg_match('/^[\w\-]+$/', $id)) {
    http_response_code(400);
    echo json_encode(['error' => '无效的 id'], JSON_UNESCAPED_UNICODE);
    exit;
}

$dataDir = __DIR__ . '/comments';
if (!is_dir($dataDir)) mkdir($dataDir, 0755, true);
$filePath = $dataDir . '/' . $id . '.json';

// ── GET：读取评论 ──
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    if (file_exists($filePath)) {
        $comments = json_decode(file_get_contents($filePath), true) ?: [];
    } else {
        $comments = [];
    }
    echo json_encode($comments, JSON_UNESCAPED_UNICODE);
    exit;
}

// ── POST：新增评论 ──
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $input = json_decode(file_get_contents('php://input'), true);
    $text = trim($input['text'] ?? '');
    if ($text === '') {
        http_response_code(400);
        echo json_encode(['error' => '评论内容不能为空'], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $comments = [];
    if (file_exists($filePath)) {
        $comments = json_decode(file_get_contents($filePath), true) ?: [];
    }

    $comment = [
        'id'        => uniqid('c_'),
        'text'      => $text,
        'author'    => trim($input['author'] ?? '默认'),
        'labels'    => $input['labels'] ?? [],
        'createdAt' => date('Y-m-d\TH:i:s'),
    ];
    $comments[] = $comment;
    file_put_contents($filePath, json_encode($comments, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));

    http_response_code(201);
    echo json_encode($comment, JSON_UNESCAPED_UNICODE);
    exit;
}

// ── 其他方法 ──
http_response_code(405);
echo json_encode(['error' => '仅支持 GET/POST'], JSON_UNESCAPED_UNICODE);
