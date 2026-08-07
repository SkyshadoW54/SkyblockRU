"""
Обновить архив раздачи на облачных дисках — БЕЗ смены ссылки.

Зачем. Ссылка на архив уходит в описание видео, в пост телеграма и в шапку
репозитория. Значит менять её нельзя НИКОГДА: протухшая ссылка хуже
отсутствующей — человек по ней приходит и упирается в «файл не найден».

⚠️ Поэтому файл на диске СОЗДАЁТ ИГРОК, руками и один раз, а инструмент
только меняет его содержимое (`files.update` по тому же fileId). Так ссылка
привязана к id и остаётся прежней.

⚠️ И вторая причина того же порядка: у сервисного аккаунта НЕТ своего места
на диске (квота 0 без Workspace). Создай он файл сам — упёрся бы в
`storageQuotaExceeded`, а владельцем стал бы он, а не игрок.

Что нужно в окружении:
    GDRIVE_KEY_FILE   путь к JSON-ключу сервисного аккаунта (ВНЕ репозитория)
    GDRIVE_FILE_ID    id файла из ссылки: .../file/d/<ID>/view
    YADISK_TOKEN      OAuth-токен Яндекс.Диска
    YADISK_PATH       путь файла на Диске: disk:/SkyblockRU-все-версии.zip

⚠️ Ключи в репозиторий не кладём: он публичный. Тот же порядок, что у ключей
облака словарей (см. tools/s3.py).

⚠️ ПРО ЯНДЕКС: документация НЕ говорит, переживает ли публичная ссылка
перезапись, а формулировка про overwrite=true звучит как «удалить и записать
заново». Проверено опытом на временном файле 07.08: ссылка СОХРАНЯЕТСЯ.
Значит можно лить по тому же пути, и ссылка в описании видео останется живой.

Запуск:
    python tools/upload_clouds.py --dry     показать, что поедет
    python tools/upload_clouds.py           залить в оба диска и СВЕРИТЬ
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "release" / "packs" / "SkyblockRU-все-версии.zip"

SCOPES = ["https://www.googleapis.com/auth/drive"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def drive_service(key_file: str):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        key_file, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


YA_API = "https://cloud-api.yandex.net/v1/disk"


def yandex(data: bytes, dry: bool) -> bool:
    """Обновить архив на Яндекс.Диске по тому же пути.

    ⚠️ Путь ТОТ ЖЕ и файл НЕ удаляем: публичная ссылка привязана к файлу,
    и перезапись её сохраняет (проверено опытом — см. шапку модуля).
    Переместить файл или создать заново — значит выдать новую ссылку,
    а старая уже ушла в описание видео.
    """
    import requests

    token = os.environ.get("YADISK_TOKEN")
    path = os.environ.get("YADISK_PATH")
    print("\n=== ЯНДЕКС.ДИСК ===")
    if not token or not path:
        print("  нет YADISK_TOKEN / YADISK_PATH — пропускаю")
        return True
    head = {"Authorization": "OAuth " + token}

    was = requests.get(f"{YA_API}/resources", headers=head,
                       params={"path": path}, timeout=30)
    if was.status_code == 200:
        info = was.json()
        print(f"  сейчас там: {info.get('size', 0)/1024/1024:.2f} МБ  "
              f"от {info.get('modified')}")
        link = info.get("public_url")
        print(f"  ссылка: {link or 'НЕ опубликован'}")
    elif was.status_code == 404:
        print("  файла ещё нет — будет создан")
    else:
        print(f"  не спросить: {was.status_code} {was.text[:200]}")
        return False

    if dry:
        return True

    ask = requests.get(f"{YA_API}/resources/upload", headers=head,
                       params={"path": path, "overwrite": "true"}, timeout=30)
    if ask.status_code != 200:
        print(f"  не дали адрес для заливки: {ask.status_code} {ask.text[:200]}")
        return False
    put = requests.put(ask.json()["href"], data=data, timeout=600)
    if put.status_code not in (201, 202):
        print(f"  заливка не прошла: {put.status_code}")
        return False

    # ⚠️ Сверяем СКАЧИВАНИЕМ: «залилось» и «лежит то, что нужно» — разные
    # утверждения. Ссылку на скачивание спрашиваем у API, а не собираем сами.
    link = requests.get(f"{YA_API}/resources/download", headers=head,
                        params={"path": path}, timeout=30)
    if link.status_code != 200:
        print("  залито, но проверить не смог — нет ссылки на скачивание")
        return False
    got = requests.get(link.json()["href"], timeout=600).content
    print(f"  скачал обратно: {len(got)/1024/1024:.2f} МБ  sha256 {sha256(got)[:16]}")
    if got != data:
        print("  СЛОМАНО: на диске лежит НЕ то, что отправляли")
        return False
    print("  байты сошлись")

    now = requests.get(f"{YA_API}/resources", headers=head,
                       params={"path": path}, timeout=30)
    public = now.json().get("public_url") if now.status_code == 200 else None
    if public:
        print(f"  ссылка не менялась: {public}")
    else:
        # файл был не опубликован — публикуем и показываем ссылку
        requests.put(f"{YA_API}/resources/publish", headers=head,
                     params={"path": path}, timeout=30)
        again = requests.get(f"{YA_API}/resources", headers=head,
                             params={"path": path}, timeout=30)
        print(f"  опубликовал: {again.json().get('public_url')}")
    return True


def google(data: bytes, dry: bool) -> bool:
    """Обновить архив на Google Drive по тому же fileId — ссылка не меняется."""
    key_file = os.environ.get("GDRIVE_KEY_FILE")
    file_id = os.environ.get("GDRIVE_FILE_ID")
    print("=== GOOGLE DRIVE ===")
    if not key_file or not file_id:
        print("  нет GDRIVE_KEY_FILE / GDRIVE_FILE_ID - пропускаю")
        return True
    if not Path(key_file).is_file():
        print(f"  файла ключа нет: {key_file}")
        return False

    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    import io as _io

    drive = drive_service(key_file)
    try:
        before = drive.files().get(
            fileId=file_id, fields="name,size,modifiedTime").execute()
    except HttpError as error:
        print(f"  не вижу файл: {error.resp.status}")
        print("  404 - не расшарен на сервисный аккаунт либо неверный id")
        print("  403 - Drive API не включён в проекте")
        return False
    print(f"  сейчас там: {int(before.get('size') or 0)/1024/1024:.2f} МБ  "
          f"от {before.get('modifiedTime')}")
    if dry:
        return True

    media = MediaFileUpload(str(ARCHIVE), mimetype="application/zip", resumable=True)
    drive.files().update(fileId=file_id, media_body=media).execute()

    # ⚠️ СВЕРЯЕМ СКАЧИВАНИЕМ, а не верим ответу: «залилось» и «лежит нужное» -
    # разные утверждения. Записанное правило проекта, и стоило оно нам
    # розданного релиза с чужими никами.
    buffer = _io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, drive.files().get_media(fileId=file_id))
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    got = buffer.getvalue()
    print(f"  скачал обратно: {len(got)/1024/1024:.2f} МБ  sha256 {sha256(got)[:16]}")
    if got != data:
        print("  СЛОМАНО: на диске лежит НЕ то, что отправляли")
        return False
    print("  байты сошлись")
    print(f"  ссылка не менялась: https://drive.google.com/file/d/{file_id}/view")
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dry = "--dry" in sys.argv

    if not ARCHIVE.is_file():
        print(f"нет архива: {ARCHIVE}")
        print("сперва: python tools/pack.py")
        return 1
    data = ARCHIVE.read_bytes()
    print(f"файл:   {ARCHIVE.name}")
    print(f"размер: {len(data)/1024/1024:.2f} МБ")
    print(f"sha256: {sha256(data)[:16]}")
    print()

    ok = google(data, dry)
    ok = yandex(data, dry) and ok

    print()
    if dry:
        print("сухой прогон: ничего не отправлено")
    elif ok:
        print("оба диска обновлены, ссылки прежние")
    else:
        print("СЛОМАНО - смотри пометки выше")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
