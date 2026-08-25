import os
import sys
import io
import threading
from typing import List, Optional, Dict
from PIL import Image, ImageTk

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES

from audio_tagger import (
    AudioMetadata,
    save_audio_cover,
    clean_text_promos,
    is_supported_audio,
    is_supported_image,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS
)

# Set appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class TrackItem:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.meta = AudioMetadata(filepath)
        self.new_image_bytes: Optional[bytes] = None
        self.new_image_path: Optional[str] = None
        self.remove_cover: bool = False

    def reload(self):
        self.meta = AudioMetadata(self.filepath)
        self.new_image_bytes = None
        self.new_image_path = None
        self.remove_cover = False


class AudioCoverApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("Audio Cover Editor — by deynnnW")
        self.geometry("1100, 720")
        self.minsize(960, 640)

        # Set window icon if exists
        icon_ico = resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(icon_ico):
            try:
                self.iconbitmap(icon_ico)
            except Exception:
                pass

        self.tracks: List[TrackItem] = []
        self.selected_indices: List[int] = []
        self.current_preview_image: Optional[ImageTk.PhotoImage] = None
        self.new_preview_image: Optional[ImageTk.PhotoImage] = None
        self.placeholder_img = self._create_placeholder_image("Нет обложки")

        self.new_global_cover_bytes: Optional[bytes] = None
        self.new_global_cover_path: Optional[str] = None

        self._build_ui()
        self._setup_dnd()

    def _create_placeholder_image(self, text: str = "Нет обложки", size=(160, 160)) -> ctk.CTkImage:
        img = Image.new("RGBA", size, (40, 44, 52, 255))
        # Use simple CTkImage
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)

    def _build_ui(self):
        # Configure grid layout (1 row, 2 columns: Left list panel, Right edit panel)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)  # Status bar
        self.grid_columnconfigure(0, weight=4, minsize=400)
        self.grid_columnconfigure(1, weight=5, minsize=500)

        # ---------------- LEFT PANEL (Track List) ----------------
        left_frame = ctk.CTkFrame(self, corner_radius=10)
        left_frame.grid(row=0, column=0, padx=(12, 6), pady=(12, 6), sticky="nsew")
        left_frame.grid_rowconfigure(2, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # Top buttons in left frame
        btn_top_box = ctk.CTkFrame(left_frame, fg_color="transparent")
        btn_top_box.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        btn_top_box.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_add_files = ctk.CTkButton(
            btn_top_box, text="🎵 Добавить треки", command=self.on_add_files,
            fg_color="#3B82F6", hover_color="#2563EB", font=ctk.CTkFont(weight="bold")
        )
        self.btn_add_files.grid(row=0, column=0, padx=3, pady=2, sticky="ew")

        self.btn_add_folder = ctk.CTkButton(
            btn_top_box, text="📁 Добавить папку", command=self.on_add_folder,
            fg_color="#4F46E5", hover_color="#4338CA", font=ctk.CTkFont(weight="bold")
        )
        self.btn_add_folder.grid(row=0, column=1, padx=3, pady=2, sticky="ew")

        self.btn_clear_list = ctk.CTkButton(
            btn_top_box, text="🗑️ Очистить", command=self.on_clear_tracks,
            fg_color="#EF4444", hover_color="#DC2626", width=80
        )
        self.btn_clear_list.grid(row=0, column=2, padx=3, pady=2, sticky="ew")

        # Filter / Search bar
        search_box = ctk.CTkFrame(left_frame, fg_color="transparent")
        search_box.grid(row=1, column=0, padx=10, pady=4, sticky="ew")
        search_box.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            search_box, placeholder_text="🔍 Поиск по названию или исполнителю..."
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.search_entry.bind("<KeyRelease>", self.on_search_filter)

        # Track List (Treeview with custom dark theme)
        tree_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        tree_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Treeview styling
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#1E293B",
            foreground="#F8FAFC",
            fieldbackground="#1E293B",
            rowheight=32,
            font=("Segoe UI", 10),
            borderwidth=0
        )
        style.configure(
            "Treeview.Heading",
            background="#334155",
            foreground="#F8FAFC",
            font=("Segoe UI", 10, "bold"),
            borderwidth=1
        )
        style.map(
            "Treeview",
            background=[("selected", "#3B82F6")],
            foreground=[("selected", "#FFFFFF")]
        )

        columns = ("title", "artist", "format", "cover")
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="extended", style="Treeview"
        )
        self.tree.heading("title", text="Название / Файл", anchor="w")
        self.tree.heading("artist", text="Исполнитель", anchor="w")
        self.tree.heading("format", text="Формат", anchor="center")
        self.tree.heading("cover", text="Обложка", anchor="center")

        self.tree.column("title", width=180, stretch=True)
        self.tree.column("artist", width=130, stretch=True)
        self.tree.column("format", width=60, anchor="center")
        self.tree.column("cover", width=80, anchor="center")

        tree_scroll = ctk.CTkScrollbar(tree_frame, orientation="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Bottom info in left panel
        self.lbl_list_count = ctk.CTkLabel(
            left_frame, text="Треков: 0 (перетащите файлы сюда ⬇️)", text_color="#94A3B8"
        )
        self.lbl_list_count.grid(row=3, column=0, padx=10, pady=(2, 8), sticky="w")

        # ---------------- RIGHT PANEL (Editor & Preview) ----------------
        right_frame = ctk.CTkScrollableFrame(self, corner_radius=10)
        right_frame.grid(row=0, column=1, padx=(6, 12), pady=(12, 6), sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)

        # Covers Preview Section (Header)
        lbl_covers_title = ctk.CTkLabel(
            right_frame, text="Управление обложкой", font=ctk.CTkFont(size=16, weight="bold")
        )
        lbl_covers_title.grid(row=0, column=0, padx=12, pady=(8, 6), sticky="w")

        # Covers side-by-side frame
        covers_box = ctk.CTkFrame(right_frame, fg_color="#1E293B", corner_radius=8)
        covers_box.grid(row=1, column=0, padx=10, pady=4, sticky="ew")
        covers_box.grid_columnconfigure((0, 1), weight=1)

        # --- Current Cover ---
        curr_box = ctk.CTkFrame(covers_box, fg_color="transparent")
        curr_box.grid(row=0, column=0, padx=10, pady=10, sticky="n")
        
        ctk.CTkLabel(curr_box, text="Текущая обложка", font=ctk.CTkFont(weight="bold")).pack(pady=(0, 4))
        self.lbl_current_img = ctk.CTkLabel(curr_box, text="", image=self.placeholder_img)
        self.lbl_current_img.pack(pady=4)

        self.lbl_current_info = ctk.CTkLabel(curr_box, text="Нет изображения", text_color="#94A3B8", font=ctk.CTkFont(size=11))
        self.lbl_current_info.pack(pady=2)

        self.btn_export_cover = ctk.CTkButton(
            curr_box, text="💾 Экспорт в файл", command=self.on_export_current_cover,
            fg_color="#475569", hover_color="#334155", height=26, font=ctk.CTkFont(size=11)
        )
        self.btn_export_cover.pack(pady=(4, 0))

        # --- New Cover ---
        new_box = ctk.CTkFrame(covers_box, fg_color="transparent")
        new_box.grid(row=0, column=1, padx=10, pady=10, sticky="n")

        ctk.CTkLabel(new_box, text="Новая обложка", font=ctk.CTkFont(weight="bold")).pack(pady=(0, 4))
        self.lbl_new_img = ctk.CTkLabel(new_box, text="", image=self.placeholder_img)
        self.lbl_new_img.pack(pady=4)

        self.lbl_new_info = ctk.CTkLabel(new_box, text="Перетащите картинку сюда", text_color="#94A3B8", font=ctk.CTkFont(size=11))
        self.lbl_new_info.pack(pady=2)

        btn_img_actions = ctk.CTkFrame(new_box, fg_color="transparent")
        btn_img_actions.pack(pady=(4, 0))

        self.btn_choose_img = ctk.CTkButton(
            btn_img_actions, text="🖼️ Выбрать", command=self.on_choose_image,
            fg_color="#10B981", hover_color="#059669", height=26, width=85, font=ctk.CTkFont(size=11, weight="bold")
        )
        self.btn_choose_img.pack(side="left", padx=2)

        self.btn_del_cover = ctk.CTkButton(
            btn_img_actions, text="❌ Убрать", command=self.on_remove_cover_click,
            fg_color="#EF4444", hover_color="#DC2626", height=26, width=80, font=ctk.CTkFont(size=11)
        )
        self.btn_del_cover.pack(side="left", padx=2)

        # ---------------- METADATA SECTION ----------------
        lbl_meta_title = ctk.CTkLabel(
            right_frame, text="Теги и информация о треке", font=ctk.CTkFont(size=15, weight="bold")
        )
        lbl_meta_title.grid(row=2, column=0, padx=12, pady=(16, 4), sticky="w")

        meta_form = ctk.CTkFrame(right_frame, fg_color="#1E293B", corner_radius=8)
        meta_form.grid(row=3, column=0, padx=10, pady=4, sticky="ew")
        meta_form.grid_columnconfigure(1, weight=1)

        # Title
        ctk.CTkLabel(meta_form, text="Название:", anchor="w").grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")
        self.entry_title = ctk.CTkEntry(meta_form, placeholder_text="Название трека")
        self.entry_title.grid(row=0, column=1, padx=10, pady=(10, 4), sticky="ew")

        # Artist
        ctk.CTkLabel(meta_form, text="Исполнитель:", anchor="w").grid(row=1, column=0, padx=10, pady=4, sticky="w")
        self.entry_artist = ctk.CTkEntry(meta_form, placeholder_text="Исполнитель / Группа")
        self.entry_artist.grid(row=1, column=1, padx=10, pady=4, sticky="ew")

        # Album
        ctk.CTkLabel(meta_form, text="Альбом:", anchor="w").grid(row=2, column=0, padx=10, pady=4, sticky="w")
        self.entry_album = ctk.CTkEntry(meta_form, placeholder_text="Альбом")
        self.entry_album.grid(row=2, column=1, padx=10, pady=4, sticky="ew")

        # Path info
        ctk.CTkLabel(meta_form, text="Путь:", anchor="w").grid(row=3, column=0, padx=10, pady=(4, 10), sticky="w")
        self.lbl_filepath = ctk.CTkLabel(
            meta_form, text="Файл не выбран", text_color="#94A3B8", anchor="w", wraplength=400
        )
        self.lbl_filepath.grid(row=3, column=1, padx=10, pady=(4, 10), sticky="w")

        # Quick Cleanup button
        self.btn_clean_promos = ctk.CTkButton(
            meta_form, text="🪄 Очистить названия от рекламы (SkySound, PromoDJ и др.)",
            command=self.on_clean_current_fields, fg_color="#6366F1", hover_color="#4F46E5", height=28
        )
        self.btn_clean_promos.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

        # Auto Clean Checkbox
        self.chk_auto_clean = ctk.CTkCheckBox(
            right_frame, text="Всегда автоматически убирать промо-сайты при сохранении",
            font=ctk.CTkFont(size=12)
        )
        self.chk_auto_clean.select()
        self.chk_auto_clean.grid(row=4, column=0, padx=12, pady=(8, 8), sticky="w")

        # ---------------- ACTION BUTTONS ----------------
        actions_box = ctk.CTkFrame(right_frame, fg_color="transparent")
        actions_box.grid(row=5, column=0, padx=10, pady=(10, 14), sticky="ew")
        actions_box.grid_columnconfigure((0, 1), weight=1)

        self.btn_save_single = ctk.CTkButton(
            actions_box, text="💾 Сохранить для выбранного трека", command=self.on_save_single,
            fg_color="#10B981", hover_color="#059669", height=38, font=ctk.CTkFont(size=13, weight="bold")
        )
        self.btn_save_single.grid(row=0, column=0, columnspan=2, pady=4, sticky="ew")

        self.btn_save_batch = ctk.CTkButton(
            actions_box, text="🚀 Применить эту новую обложку ко ВСЕМ трекам в списке",
            command=self.on_apply_cover_to_all, fg_color="#3B82F6", hover_color="#2563EB", height=34
        )
        self.btn_save_batch.grid(row=1, column=0, columnspan=2, pady=4, sticky="ew")

        self.btn_batch_clean_all = ctk.CTkButton(
            actions_box, text="🧹 Очистить мусорные теги у ВСЕХ файлов в списке",
            command=self.on_batch_clean_tags, fg_color="#475569", hover_color="#334155", height=30
        )
        self.btn_batch_clean_all.grid(row=2, column=0, columnspan=2, pady=4, sticky="ew")

        # ---------------- STATUS BAR ----------------
        status_bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#0F172A")
        status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        status_bar.grid_columnconfigure(0, weight=1)

        self.lbl_status = ctk.CTkLabel(
            status_bar, text="Audio Cover Editor by deynnnW — Готово к работе. Перетащите треки сюда.",
            text_color="#94A3B8", font=ctk.CTkFont(size=12), anchor="w"
        )
        self.lbl_status.grid(row=0, column=0, padx=12, pady=2, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(status_bar, width=160, height=10)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, padx=12, pady=6, sticky="e")
        self.progress_bar.grid_remove()

    def _setup_dnd(self):
        # Register drag and drop on the whole window
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self.on_drop_files)

    def on_drop_files(self, event):
        files = self.tk.splitlist(event.data)
        audio_files = []
        image_files = []

        for f in files:
            f = os.path.normpath(f)
            if os.path.isdir(f):
                for root_dir, _, filenames in os.walk(f):
                    for fn in filenames:
                        fp = os.path.join(root_dir, fn)
                        if is_supported_audio(fp):
                            audio_files.append(fp)
            elif is_supported_audio(f):
                audio_files.append(f)
            elif is_supported_image(f):
                image_files.append(f)

        if audio_files:
            self._add_audio_filepaths(audio_files)

        if image_files:
            # Set the first dropped image as new cover
            self._set_new_cover_from_file(image_files[0])

    def on_add_files(self):
        types = [
            ("Аудиофайлы (*.mp3, *.flac, *.m4a, *.ogg)", "*.mp3 *.flac *.m4a *.mp4 *.ogg *.opus"),
            ("Все файлы", "*.*")
        ]
        files = filedialog.askopenfilenames(title="Выберите аудиофайлы", filetypes=types)
        if files:
            self._add_audio_filepaths(files)

    def on_add_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку с музыкой")
        if folder:
            audio_files = []
            for root_dir, _, filenames in os.walk(folder):
                for fn in filenames:
                    fp = os.path.join(root_dir, fn)
                    if is_supported_audio(fp):
                        audio_files.append(fp)
            if audio_files:
                self._add_audio_filepaths(audio_files)
            else:
                messagebox.showinfo("Папка пуста", "В выбранной папке не найдено поддерживаемых аудиофайлов.")

    def _add_audio_filepaths(self, paths: List[str]):
        existing_paths = {t.filepath for t in self.tracks}
        added_count = 0

        for p in paths:
            if p not in existing_paths:
                track = TrackItem(p)
                self.tracks.append(track)
                existing_paths.add(p)
                added_count += 1

        self._refresh_tree()
        self.lbl_status.configure(text=f"Добавлено файлов: {added_count}. Всего в списке: {len(self.tracks)}.")

        # Select first item if nothing selected
        if self.tracks and not self.tree.selection():
            first_id = self.tree.get_children()[0]
            self.tree.selection_set(first_id)
            self.tree.focus(first_id)
            self._load_track_to_ui(0)

    def on_clear_tracks(self):
        self.tracks.clear()
        self.selected_indices.clear()
        self._refresh_tree()
        self._clear_ui_fields()
        self.lbl_status.configure(text="Список очищен.")

    def _refresh_tree(self, filter_query: str = ""):
        self.tree.delete(*self.tree.get_children())
        query = filter_query.lower()

        for idx, t in enumerate(self.tracks):
            title = t.meta.title or t.filename
            artist = t.meta.artist or "—"
            ext = t.meta.ext.upper().replace(".", "")
            cover_status = "🖼️ Есть" if t.meta.has_cover else "❌ Нет"

            if query:
                if query not in title.lower() and query not in artist.lower() and query not in t.filename.lower():
                    continue

            self.tree.insert("", "end", iid=str(idx), values=(title, artist, ext, cover_status))

        self.lbl_list_count.configure(text=f"Всего треков: {len(self.tracks)}")

    def on_search_filter(self, event=None):
        query = self.search_entry.get().strip()
        self._refresh_tree(filter_query=query)

    def on_tree_select(self, event=None):
        selected_iids = self.tree.selection()
        if not selected_iids:
            return

        self.selected_indices = [int(iid) for iid in selected_iids]
        if self.selected_indices:
            self._load_track_to_ui(self.selected_indices[0])

    def _load_track_to_ui(self, track_idx: int):
        if track_idx < 0 or track_idx >= len(self.tracks):
            return

        t = self.tracks[track_idx]
        self.entry_title.delete(0, "end")
        self.entry_title.insert(0, t.meta.title or os.path.splitext(t.filename)[0])

        self.entry_artist.delete(0, "end")
        self.entry_artist.insert(0, t.meta.artist or "")

        self.entry_album.delete(0, "end")
        self.entry_album.insert(0, t.meta.album or "")

        self.lbl_filepath.configure(text=t.filepath)

        # Show current cover
        if t.meta.has_cover and t.meta.cover_bytes:
            try:
                pil_img = Image.open(io.BytesIO(t.meta.cover_bytes))
                w, h = pil_img.size
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(160, 160))
                self.lbl_current_img.configure(image=ctk_img)
                self.lbl_current_img.image = ctk_img
                size_kb = len(t.meta.cover_bytes) // 1024
                self.lbl_current_info.configure(text=f"{w}x{h} px ({size_kb} KB, {t.meta.cover_mime or 'IMG'})")
            except Exception as e:
                self.lbl_current_img.configure(image=self.placeholder_img)
                self.lbl_current_info.configure(text=f"Ошибка чтения: {e}")
        else:
            self.lbl_current_img.configure(image=self.placeholder_img)
            self.lbl_current_info.configure(text="Нет встроенной обложки")

        # Show new cover state for this track or global pending
        if t.remove_cover:
            self.lbl_new_img.configure(image=self.placeholder_img)
            self.lbl_new_info.configure(text="Обложка будет удалена ❌")
        elif t.new_image_bytes:
            self._render_new_cover_image(t.new_image_bytes, t.new_image_path)
        elif self.new_global_cover_bytes:
            self._render_new_cover_image(self.new_global_cover_bytes, self.new_global_cover_path)
        else:
            self.lbl_new_img.configure(image=self.placeholder_img)
            self.lbl_new_info.configure(text="Перетащите картинку сюда")

    def _render_new_cover_image(self, img_bytes: bytes, filepath: Optional[str] = None):
        try:
            pil_img = Image.open(io.BytesIO(img_bytes))
            w, h = pil_img.size
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(160, 160))
            self.lbl_new_img.configure(image=ctk_img)
            self.lbl_new_img.image = ctk_img
            name = os.path.basename(filepath) if filepath else "Новая"
            self.lbl_new_info.configure(text=f"{name} ({w}x{h} px)")
        except Exception as e:
            self.lbl_new_img.configure(image=self.placeholder_img)
            self.lbl_new_info.configure(text=f"Ошибка: {e}")

    def _clear_ui_fields(self):
        self.entry_title.delete(0, "end")
        self.entry_artist.delete(0, "end")
        self.entry_album.delete(0, "end")
        self.lbl_filepath.configure(text="Файл не выбран")
        self.lbl_current_img.configure(image=self.placeholder_img)
        self.lbl_current_info.configure(text="Нет изображения")
        self.lbl_new_img.configure(image=self.placeholder_img)
        self.lbl_new_info.configure(text="Перетащите картинку сюда")

    def on_choose_image(self):
        types = [
            ("Изображения (*.jpg, *.png, *.webp, *.jfif, *.bmp)", "*.jpg *.jpeg *.png *.webp *.jfif *.bmp"),
            ("Все файлы", "*.*")
        ]
        img_path = filedialog.askopenfilename(title="Выберите новую обложку для трека", filetypes=types)
        if img_path:
            self._set_new_cover_from_file(img_path)

    def _set_new_cover_from_file(self, img_path: str):
        try:
            with open(img_path, "rb") as f:
                img_bytes = f.read()

            self.new_global_cover_bytes = img_bytes
            self.new_global_cover_path = img_path

            # Update selected track
            if self.selected_indices:
                for idx in self.selected_indices:
                    t = self.tracks[idx]
                    t.new_image_bytes = img_bytes
                    t.new_image_path = img_path
                    t.remove_cover = False

            self._render_new_cover_image(img_bytes, img_path)
            self.lbl_status.configure(text=f"Выбрана новая обложка: {os.path.basename(img_path)}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать изображение: {e}")

    def on_remove_cover_click(self):
        if not self.selected_indices:
            messagebox.showwarning("Внимание", "Выберите трек из списка!")
            return

        for idx in self.selected_indices:
            t = self.tracks[idx]
            t.new_image_bytes = None
            t.new_image_path = None
            t.remove_cover = True

        self.lbl_new_img.configure(image=self.placeholder_img)
        self.lbl_new_info.configure(text="Обложка будет удалена ❌")
        self.lbl_status.configure(text="Установлен флаг удаления обложки для выбранного(ых) трека(ов).")

    def on_export_current_cover(self):
        if not self.selected_indices:
            return
        t = self.tracks[self.selected_indices[0]]
        if not t.meta.has_cover or not t.meta.cover_bytes:
            messagebox.showinfo("Экспорт", "У этого трека нет встроенной обложки.")
            return

        ext = ".jpg" if t.meta.cover_mime == "image/jpeg" else ".png"
        default_name = f"{os.path.splitext(t.filename)[0]}_cover{ext}"
        out_path = filedialog.asksaveasfilename(
            title="Сохранить обложку как...",
            initialfile=default_name,
            filetypes=[("Image file", f"*{ext}"), ("All files", "*.*")]
        )
        if out_path:
            try:
                with open(out_path, "wb") as f:
                    f.write(t.meta.cover_bytes)
                messagebox.showinfo("Успех", f"Обложка успешно экспортирована в:\n{out_path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")

    def on_clean_current_fields(self):
        title = self.entry_title.get()
        artist = self.entry_artist.get()
        album = self.entry_album.get()

        self.entry_title.delete(0, "end")
        self.entry_title.insert(0, clean_text_promos(title))

        self.entry_artist.delete(0, "end")
        self.entry_artist.insert(0, clean_text_promos(artist))

        self.entry_album.delete(0, "end")
        self.entry_album.insert(0, clean_text_promos(album))

        self.lbl_status.configure(text="Поля очищены от промо-тегов и сайтов.")

    def on_save_single(self):
        if not self.selected_indices:
            messagebox.showwarning("Внимание", "Выберите трек из списка!")
            return

        idx = self.selected_indices[0]
        track = self.tracks[idx]

        new_title = self.entry_title.get().strip()
        new_artist = self.entry_artist.get().strip()
        new_album = self.entry_album.get().strip()
        auto_clean = bool(self.chk_auto_clean.get())

        # Determine which image to save
        img_bytes = track.new_image_bytes or self.new_global_cover_bytes
        remove_cov = track.remove_cover

        success = save_audio_cover(
            filepath=track.filepath,
            new_image_bytes=img_bytes,
            remove_cover=remove_cov,
            new_title=new_title,
            new_artist=new_artist,
            new_album=new_album,
            clean_promos=auto_clean
        )

        if success:
            track.reload()
            self._refresh_tree(filter_query=self.search_entry.get().strip())
            self.tree.selection_set(str(idx))
            self._load_track_to_ui(idx)
            self.lbl_status.configure(text=f"✅ Файл '{track.filename}' успешно сохранен!")
            messagebox.showinfo("Успех", f"Файл '{track.filename}' успешно обновлен!")
        else:
            messagebox.showerror("Ошибка", f"Не удалось сохранить изменения в файл '{track.filename}'.")

    def on_apply_cover_to_all(self):
        if not self.tracks:
            messagebox.showwarning("Внимание", "Список треков пуст!")
            return

        img_bytes = self.new_global_cover_bytes
        if not img_bytes and self.selected_indices:
            img_bytes = self.tracks[self.selected_indices[0]].new_image_bytes

        if not img_bytes:
            messagebox.showwarning("Внимание", "Сначала выберите новую картинку для обложки (кнопка 'Выбрать' или перетащите файл)!")
            return

        count = len(self.tracks)
        if not messagebox.askyesno("Подтверждение", f"Применить эту обложку ко всем {count} трекам в списке?"):
            return

        auto_clean = bool(self.chk_auto_clean.get())

        self._start_batch_thread(
            target_fn=self._batch_apply_cover_worker,
            args=(img_bytes, auto_clean),
            task_name="Применение обложки ко всем трекам"
        )

    def _batch_apply_cover_worker(self, img_bytes: bytes, auto_clean: bool):
        total = len(self.tracks)
        success_count = 0

        for i, track in enumerate(self.tracks):
            ok = save_audio_cover(
                filepath=track.filepath,
                new_image_bytes=img_bytes,
                remove_cover=False,
                clean_promos=auto_clean
            )
            if ok:
                success_count += 1
                track.reload()

            # Update progress
            progress = (i + 1) / total
            self.after(0, self._update_progress, progress, f"Обработка: {i + 1}/{total} ({track.filename})")

        self.after(0, self._batch_finished, success_count, total, "Обложка успешно обновлена")

    def on_batch_clean_tags(self):
        if not self.tracks:
            messagebox.showwarning("Внимание", "Список треков пуст!")
            return

        count = len(self.tracks)
        if not messagebox.askyesno("Подтверждение", f"Очистить рекламные теги (SkySound и др.) у всех {count} треков?"):
            return

        self._start_batch_thread(
            target_fn=self._batch_clean_tags_worker,
            args=(),
            task_name="Очистка тегов"
        )

    def _batch_clean_tags_worker(self):
        total = len(self.tracks)
        success_count = 0

        for i, track in enumerate(self.tracks):
            ok = save_audio_cover(
                filepath=track.filepath,
                clean_promos=True
            )
            if ok:
                success_count += 1
                track.reload()

            progress = (i + 1) / total
            self.after(0, self._update_progress, progress, f"Очистка тегов: {i + 1}/{total} ({track.filename})")

        self.after(0, self._batch_finished, success_count, total, "Теги успешно очищены")

    def _start_batch_thread(self, target_fn, args: tuple, task_name: str):
        self.progress_bar.grid()
        self.progress_bar.set(0)
        self.lbl_status.configure(text=f"Запуск: {task_name}...")
        self.btn_save_single.configure(state="disabled")
        self.btn_save_batch.configure(state="disabled")
        self.btn_batch_clean_all.configure(state="disabled")

        t = threading.Thread(target=target_fn, args=args, daemon=True)
        t.start()

    def _update_progress(self, val: float, status_text: str):
        self.progress_bar.set(val)
        self.lbl_status.configure(text=status_text)

    def _batch_finished(self, success: int, total: int, msg_prefix: str):
        self.progress_bar.grid_remove()
        self.btn_save_single.configure(state="normal")
        self.btn_save_batch.configure(state="normal")
        self.btn_batch_clean_all.configure(state="normal")

        self._refresh_tree(filter_query=self.search_entry.get().strip())
        if self.selected_indices:
            self._load_track_to_ui(self.selected_indices[0])

        final_msg = f"{msg_prefix} для {success} из {total} файлов."
        self.lbl_status.configure(text=f"🎉 {final_msg}")
        messagebox.showinfo("Готово", final_msg)


if __name__ == "__main__":
    app = AudioCoverApp()
    app.mainloop()
