# -*- coding: utf-8 -*-
"""
Минимальный клиент S3 — ровно столько, сколько нужно для выкладки словарей.

⚠️ Почему не boto3. Он весит десятки мегабайт и тянет свои зависимости,
а нам нужны две операции: положить файл и посмотреть, что лежит. Подпись
AWS SigV4 — это полсотни строк, и она не устаревает. Остальные инструменты
проекта тоже обходятся `requests`, лишней зависимости в сборке не появится.

⚠️ КЛЮЧИ ЧИТАЮТСЯ ИЗ ОКРУЖЕНИЯ и нигде не печатаются — ни в логе, ни в
сообщении об ошибке. Секрет, попавший в вывод, считается утёкшим: вывод
уходит в историю терминала, в отчёты и в переписку.

    YC_S3_KEY_ID   идентификатор статического ключа
    YC_S3_SECRET   секретный ключ
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import os
import re
import urllib.parse

import requests

ENDPOINT = "storage.yandexcloud.kz"
BUCKET = "skyblockru-dict"

# ⚠️ Регион входит в ПОДПИСЬ, и угадывать его не нужно: при несовпадении
# S3 отвечает «expecting 'X'» и прямо называет верный. Стартуем с наиболее
# вероятного, а дальше слушаем сервер.
DEFAULT_REGION = "kz1"
WRONG_REGION = re.compile(r"expecting '([a-z0-9-]+)'")

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class S3Error(RuntimeError):
    """Ошибка S3. Текст ответа сервера — без ключей."""


def credentials() -> tuple[str, str]:
    """Пара (идентификатор, секрет) из окружения."""
    key_id = os.environ.get("YC_S3_KEY_ID", "").strip()
    secret = os.environ.get("YC_S3_SECRET", "").strip()
    if not key_id or not secret:
        raise S3Error(
            "нет ключей: заведи переменные окружения YC_S3_KEY_ID и YC_S3_SECRET\n"
            "  (Win+R -> sysdm.cpl -> Дополнительно -> Переменные среды)")
    return key_id, secret


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, stamp: str, region: str, service: str) -> bytes:
    key = _sign(("AWS4" + secret).encode("utf-8"), stamp)
    key = _sign(key, region)
    key = _sign(key, service)
    return _sign(key, "aws4_request")


def request(method: str, key: str, *, data: bytes | None = None,
            headers: dict[str, str] | None = None, region: str = DEFAULT_REGION,
            key_id: str | None = None, secret: str | None = None,
            query: str = "") -> requests.Response:
    """
    Подписанный запрос к объекту бакета.

    `key` — путь внутри бакета («packs/40-lore.json»), пустой для самого бакета.
    """
    if key_id is None or secret is None:
        key_id, secret = credentials()

    payload = data if data is not None else b""
    payload_hash = hashlib.sha256(payload).hexdigest() if payload else EMPTY_SHA256

    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    stamp = now.strftime("%Y%m%d")

    # ⚠️ Косые в пути НЕ экранируем: они разделители, и safe="/" тут обязателен,
    # иначе «packs/x.json» превратится в «packs%2Fx.json» и подпись не сойдётся.
    path = "/" + BUCKET + ("/" + urllib.parse.quote(key, safe="/") if key else "")

    signed = {
        "host": ENDPOINT,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    for name, value in (headers or {}).items():
        signed[name.lower()] = value

    names = sorted(signed)
    canonical_headers = "".join(f"{n}:{signed[n].strip()}\n" for n in names)
    signed_names = ";".join(names)

    canonical = "\n".join([
        method, path, query, canonical_headers, signed_names, payload_hash,
    ])
    scope = f"{stamp}/{region}/s3/aws4_request"
    to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    ])
    signature = hmac.new(_signing_key(secret, stamp, region, "s3"),
                         to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    send = dict(signed)
    send["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={key_id}/{scope}, "
        f"SignedHeaders={signed_names}, Signature={signature}")

    url = f"https://{ENDPOINT}{path}" + (f"?{query}" if query else "")
    return requests.request(method, url, data=payload or None, headers=send,
                            timeout=60)


def call(method: str, key: str, *, data: bytes | None = None,
         headers: dict[str, str] | None = None, region: str | None = None,
         key_id: str | None = None, secret: str | None = None,
         query: str = "") -> requests.Response:
    """
    То же, что `request`, но сам подбирает РЕГИОН по ответу сервера.

    ⚠️ Регион не угадываем и не держим списком: S3 при несовпадении отвечает
    «the region ... is wrong; expecting 'kz1'» — то есть называет верный сам.
    Один повтор, дальше ошибка отдаётся как есть.
    """
    used = region or DEFAULT_REGION
    answer = request(method, key, data=data, headers=headers, region=used,
                     key_id=key_id, secret=secret, query=query)
    if answer.status_code == 400:
        found = WRONG_REGION.search(answer.text or "")
        if found and found.group(1) != used:
            answer = request(method, key, data=data, headers=headers,
                             region=found.group(1), key_id=key_id,
                             secret=secret, query=query)
    return answer


def put(key: str, data: bytes, content_type: str = "application/json",
        **kwargs) -> requests.Response:
    """Положить файл в бакет."""
    headers = {"content-type": content_type}
    answer = call("PUT", key, data=data, headers=headers, **kwargs)
    if answer.status_code not in (200, 201):
        raise S3Error(f"PUT {key}: {answer.status_code}\n{answer.text[:400]}")
    return answer


def public_url(key: str) -> str:
    """Адрес, по которому файл увидит игрок."""
    return f"https://{ENDPOINT}/{BUCKET}/{urllib.parse.quote(key, safe='/')}"
