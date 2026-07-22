<?php
ini_set('display_errors', 0); error_reporting(0);
header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type");
if (($_SERVER["REQUEST_METHOD"] ?? "") === "OPTIONS") { http_response_code(200); exit; }
if (($_SERVER["REQUEST_METHOD"] ?? "") !== "POST") { echo json_encode(["ok"=>false,"error"=>"POST only"]); exit; }

$input = json_decode(file_get_contents("php://input"), true);
$raw = trim($input["cmd"] ?? "");
if (!$raw) { echo json_encode(["ok"=>false,"error"=>"missing cmd"]); exit; }

$root = dirname(__DIR__);
$cwd = $input["cwd"] ?? null;
$base = $root;
if ($cwd) { $rc = realpath($cwd); if ($rc && strpos($rc, realpath($root)) === 0) $base = $rc; }
$parts = explode(" ", $raw, 2);
$cmd = $parts[0];
$arg = $parts[1] ?? "";

$ok = ["php","server","disk","git","files","logs","env","db","proc","help","ls","pwd","cat","du","whoami","head","tail","cd","df","free","ps","uname","uptime","id","date","docker","cleanup"];
if (!in_array($cmd, $ok)) { echo json_encode(["ok"=>false,"error"=>"unknown: $cmd"]); exit; }

function sp($r,$p){$p=trim(str_replace("\\","/",$p),"/");if($p===""||$p===".")return realpath($r);if(strpos($p,"..")!==false)return null;$f=realpath($r."/".$p);if(!$f||strpos($f,realpath($r))!==0)return null;return $f;}
function fb($b){if($b>=1073741824)return round($b/1073741824,2)." GB";if($b>=1048576)return round($b/1048576,2)." MB";if($b>=1024)return round($b/1024,2)." KB";return $b." B";}
function ds($d){$s=0;try{foreach(new RecursiveIteratorIterator(new RecursiveDirectoryIterator($d,RecursiveDirectoryIterator::SKIP_DOTS)) as $i){if($i->isFile()){$p=$i->getPathname();if(strpos($p,".git")!==false||strpos($p,".jj")!==false||strpos($p,"node_modules")!==false)continue;$s+=$i->getSize();}}}catch(Exception $e){}return $s;}
function sa($cmd,&$out=null,&$ret=null){static$eOk=null;if($eOk===null){$df=ini_get('disable_functions')?:'';$eOk=!in_array('exec',array_map('trim',explode(',',$df)));}if(!$eOk){if($out!==null)$out=[];if($ret!==null)$ret=127;return false;}return @exec($cmd,$out,$ret);}

