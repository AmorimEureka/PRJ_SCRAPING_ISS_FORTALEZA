from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, unquote, urlsplit, urlunsplit

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
DEFAULT_ARTIFACTS_DIR = PROJECT_ROOT / ".artifacts"


@dataclass(frozen=True)
class Settings:
    portal_url: str
    cpf_login: str
    senha: str
    database_url: str
    postgres_schema: str
    inscricao_cnpj: str | None = None
    inscricao_municipal: str | None = None
    inscricao_nome: str | None = None

    @property
    def portal_root(self) -> str:
        """Return the application root, preserving the context path."""
        parsed = urlsplit(self.portal_url)
        path = parsed.path

        matched = False
        for marker in ("/home.seam", "/pages/"):
            if marker in path:
                path = path.split(marker, 1)[0] + "/"
                matched = True
                break

        if not matched and not path.endswith("/"):
            path = path.rsplit("/", 1)[0] + "/"

        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    @property
    def portal_origin(self) -> str:
        parsed = urlsplit(self.portal_url)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    def portal_page(self, relative_path: str) -> str:
        return self.portal_root.rstrip("/") + "/" + relative_path.lstrip("/")


def load_settings(env_path: Path | None = None) -> Settings:
    load_dotenv(env_path or PROJECT_ROOT / ".env")

    missing = [
        name
        for name in (
            "PORTAL_PREFEITURA_FORTALEZA",
            "CPF_LOGIN",
            "SENHA",
            "DATABASE_URL",
            "POSTGRES_SCHEMA",
        )
        if not os.getenv(name)
    ]
    if missing:
        raise RuntimeError(
            "Variaveis obrigatorias ausentes no .env: " + ", ".join(sorted(missing))
        )

    return Settings(
        portal_url=normalize_portal_url(os.environ["PORTAL_PREFEITURA_FORTALEZA"]),
        cpf_login=os.environ["CPF_LOGIN"],
        senha=os.environ["SENHA"],
        database_url=normalize_postgres_url(os.environ["DATABASE_URL"]),
        postgres_schema=os.environ["POSTGRES_SCHEMA"],
        inscricao_cnpj=_optional_env("INSCRICAO_CNPJ", "CNPJ_INSCRICAO", "PORTAL_INSCRICAO_CNPJ"),
        inscricao_municipal=_optional_env(
            "INSCRICAO_MUNICIPAL",
            "PORTAL_INSCRICAO_MUNICIPAL",
            "INSCRICAO_ATUAL",
        ),
        inscricao_nome=_optional_env("INSCRICAO_NOME", "PORTAL_INSCRICAO_NOME"),
    )


def normalize_portal_url(raw_url: str) -> str:
    """Avoid stale Keycloak auth URLs by returning a stable ISS entry point."""
    parsed = urlsplit(raw_url.strip())
    query = parse_qs(parsed.query)
    redirect_uri = query.get("redirect_uri", [None])[0]

    if redirect_uri:
        return _home_from_redirect_uri(unquote(redirect_uri))

    if "idp" in parsed.netloc.lower():
        raise RuntimeError(
            "PORTAL_PREFEITURA_FORTALEZA aponta para o IdP, mas nao contem redirect_uri. "
            "Use uma URL do ISS, por exemplo https://iss.fortaleza.ce.gov.br/grpfor/home.seam"
        )

    return raw_url.strip()


def _optional_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _home_from_redirect_uri(redirect_uri: str) -> str:
    parsed = urlsplit(redirect_uri)
    path = parsed.path
    for marker in ("/oauth2/callback", "/home.seam", "/pages/"):
        if marker in path:
            path = path.split(marker, 1)[0] + "/home.seam"
            break
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def normalize_postgres_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url.strip())
    scheme = parsed.scheme
    if scheme.startswith("postgresql+"):
        scheme = "postgresql"
    elif scheme == "postgres":
        scheme = "postgresql"

    query_items: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if value:
            query_items.append((key, value))
        elif key == "connect_timeout":
            query_items.append((key, "10"))

    return urlunsplit(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            parsed.query and urlencode(query_items),
            parsed.fragment,
        )
    )
