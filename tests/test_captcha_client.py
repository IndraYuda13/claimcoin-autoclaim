from __future__ import annotations

import base64
import io
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from claimcoin_autoclaim.clients.captcha_client import CaptchaClient
from claimcoin_autoclaim.config import CaptchaConfig, app_config_from_dict


class CaptchaClientIconCaptchaApiTests(unittest.TestCase):
    def _build_canvas_data_url(self) -> str:
        width = 320
        height = 50
        cell_width = width // 5
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for index in range(5):
            left = index * cell_width + 10
            right = (index + 1) * cell_width - 10
            top = 8
            bottom = height - 8
            if index == 3:
                draw.ellipse((left, top, right, bottom), fill=(40, 40, 40, 255))
            else:
                draw.rectangle((left, top, right, bottom), fill=(40, 40, 40, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    def test_config_loads_iconcaptcha_endpoint(self) -> None:
        config = app_config_from_dict({"captcha": {"iconcaptcha_endpoint": "http://127.0.0.1:8091/solve"}})

        self.assertEqual(config.captcha.iconcaptcha_endpoint, "http://127.0.0.1:8091/solve")

    def test_iconcaptcha_endpoint_is_preferred(self) -> None:
        response = Mock()
        response.json.return_value = {
            "success": True,
            "position": 4,
            "x": 224,
            "y": 25,
            "centerX": 224,
            "centerY": 25,
            "start": 192,
            "end": 256,
            "confidence": 0.91,
            "cell_count": 5,
            "width": 320,
            "height": 50,
            "groups": [[0, 1, 2, 3], [4]],
        }
        response.raise_for_status.return_value = None

        with patch("claimcoin_autoclaim.clients.captcha_client.requests.post", return_value=response) as post:
            result = CaptchaClient(
                CaptchaConfig(iconcaptcha_endpoint="http://127.0.0.1:8091/solve")
            ).solve_iconcaptcha_detailed("data:image/png;base64,abc", cell_count=5, domain_hint="claimcoin")

        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["canvas_data_url"], "data:image/png;base64,abc")
        self.assertEqual(payload["cell_count"], 5)
        self.assertEqual(payload["similarity_threshold"], 20.0)
        self.assertEqual(payload["return_debug"], True)
        self.assertEqual(result["provider"], "api")
        self.assertEqual(result["selected_cell_number"], 4)
        self.assertEqual(result["click_x"], 224)
        self.assertEqual(result["click_y"], 25)
        self.assertEqual(result["confidence"], 0.91)

    def test_iconcaptcha_endpoint_failure_falls_back_to_internal_solver(self) -> None:
        canvas = self._build_canvas_data_url()
        with patch("claimcoin_autoclaim.clients.captcha_client.requests.post", side_effect=RuntimeError("api down")):
            result = CaptchaClient(
                CaptchaConfig(iconcaptcha_endpoint="http://127.0.0.1:8091/solve", iconcaptcha_similarity_threshold=20.0)
            ).solve_iconcaptcha_detailed(canvas, cell_count=5, domain_hint="claimcoin")

        self.assertEqual(result["provider"], "internal")
        self.assertEqual(result["selected_cell_number"], 4)
        self.assertEqual(result["click_x"], 224)
        self.assertEqual(result["click_y"], 25)


if __name__ == "__main__":
    unittest.main()
