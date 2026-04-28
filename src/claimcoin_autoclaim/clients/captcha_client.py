from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

import requests

from ..config import CaptchaConfig
from ..models import CaptchaChallenge


class CaptchaClient:
    def __init__(self, config: CaptchaConfig) -> None:
        self.config = config

    def solve(self, challenge: CaptchaChallenge) -> dict[str, Any]:
        if challenge.kind == "claimcoin_antibot":
            main_image = str(challenge.extra.get("main_image") or "")
            items = list(challenge.extra.get("items") or [])
            capture = challenge.extra.get("capture") if isinstance(challenge.extra.get("capture"), dict) else None
            return self.solve_antibot_detailed(
                main_image,
                items,
                domain_hint=str(challenge.extra.get("domain_hint") or challenge.extra.get("site") or "claimcoin"),
                capture=capture,
            )
        if challenge.kind in {"iconcaptcha", "claimcoin_iconcaptcha"}:
            canvas_data_url = str(challenge.extra.get("canvas_data_url") or "")
            cell_count = int(challenge.extra.get("cell_count") or 5)
            domain_hint = str(challenge.extra.get("domain_hint") or challenge.extra.get("site") or "claimcoin")
            return self.solve_iconcaptcha_detailed(
                canvas_data_url,
                cell_count=cell_count,
                domain_hint=domain_hint,
            )
        if challenge.kind in {"recaptchav3", "claimcoin_recaptchav3"}:
            token = self.solve_recaptchav3(
                sitekey=challenge.sitekey or self.config.recaptcha_v3_sitekey,
                page_url=challenge.page_url,
                action=challenge.action or self.config.recaptcha_v3_action,
            )
            return {"recaptchav3": token}

        if self.config.provider == "manual" or not self.config.endpoint:
            raise RuntimeError("captcha solver not configured")

        payload = {
            "kind": challenge.kind,
            "sitekey": challenge.sitekey,
            "page_url": challenge.page_url,
            "action": challenge.action,
            "extra": challenge.extra,
        }
        response = requests.post(
            self.config.endpoint,
            json=payload,
            timeout=self.config.timeout_seconds,
            headers={"x-api-key": self.config.api_key} if self.config.api_key else None,
        )
        response.raise_for_status()
        return response.json()

    def solve_antibot(self, main_image: str, items: list[dict[str, str]]) -> str:
        return str(self.solve_antibot_detailed(main_image, items).get("antibotlinks") or "")

    def solve_iconcaptcha_detailed(
        self,
        canvas_data_url: str,
        *,
        cell_count: int = 5,
        domain_hint: str = "claimcoin",
    ) -> dict[str, Any]:
        started_at = time.time()
        if self.config.iconcaptcha_endpoint:
            try:
                return self._finalize_iconcaptcha_result(
                    self._solve_iconcaptcha_via_endpoint(canvas_data_url, cell_count=cell_count),
                    provider="api",
                    started_at=started_at,
                    domain_hint=domain_hint,
                )
            except Exception:
                pass

        if self.config.iconcaptcha_core_python and self.config.iconcaptcha_core_src:
            try:
                return self._finalize_iconcaptcha_result(
                    self._solve_iconcaptcha_via_core(canvas_data_url, cell_count=cell_count),
                    provider="core",
                    started_at=started_at,
                    domain_hint=domain_hint,
                )
            except Exception:
                pass

        from ..iconcaptcha_solver import solve_iconcaptcha_data_url

        result = solve_iconcaptcha_data_url(
            canvas_data_url,
            cell_count=cell_count,
            similarity_threshold=self.config.iconcaptcha_similarity_threshold,
        )
        return self._finalize_iconcaptcha_result(
            {
                "success": True,
                "solution": result.to_dict(),
                "confidence": result.confidence,
                "meta": {"cell_count": cell_count},
            },
            provider="internal",
            started_at=started_at,
            domain_hint=domain_hint,
        )

    def solve_antibot_detailed(
        self,
        main_image: str,
        items: list[dict[str, str]],
        *,
        domain_hint: str = "claimcoin",
        capture: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started_at = time.time()
        if self.config.antibot_core_python and self.config.antibot_core_src:
            try:
                return self._finalize_antibot_result(
                    self._solve_antibot_via_core(main_image, items, domain_hint=domain_hint, capture=capture),
                    provider="core",
                    started_at=started_at,
                    domain_hint=domain_hint,
                )
            except Exception:
                if not self.config.antibot_endpoint:
                    raise

        if self.config.antibot_endpoint:
            payload = {
                "instruction_image_base64": main_image,
                "options": [
                    {"id": str(item["id"]), "image_base64": str(item["image"])}
                    for item in items
                ],
                "domain_hint": domain_hint,
                "debug": True,
            }
            if capture:
                payload["capture"] = capture
            try:
                response = requests.post(
                    self.config.antibot_endpoint,
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                return self._finalize_antibot_result(
                    data,
                    provider="api",
                    started_at=started_at,
                    domain_hint=domain_hint,
                )
            except Exception:
                raise

        if self.config.provider not in {"waryono", "custom", "hybrid"} or not self.config.endpoint or not self.config.api_key:
            raise RuntimeError("antibot solver is not configured")

        body: dict[str, Any] = {
            "apikey": self.config.api_key,
            "methods": "antibot",
            "main": main_image,
        }
        for item in items[:3]:
            body[str(item["id"])] = item["image"]

        request_id = self._submit_waryono(body)
        result = self._poll_waryono(request_id)
        ordered = str(result["result"]).replace(",", " ")
        return {
            "antibotlinks": ordered,
            "ordered_ids": [token for token in ordered.split() if token],
            "confidence": None,
            "provider": "waryono",
            "elapsed_ms": round((time.time() - started_at) * 1000, 2),
            "raw": result,
            "meta": {
                "domain_hint": domain_hint,
                "mode": "waryono",
            },
            "debug": None,
        }

    def _solve_antibot_via_core(
        self,
        main_image: str,
        items: list[dict[str, str]],
        *,
        domain_hint: str = "claimcoin",
        capture: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.config.antibot_core_python or not self.config.antibot_core_src:
            raise RuntimeError("antibot core solver is not configured")

        payload = {
            "instruction_image_base64": main_image,
            "options": [
                {"id": str(item["id"]), "image_base64": str(item["image"])}
                for item in items
            ],
            "domain_hint": domain_hint,
        }
        if capture:
            payload["capture"] = capture
        script = """
import json, sys
from antibot_image_solver.capture import CaptureRequest
from antibot_image_solver.models import AntibotChallenge, OptionImage
from antibot_image_solver.solver import solve_challenge

payload = json.load(sys.stdin)
challenge = AntibotChallenge(
    instruction_image_base64=payload["instruction_image_base64"],
    options=[OptionImage(id=str(item["id"]), image_base64=str(item["image_base64"])) for item in payload["options"]],
    domain_hint=payload.get("domain_hint"),
)
capture = CaptureRequest(**payload["capture"]) if payload.get("capture") else None
result = solve_challenge(challenge, debug=True, capture=capture)
print(json.dumps(result.to_dict(include_debug=True)))
""".strip()
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{self.config.antibot_core_src}:{existing_pythonpath}"
            if existing_pythonpath
            else str(self.config.antibot_core_src)
        )
        if self.config.antibot_core_profile:
            env["ANTIBOT_OCR_PROFILE"] = self.config.antibot_core_profile

        completed = subprocess.run(
            [self.config.antibot_core_python, "-c", script],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=self.config.timeout_seconds,
            env=env,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "antibot core solver failed").strip())

        data = json.loads(completed.stdout)
        return data

    def _solve_iconcaptcha_via_endpoint(
        self,
        canvas_data_url: str,
        *,
        cell_count: int = 5,
    ) -> dict[str, Any]:
        if not self.config.iconcaptcha_endpoint:
            raise RuntimeError("iconcaptcha API endpoint is not configured")
        response = requests.post(
            self.config.iconcaptcha_endpoint,
            json={
                "canvas_data_url": canvas_data_url,
                "cell_count": cell_count,
                "similarity_threshold": self.config.iconcaptcha_similarity_threshold,
                "return_debug": True,
            },
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            raise RuntimeError(data.get("error") or "iconcaptcha API solver failed")
        position = int(data.get("position") or 0)
        if position < 1:
            raise RuntimeError("iconcaptcha API returned empty position")
        click_x = int(data.get("x", data.get("centerX", 0)))
        click_y = int(data.get("y", data.get("centerY", 0)))
        solution = {
            "selected_cell_index": position - 1,
            "selected_cell_number": position,
            "click_x": click_x,
            "click_y": click_y,
            "groups": data.get("groups") or [],
            "pairwise_mad": data.get("pairwise_mad") or [],
            "distinctness": data.get("distinctness") or [],
            "cell_count": data.get("cell_count", cell_count),
            "width": data.get("width"),
            "height": data.get("height"),
            "similarity_threshold": data.get("similarity_threshold", self.config.iconcaptcha_similarity_threshold),
        }
        return {
            "success": True,
            "solution": solution,
            "confidence": data.get("confidence"),
            "meta": {"cell_count": solution["cell_count"], "endpoint": self.config.iconcaptcha_endpoint},
            "raw_api": data,
        }

    def _solve_iconcaptcha_via_core(
        self,
        canvas_data_url: str,
        *,
        cell_count: int = 5,
    ) -> dict[str, Any]:
        if not self.config.iconcaptcha_core_python or not self.config.iconcaptcha_core_src:
            raise RuntimeError("iconcaptcha core solver is not configured")

        payload = {
            "canvas_data_url": canvas_data_url,
            "cell_count": cell_count,
            "similarity_threshold": self.config.iconcaptcha_similarity_threshold,
        }
        script = """
import json, sys
from iconcaptcha_solver.solver import solve_iconcaptcha_data_url

payload = json.load(sys.stdin)
result = solve_iconcaptcha_data_url(
    payload["canvas_data_url"],
    cell_count=payload.get("cell_count", 5),
    similarity_threshold=payload.get("similarity_threshold", 5.0),
)
print(json.dumps({
    "success": True,
    "solution": result.to_dict(),
    "confidence": result.confidence,
    "meta": {"cell_count": result.cell_count},
}))
""".strip()
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{self.config.iconcaptcha_core_src}:{existing_pythonpath}"
            if existing_pythonpath
            else str(self.config.iconcaptcha_core_src)
        )

        completed = subprocess.run(
            [self.config.iconcaptcha_core_python, "-c", script],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=self.config.timeout_seconds,
            env=env,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "iconcaptcha core solver failed").strip())

        return json.loads(completed.stdout)

    def _finalize_antibot_result(self, data: dict[str, Any], *, provider: str, started_at: float, domain_hint: str) -> dict[str, Any]:
        if not data.get("success"):
            raise RuntimeError(data.get("error", {}).get("message") or "antibot solver failed")
        ordered_ids = ((data.get("solution") or {}).get("ordered_ids") or [])
        if not ordered_ids:
            raise RuntimeError("antibot solver returned empty ordered_ids")
        return {
            "antibotlinks": " ".join(str(item) for item in ordered_ids),
            "ordered_ids": [str(item) for item in ordered_ids],
            "confidence": data.get("confidence"),
            "provider": provider,
            "elapsed_ms": round((time.time() - started_at) * 1000, 2),
            "raw": data,
            "capture": data.get("capture"),
            "meta": {
                **(data.get("meta") or {}),
                "domain_hint": domain_hint,
            },
            "debug": data.get("debug"),
        }

    def _finalize_iconcaptcha_result(self, data: dict[str, Any], *, provider: str, started_at: float, domain_hint: str) -> dict[str, Any]:
        if not data.get("success"):
            raise RuntimeError(data.get("error", {}).get("message") or "iconcaptcha solver failed")
        solution = data.get("solution") or {}
        if solution.get("selected_cell_index") is None:
            raise RuntimeError("iconcaptcha solver returned empty selection")
        return {
            "selected_cell_index": int(solution["selected_cell_index"]),
            "selected_cell_number": int(solution.get("selected_cell_number", int(solution["selected_cell_index"]) + 1)),
            "click_x": int(solution["click_x"]),
            "click_y": int(solution["click_y"]),
            "groups": solution.get("groups") or [],
            "confidence": data.get("confidence", solution.get("confidence")),
            "provider": provider,
            "elapsed_ms": round((time.time() - started_at) * 1000, 2),
            "raw": data,
            "meta": {
                **(data.get("meta") or {}),
                "domain_hint": domain_hint,
            },
            "debug": {
                "pairwise_mad": solution.get("pairwise_mad") or [],
                "distinctness": solution.get("distinctness") or [],
                "cell_count": solution.get("cell_count"),
                "width": solution.get("width"),
                "height": solution.get("height"),
                "similarity_threshold": solution.get("similarity_threshold"),
            },
        }

    def solve_recaptchav3(self, sitekey: str, page_url: str | None = None, action: str = "homepage") -> str:
        if self.config.recaptcha_v3_endpoint:
            payload = {
                "url": page_url or "https://claimcoin.in/faucet",
                "siteKey": sitekey,
                "action": action,
            }
            response = requests.post(
                self.config.recaptcha_v3_endpoint,
                json=payload,
                timeout=max(self.config.timeout_seconds, 90),
            )
            if response.status_code == 429:
                raise RuntimeError("rv3 solver busy")
            response.raise_for_status()
            data = response.json()
            if data.get("status") != "success" or not data.get("token"):
                raise RuntimeError(data.get("message") or data.get("error") or "rv3 solver failed")
            return str(data["token"])

        if self.config.provider not in {"waryono", "custom", "hybrid"} or not self.config.endpoint or not self.config.api_key:
            raise RuntimeError("recaptcha solver is not configured")

        body = {
            "apikey": self.config.api_key,
            "methods": "recapv3",
            "domain": page_url or "https://claimcoin.in",
            "sitekey": sitekey,
            "action": action,
        }
        request_id = self._submit_waryono(body)
        result = self._poll_waryono(request_id)
        return str(result["result"])

    def _submit_waryono(self, body: dict[str, Any]) -> str:
        response = requests.post(
            self.config.endpoint,
            json=body,
            timeout=self.config.timeout_seconds,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        text = response.text
        self._raise_known_waryono_error(text)
        payload = response.json()
        return str(payload["request"])

    def _poll_waryono(self, request_id: str) -> dict[str, Any]:
        endpoint = self.config.result_endpoint or self._derive_result_endpoint()
        deadline = time.time() + self.config.timeout_seconds
        while time.time() < deadline:
            response = requests.get(
                endpoint,
                params={"apikey": self.config.api_key, "id": request_id},
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            text = response.text
            if "CAPCHA_NOT_READY" in text:
                time.sleep(self.config.poll_interval_seconds)
                continue
            self._raise_known_waryono_error(text)
            return response.json()
        raise TimeoutError(f"captcha result timeout for request {request_id}")

    def _derive_result_endpoint(self) -> str:
        if not self.config.endpoint:
            raise RuntimeError("captcha endpoint not configured")
        if self.config.endpoint.endswith("/in.php"):
            return self.config.endpoint[:-6] + "/res.php"
        if self.config.endpoint.endswith("in.php"):
            return self.config.endpoint[:-6] + "res.php"
        return self.config.endpoint.replace("in.php", "res.php")

    @staticmethod
    def _raise_known_waryono_error(text: str) -> None:
        for marker in [
            "ERROR_WRONG_METHOD",
            "ERROR_KEY_DOES_NOT_EXIST",
            "ERROR_METHOD_NOT_SPECIFIED",
            "ERROR_NO_SUCH_METHOD",
            "ERROR_DATABASE_CONNECTION_FAILED",
            "ERROR_TOO_MANY_REQUESTS",
            "ERROR_WRONG_USER_KEY",
            "ERROR_ZERO_BALANCE",
            "ERROR_BAD_PARAMETERS",
            "ERROR_EMPTY_IMAGE",
            "ERROR_UNKNOWN",
            "WRONG_CAPTCHA_ID",
            "ERROR_SOLVE_PENDING",
            "ERROR_CAPTCHA_UNSOLVABLE",
            "ERROR_BAD_REQUEST",
            "INTENAL_SERVER_ERROR",
            "Database connection failed",
        ]:
            if marker in text:
                raise RuntimeError(marker)
        if not text.strip():
            raise RuntimeError("empty captcha response")
        try:
            json.loads(text)
        except Exception:
            pass
