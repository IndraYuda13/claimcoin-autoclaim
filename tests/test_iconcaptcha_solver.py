from __future__ import annotations

import base64
import io
import unittest

from PIL import Image, ImageDraw

from claimcoin_autoclaim.iconcaptcha_solver import solve_iconcaptcha_data_url


class IconCaptchaSolverTests(unittest.TestCase):
    def _build_canvas(self, labels: list[str]) -> str:
        width = 320
        height = 50
        cell_width = width // len(labels)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for index, label in enumerate(labels):
            left = index * cell_width + 10
            right = (index + 1) * cell_width - 10
            top = 8
            bottom = height - 8
            if label == "square":
                draw.rectangle((left, top, right, bottom), fill=(40, 40, 40, 255))
            elif label == "circle":
                draw.ellipse((left, top, right, bottom), fill=(40, 40, 40, 255))
            elif label == "triangle":
                draw.polygon(
                    [(left + (right - left) / 2, top), (right, bottom), (left, bottom)],
                    fill=(40, 40, 40, 255),
                )
            elif label == "diamond":
                draw.polygon(
                    [
                        (left + (right - left) / 2, top),
                        (right, top + (bottom - top) / 2),
                        (left + (right - left) / 2, bottom),
                        (left, top + (bottom - top) / 2),
                    ],
                    fill=(40, 40, 40, 255),
                )
            else:
                raise ValueError(label)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    def test_selects_unique_cell_against_four_of_a_kind(self) -> None:
        data_url = self._build_canvas(["circle", "square", "square", "square", "square"])
        result = solve_iconcaptcha_data_url(data_url)
        self.assertEqual(result.selected_cell_number, 1)
        self.assertEqual(len(result.groups), 2)

    def test_selects_unique_cell_in_two_two_one_shape(self) -> None:
        data_url = self._build_canvas(["square", "circle", "circle", "triangle", "triangle"])
        result = solve_iconcaptcha_data_url(data_url)
        self.assertEqual(result.selected_cell_number, 1)
        self.assertEqual(sorted(len(group) for group in result.groups), [1, 2, 2])


if __name__ == "__main__":
    unittest.main()
