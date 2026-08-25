import os
import unittest
from PIL import Image
import io
import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, APIC
from audio_tagger import AudioMetadata, save_audio_cover, clean_text_promos, process_image_to_bytes

class TestAudioTagger(unittest.TestCase):
    def setUp(self):
        self.test_mp3 = "test_sample.mp3"
        # Generate minimal valid MP3 frame
        # MPEG1 Layer III header + minimal audio frame
        mp3_header = bytes([
            0xFF, 0xFB, 0x90, 0x64, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        ]) * 20
        with open(self.test_mp3, "wb") as f:
            f.write(mp3_header)

        # Create dummy image
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        self.test_img_bytes = img_byte_arr.getvalue()

    def tearDown(self):
        if os.path.exists(self.test_mp3):
            try:
                os.remove(self.test_mp3)
            except Exception:
                pass

    def test_clean_promos(self):
        s1 = "Song Name [skysound]"
        self.assertEqual(clean_text_promos(s1), "Song Name")
        s2 = "Artist (SkySound) - Best"
        self.assertEqual(clean_text_promos(s2), "Artist - Best")
        s3 = "https://skysound.top Track"
        self.assertEqual(clean_text_promos(s3), "Track")

    def test_embed_and_read_mp3_cover(self):
        # Save cover and tags
        ok = save_audio_cover(
            self.test_mp3,
            new_image_bytes=self.test_img_bytes,
            new_title="My Cool Song [skysound]",
            new_artist="Great Artist",
            new_album="Best Album",
            clean_promos=True
        )
        self.assertTrue(ok)

        # Read back
        meta = AudioMetadata(self.test_mp3)
        self.assertTrue(meta.has_cover)
        self.assertIsNotNone(meta.cover_bytes)
        self.assertEqual(meta.title, "My Cool Song")
        self.assertEqual(meta.artist, "Great Artist")
        self.assertEqual(meta.album, "Best Album")

    def test_remove_cover(self):
        # Save cover
        save_audio_cover(self.test_mp3, new_image_bytes=self.test_img_bytes)
        meta = AudioMetadata(self.test_mp3)
        self.assertTrue(meta.has_cover)

        # Remove cover
        save_audio_cover(self.test_mp3, remove_cover=True)
        meta2 = AudioMetadata(self.test_mp3)
        self.assertFalse(meta2.has_cover)

if __name__ == "__main__":
    unittest.main()
