## Dataloader

Утилита для загрузки файлов с SD-карты на S3.

### Важно для подключения к S3

Для успешного подключения к S3 предварительно нужно положить индивидуальные креды в файл ~/.aws/credentials

### Пример файла credentials
```
[default]
         aws_access_key_id = YOUR_ACCESS_KEY
         aws_secret_access_key = YOUR_SECRET_ACCESS_KEY
```

### Также необходимо установить следующие пакеты:

Для Ubuntu:
```bash
sudo apt update
sudo apt install libimage-exiftool-perl
```

Для macOS:
```bash
brew install exiftool
```

Если `brew` не установлен, то вот инструкция по установке: https://brew.sh/