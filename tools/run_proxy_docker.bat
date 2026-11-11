@echo off
REM Официальный прокси Tesla (Vehicle Command Protocol) в Docker.
REM Папка keys должна содержать private-key.pem, tls-key.pem, tls-cert.pem.
REM Порт открыт только для этого компьютера (127.0.0.1).
docker run --rm --name tesla-http-proxy ^
  -p 127.0.0.1:4443:4443 ^
  -v "%~dp0..\keys":/config:ro ^
  tesla/vehicle-command:latest ^
  -tls-key /config/tls-key.pem ^
  -cert /config/tls-cert.pem ^
  -key-file /config/private-key.pem ^
  -host 0.0.0.0 -port 4443
