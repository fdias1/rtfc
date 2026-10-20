"""Listas padrão de domínios por idioma (os bloqueios extras são editáveis nas configurações).

Tipos de fonte, em ordem de preferência (ADR 0006):
- `primary`: fontes **primárias e auditáveis**: governo, legislativo, judiciário, órgãos de
  estatística, bancos centrais, institutos de pesquisa, universidades, periódicos científicos,
  organismos internacionais. O dado pode ser conferido na origem.
- `factchecker`: agências de checagem (citam e linkam as fontes que usaram).
- `press`: veículos jornalísticos (úteis, mas secundários: limitados por cota no ranking).

Domínios casam por sufixo (gov.br pega ibge.gov.br); um padrão começando com "." casa
qualquer domínio com esse final (".edu"); "dominio/caminho" exige o prefixo de caminho.
"""

_PRIMARY_GLOBAL: tuple[str, ...] = (
    # Organismos internacionais e estatística
    "un.org",
    "who.int",
    "paho.org",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "ilo.org",
    "unesco.org",
    "unicef.org",
    "fao.org",
    "wto.org",
    "data.un.org",
    "cepal.org",
    "europa.eu",
    "ourworldindata.org",
    # Ciência e academia
    ".edu",
    ".ac.uk",
    "scielo.org",
    "scielo.br",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "nature.com",
    "science.org",
    "thelancet.com",
    "nejm.org",
    "arxiv.org",
    "doi.org",
)

TIERS: dict[str, dict[str, tuple[str, ...]]] = {
    "pt": {
        "primary": (
            # Governo, legislativo, judiciário, ministério público, defensoria
            "gov.br",
            "leg.br",
            "jus.br",
            "mp.br",
            "def.br",
            "planalto.gov.br",
            # Estatística, bancos públicos de dados e institutos de pesquisa
            "ibge.gov.br",
            "bcb.gov.br",
            "ipea.gov.br",
            "inep.gov.br",
            "datasus.saude.gov.br",
            "inpe.br",
            "fiocruz.br",
            "embrapa.br",
            "fgv.br",
            "dieese.org.br",
            "seade.gov.br",
            "transparencia.gov.br",
            "tse.jus.br",
            # Universidades
            "usp.br",
            "unicamp.br",
            "unesp.br",
            "ufrj.br",
            "ufmg.br",
            "unb.br",
            "ufrgs.br",
            "ufpe.br",
            "ufba.br",
            "ufsc.br",
            "insper.edu.br",
            ".edu.br",
            *_PRIMARY_GLOBAL,
        ),
        "factchecker": (
            "agencialupa.org",
            "lupa.uol.com.br",
            "piaui.folha.uol.com.br",
            "aosfatos.org",
            "estadao.com.br/estadao-verifica",
            "checamos.afp.com",
            "g1.globo.com/fato-ou-fake",
            "projetocomprova.com.br",
            "boatos.org",
            "e-farsas.com",
            "uol.com.br/confere",
            "politifact.com",
            "fullfact.org",
            "snopes.com",
        ),
        "press": (
            "g1.globo.com",
            "globo.com",
            "folha.uol.com.br",
            "estadao.com.br",
            "uol.com.br",
            "cnnbrasil.com.br",
            "bbc.com",
            "valor.globo.com",
            "poder360.com.br",
            "agenciabrasil.ebc.com.br",
            "exame.com",
            "infomoney.com.br",
            "correiobraziliense.com.br",
            "oglobo.globo.com",
            "metropoles.com",
            "nexojornal.com.br",
            "reuters.com",
            "apnews.com",
            "elpais.com",
        ),
    },
    "en": {
        "primary": (
            ".gov",
            ".mil",
            "census.gov",
            "bls.gov",
            "federalreserve.gov",
            *_PRIMARY_GLOBAL,
        ),
        "factchecker": (
            "politifact.com",
            "factcheck.org",
            "fullfact.org",
            "snopes.com",
            "apnews.com/hub/ap-fact-check",
            "reuters.com/fact-check",
        ),
        "press": (
            "reuters.com",
            "apnews.com",
            "bbc.com",
            "nytimes.com",
            "theguardian.com",
            "washingtonpost.com",
        ),
    },
    "es": {
        "primary": (
            ".gob",
            ".gov",
            ".gob.es",
            ".gob.mx",
            "ine.es",
            "indec.gob.ar",
            *_PRIMARY_GLOBAL,
        ),
        "factchecker": (
            "maldita.es",
            "newtral.es",
            "chequeado.com",
            "colombiacheck.com",
            "efe.com/verifica",
        ),
        "press": ("elpais.com", "efe.com", "bbc.com", "reuters.com", "clarin.com", "eltiempo.com"),
    },
}

BLOCKED: tuple[str, ...] = (
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "kwai.com",
    "pinterest.com",
    "reddit.com",
    "quora.com",
    "youtube.com",
    "brainly.com.br",
)
"""Redes sociais e fóruns: não servem como evidência (o rtfc só lê texto de páginas)."""