$o="";
switch($cmd){
case "help":$o="ls [path] | pwd | cat <f> | head <f> | tail <f> | du | whoami | php | server | disk | git | files | logs | env | db | proc | df | free | ps | uname | uptime | id | date | docker";break;
case "ls":$t=$arg?sp($base,$arg):$base;if(!$t||!is_dir($t)){$o="ls: $arg: no access";break;}$o="━━ ".($t===$base?"(base)":$t)." ━━\n";$it=@scandir($t);if(!$it)break;$dd=[];$ff=[];foreach($it as $n){if($n==="."||$n==="..")continue;if($t===$base&&$n[0]===".")continue;if(is_dir($t."/".$n))$dd[]=$n."/";else $ff[]=$n;}sort($dd);sort($ff);foreach($dd as $d)$o.="  📁 $d\n";foreach($ff as $f)$o.="  📄 $f\n";$o.=count($dd)." dirs, ".count($ff)." files";break;
case "pwd":$o=$base;break;
case "cat":$f=sp($base,$arg);if(!$f||!is_file($f)){$o="cat: $arg: no access";break;}$c=@file_get_contents($f);if($c===false){$o="cat: read error";break;}$o="━ $arg (".strlen($c)." B, ".substr_count($c,"\n")." lines) ━\n".$c;break;
case "head":$f=sp($base,$arg);if(!$f||!is_file($f)){$o="head: $arg: no access";break;}$ln=@file($f);if($ln===false){$o="head: read error";break;}$o="━ $arg (first 20/".count($ln)." lines) ━\n";foreach(array_slice($ln,0,20)as $l)$o.=rtrim($l)."\n";break;
case "tail":$f=sp($base,$arg);if(!$f||!is_file($f)){$o="tail: $arg: no access";break;}$ln=@file($f);if($ln===false){$o="tail: read error";break;}$o="━ $arg (last 20/".count($ln)." lines) ━\n";foreach(array_slice($ln,-20)as $l)$o.=rtrim($l)."\n";break;
case "du":$t=$arg?sp($base,$arg):$base;if(!$t||!is_dir($t)){$o="du: $arg: no access";break;}$o="━ disk usage ━\n";$sub=@scandir($t);if($sub){foreach($sub as $n){if($n==="."||$n==="..")continue;$p=$t."/".$n;$sz=is_dir($p)?ds($p):filesize($p);$o.="  ".(is_dir($p)?"📁":"📄")." $n: ".fb($sz)."\n";}}$o.="total: ".fb(ds($t));break;
case "whoami":$o=function_exists("get_current_user")?get_current_user():trim(sa("whoami 2>/dev/null")?:getenv("USER")?:"");break;
case "php":$o="PHP ".phpversion()." | ".php_sapi_name()." | mem:".ini_get("memory_limit")." | ext:".implode(",",get_loaded_extensions());break;
case "server":$o="OS: ".php_uname("s")." ".php_uname("r")." | Host: ".php_uname("n")." | Web: ".($_SERVER["SERVER_SOFTWARE"]??"?")." | User: ".(function_exists("get_current_user")?get_current_user():"?")." | Root: $root";break;
case "disk":$fr=disk_free_space($root);$to=disk_total_space($root);$o=fb($to-$fr)."/".fb($to)." | project: ".fb(ds($root));break;
case "git":$gd=$root."/.git";if(!is_dir($gd)){$o="no .git";break;}$h=@file_get_contents($gd."/HEAD");$o="branch: ".($h?trim(str_replace("ref: refs/heads/","",$h)):"?")."\n";$so=[];$sc=0;sa('git -C "'.$root.'" status --short 2>&1',$so,$sc);if($sc===0){if(empty($so))$o.="clean";else{$o.=count($so)." files:\n";foreach(array_slice($so,0,15)as $l)$o.="  $l\n";}}break;
case "files":$tf=0;$ts=0;$ec=[];foreach(new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root,RecursiveDirectoryIterator::SKIP_DOTS),RecursiveIteratorIterator::SELF_FIRST) as $i){if($i->isFile()){$p=$i->getPathname();if(strpos($p,".git")!==false||strpos($p,".jj")!==false||strpos($p,"node_modules")!==false)continue;$tf++;$ts+=$i->getSize();$e=strtolower($i->getExtension());$ec[$e]=($ec[$e]??0)+1;}}$o="$tf files, ".fb($ts)."\n";arsort($ec);foreach(array_slice($ec,0,10)as $e=>$c)$o.="  .$e: $c\n";break;
case "logs":$lf=ini_get("error_log");if(!$lf||!file_exists($lf)){$o="no log file";break;}$o="$lf (".fb(filesize($lf)).")\n";$ln=@file($lf);if($ln)foreach(array_slice($ln,-20)as $l)$o.=trim($l)."\n";break;
case "env":$o="cwd: ".getcwd()." | tmp: ".sys_get_temp_dir()." | root: $root\n";foreach(["PATH","HOME","USER"] as $k){$v=getenv($k);if($v!==false)$o.="$k=$v\n";}break;
case "db":$dp=$root."/vault/vault.db";if(!file_exists($dp)){$o="no vault.db";break;}$o="vault.db: ".fb(filesize($dp))."\n";try{$db=new SQLite3($dp,SQLITE3_OPEN_READONLY);$tb=[];$r=$db->query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name");while($rw=$r->fetchArray(SQLITE3_ASSOC))$tb[]=$rw["name"];$o.="tables: ".implode(",",$tb)."\n";foreach($tb as $t){$c=$db->querySingle("SELECT COUNT(*) FROM \"$t\"");$o.="  $t: $c rows\n";}$db->close();}catch(Exception $e){$o.="error: ".$e->getMessage();}break;
case "proc":$o="";if(file_exists('/proc/loadavg'))$o.="负载: ".@file_get_contents('/proc/loadavg');if(file_exists('/proc/meminfo')){$ln=@file('/proc/meminfo');if($ln)foreach(array_slice($ln,0,5)as$l)$o.=$l;}if(!$o)$o="proc: 无法读取 /proc";break;
case "cd":$t=$arg?sp($base,$arg):$base;if(!$t||!is_dir($t)){$o="cd: $arg: no such directory";break;}if(!@chdir($t)){$o="cd: $arg: permission denied";break;}$o=getcwd();$base=$t;break;
case "df":$po=[];$ec=-1;sa("df -h 2>&1",$po,$ec);$o=$ec===0?implode("\n",$po):"df: not available";break;
case "free":$po=[];$ec=-1;sa("free -h 2>&1",$po,$ec);$o=$ec===0?implode("\n",$po):"free: not available";break;
case "ps":$po=[];sa("ps aux --cols=120 2>&1 | head -30",$po);$o=implode("\n",$po?:[]);break;
case "uname":$o=php_uname("a");break;
case "uptime":$po=[];sa("uptime 2>&1",$po);$o=$po?implode("\n",$po):"";break;
case "id":$po=[];sa("id 2>&1",$po);$o=implode("\n",$po);break;
case "date":$o=date("Y-m-d H:i:s T");break;
case "docker":$po=[];$ec=-1;sa("docker $arg 2>&1",$po,$ec);$o=$ec===0?implode("\n",$po):"docker: not available or error";break;
case "cleanup":$sub=$arg?:'scan';switch($sub){
case"scan":$o="🔍 服务器垃圾扫描\n".str_repeat("━",40)."\n\n";$po=[];$ec=-1;sa("docker system df 2>&1",$po,$ec);if($ec===0&&!empty($po)){$o.="🐳 Docker:\n";foreach($po as $l)$o.="  $l\n";$o.="\n";}$tc=0;$ts=0;$oc=0;$os=0;$nw=time();try{if(is_dir('/tmp')){$it=new RecursiveIteratorIterator(new RecursiveDirectoryIterator('/tmp',RecursiveDirectoryIterator::SKIP_DOTS),RecursiveIteratorIterator::SELF_FIRST);foreach($it as $f){if($f->isFile()&&$f->isReadable()){$sz=$f->getSize();$tc++;$ts+=$sz;if($nw-$f->getMTime()>7*86400){$oc++;$os+=$sz;}}}}}catch(Exception$e){}$o.="📁 /tmp: {$tc} 文件 (".fb($ts).")\n";if($oc>0)$o.="  其中 >7 天: {$oc} 文件 (".fb($os).")\n";$o.="\n";$gd=$root.'/.git';if(is_dir($gd)){$gs=ds($gd);$o.="📦 .git: ".fb($gs)."\n";$lo=0;$lod=$gd.'/objects';if(is_dir($lod)){try{foreach(new DirectoryIterator($lod) as $d){if(!$d->isDot()&&$d->isDir()&&strlen($d->getFilename())===2){foreach(new DirectoryIterator($d->getPathname()) as $f){if($f->isFile())$lo++;}}}}catch(Exception$e){}}if($lo>0)$o.="  松散对象: {$lo} 个\n";$o.="\n";}$ll=[];try{$ri=new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root,RecursiveDirectoryIterator::SKIP_DOTS),RecursiveIteratorIterator::SELF_FIRST);foreach($ri as $f){if($f->isFile()&&$f->getSize()>1048576){$ext=strtolower($f->getExtension());if(in_array($ext,['log','txt']))$ll[]=['path'=>str_replace($root,'.',$f->getPathname()),'size'=>$f->getSize()];}}}catch(Exception$e){}$o.="📋 项目大文件 (>1MB): ".count($ll)." 个\n";foreach($ll as $l)$o.="  {$l['path']}: ".fb($l['size'])."\n";$o.="\n".str_repeat("━",40)."\n清理命令: cleanup docker | cleanup tmp | cleanup git | cleanup all";break;
case"docker":$po=[];$ec=-1;sa("docker system prune -f 2>&1",$po,$ec);$o=$ec===0?"🐳 Docker 清理完成:\n".implode("\n",$po):"🐳 Docker: 不可用或无权限";break;
case"tmp":$oc=0;$os=0;$nw=time();try{if(is_dir('/tmp')){$it=new RecursiveIteratorIterator(new RecursiveDirectoryIterator('/tmp',RecursiveDirectoryIterator::SKIP_DOTS),RecursiveIteratorIterator::CHILD_FIRST);foreach($it as $f){if($f->isFile()&&$f->isReadable()&&($nw-$f->getMTime()>7*86400)){$os+=$f->getSize();$oc++;@unlink($f->getPathname());}}}}catch(Exception$e){}$o="📁 /tmp: 删除了 {$oc} 个旧文件 (>7天), 释放 ".fb($os);break;
case"git":$po=[];$ec=-1;sa('git -C "'.$root.'" gc --auto 2>&1',$po,$ec);$o=$ec===0?"📦 Git GC 完成\n".implode("\n",$po):"📦 Git: 不可用";break;
case"all":$o="🧹 开始全面清理...\n\n";$po=[];$ec=-1;sa("docker system prune -f 2>&1",$po,$ec);$o.="🐳 Docker: ".($ec===0?implode("\n  ",$po):"跳过(不可用)")."\n\n";$oc=0;$os=0;$nw=time();try{if(is_dir('/tmp')){$it=new RecursiveIteratorIterator(new RecursiveDirectoryIterator('/tmp',RecursiveDirectoryIterator::SKIP_DOTS),RecursiveIteratorIterator::CHILD_FIRST);foreach($it as $f){if($f->isFile()&&$f->isReadable()&&($nw-$f->getMTime()>7*86400)){$os+=$f->getSize();$oc++;@unlink($f->getPathname());}}}}catch(Exception$e){}$o.="📁 /tmp: 清理 {$oc} 旧文件 (>7天), 释放 ".fb($os)."\n\n";$po2=[];$ec2=-1;sa('git -C "'.$root.'" gc --auto 2>&1',$po2,$ec2);$o.="📦 Git: ".($ec2===0?"GC 完成":"跳过(不可用)")."\n\n";$o.="✅ 清理完毕!";break;
default:$o="cleanup: 未知子命令 '$sub'\n可用: scan, docker, tmp, git, all";}break;
default:$o="unknown: $cmd";
}
echo json_encode(["ok"=>true,"cmd"=>$raw,"output"=>$o],JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
