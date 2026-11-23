"""Smart artwork cropper tests (16:9 -> 1:1)."""

from __future__ import annotations

import io

from PIL import Image

from melodine.services.artwork import crop_to_square


def jpeg_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def letterboxed_16_9() -> bytes:
    """1280x720 black frame with a 720x720 colored square in the middle."""
    image = Image.new("RGB", (1280, 720), (0, 0, 0))
    content = Image.new("RGB", (720, 720), (180, 60, 200))
    image.paste(content, (280, 0))
    return jpeg_bytes(image)


class TestCropToSquare:
    def test_letterboxed_becomes_square(self):
        result = crop_to_square(letterboxed_16_9(), size=1000)
        image = Image.open(io.BytesIO(result))
        assert image.size == (1000, 1000)
        # Corners must be part of the colored content, not black bars.
        assert image.getpixel((10, 10)) != (0, 0, 0)
        assert image.getpixel((990, 990)) != (0, 0, 0)

    def test_full_bleed_16_9_center_cropped(self):
        gradient = Image.new("RGB", (1280, 720))
        for x in range(1280):
            for y in range(0, 720, 8):
                gradient.paste((x // 5, y // 3, 90), (x, y, 1, 8))
        result = crop_to_square(jpeg_bytes(gradient), size=500)
        image = Image.open(io.BytesIO(result))
        assert image.size == (500, 500)

    def test_already_square_resized(self):
        square = Image.new("RGB", (640, 640), (10, 200, 30))
        result = crop_to_square(jpeg_bytes(square), size=1000)
        image = Image.open(io.BytesIO(result))
        assert image.size == (1000, 1000)

    def test_all_black_image_does_not_crash(self):
        black = jpeg_bytes(Image.new("RGB", (1280, 720), (0, 0, 0)))
        result = crop_to_square(black, size=300)
        image = Image.open(io.BytesIO(result))
        assert image.size == (300, 300)

    def test_small_content_box_falls_back_to_full_frame(self):
        # A tiny bright dot in the corner must not produce a 3x3 crop.
        image = Image.new("RGB", (1000, 1000), (5, 5, 5))
        image.paste((255, 255, 255), (5, 5, 12, 12))
        result = crop_to_square(jpeg_bytes(image), size=400)
        out = Image.open(io.BytesIO(result))
        assert out.size == (400, 400)

    def test_garbage_bytes_returned_unchanged(self):
        garbage = b"not-an-image-at-all"
        assert crop_to_square(garbage) == garbage

    def test_vertical_video_in_horizontal_frame(self):
        image = Image.new("RGB", (1280, 720), (0, 0, 0))
        content = Image.new("RGB", (405, 720), (200, 120, 40))
        image.paste(content, (437, 0))
        result = crop_to_square(jpeg_bytes(image), size=600)
        out = Image.open(io.BytesIO(result))
        assert out.size == (600, 600)
        assert out.getpixel((300, 300)) != (0, 0, 0)
