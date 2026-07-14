<?php
// PHP-Reverse-Proxy für Infomaniak Managed Hosting (Muster wie dashboard-projekte.ch).
//
// In den Web-Root der Radar-Subdomain legen (zusammen mit .htaccess) und $BACKEND
// auf den Gunicorn-Port des Radar-MVP setzen:
//
//   app.ki-tech-radar.ch  ->  127.0.0.1:8030
//
// HTTPS wird von der Infomaniak-Plattform erzwungen (Panel), NICHT hier per Redirect.

$BACKEND = 'http://127.0.0.1:8030';

$target = $BACKEND . ($_SERVER['REQUEST_URI'] ?? '/');
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

$ch = curl_init($target);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
curl_setopt($ch, CURLOPT_TIMEOUT, 120);

// Request-Header durchreichen (Host weglassen – Backend bindet lokal)
$headers = [];
foreach (getallheaders() as $k => $v) {
    if (strtolower($k) === 'host') {
        continue;
    }
    $headers[] = "$k: $v";
}
$headers[] = 'X-Forwarded-Proto: https';
$headers[] = 'X-Forwarded-For: ' . ($_SERVER['REMOTE_ADDR'] ?? '');
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

// Request-Body bei schreibenden Methoden
if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'], true)) {
    curl_setopt($ch, CURLOPT_POSTFIELDS, file_get_contents('php://input'));
}

$response = curl_exec($ch);
if ($response === false) {
    http_response_code(502);
    header('Content-Type: text/plain; charset=utf-8');
    echo 'Bad Gateway: Radar-MVP nicht erreichbar.';
    exit;
}

$header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$status      = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$raw_headers = substr($response, 0, $header_size);
$body        = substr($response, $header_size);
curl_close($ch);

http_response_code($status);
foreach (explode("\r\n", $raw_headers) as $line) {
    if ($line === '') {
        continue;
    }
    // Status- und Hop-by-hop-Zeilen nicht weiterreichen (Set-Cookie bleibt erhalten)
    if (stripos($line, 'HTTP/') === 0) {
        continue;
    }
    if (stripos($line, 'Transfer-Encoding:') === 0) {
        continue;
    }
    if (stripos($line, 'Connection:') === 0) {
        continue;
    }
    header($line, false);
}
echo $body;
