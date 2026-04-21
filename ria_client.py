"""
ria_client.py — Cliente HTTP para la API de Redactoria (RIA).

Wrapper sobre la REST API de RIA (FastAPI) para automatizar:
- Autenticación OAuth2
- Gestión de proyectos, templates y landing pages
- Generación de contenido IA por bloques
- Traducción EN/PT
- Guardado de secciones (bulk-update)
- Exportación de Excel (2 hojas: Template + Imagenes)
"""
import sys
import io
import time
import logging
from typing import Optional
from uuid import UUID

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

log = logging.getLogger("ria_client")


class RIAError(Exception):
    """Error de la API de RIA."""
    def __init__(self, status_code: int, detail: str, endpoint: str = ""):
        self.status_code = status_code
        self.detail = detail
        self.endpoint = endpoint
        super().__init__(f"[{status_code}] {endpoint}: {detail}")


class RIAClient:
    """Cliente HTTP para Redactoria API."""

    def __init__(self, base_url: str, email: str, password: str, auto_auth: bool = True):
        self.base_url = base_url.rstrip('/')
        self.email = email
        self.password = password
        self.token: Optional[str] = None
        self.token_time: Optional[float] = None
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        if auto_auth:
            self.auth()

    # ── Auth ───────────────────────────────────────────────────────────

    def auth(self) -> str:
        """Authenticate and store Bearer token. Token lasts 240 min."""
        resp = self.session.post(
            f"{self.base_url}/auth/token",
            data={"username": self.email, "password": self.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise RIAError(resp.status_code, resp.text, "POST /auth/token")

        data = resp.json()
        self.token = data["access_token"]
        self.token_time = time.time()
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        log.info("Autenticado como %s", self.email)
        return self.token

    def _ensure_auth(self):
        """Re-auth if token is older than 200 min (safety margin)."""
        if not self.token or (time.time() - (self.token_time or 0)) > 12000:
            self.auth()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make an authenticated request with auto-retry on 401."""
        self._ensure_auth()
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, **kwargs)

        if resp.status_code == 401:
            log.warning("Token expirado, re-autenticando...")
            self.auth()
            resp = self.session.request(method, url, **kwargs)

        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise RIAError(resp.status_code, detail, f"{method} {path}")

        return resp

    def _get(self, path: str, **kwargs):
        return self._request("GET", path, **kwargs).json()

    def _post(self, path: str, json_data=None, **kwargs):
        return self._request("POST", path, json=json_data, **kwargs).json()

    def _put(self, path: str, json_data=None, **kwargs):
        return self._request("PUT", path, json=json_data, **kwargs).json()

    def _delete(self, path: str, **kwargs):
        return self._request("DELETE", path, **kwargs)

    # ── Templates ──────────────────────────────────────────────────────

    def list_templates(self, active_only: bool = True) -> list:
        """List all active templates (public endpoint)."""
        return self._get("/templates/public/active")

    def get_template(self, template_id: str) -> dict:
        """Get a single template by ID."""
        return self._get(f"/templates/{template_id}")

    def get_template_config(self, template_id: str) -> dict:
        """Get the template config structure (blocks_metadata, templateData, etc.)."""
        return self._get(f"/templates/{template_id}/config")

    # ── Proyectos ──────────────────────────────────────────────────────

    def create_proyecto(self, name: str, template_id: str = None, description: str = "") -> dict:
        """Create a proyecto. Auto-creates a LandingPage."""
        body = {"name": name}
        if description:
            body["description"] = description
        if template_id:
            body["template_id"] = template_id
        return self._post("/proyectos/", body)

    def list_proyectos(self) -> list:
        return self._get("/proyectos/")

    def get_proyecto(self, proyecto_id: str) -> dict:
        return self._get(f"/proyectos/{proyecto_id}")

    def delete_proyecto(self, proyecto_id: str):
        return self._delete(f"/proyectos/{proyecto_id}")

    # ── Landing Pages ──────────────────────────────────────────────────

    def get_landing_page_by_proyecto(self, proyecto_id: str) -> dict:
        """Get the LP auto-created with a proyecto."""
        return self._get(f"/landing-pages/by-proyecto/{proyecto_id}")

    def update_landing_page(self, lp_id: str, **fields) -> dict:
        """Update LP fields (url_slug, title, meta_description)."""
        return self._put(f"/landing-pages/{lp_id}", fields)

    def list_landing_pages(self) -> list:
        return self._get("/landing-pages/")

    # ── IA Content Generation ──────────────────────────────────────────

    def generate_block(
        self,
        lp_id: str,
        block_number: int,
        block_type: str,
        tit: str,
        tema: str,
        cell_key: str = "0-3",
        faq_questions: list = None,
        car_types: list = None,
        fav_city_questions: list = None,
        template_proyecto: str = None,
        template_dominio: str = None,
        template_categoria: str = None,
    ) -> dict:
        """
        Generate content for a single block via IA.
        Returns IAContentResponse with generatedContent.
        Does NOT save to secciones — caller must bulk-update.
        """
        body = {
            "cellKey": cell_key,
            "blockNumber": block_number,
            "tit": tit,
            "blockType": block_type,
            "tema": tema,
            "lpId": str(lp_id),
        }
        if faq_questions:
            body["faq_questions"] = faq_questions
        if car_types:
            body["car_types"] = car_types
        if fav_city_questions:
            body["fav_city_questions"] = fav_city_questions
        if template_proyecto:
            body["template_proyecto"] = template_proyecto
        if template_dominio:
            body["template_dominio"] = template_dominio
        if template_categoria:
            body["template_categoria"] = template_categoria

        log.info("Generando bloque %d (%s): %s", block_number, block_type, tit[:50])
        t0 = time.time()
        result = self._post(f"/ia/{lp_id}/block-{block_number}", body)
        elapsed = time.time() - t0
        log.info("  → Bloque %d completado en %.1fs", block_number, elapsed)
        return result

    def translate(
        self,
        lp_id: str,
        source_content: str,
        target_language: str,
        cell_key: str = "0-3",
    ) -> dict:
        """
        Translate a single cell from ES to EN or PT.
        Returns TranslationResponse with translatedContent.
        """
        body = {
            "sourceContent": source_content,
            "targetLanguage": target_language,
            "cellKey": cell_key,
            "lpId": str(lp_id),
        }
        return self._post(f"/ia/{lp_id}/translate", body)

    # ── Secciones LP ───────────────────────────────────────────────────

    def get_secciones(self, lp_id: str) -> list:
        """Get all secciones for a landing page."""
        return self._get(f"/secciones-lp/landing-page/{lp_id}")

    def bulk_update_secciones(self, lp_id: str, sections: list) -> list:
        """
        Save/update multiple secciones at once.
        sections: list of {cell_position: str, content: str, section_type: str}
        """
        body = {"sections": sections}
        return self._post(f"/secciones-lp/landing-page/{lp_id}/bulk-update", body)

    # ── Excel Export ───────────────────────────────────────────────────

    def export_excel(self, template_config: dict, template_info: dict, cell_data: dict = None) -> bytes:
        """
        Export Excel with generated content. Returns raw XLSX bytes.
        template_config: full config from get_template_config()
        template_info: {id, name, description, categoria, proyecto, dominio, is_active}
        cell_data: optional dict of {cell_key: {value, style?, type?}}
        """
        body = {
            "template_config": template_config,
            "template_info": template_info,
        }
        if cell_data:
            body["cell_data"] = cell_data

        resp = self._request("POST", "/export/excel", json=body)
        return resp.content

    def validate_export(self, template_config: dict, template_info: dict, cell_data: dict = None) -> dict:
        """Validate export without generating file."""
        body = {
            "template_config": template_config,
            "template_info": template_info,
        }
        if cell_data:
            body["cell_data"] = cell_data
        return self._post("/export/excel/validate", body)

    # ── Utilities ──────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Check if RIA is reachable."""
        try:
            resp = requests.get(f"{self.base_url}/docs", timeout=5)
            return resp.status_code == 200
        except requests.ConnectionError:
            return False

    def whoami(self) -> dict:
        """Get current user info."""
        return self._get("/users/me")
