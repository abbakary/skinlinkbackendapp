from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# ---------------------------------------------------------------------------
# JSON Schemas — Gemini responseSchema (OpenAPI-like subset)
# ---------------------------------------------------------------------------

IMAGE_QUALITY_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "image_quality": {
            "type": "OBJECT",
            "properties": {
                "rating": {
                    "type": "STRING",
                    "enum": ["good", "acceptable", "poor"],
                },
                "focus": {
                    "type": "BOOLEAN",
                    "description": "True if lesion is in sharp focus with no motion blur",
                },
                "lighting": {
                    "type": "BOOLEAN",
                    "description": "True if lighting is even with no harsh shadows or glare",
                },
                "lesion_visible": {
                    "type": "BOOLEAN",
                    "description": "True if the entire lesion is visible and not cropped",
                },
                "required_angles_present": {
                    "type": "BOOLEAN",
                    "description": "True if the required clinical angles are provided",
                },
                "issues": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Specific quality issues found, e.g. motion blur, glare",
                },
                "score": {
                    "type": "INTEGER",
                    "description": "Overall image quality score 0-100 for dermoscopic assessment",
                },
            },
            "required": [
                "rating",
                "focus",
                "lighting",
                "lesion_visible",
                "required_angles_present",
                "issues",
                "score",
            ],
        },
    },
    "required": ["image_quality"],
}

SKIN_ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "image_quality": {
            "type": "OBJECT",
            "properties": {
                "rating": {"type": "STRING", "enum": ["good", "acceptable", "poor"]},
                "focus": {"type": "BOOLEAN"},
                "lighting": {"type": "BOOLEAN"},
                "lesion_visible": {"type": "BOOLEAN"},
                "required_angles_present": {"type": "BOOLEAN"},
                "issues": {"type": "ARRAY", "items": {"type": "STRING"}},
                "score": {"type": "INTEGER"},
            },
            "required": [
                "rating",
                "focus",
                "lighting",
                "lesion_visible",
                "required_angles_present",
                "issues",
                "score",
            ],
        },
        "observations": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Short objective visual observations: erythema, scaling, well-demarcated border, etc.",
        },
        "possible_conditions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "condition": {
                        "type": "STRING",
                        "description": "Clinical condition name, e.g. Atopic Dermatitis",
                    },
                    "likelihood": {
                        "type": "STRING",
                        "enum": ["unlikely", "possible", "probable", "highly_likely"],
                    },
                    "probability": {
                        "type": "INTEGER",
                        "nullable": True,
                        "description": "0-100 estimated probability",
                    },
                    "rationale": {
                        "type": "STRING",
                        "nullable": True,
                        "description": "Short clinical rationale linking visual features to this condition",
                    },
                },
                "required": ["condition", "likelihood"],
            },
        },
        "urgency": {"type": "STRING", "enum": ["routine", "urgent", "emergency"]},
        "missing_information": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Clinical information missing that would improve assessment",
        },
        "red_flags_detected": {"type": "BOOLEAN"},
        "detected_red_flags": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Red flags if any: rapid growth, bleeding, irregular pigmentation, etc.",
        },
        "suggested_next_step": {
            "type": "STRING",
            "description": "Suggested next clinical step: specialist_review, additional_images, in_person_visit, etc.",
        },
        "confidence": {"type": "STRING", "enum": ["low", "moderate", "high"]},
        "disclaimer": {"type": "STRING"},
    },
    "required": [
        "image_quality",
        "observations",
        "possible_conditions",
        "urgency",
        "missing_information",
        "red_flags_detected",
        "detected_red_flags",
        "suggested_next_step",
        "confidence",
        "disclaimer",
    ],
}


class GeminiServiceError(Exception):
    """Raised when Gemini is not configured or a live API call fails. No mock fallback."""

    def __init__(self, message: str, *, code: str = "ai_error", status_code: int = 503) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_remote_url(url: str) -> bool:
    return bool(re.match(r"^https?://", url, re.IGNORECASE))


def _is_data_uri(url: str) -> bool:
    return url.startswith("data:")


