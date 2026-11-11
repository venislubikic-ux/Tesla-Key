@echo off
REM Официальный прокси Tesla без Docker.
REM Установка (нужен Go 1.23+):  go install github.com/teslamotors/vehicle-command/cmd/tesla-http-proxy@latest
set KEYS=%~dp0..\keys
tesla-http-proxy -tls-key "%KEYS%\tls-key.pem" -cert "%KEYS%\tls-cert.pem" -key-file "%KEYS%\private-key.pem" -host 127.0.0.1 -port 4443
