import os
import re
import io
import time
import urllib.request
from typing import Optional, Dict, Any, Callable
from PIL import Image

import yt_dlp
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = None


def sanitize_filename(name: str) -> str:
    """Removes illegal filesystem characters"""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """
    Extracts video/track info without downloading.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
        'skip_download': True
    }
    if FFMPEG_PATH:
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            is_playlist = 'entries' in info and info['entries'] is not None

            title = info.get('title', 'Unknown Title')
            uploader = info.get('uploader') or info.get('artist') or info.get('channel') or 'Unknown Artist'
            duration_sec = info.get('duration', 0) or 0
            mins = int(duration_sec // 60)
            secs = int(duration_sec % 60)
            duration_str = f"{mins}:{secs:02d}" if duration_sec else "N/A"

            thumbnail = info.get('thumbnail')
            if not thumbnail and 'thumbnails' in info and info['thumbnails']:
                thumbnail = info['thumbnails'][-1].get('url')

            entries_count = len(list(info.get('entries', []))) if is_playlist else 1

            return {
                'url': url,
                'title': title,
                'uploader': uploader,
                'duration_str': duration_str,
                'thumbnail_url': thumbnail,
                'is_playlist': is_playlist,
                'entries_count': entries_count,
                'description': info.get('description', '')[:200]
            }
    except Exception as e:
        print(f"Error extracting info for {url}: {e}")
        return None


def fetch_thumbnail_bytes(thumbnail_url: str) -> Optional[bytes]:
    """Downloads thumbnail and converts to high-quality JPEG bytes"""
    if not thumbnail_url:
        return None
    try:
        req = urllib.request.Request(
            thumbnail_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            raw_bytes = response.read()

        img = Image.open(io.BytesIO(raw_bytes))
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        if max(img.size) > 1400:
            img.thumbnail((1400, 1400), Image.Resampling.LANCZOS)

        out_io = io.BytesIO()
        img.save(out_io, format="JPEG", quality=92, optimize=True)
        return out_io.getvalue()
    except Exception as e:
        print(f"Error fetching thumbnail: {e}")
        return None


def embed_cover_art(filepath: str, image_bytes: bytes, title: str, artist: str):
    """Embeds cover art and tags into MP3/FLAC/M4A"""
    ext = os.path.splitext(filepath)[1].lower()
    if not os.path.exists(filepath) or not image_bytes:
        return

    try:
        if ext == ".mp3":
            try:
                tags = ID3(filepath)
            except ID3NoHeaderError:
                tags = ID3()

            tags.delall("APIC")
            tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=image_bytes
                )
            )
            tags.save(filepath, v2_version=3)

            try:
                ez = EasyID3(filepath)
            except Exception:
                ez = EasyID3()
            ez["title"] = title
            ez["artist"] = artist
            ez.save(filepath, v2_version=3)

        elif ext == ".flac":
            audio = FLAC(filepath)
            audio.clear_pictures()
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.desc = "Cover"
            pic.data = image_bytes
            audio.add_picture(pic)
            audio["title"] = [title]
            audio["artist"] = [artist]
            audio.save()

        elif ext in (".m4a", ".mp4"):
            audio = MP4(filepath)
            if audio.tags is None:
                audio.add_tags()
            audio.tags["covr"] = [MP4Cover(image_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.tags["\xa9nam"] = [title]
            audio.tags["\xa9ART"] = [artist]
            audio.save()

    except Exception as e:
        print(f"Error embedding cover in {filepath}: {e}")


class MediaDownloader:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def download(
        self,
        url: str,
        format_type: str = "mp3_320",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        self.is_cancelled = False
        os.makedirs(self.output_dir, exist_ok=True)

        if log_callback:
            log_callback("Получение информации о треке...")

        info = extract_media_info(url)
        if not info:
            if log_callback:
                log_callback("Ошибка: Не удалось получить данные по ссылке.")
            return False

        title = info['title']
        uploader = info['uploader']
        thumb_bytes = fetch_thumbnail_bytes(info.get('thumbnail_url', ''))

        out_template = os.path.join(self.output_dir, '%(title)s.%(ext)s')

        def ytdl_hook(d):
            if self.is_cancelled:
                raise Exception("Download cancelled by user")

            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                percent = (downloaded / total * 100) if total else 0
                speed = d.get('speed', 0) or 0
                speed_str = f"{speed / (1024 * 1024):.2f} MB/s" if speed else "—"
                eta = d.get('eta', 0) or 0
                eta_str = f"{eta}s" if eta else "—"

                if progress_callback:
                    progress_callback({
                        'status': 'downloading',
                        'percent': percent,
                        'downloaded': downloaded,
                        'total': total,
                        'speed_str': speed_str,
                        'eta_str': eta_str,
                        'filename': d.get('filename', '')
                    })

            elif d['status'] == 'finished':
                if progress_callback:
                    progress_callback({
                        'status': 'converting',
                        'percent': 100,
                        'filename': d.get('filename', '')
                    })

        ydl_opts: Dict[str, Any] = {
            'outtmpl': out_template,
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [ytdl_hook],
            'nocheckcertificate': True,
            'ignoreerrors': False,
        }
        if FFMPEG_PATH:
            ydl_opts['ffmpeg_location'] = FFMPEG_PATH

        if format_type == "mp3_320":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
        elif format_type == "flac":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'flac',
            }]
        elif format_type == "m4a":
            ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '256',
            }]
        elif format_type == "mp4_video":
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

        try:
            if log_callback:
                log_callback(f"Начало загрузки: {title} ({format_type.upper()})")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if thumb_bytes and format_type in ("mp3_320", "flac", "m4a"):
                target_ext = ".mp3" if format_type == "mp3_320" else (".flac" if format_type == "flac" else ".m4a")
                for fn in os.listdir(self.output_dir):
                    if fn.endswith(target_ext):
                        full_p = os.path.join(self.output_dir, fn)
                        if time.time() - os.path.getmtime(full_p) < 60:
                            embed_cover_art(full_p, thumb_bytes, title, uploader)

            if log_callback:
                log_callback(f"✅ Успешно сохранено: {title}")
            return True

        except Exception as e:
            if "cancelled" in str(e).lower():
                if log_callback:
                    log_callback("Загрузка отменена.")
            else:
                if log_callback:
                    log_callback(f"Ошибка: {e}")
            return False
