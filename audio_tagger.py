import io
import os
import re
import base64
from typing import Optional, Tuple
from PIL import Image

import mutagen
from mutagen.id3 import (
    ID3, APIC, TIT2, TPE1, TALB, COMM, ID3NoHeaderError
)
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

SUPPORTED_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.mp4', '.ogg', '.opus', '.wav', '.wma'}
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.jfif', '.ico'}


def is_supported_audio(filepath: str) -> bool:
    ext = os.path.splitext(filepath)[1].lower()
    return ext in SUPPORTED_EXTENSIONS


def is_supported_image(filepath: str) -> bool:
    ext = os.path.splitext(filepath)[1].lower()
    return ext in SUPPORTED_IMAGE_EXTENSIONS


def process_image_to_bytes(image_path_or_bytes, max_dim: int = 1400, format: str = "JPEG", quality: int = 92) -> Tuple[bytes, str]:
    """
    Reads image, converts RGBA to RGB if JPEG, resizes if larger than max_dim,
    and returns (image_bytes, mime_type).
    """
    if isinstance(image_path_or_bytes, (bytes, bytearray)):
        img = Image.open(io.BytesIO(image_path_or_bytes))
    else:
        img = Image.open(image_path_or_bytes)

    if img.mode in ("RGBA", "LA", "P") and format.upper() in ("JPEG", "JPG"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            background.paste(img, mask=img.split()[-1])
        else:
            background.paste(img)
        img = background
    elif img.mode != "RGB" and format.upper() in ("JPEG", "JPG"):
        img = img.convert("RGB")

    width, height = img.size
    if max(width, height) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    out_io = io.BytesIO()
    if format.upper() in ("JPEG", "JPG"):
        img.save(out_io, format="JPEG", quality=quality, optimize=True)
        mime = "image/jpeg"
    else:
        img.save(out_io, format="PNG", optimize=True)
        mime = "image/png"

    return out_io.getvalue(), mime


class AudioMetadata:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.ext = os.path.splitext(filepath)[1].lower()
        self.title = ""
        self.artist = ""
        self.album = ""
        self.comment = ""
        self.has_cover = False
        self.cover_bytes: Optional[bytes] = None
        self.cover_mime: Optional[str] = None
        self.duration_str = ""
        self.bitrate_str = ""
        self.load()

    def load(self):
        if not os.path.isfile(self.filepath):
            return

        # Attempt to get audio stream info if possible
        try:
            audio_info = mutagen.File(self.filepath)
            if audio_info and audio_info.info:
                if hasattr(audio_info.info, "length") and audio_info.info.length:
                    mins = int(audio_info.info.length // 60)
                    secs = int(audio_info.info.length % 60)
                    self.duration_str = f"{mins}:{secs:02d}"
                if hasattr(audio_info.info, "bitrate") and audio_info.info.bitrate:
                    self.bitrate_str = f"{int(audio_info.info.bitrate / 1000)} kbps"
        except Exception:
            pass

        try:
            if self.ext == ".mp3":
                self._load_mp3()
            elif self.ext == ".flac":
                self._load_flac()
            elif self.ext in (".m4a", ".mp4"):
                self._load_mp4()
            elif self.ext in (".ogg", ".opus"):
                self._load_ogg()
        except Exception as e:
            print(f"Error reading tags for {self.filepath}: {e}")

    def _load_mp3(self):
        try:
            tags = ID3(self.filepath)
        except ID3NoHeaderError:
            tags = None
        except Exception:
            tags = None

        if tags:
            self.title = str(tags.get("TIT2", ""))
            self.artist = str(tags.get("TPE1", ""))
            self.album = str(tags.get("TALB", ""))
            comments = tags.getall("COMM")
            if comments:
                self.comment = str(comments[0])

            apics = tags.getall("APIC")
            if apics:
                self.has_cover = True
                self.cover_bytes = apics[0].data
                self.cover_mime = apics[0].mime

    def _load_flac(self):
        try:
            audio = FLAC(self.filepath)
            if audio:
                self.title = str(audio.get("title", [""])[0])
                self.artist = str(audio.get("artist", [""])[0])
                self.album = str(audio.get("album", [""])[0])
                self.comment = str(audio.get("comment", [""])[0])

                if hasattr(audio, "pictures") and audio.pictures:
                    self.has_cover = True
                    self.cover_bytes = audio.pictures[0].data
                    self.cover_mime = audio.pictures[0].mime
        except Exception:
            pass

    def _load_mp4(self):
        try:
            audio = MP4(self.filepath)
            if audio and audio.tags:
                tags = audio.tags
                self.title = str(tags.get("\xa9nam", [""])[0]) if "\xa9nam" in tags else ""
                self.artist = str(tags.get("\xa9ART", [""])[0]) if "\xa9ART" in tags else ""
                self.album = str(tags.get("\xa9alb", [""])[0]) if "\xa9alb" in tags else ""
                self.comment = str(tags.get("\xa9cmt", [""])[0]) if "\xa9cmt" in tags else ""

                if "covr" in tags and tags["covr"]:
                    self.has_cover = True
                    covr = tags["covr"][0]
                    self.cover_bytes = bytes(covr)
                    self.cover_mime = "image/jpeg" if getattr(covr, "imageformat", None) == MP4Cover.FORMAT_JPEG else "image/png"
        except Exception:
            pass

    def _load_ogg(self):
        try:
            audio = mutagen.File(self.filepath)
            if audio:
                self.title = str(audio.get("TITLE", audio.get("title", [""]))[0])
                self.artist = str(audio.get("ARTIST", audio.get("artist", [""]))[0])
                self.album = str(audio.get("ALBUM", audio.get("album", [""]))[0])
                self.comment = str(audio.get("COMMENT", audio.get("comment", [""]))[0])

                pictures = audio.get("metadata_block_picture", [])
                if pictures:
                    try:
                        raw_data = base64.b64decode(pictures[0])
                        pic = Picture(raw_data)
                        self.has_cover = True
                        self.cover_bytes = pic.data
                        self.cover_mime = pic.mime
                    except Exception:
                        pass
        except Exception:
            pass


def clean_text_promos(text: str) -> str:
    """Cleans typical sky sound / downloader promo watermarks and URLs from string"""
    if not text:
        return ""
    cleaned = text
    # 1. Remove URLs (http://, https://, www., t.me/, vk.com/)
    cleaned = re.sub(r'https?://\S+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'www\.\S+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(t\.me|vk\.com)/\S+', '', cleaned, flags=re.IGNORECASE)
    
    # 2. Remove common site tags and keywords
    promo_patterns = [
        r'\[\s*(?:skysound|promodj|zaycev|mp3party|hitster|vmusice|muzofond|pesni|mp3|bassboosted|remix\s*by\s*\S+)\b[^\]]*\]',
        r'\(\s*(?:skysound|promodj|zaycev|mp3party|hitster|vmusice|muzofond|pesni|mp3|bassboosted|remix\s*by\s*\S+)\b[^\)]*\)',
        r'\{\s*(?:skysound|promodj|zaycev|mp3party|hitster|vmusice|muzofond|pesni|mp3|bassboosted)\b[^\}]*\}',
        r'\b(?:skysound(?:\.top|\.ru|\.me|\.org|\.cc|\.net)?|promodj|zaycev\.net|mp3party\.net)\b'
    ]
    for pattern in promo_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # 3. Clean leftovers
    cleaned = re.sub(r'[\[\(\{]\s*[\]\)\}]', '', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned.strip(" -_|\t\r\n")


def save_audio_cover(
    filepath: str,
    new_image_bytes: Optional[bytes] = None,
    image_format: str = "JPEG",
    remove_cover: bool = False,
    new_title: Optional[str] = None,
    new_artist: Optional[str] = None,
    new_album: Optional[str] = None,
    clean_promos: bool = False
) -> bool:
    """
    Saves new cover and/or updates metadata in the given audio file.
    If remove_cover=True, existing cover is removed.
    """
    ext = os.path.splitext(filepath)[1].lower()
    img_data = None
    img_mime = "image/jpeg"

    if new_image_bytes and not remove_cover:
        img_data, img_mime = process_image_to_bytes(new_image_bytes, format=image_format)

    if ext == ".mp3":
        return _save_mp3(filepath, img_data, img_mime, remove_cover, new_title, new_artist, new_album, clean_promos)
    elif ext == ".flac":
        return _save_flac(filepath, img_data, img_mime, remove_cover, new_title, new_artist, new_album, clean_promos)
    elif ext in (".m4a", ".mp4"):
        return _save_mp4(filepath, img_data, img_mime, remove_cover, new_title, new_artist, new_album, clean_promos)
    elif ext in (".ogg", ".opus"):
        return _save_ogg(filepath, img_data, img_mime, remove_cover, new_title, new_artist, new_album, clean_promos)
    return False


def _save_mp3(filepath, img_data, img_mime, remove_cover, title, artist, album, clean_promos):
    try:
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            tags = ID3()

        if remove_cover or img_data is not None:
            tags.delall("APIC")

        if img_data is not None and not remove_cover:
            tags.add(
                APIC(
                    encoding=3,  # UTF-8
                    mime=img_mime,
                    type=3,  # Front cover
                    desc="Cover",
                    data=img_data
                )
            )

        if title is not None:
            t = clean_text_promos(title) if clean_promos else title
            tags["TIT2"] = TIT2(encoding=3, text=t)
        elif clean_promos and "TIT2" in tags:
            tags["TIT2"] = TIT2(encoding=3, text=clean_text_promos(str(tags["TIT2"])))

        if artist is not None:
            a = clean_text_promos(artist) if clean_promos else artist
            tags["TPE1"] = TPE1(encoding=3, text=a)
        elif clean_promos and "TPE1" in tags:
            tags["TPE1"] = TPE1(encoding=3, text=clean_text_promos(str(tags["TPE1"])))

        if album is not None:
            al = clean_text_promos(album) if clean_promos else album
            tags["TALB"] = TALB(encoding=3, text=al)
        elif clean_promos and "TALB" in tags:
            tags["TALB"] = TALB(encoding=3, text=clean_text_promos(str(tags["TALB"])))

        if clean_promos:
            tags.delall("COMM")
            tags.delall("WXXX")
            tags.delall("WOAR")
            tags.delall("WOAF")
            tags.delall("WOAS")

        tags.save(filepath, v2_version=3)
        return True
    except Exception as e:
        print(f"Error saving MP3 {filepath}: {e}")
        return False


def _save_flac(filepath, img_data, img_mime, remove_cover, title, artist, album, clean_promos):
    try:
        audio = FLAC(filepath)
        if remove_cover or img_data is not None:
            audio.clear_pictures()

        if img_data is not None and not remove_cover:
            pic = Picture()
            pic.type = 3  # front cover
            pic.mime = img_mime
            pic.desc = "Cover"
            pic.data = img_data
            audio.add_picture(pic)

        if title is not None:
            audio["title"] = [clean_text_promos(title) if clean_promos else title]
        if artist is not None:
            audio["artist"] = [clean_text_promos(artist) if clean_promos else artist]
        if album is not None:
            audio["album"] = [clean_text_promos(album) if clean_promos else album]

        if clean_promos:
            if "comment" in audio:
                del audio["comment"]
            if "description" in audio:
                del audio["description"]

        audio.save()
        return True
    except Exception as e:
        print(f"Error saving FLAC {filepath}: {e}")
        return False


def _save_mp4(filepath, img_data, img_mime, remove_cover, title, artist, album, clean_promos):
    try:
        audio = MP4(filepath)
        if audio.tags is None:
            audio.add_tags()

        if remove_cover and "covr" in audio.tags:
            del audio.tags["covr"]

        if img_data is not None and not remove_cover:
            fmt = MP4Cover.FORMAT_JPEG if img_mime == "image/jpeg" else MP4Cover.FORMAT_PNG
            audio.tags["covr"] = [MP4Cover(img_data, imageformat=fmt)]

        if title is not None:
            audio.tags["\xa9nam"] = [clean_text_promos(title) if clean_promos else title]
        if artist is not None:
            audio.tags["\xa9ART"] = [clean_text_promos(artist) if clean_promos else artist]
        if album is not None:
            audio.tags["\xa9alb"] = [clean_text_promos(album) if clean_promos else album]

        if clean_promos and "\xa9cmt" in audio.tags:
            del audio.tags["\xa9cmt"]

        audio.save()
        return True
    except Exception as e:
        print(f"Error saving MP4/M4A {filepath}: {e}")
        return False


def _save_ogg(filepath, img_data, img_mime, remove_cover, title, artist, album, clean_promos):
    try:
        audio = mutagen.File(filepath)
        if audio is None:
            return False

        if remove_cover and "metadata_block_picture" in audio:
            del audio["metadata_block_picture"]

        if img_data is not None and not remove_cover:
            pic = Picture()
            pic.type = 3
            pic.mime = img_mime
            pic.desc = "Cover"
            pic.data = img_data
            pic_data = pic.write()
            encoded_data = base64.b64encode(pic_data).decode("ascii")
            audio["metadata_block_picture"] = [encoded_data]

        if title is not None:
            audio["title"] = [clean_text_promos(title) if clean_promos else title]
        if artist is not None:
            audio["artist"] = [clean_text_promos(artist) if clean_promos else artist]
        if album is not None:
            audio["album"] = [clean_text_promos(album) if clean_promos else album]

        if clean_promos and "comment" in audio:
            del audio["comment"]

        audio.save()
        return True
    except Exception as e:
        print(f"Error saving OGG {filepath}: {e}")
        return False
