import os
import sys
import io
import threading
import subprocess
from typing import Optional, Dict, Any
from PIL import Image

import customtkinter as ctk
from tkinter import filedialog, messagebox

from downloader import (
    MediaDownloader,
    extract_media_info,
    fetch_thumbnail_bytes
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class UniversalGrabberApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Universal Audio Grabber — Загрузчик аудио и видео (320kbps + Обложки)")
        self.geometry("860, 680")
        self.minsize(800, 600)

        # Output folder (Default to User Downloads / Music)
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Music_Downloads")
        self.output_dir = default_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.downloader = MediaDownloader(self.output_dir)
        self.current_media_info: Optional[Dict[str, Any]] = None
        self.is_downloading = False

        self.placeholder_img = self._create_placeholder_image()
        self._build_ui()

        # Clipboard auto-monitor
        self.last_clipboard = ""
        self._check_clipboard_loop()

    def _create_placeholder_image(self, size=(220, 130)) -> ctk.CTkImage:
        img = Image.new("RGBA", size, (25, 30, 42, 255))
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ---------------- HEADER ----------------
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=20, pady=(16, 8), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="⚡ UNIVERSAL AUDIO GRABBER",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#F8FAFC"
        )
        title_lbl.grid(row=0, column=0, sticky="w")

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text="Загрузка музыки и видео с YouTube, SoundCloud, VK, TikTok и 1000+ сайтов в Hi-Res качестве с авто-обложками",
            font=ctk.CTkFont(size=12),
            text_color="#94A3B8"
        )
        sub_lbl.grid(row=1, column=0, sticky="w")

        # ---------------- INPUT URL BOX ----------------
        url_frame = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=10)
        url_frame.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        url_frame.grid_columnconfigure(0, weight=1)

        input_row = ctk.CTkFrame(url_frame, fg_color="transparent")
        input_row.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        input_row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="🔗 Вставьте ссылку на трек, видео или плейлист...",
            height=40,
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.url_entry.bind("<Return>", lambda e: self.on_fetch_info())

        self.btn_paste = ctk.CTkButton(
            input_row, text="📋 Вставить", width=95, height=40,
            command=self.on_paste_click, fg_color="#475569", hover_color="#334155"
        )
        self.btn_paste.grid(row=0, column=1, padx=4)

        self.btn_fetch = ctk.CTkButton(
            input_row, text="🔍 Проверить", width=110, height=40,
            command=self.on_fetch_info, fg_color="#3B82F6", hover_color="#2563EB", font=ctk.CTkFont(weight="bold")
        )
        self.btn_fetch.grid(row=0, column=2, padx=(4, 0))

        # Auto-paste check & Supported badge
        opts_row = ctk.CTkFrame(url_frame, fg_color="transparent")
        opts_row.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")

        self.chk_auto_paste = ctk.CTkCheckBox(
            opts_row, text="Авто-вставка ссылки из буфера", font=ctk.CTkFont(size=12)
        )
        self.chk_auto_paste.select()
        self.chk_auto_paste.pack(side="left")

        ctk.CTkLabel(
            opts_row, text="Поддерживает: YouTube, SoundCloud, VK, TikTok, Bandcamp, Twitch, etc.",
            text_color="#64748B", font=ctk.CTkFont(size=11)
        ).pack(side="right")

        # ---------------- MAIN CONTENT (Preview & Settings) ----------------
        main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_scroll.grid(row=2, column=0, padx=20, pady=6, sticky="nsew")
        main_scroll.grid_columnconfigure(0, weight=1)

        # PREVIEW CARD
        self.preview_card = ctk.CTkFrame(main_scroll, fg_color="#0F172A", corner_radius=10, border_width=1, border_color="#334155")
        self.preview_card.grid(row=0, column=0, pady=6, sticky="ew")
        self.preview_card.grid_columnconfigure(1, weight=1)

        self.lbl_thumb = ctk.CTkLabel(self.preview_card, text="", image=self.placeholder_img)
        self.lbl_thumb.grid(row=0, column=0, rowspan=4, padx=12, pady=12, sticky="nw")

        self.lbl_track_title = ctk.CTkLabel(
            self.preview_card, text="Название появится здесь после проверки ссылки",
            font=ctk.CTkFont(size=15, weight="bold"), text_color="#F8FAFC", anchor="w", wraplength=480
        )
        self.lbl_track_title.grid(row=0, column=1, padx=(4, 12), pady=(12, 2), sticky="w")

        self.lbl_track_artist = ctk.CTkLabel(
            self.preview_card, text="Автор / Исполнитель: —",
            font=ctk.CTkFont(size=13), text_color="#94A3B8", anchor="w"
        )
        self.lbl_track_artist.grid(row=1, column=1, padx=(4, 12), pady=2, sticky="w")

        self.lbl_track_meta = ctk.CTkLabel(
            self.preview_card, text="Длительность: — | Тип: —",
            font=ctk.CTkFont(size=12), text_color="#64748B", anchor="w"
        )
        self.lbl_track_meta.grid(row=2, column=1, padx=(4, 12), pady=2, sticky="w")

        # FORMAT SELECTION
        format_card = ctk.CTkFrame(main_scroll, fg_color="#1E293B", corner_radius=10)
        format_card.grid(row=1, column=0, pady=8, sticky="ew")
        format_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            format_card, text="Формат сохранения:", font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, padx=12, pady=10, sticky="w")

        self.combo_format = ctk.CTkSegmentedButton(
            format_card,
            values=[
                "🎵 MP3 320 kbps (Лучший)",
                "💎 FLAC (Lossless)",
                "🎧 M4A / AAC",
                "🎬 MP4 Video"
            ]
        )
        self.combo_format.set("🎵 MP3 320 kbps (Лучший)")
        self.combo_format.grid(row=0, column=1, padx=12, pady=10, sticky="ew")

        # FOLDER SELECTION
        folder_card = ctk.CTkFrame(main_scroll, fg_color="#1E293B", corner_radius=10)
        folder_card.grid(row=2, column=0, pady=6, sticky="ew")
        folder_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            folder_card, text="Папка сохранения:", font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, padx=12, pady=10, sticky="w")

        self.lbl_folder_path = ctk.CTkLabel(
            folder_card, text=self.output_dir, text_color="#94A3B8", anchor="w", wraplength=450
        )
        self.lbl_folder_path.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        btn_browse_folder = ctk.CTkButton(
            folder_card, text="📁 Обзор", width=80, command=self.on_browse_folder,
            fg_color="#475569", hover_color="#334155"
        )
        btn_browse_folder.grid(row=0, column=2, padx=6, pady=10)

        btn_open_folder = ctk.CTkButton(
            folder_card, text="📂 Открыть", width=85, command=self.on_open_folder,
            fg_color="#334155", hover_color="#1E293B"
        )
        btn_open_folder.grid(row=0, column=3, padx=(0, 12), pady=10)

        # DOWNLOAD BUTTON & PROGRESS
        self.btn_download = ctk.CTkButton(
            main_scroll,
            text="🚀 СКАЧАТЬ В МАКСИМАЛЬНОМ КАЧЕСТВЕ",
            command=self.on_download_click,
            height=46,
            fg_color="#10B981",
            hover_color="#059669",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        self.btn_download.grid(row=3, column=0, pady=(12, 6), sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(main_scroll, height=14, corner_radius=7)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=4, column=0, pady=4, sticky="ew")

        self.lbl_speed_status = ctk.CTkLabel(
            main_scroll, text="Готово к загрузке", text_color="#94A3B8", font=ctk.CTkFont(size=12)
        )
        self.lbl_speed_status.grid(row=5, column=0, pady=(2, 6))

        # LOG BOX
        self.log_box = ctk.CTkTextbox(main_scroll, height=90, fg_color="#090D16", text_color="#94A3B8", font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.grid(row=6, column=0, pady=6, sticky="ew")
        self.log_box.insert("end", "[Info] Universal Audio Grabber запущен. Вставьте ссылку для скачивания.\n")

    def _check_clipboard_loop(self):
        if bool(self.chk_auto_paste.get()) and not self.is_downloading:
            try:
                clip = self.clipboard_get().strip()
                if clip != self.last_clipboard and (
                    "youtube.com" in clip or "youtu.be" in clip or
                    "soundcloud.com" in clip or "vk.com" in clip or
                    "tiktok.com" in clip or "bandcamp.com" in clip or
                    "http://" in clip or "https://" in clip
                ):
                    self.last_clipboard = clip
                    self.url_entry.delete(0, "end")
                    self.url_entry.insert(0, clip)
                    self.on_fetch_info()
            except Exception:
                pass
        self.after(1500, self._check_clipboard_loop)

    def on_paste_click(self):
        try:
            clip = self.clipboard_get().strip()
            if clip:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, clip)
                self.on_fetch_info()
        except Exception:
            pass

    def on_fetch_info(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Внимание", "Пожалуйста, вставьте ссылку на аудио или видео!")
            return

        self.lbl_track_title.configure(text="🔍 Получение информации о треке...")
        self.btn_fetch.configure(state="disabled")

        def fetch_worker():
            info = extract_media_info(url)
            self.after(0, self._update_preview_ui, info)

        threading.Thread(target=fetch_worker, daemon=True).start()

    def _update_preview_ui(self, info: Optional[Dict[str, Any]]):
        self.btn_fetch.configure(state="normal")
        if not info:
            self.lbl_track_title.configure(text="❌ Не удалось получить информацию по этой ссылке")
            self.lbl_track_artist.configure(text="Проверьте правильность URL")
            self.lbl_thumb.configure(image=self.placeholder_img)
            return

        self.current_media_info = info
        self.lbl_track_title.configure(text=info['title'])
        self.lbl_track_artist.configure(text=f"Автор: {info['uploader']}")
        is_p = "Плейлист" if info['is_playlist'] else "Одиночный трек/видео"
        self.lbl_track_meta.configure(text=f"Длительность: {info['duration_str']} | Тип: {is_p}")

        # Fetch and show thumbnail
        thumb_url = info.get('thumbnail_url')
        if thumb_url:
            def thumb_worker():
                t_bytes = fetch_thumbnail_bytes(thumb_url)
                if t_bytes:
                    try:
                        pil_img = Image.open(io.BytesIO(t_bytes))
                        pil_img.thumbnail((220, 130), Image.Resampling.LANCZOS)
                        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
                        self.after(0, self._set_thumb_image, ctk_img)
                    except Exception:
                        pass
            threading.Thread(target=thumb_worker, daemon=True).start()

    def _set_thumb_image(self, ctk_img):
        self.lbl_thumb.configure(image=ctk_img)
        self.lbl_thumb.image = ctk_img

    def on_browse_folder(self):
        chosen = filedialog.askdirectory(title="Выберите папку для сохранения", initialdir=self.output_dir)
        if chosen:
            self.output_dir = chosen
            self.downloader.output_dir = chosen
            self.lbl_folder_path.configure(text=chosen)

    def on_open_folder(self):
        if os.path.exists(self.output_dir):
            os.startfile(self.output_dir)

    def on_download_click(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Внимание", "Вставьте ссылку для скачивания!")
            return

        if self.is_downloading:
            self.downloader.cancel()
            self.btn_download.configure(text="🚀 СКАЧАТЬ В МАКСИМАЛЬНОМ КАЧЕСТВЕ", fg_color="#10B981")
            self.is_downloading = False
            return

        fmt_selection = self.combo_format.get()
        if "MP3" in fmt_selection:
            fmt_type = "mp3_320"
        elif "FLAC" in fmt_selection:
            fmt_type = "flac"
        elif "M4A" in fmt_selection:
            fmt_type = "m4a"
        else:
            fmt_type = "mp4_video"

        self.is_downloading = True
        self.btn_download.configure(text="⛔ ОСТАНОВИТЬ ЗАГРУЗКУ", fg_color="#EF4444")
        self.progress_bar.set(0)

        def download_thread():
            def progress_cb(data):
                percent = data.get('percent', 0) / 100.0
                status = data.get('status')
                speed = data.get('speed_str', '')
                eta = data.get('eta_str', '')
                if status == 'downloading':
                    txt = f"Скачивание: {data.get('percent', 0):.1f}% | Скорость: {speed} | Осталось: {eta}"
                else:
                    txt = "Конвертация в высокое качество и вшивание обложки..."
                self.after(0, self._update_download_progress, percent, txt)

            def log_cb(msg):
                self.after(0, self._append_log, msg)

            success = self.downloader.download(
                url=url,
                format_type=fmt_type,
                progress_callback=progress_cb,
                log_callback=log_cb
            )
            self.after(0, self._download_finished, success)

        threading.Thread(target=download_thread, daemon=True).start()

    def _update_download_progress(self, val: float, status_text: str):
        self.progress_bar.set(val)
        self.lbl_speed_status.configure(text=status_text)

    def _append_log(self, msg: str):
        self.log_box.insert("end", f"{msg}\n")
        self.log_box.see("end")

    def _download_finished(self, success: bool):
        self.is_downloading = False
        self.btn_download.configure(text="🚀 СКАЧАТЬ В МАКСИМАЛЬНОМ КАЧЕСТВЕ", fg_color="#10B981")
        if success:
            self.progress_bar.set(1.0)
            self.lbl_speed_status.configure(text="🎉 Загрузка успешно завершена! Файл сохранен с обложкой.")
            messagebox.showinfo("Успех", f"Файл успешно скачан и сохранен в:\n{self.output_dir}")
        else:
            self.lbl_speed_status.configure(text="Загрузка прервана или завершилась с ошибкой.")


if __name__ == "__main__":
    app = UniversalGrabberApp()
    app.mainloop()
