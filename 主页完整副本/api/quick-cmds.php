<?php
header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type");
if ($_SERVER["REQUEST_METHOD"] === "OPTIONS") { http_response_code(200); exit; }

$file = __DIR__ . '/quick-cmds.json';

if ($_SERVER["REQUEST_METHOD"] === "GET") {
    if (file_exists($file)) {
        echo file_get_contents($file);
    } else {
        echo json_encode(["groups"=>new stdClass,"active"=>"","_version"=>2], JSON_UNESCAPED_UNICODE);
    }
    exit;
}

if ($_SERVER["REQUEST_METHOD"] === "POST") {
    $input = json_decode(file_get_contents("php://input"), true);
    if (!is_array($input)) { echo json_encode(["ok"=>false,"error"=>"array required"]); exit; }
    file_put_contents($file, json_encode($input, JSON_UNESCAPED_UNICODE|JSON_PRETTY_PRINT), LOCK_EX);
    echo json_encode(["ok"=>true]);
    exit;
}
