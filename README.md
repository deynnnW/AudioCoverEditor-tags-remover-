# 🎧 Audio Suite — Media Tools by deynnnW

Набор удобных инструментов для работы с музыкой и мультимедиа с современным тёмным интерфейсом и готовыми `.exe` файлами для Windows.

---

## 📁 Структура репозитория

```text
├── AudioCoverEditor/         # Редактор и удалитель обложек, очистка рекламных тегов
│   ├── dist/
│   │   └── AudioCoverEditor.exe
│   ├── app.py
│   ├── audio_tagger.py
│   ├── build.bat / run.bat
│   └── README.md
│
└── UniversalAudioGrabber/    # Загрузчик аудио и видео в 320kbps с обложками
    ├── dist/
    │   └── UniversalAudioGrabber.exe
    ├── universal_grabber.py
    ├── downloader.py
    ├── build_grabber.bat / run_grabber.bat
    └── README.md
```

---

## 🛠️ Проекты

### 1. 🖼️ [Audio Cover Editor](./AudioCoverEditor)
- **Смена и удаление обложек**: Поддержка MP3, FLAC, M4A, OGG.
- **Очистка от промо-тегов**: Автоматическое удаление ссылок (SkySound, PromoDJ и др.).
- **Пакетная обработка**: Установка одной обложки сразу на все песни в папке.
- **Drag & Drop**: Перетаскивание файлов и картинок в окно программы.

### 2. ⚡ [Universal Audio Grabber](./UniversalAudioGrabber)
- **Загрузка с 1000+ сервисов**: YouTube, SoundCloud, VK, TikTok, Bandcamp и др.
- **Форматы**: MP3 320 kbps (Hi-Res), FLAC (Lossless), M4A (AAC), MP4 Video.
- **Авто-вшивание обложек**: Автоматический поиск и вшивание HD-обложки в скачанный файл.
- **Умный буфер**: Автоматическое распознавание скопированных ссылок.

---

## 🚀 Быстрый запуск

Каждый проект содержит готовый `.exe` файл в папке `dist/`, который запускается сразу без необходимости устанавливать Python.

---

## 📄 Лицензия
MIT License © 2026 [deynnnW](https://github.com/deynnnW)
