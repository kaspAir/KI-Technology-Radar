<?php
/**
 * proxy.php — Reverse-Proxy vom öffentlichen Docroot auf den lokalen Radar-MVP.
 *
 * Infomaniak Managed Hosting erlaubt kein mod_proxy -> dieser PHP-Proxy leitet
 * JEDE Anfrage (Methode/Pfad/Query/Header/Cookies/Body) an den Gunicorn-Prozess
 * an 127.0.0.1:PORT weiter und gibt Status/Header/Body zurück. Gleiche Bauart wie
 * der bewährte hermespia.ch-Proxy. Bindet zusammen mit .htaccess (alles -> proxy.php).
 *
 * WICHTIG: PORT muss zu RADAR_PORT (gunicorn_conf.py) passen.
 */
$PORT = getenv('RADAR_PORT') ?: '8030';
$UPSTREAM = "http://127.0.0.1:$PORT";

// --- Ziel-URL: Originalpfad + Query 1:1 übernehmen ---------------------------
$uri = $_SERVER['REQUEST_URI'] ?? '/';
$url = $UPSTREAM . $uri;

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$body = file_get_contents('php://input');

// --- Anfrage-Header einsammeln (Hop-by-Hop weglassen) ------------------------
$skip = ['host' => 1, 'connection' => 1, 'content-length' => 1,
         'accept-encoding' => 1, 'transfer-encoding' => 1];
$fwd = [];
foreach (getallheaders() as $k => $v) {
    if (isset($skip[strtolower($k)])) continue;
    $fwd[] = "$k: $v";
}

$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_CUSTOMREQUEST  => $method,
    CURLOPT_HTTPHEADER     => $fwd,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HEADER         => true,
    CURLOPT_FOLLOWLOCATION => false,   // Redirects (302/303) an den Browser durchreichen
    CURLOPT_TIMEOUT        => 60,
    CURLOPT_ENCODING       => '',      // keine transparente Kompression
]);
if ($method !== 'GET' && $method !== 'HEAD') {
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
}

$resp = curl_exec($ch);
if ($resp === false) {
    http_response_code(502);
    header('Content-Type: text/plain; charset=utf-8');
    echo "Radar-MVP nicht erreichbar (502). Läuft der Prozess? " . curl_error($ch);
    exit;
}

$status     = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$rawHeaders = substr($resp, 0, $headerSize);
$respBody   = substr($resp, $headerSize);
curl_close($ch);

// --- Antwort-Header zurückgeben (Set-Cookie behalten!) -----------------------
http_response_code($status);
$dropResp = ['transfer-encoding' => 1, 'content-length' => 1, 'connection' => 1,
             'content-encoding' => 1];
foreach (explode("\r\n", $rawHeaders) as $line) {
    if (strpos($line, ':') === false) continue;          // Statuszeile o.ä.
    list($name, ) = explode(':', $line, 2);
    if (isset($dropResp[strtolower(trim($name))])) continue;
    header($line, false);                                 // false = mehrfach erlauben (Set-Cookie)
}
echo $respBody;
