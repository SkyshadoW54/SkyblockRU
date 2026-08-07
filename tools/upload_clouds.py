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

⚠️ Ключ в репозиторий не кладём: он публичный. Тот же порядок, что у ключей
облака словарей (см. tools/s3.py).

Запуск:
    python tools/upload_clouds.py --dry     показать, что поедет
    python tools/upload_clouds.py           залить и СВЕРИТЬ
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


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dry = "--dry" in sys.argv

    key_file = os.environ.get("GDRIVE_KEY_FILE")
    file_id = os.environ.get("GDRIVE_FILE_ID")
    if not key_file or not file_id:
        print("нет GDRIVE_KEY_FILE / GDRIVE_FILE_ID в окружении")
        print("⚠️ В PowerShell переменные пользователя новая сессия видит не сразу:")
        print("   $env:GDRIVE_KEY_FILE=[Environment]::GetEnvironmentVariable("
              "'GDRIVE_KEY_FILE','User')")
        return 1
    if not Path(key_file).is_file():
        print(f"файла ключа нет: {key_file}")
        return 1
    if not ARCHIVE.is_file():
        print(f"нет архива: {ARCHIVE}")
        print("сперва: python tools/pack.py")
        return 1

    data = ARCHIVE.read_bytes()
    print(f"файл:   {ARCHIVE.name}")
    print(f"размер: {len(data) / 1024 / 1024:.2f} МБ")
    print(f"sha256: {sha256(data)[:16]}")

    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    drive = drive_service(key_file)
    try:
        before = drive.files().get(
            fileId=file_id, fields="name,size,modifiedTime").execute()
    except HttpError as error:
        print(f"\nне вижу файл на диске: {error.resp.status}")
        print("  404 — не расшарен на сервисный аккаунт либо неверный id")
        print("  403 — Drive API не включён в проекте")
        return 1
    print(f"\nна диске сейчас: {before.get('name')}  "
          f"{int(before.get('size') or 0) / 1024 / 1024:.2f} МБ  "
          f"от {before.get('modifiedTime')}")

    if dry:
        print("\nсухой прогон: ничего не отправлено")
        return 0

    media = MediaFileUpload(str(ARCHIVE), mimetype="application/zip",
                            resumable=True)
    drive.files().update(fileId=file_id, media_body=media).execute()

    # ⚠️ СВЕРЯЕМ СКАЧИВАНИЕМ, а не верим ответу. «Залилось» и «на диске лежит
    # то, что нужно» — разные утверждения: это записанное правило проекта,
    # и стоило оно нам розданного релиза с чужими никами.
    from googleapiclient.http import MediaIoBaseDownload
    import io

    buffer = io.BytesIO()
    request = drive.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    got = buffer.getvalue()

    print(f"\nскачал обратно: {len(got) / 1024 / 1024:.2f} МБ  "
          f"sha256 {sha256(got)[:16]}")
    if got != data:
        print("СЛОМАНО: на диске лежит НЕ то, что отправляли")
        return 1
    print("байты сошлись — на диске ровно наш архив")
    print(f"\nссылка не менялась: https://drive.google.com/file/d/{file_id}/view")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