def _resolve_local_path(path_or_url: str) -> Optional[str]:
    candidate = path_or_url
    if candidate.startswith("/uploads/"):
        candidate = os.path.join(settings.upload_dir, os.path.basename(candidate))
    if not os.path.isabs(candidate):
        candidate = os.path.abspath(candidate)
    if os.path.isfile(candidate):
        return candidate
    alt = os.path.join(
        os.path.dirname(settings.database_path), "..", path_or_url.lstrip("/\\")
    )
    if os.path.isfile(alt):
        return alt
    return None


def _load_image_bytes(path_or_url: str) -> tuple[bytes, str]:
    """Load image bytes + MIME type from data URI, remote URL, or local file."""
    if _is_data_uri(path_or_url):
        header, b64_data = path_or_url.split(",", 1)
        mime = header.split(":")[1].split(";")[0] if ":" in header else "image/jpeg"
        try:
            return base64.b64decode(b64_data), mime
        except Exception as exc:
            raise GeminiServiceError(
                f"Invalid image data URI: {exc}",
                code="image_unavailable",
                status_code=400,
            ) from exc

    if _is_remote_url(path_or_url):
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                resp = client.get(path_or_url)
                resp.raise_for_status()
            mime = resp.headers.get("content-type", "").split(";")[0].strip() or "image/jpeg"
            if not mime.startswith("image/"):
                mime = "image/jpeg"
            return resp.content, mime
        except Exception as exc:
            raise GeminiServiceError(
                f"Failed to download image for Gemini: {exc}",
                code="image_unavailable",
                status_code=400,
            ) from exc

    local = _resolve_local_path(path_or_url)
    if not local:
        raise GeminiServiceError(
            f"Image not found: {path_or_url}",
            code="image_unavailable",
            status_code=400,
        )
    mime, _ = mimetypes.guess_type(local)
    mime = mime or "image/jpeg"
    try:
        with open(local, "rb") as f:
            return f.read(), mime
    except OSError as exc:
        raise GeminiServiceError(
            f"Failed to read image file: {exc}",
            code="image_unavailable",
            status_code=400,
        ) from exc


def _build_gemini_parts(prompt: str, image_urls: list[str]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"text": prompt}]
    for url in image_urls:
        raw, mime = _load_image_bytes(url)
        parts.append({
            "inline_data": {
                "mime_type": mime,
                "data": base64.b64encode(raw).decode("ascii"),
            }
        })
    return parts


def _parse_json_response(raw: str, required_keys: list[str]) -> dict[str, Any]:
    if not raw:
        raise GeminiServiceError(
            "Gemini returned an empty response",
            code="empty_response",
        )
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    s = s.strip()
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if not m:
            raise GeminiServiceError(
                "Gemini response was not valid JSON",
                code="invalid_json",
            )
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            raise GeminiServiceError(
                f"Gemini response was not valid JSON: {exc}",
                code="invalid_json",
            ) from exc
    if not isinstance(parsed, dict):
        raise GeminiServiceError(
            "Gemini JSON response was not an object",
            code="invalid_json",
        )
    missing = [k for k in required_keys if k not in parsed]
    if missing:
        raise GeminiServiceError(
            f"Gemini response missing required keys: {', '.join(missing)}",
            code="invalid_schema",
        )
    return parsed


