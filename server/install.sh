#!/usr/bin/env bash
# Установка приёмника строк на сервер. Запускать от root:
#     bash /opt/skyblockru/install.sh
#
# ⚠️ НИЧЕГО ЧУЖОГО НЕ ТРОГАЕТ. На сервере уже работает SMS Relay (порт 8080,
# свой блок в Caddyfile). Мы добавляем СВОЙ сервис на 8787 и СВОЙ блок домена;
# существующий блок остаётся как есть, а перед правкой делается копия.
#
# ⚠️ Скрипт идемпотентный: повторный запуск ничего не ломает и не дублирует.
set -euo pipefail

DOMAIN="skyblockru.duckdns.org"
PORT=8787
DATA="/var/lib/skyblockru"
APP="/opt/skyblockru"
CADDYFILE="/etc/caddy/Caddyfile"

echo "=== пользователь и папки ==="
id skyblockru >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin skyblockru
mkdir -p "$APP" "$DATA"
chown skyblockru:skyblockru "$DATA"
echo "ок"

echo
echo "=== проверка приёмника ==="
python3 -c "import ast; ast.parse(open('$APP/receiver.py', encoding='utf-8').read())"
echo "receiver.py разбирается"

echo
echo "=== служба systemd ==="
cat > /etc/systemd/system/skyblockru-receiver.service <<UNIT
[Unit]
Description=SkyblockRU translation receiver
After=network.target

[Service]
# ⚠️ Слушаем ТОЛЬКО localhost: наружу смотрит Caddy, он же держит https.
# Открыть порт наружу значило бы отдать приём без шифрования и без имени.
ExecStart=/usr/bin/python3 $APP/receiver.py --host 127.0.0.1 --port $PORT --dir $DATA
Restart=always
RestartSec=5
User=skyblockru
Group=skyblockru
# Ограничения: сервису нужен ровно один каталог на запись, остальное — нет.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now skyblockru-receiver.service
sleep 1
systemctl is-active skyblockru-receiver.service && echo "служба поднята"

echo
echo "=== блок в Caddyfile ==="
if grep -q "$DOMAIN" "$CADDYFILE"; then
	echo "блок уже есть — не трогаю"
else
	cp "$CADDYFILE" "$CADDYFILE.bak.$(date +%Y%m%d%H%M%S)"
	cat >> "$CADDYFILE" <<CADDY

$DOMAIN {
	reverse_proxy localhost:$PORT
}
CADDY
	echo "блок добавлен, копия старого конфига сделана"
fi

echo
echo "=== проверка конфига Caddy ==="
# ⚠️ Сначала validate, потом reload. Битый конфиг при перезапуске уронил бы
# и чужой сайт — а reload на проверенном конфиге не рвёт существующие соединения.
caddy validate --config "$CADDYFILE" --adapter caddyfile 2>&1 | tail -3
systemctl reload caddy
echo "caddy перечитал конфиг"

echo
echo "=== проверка на месте ==="
sleep 2
curl -s -o /dev/null -w "приёмник (локально): %{http_code}\n" "http://127.0.0.1:$PORT/health"
echo "жду сертификат Let's Encrypt (до 30 с)..."
for i in $(seq 1 15); do
	code=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/health" --max-time 5 || true)
	if [ "$code" = "200" ]; then
		echo "https://$DOMAIN/health -> 200, сертификат выдан"
		break
	fi
	sleep 2
done
[ "${code:-}" = "200" ] || echo "https пока не отвечает (код ${code:-нет}) — смотри: journalctl -u caddy -n 30"

echo
echo "=== соседи по серверу целы? ==="
# ⚠️ На машине может жить ЧУЖОЙ проект: мы добавляемся рядом, а не вместо.
# Проверить, что он пережил правку Caddy, — обязательный шаг.
# Адрес и имя службы задаются переменными окружения, в код не вписаны:
# репозиторий публичный, и раскрывать чужую инфраструктуру нельзя.
#   NEIGHBOUR_URL=https://пример/  NEIGHBOUR_SERVICE=имя.service  bash install.sh
if [ -n "${NEIGHBOUR_URL:-}" ]; then
	curl -s -o /dev/null -w "сосед по http: %{http_code}\n" "$NEIGHBOUR_URL" --max-time 10 || true
fi
if [ -n "${NEIGHBOUR_SERVICE:-}" ]; then
	systemctl is-active "$NEIGHBOUR_SERVICE" | sed "s/^/$NEIGHBOUR_SERVICE: /"
fi
if [ -z "${NEIGHBOUR_URL:-}${NEIGHBOUR_SERVICE:-}" ]; then
	echo "(проверка пропущена: задай NEIGHBOUR_URL и NEIGHBOUR_SERVICE)"
fi
