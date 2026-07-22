<?php
/**
 * Wiki 文档索引专用入口。
 * 无论服务器是否保留查询参数，都明确进入 documents 路由。
 */
$_GET['action'] = 'documents';
require __DIR__ . '/api-backup.php';
