<?php
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$sourceDir = realpath(__DIR__ . '/source');
if ($sourceDir === false || !is_dir($sourceDir)) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => '未找到原书库资源目录'], JSON_UNESCAPED_UNICODE);
    exit;
}

function publicUrl(string $relative): string {
    $segments = array_map('rawurlencode', explode('/', str_replace('\\', '/', $relative)));
    return 'source/' . implode('/', $segments);
}

function scanPdfs(string $root, string $relative = ''): array {
    $files = [];
    $items = scandir($root);
    if ($items === false) return $files;
    foreach ($items as $item) {
        if ($item === '.' || $item === '..') continue;
        $full = $root . DIRECTORY_SEPARATOR . $item;
        $path = $relative === '' ? $item : $relative . '/' . $item;
        if (is_dir($full)) {
            $files = array_merge($files, scanPdfs($full, $path));
        } elseif (is_file($full) && strtolower(pathinfo($item, PATHINFO_EXTENSION)) === 'pdf') {
            $stat = stat($full);
            $files[] = [
                'name' => pathinfo($item, PATHINFO_FILENAME),
                'path' => $path,
                'url' => publicUrl($path),
                'folder' => $relative === '' ? '未分类' : $relative,
                'size' => $stat['size'] ?? 0,
                'modified' => date(DATE_ATOM, $stat['mtime'] ?? time()),
            ];
        }
    }
    return $files;
}

$grouped = [];
foreach (scanPdfs($sourceDir) as $file) {
    $grouped[$file['folder']][] = $file;
}
uksort($grouped, 'strnatcasecmp');
foreach ($grouped as &$books) {
    usort($books, fn($a, $b) => strnatcasecmp($a['name'], $b['name']));
}
unset($books);

echo json_encode(['ok' => true, 'folders' => $grouped], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);