def _extract_text_from_gemini_response(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        block = payload.get("promptFeedback") or {}
        raise GeminiServiceError(
            f"Gemini returned no candidates (promptFeedback={block})",
            code="no_candidates",
        )
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
    return "\n".join(texts).strip()


# ---------------------------------------------------------------------------
# Gemini service — live generateContent only (no mock fallback)
# ---------------------------------------------------------------------------

class GeminiService:
    def __init__(self) -> None:
        self.api_key: str = (settings.gemini_api_key or "").strip()
        self.model: str = settings.gemini_model or "gemini-3.5-flash"
        self.temperature: float = settings.gemini_temperature
        self.timeout_seconds: float = 90.0

    @property
    def is_configured(self) -> bool:
        key = self.api_key
        if not key:
            return False
        # Reject common placeholder values
        lowered = key.lower()
        if lowered.startswith("your-") or "placeholder" in lowered or key in ("changeme", "xxx"):
            return False
        return True

    def require_configured(self) -> None:
        if not self.is_configured:
            raise GeminiServiceError(
                "Gemini API is not configured. Set GEMINI_API_KEY in the backend environment "
                "(get a key from Google AI Studio: https://aistudio.google.com/apikey).",
                code="not_configured",
                status_code=503,
            )

    def check_image_quality(
        self,
        image_url: str,
        angle: Optional[str] = None,
        required_angles: Optional[list[str]] = None,
    ) -> tuple[dict[str, Any], str]:
        self.require_configured()
        if not image_url:
            raise GeminiServiceError(
                "image_url is required for quality check",
                code="no_images",
                status_code=400,
            )

        required = required_angles or []
        prompt_parts = [
            "You are a dermatological imaging quality auditor reviewing a skin lesion photograph "
            "submitted via a teledermatology platform (SkinLink).",
            "Evaluate the image for clinical utility. Check: (1) focus and motion blur, "
            "(2) lighting and glare/shadows, (3) lesion visibility and framing, (4) angle adequacy.",
        ]
        if angle:
            prompt_parts.append(f"The image is labelled as angle: {angle}.")
        if required:
            prompt_parts.append(f"Clinically required angles for this case: {', '.join(required)}.")
        prompt_parts.append(
            "Respond only with JSON matching the response schema. "
            "Do not add prose, preamble, or markdown."
        )
        prompt = " ".join(prompt_parts)

        result = self._generate_content(
            prompt=prompt,
            image_urls=[image_url],
            schema=IMAGE_QUALITY_SCHEMA,
            required_keys=["image_quality"],
        )
        return result, self.model

    def assess_skin(
        self,
        clinical: dict[str, Any],
        image_urls: list[str],
    ) -> tuple[dict[str, Any], str]:
        self.require_configured()
        if not image_urls:
            raise GeminiServiceError(
                "At least one clinical image is required for skin assessment",
                code="no_images",
                status_code=400,
            )

        lines: list[str] = []
        if clinical.get("case_id"):
            lines.append(f"Case reference: {clinical['case_id']}")
        if clinical.get("patient_age") is not None:
            lines.append(f"Patient age: {clinical['patient_age']}")
        if clinical.get("sex"):
            lines.append(f"Sex: {clinical['sex']}")
        if clinical.get("primary_concern"):
            lines.append(f"Primary concern: {clinical['primary_concern']}")
        if clinical.get("clinical_info"):
            lines.append(f"Additional clinical context: {clinical['clinical_info']}")
        symptoms = clinical.get("symptoms") or []
        if symptoms:
            lines.append(f"Reported symptoms: {', '.join(symptoms)}")
        duration = clinical.get("duration")
        if not duration and clinical.get("duration_days"):
            duration = f"{clinical['duration_days']} days"
        if duration:
            lines.append(f"Duration: {duration}")
        if clinical.get("body_site"):
            lines.append(f"Body site: {clinical['body_site']}")
        if clinical.get("severity"):
            lines.append(f"Clinician-rated severity: {clinical['severity']}")
        if clinical.get("previous_treatment"):
            lines.append(f"Previous treatment: {clinical['previous_treatment']}")
        if clinical.get("treatment_response"):
            lines.append(f"Treatment response: {clinical['treatment_response']}")
        if clinical.get("adherence"):
            lines.append(f"Adherence: {clinical['adherence']}")
        lang = str(clinical.get("language") or "").strip()
        is_swahili = "swahili" in lang.lower() or lang.lower() == "sw"
        if is_swahili:
            lines.append("Patient preferred language: Swahili (Kiswahili)")

        lang_instruction = ""
        if is_swahili:
            lang_instruction = (
                "\n\nIMPORTANT LANGUAGE REQUIREMENT: The patient's preferred language is SWAHILI (Kiswahili). "
                "Provide all clinical rationale, visual observation explanations, and suggested next steps in clear Kiswahili (or bilingual Swahili/English) "
                "so the rural health worker and patient can understand the clinical guidance."
            )

        prompt = (
            "You are an AI decision-support assistant for teledermatology within the SkinLink platform. "
            "You do NOT give a final diagnosis and you do NOT prescribe treatment. Your role is to:\n"
            "1. Rate the submitted image(s) for clinical quality.\n"
            "2. List objective visual observations (morphological features, NOT a diagnosis).\n"
            "3. Provide an ordered differential of POSSIBLE conditions with likelihood levels and a short rationale.\n"
            "4. Triage urgency as routine / urgent / emergency for specialist review.\n"
            "5. Flag any red-flag features (e.g. rapid growth, irregular pigmentation suggestive of melanoma).\n"
            "6. Note missing clinical or imaging information that would improve confidence.\n"
            "Always include the disclaimer that specialist confirmation is required."
            f"{lang_instruction}\n\n"
            "Clinical information:\n" + "\n".join(lines) + "\n\n"
            "Respond only with JSON matching the response schema. No preamble, no markdown."
        )

        result = self._generate_content(
            prompt=prompt,
            image_urls=image_urls,
            schema=SKIN_ASSESSMENT_SCHEMA,
            required_keys=[
                "image_quality",
                "observations",
                "possible_conditions",
                "urgency",
                "missing_information",
                "red_flags_detected",
                "detected_red_flags",
                "suggested_next_step",
                "confidence",
                "disclaimer",
            ],
        )
        return result, self.model

    def _generate_content(
        self,
        prompt: str,
        image_urls: list[str],
        schema: dict[str, Any],
        required_keys: list[str],
    ) -> dict[str, Any]:
        """Call Gemini generateContent (REST) with vision + structured JSON output.

        Official API: https://ai.google.dev/api
        Endpoint: POST /v1beta/models/{model}:generateContent
        Auth: x-goog-api-key header
        """
        parts = _build_gemini_parts(prompt, image_urls)
        url = f"{GEMINI_API_BASE}/models/{self.model}:generateContent"
        body: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": parts,
                }
            ],
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "You are a clinical decision-support AI assistant for dermatology "
                            "on the SkinLink tele-dermatology platform. "
                            "Always respond with valid JSON that exactly matches the required schema. "
                            "No prose, no markdown fences, no extra fields. "
                            "AI suggestions are decision support only; a specialist must confirm."
                        )
                    }
                ]
            },
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": self.api_key,
                    },
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise GeminiServiceError(
                "Gemini API request timed out",
                code="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise GeminiServiceError(
                f"Gemini API network error: {exc}",
                code="network_error",
            ) from exc

        if resp.status_code >= 400:
            detail = resp.text[:1200]
            try:
                err_json = resp.json()
                err_obj = err_json.get("error", err_json)
                detail = json.dumps(err_obj)[:1200]
            except Exception:
                pass
            print(f"\n==== GEMINI ERROR ====\nHTTP {resp.status_code}\n{detail}\n=====================\n")
            logger.error("Gemini API error %s: %s", resp.status_code, detail)

            # Parse known error codes and return clean user-facing messages
            http_code = resp.status_code
            user_message = f"Gemini API error ({http_code}): {detail}"
            error_code = "api_error"
            backend_status = 502 if http_code >= 500 else 503

            try:
                err_json = resp.json()
                err_obj = err_json.get("error", {})
                grpc_code = err_obj.get("code", http_code)
                grpc_status = err_obj.get("status", "")
                if http_code == 429 or grpc_code == 429 or grpc_status == "RESOURCE_EXHAUSTED":
                    user_message = (
                        "AI quota exceeded for today. The free tier limit has been reached. "
                        "Please try again later or upgrade to a paid Gemini API plan at "
                        "https://ai.google.dev/pricing"
                    )
                    error_code = "quota_exceeded"
                    backend_status = 429
                elif http_code == 401 or grpc_status == "UNAUTHENTICATED":
                    user_message = "Gemini API key is invalid or has been revoked. Please update your GEMINI_API_KEY."
                    error_code = "invalid_key"
                    backend_status = 503
                elif http_code == 403 or grpc_status == "PERMISSION_DENIED":
                    user_message = "Permission denied. Ensure billing is enabled on your Google AI project."
                    error_code = "permission_denied"
                    backend_status = 503
                elif http_code == 404 or grpc_status == "NOT_FOUND":
                    user_message = f"Gemini model '{self.model}' not found. Check GEMINI_MODEL in your .env file."
                    error_code = "model_not_found"
                    backend_status = 503
            except Exception:
                pass

            raise GeminiServiceError(user_message, code=error_code, status_code=backend_status)

        try:
            payload = resp.json()
        except Exception as exc:
            raise GeminiServiceError(
                "Gemini API returned non-JSON body",
                code="invalid_response",
            ) from exc

        raw_text = _extract_text_from_gemini_response(payload)
        parsed = _parse_json_response(raw_text, required_keys)
        logger.info("Gemini %s generateContent succeeded (model=%s)", required_keys[0], self.model)
        return parsed

    def translate_clinical_text(
        self,
        text: str,
        target_language: str = "Swahili",
        source_context: str = "specialist clinical review",
    ) -> str:
        """Translate specialist or nurse clinical notes/guidance to the target language (e.g. Swahili)."""
        if not text or not text.strip():
            return ""
        if not self.is_configured:
            return text

        prompt = (
            f"You are a medical translator for the SkinLink teledermatology platform in Tanzania. "
            f"Translate the following {source_context} text into clear, empathetic, and patient-friendly {target_language} (Kiswahili). "
            f"Maintain exact clinical accuracy and medical terms.\n\n"
            f"Text to translate:\n\"\"\"{text}\"\"\"\n\n"
            f"Respond ONLY with a JSON object containing a single key 'translated_text': string. No prose, no markdown."
        )
        schema = {
            "type": "OBJECT",
            "properties": {
                "translated_text": {"type": "STRING", "description": f"The translated text in {target_language}"}
            },
            "required": ["translated_text"],
        }
        try:
            res = self._generate_content(
                prompt=prompt,
                image_urls=[],
                schema=schema,
                required_keys=["translated_text"],
            )
            return res.get("translated_text", text)
        except Exception as exc:
            logger.warning("Clinical text translation failed: %s", exc)
            return text

    def translate_treatment_plan(
        self,
        plan: dict[str, Any],
        target_language: str = "Swahili",
    ) -> dict[str, Any]:
        """Review and convert a specialist treatment plan (diagnosis, instructions, education) to target language."""
        if not plan:
            return {}
        translated_plan = dict(plan)
        diagnosis = plan.get("diagnosis", "")
        notes = plan.get("notes", "")
        education = plan.get("patientEducation", [])
        medications = plan.get("medications", [])

        if diagnosis:
            translated_plan["diagnosisSwahili"] = self.translate_clinical_text(diagnosis, target_language, "specialist diagnosis")

        if notes:
            translated_plan["notesSwahili"] = self.translate_clinical_text(notes, target_language, "specialist notes")

        if education and isinstance(education, list):
            translated_edu = []
            for item in education:
                if isinstance(item, str) and item.strip():
                    translated_edu.append(self.translate_clinical_text(item, target_language, "patient education advice"))
                else:
                    translated_edu.append(item)
            translated_plan["patientEducationSwahili"] = translated_edu

        if medications and isinstance(medications, list):
            translated_meds = []
            for med in medications:
                if isinstance(med, dict):
                    m_copy = dict(med)
                    instr = med.get("instructions", "")
                    if instr:
                        m_copy["instructionsSwahili"] = self.translate_clinical_text(instr, target_language, "medication instruction")
                    translated_meds.append(m_copy)
                else:
                    translated_meds.append(med)
            translated_plan["medications"] = translated_meds

        return translated_plan


gemini_service = GeminiService()
