"""Cliente de LLM agnóstico de fornecedor (LiteLLM) com saída estruturada validada.

- Usa JSON Schema nativo quando o modelo suporta; senão pede JSON e valida com Pydantic,
  com até 2 tentativas de correção (o erro de validação volta para o modelo).
- Timeout, retry com backoff em erros transitórios e cancelamento (cancelar a task aborta
  a requisição HTTP).
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from rtfc.config import LlmRole, SecretStore, get_provider

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_REPAIRS = 2
OLLAMA_NUM_CTX = 12_288

# Alfabetos que não deveriam aparecer em respostas pt/en/es (grego, cirílico, árabe, indianos,
# CJK…). Modelos às vezes "vazam" uma palavra de outro idioma no meio do texto.
_FOREIGN_SCRIPT = re.compile(
    r"[\u0370-\u03ff\u0400-\u052f\u0590-\u08ff\u0900-\u0dff\u0e00-\u0fff"
    r"\u1100-\u11ff\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]"
)
MAX_RETRIES = 2


ErrorKind = str
"""auth, quota, rate_limit, not_found, offline, timeout, server, too_long, format, other."""


class LlmError(RuntimeError):
    """Erro com mensagem pronta para o usuário (pt-BR, diz o que fazer)."""

    def __init__(self, message: str, kind: ErrorKind = "other") -> None:
        super().__init__(message)
        self.kind = kind


class LlmConfigError(LlmError):
    """Configuração incompleta (sem chave, sem modelo…): não adianta tentar de novo."""


@dataclass(frozen=True)
class LlmResult[M: BaseModel]:
    value: M
    latency_ms: int
    model: str


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    # Modelos de raciocínio às vezes devolvem <think>…</think> antes do JSON.
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


class LlmClient:
    def __init__(self, role: LlmRole, secrets: SecretStore, *, timeout_s: float = 60.0) -> None:
        self.role = role
        self.provider = get_provider(role.provider)
        self._secrets = secrets
        self._timeout = timeout_s

    @property
    def is_local(self) -> bool:
        return self.provider.id == "ollama"

    @property
    def litellm_model(self) -> str:
        return f"{self.provider.litellm_prefix}{self.role.model}"

    def _call_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        base_url = self.role.base_url or self.provider.default_base_url
        if base_url:
            kwargs["api_base"] = base_url
        key = self._secrets.get(self.provider.id)
        if self.provider.needs_key and not key:
            raise LlmConfigError(
                f"Falta a chave de API do {self.provider.label}. "
                "Configure em Configurações → Modelos de IA.",
                "auth",
            )
        if key:
            kwargs["api_key"] = key
        if self.provider.id == "ollama":
            # Raciocínio (Qwen3, DeepSeek-R1) deixa lento demais para rodar a cada frase.
            kwargs["think"] = False
            # O padrão do Ollama é 4.096 tokens e o excesso é cortado em silêncio PELO
            # COMEÇO — justamente as instruções. O prompt de veredicto passa disso.
            kwargs["num_ctx"] = OLLAMA_NUM_CTX
        return kwargs

    def _supports_schema(self) -> bool:
        if self.provider.id in ("openai", "ollama", "gemini"):
            return True
        try:
            import litellm

            return bool(litellm.supports_response_schema(model=self.litellm_model))
        except Exception:
            return False

    async def structured(self, messages: list[dict[str, str]], schema: type[T]) -> LlmResult[T]:
        if self.provider.id == "fake":
            from rtfc.llm.fake import fake_reply

            await asyncio.sleep(0.05)
            reply = fake_reply(messages, schema, model=self.role.model)
            return LlmResult(reply, 50, f"fake/{self.role.model}")  # type: ignore[arg-type]

        import litellm

        litellm.suppress_debug_info = True
        kwargs = self._call_kwargs()
        json_schema = schema.model_json_schema()
        if self._supports_schema():
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": json_schema, "strict": True},
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}
            messages = [
                *messages[:-1],
                {
                    "role": messages[-1]["role"],
                    "content": messages[-1]["content"]
                    + "\n\nResponda SOMENTE com um JSON válido neste schema:\n"
                    + json.dumps(json_schema, ensure_ascii=False),
                },
            ]

        t0 = time.perf_counter()
        conversation = list(messages)
        for attempt in range(MAX_REPAIRS + 1):
            text = await self._complete(conversation, kwargs)
            if _FOREIGN_SCRIPT.search(text):
                if attempt < MAX_REPAIRS:
                    log.info("resposta com caracteres de outro alfabeto; pedindo correção")
                    conversation += [
                        {"role": "assistant", "content": text},
                        {
                            "role": "user",
                            "content": "A resposta tem palavras em outro alfabeto. Reescreva o "
                            "mesmo JSON usando só o idioma pedido, sem trocar o conteúdo.",
                        },
                    ]
                    continue
                # Última tentativa: melhor tirar os caracteres estranhos do que falhar.
                text = _FOREIGN_SCRIPT.sub("", text)
            try:
                value = schema.model_validate_json(_strip_fences(text))
            except ValidationError as exc:
                if attempt == MAX_REPAIRS:
                    raise LlmError(
                        f"{self.role.model} respondeu fora do formato esperado "
                        f"{attempt + 1} vezes seguidas. Um modelo maior costuma resolver.",
                        "format",
                    ) from exc
                log.info("JSON inválido do %s; pedindo correção", self.litellm_model)
                conversation += [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": "O JSON não segue o schema: "
                        + str(exc.errors()[:3])
                        + ". Responda de novo só com o JSON corrigido.",
                    },
                ]
                continue
            return LlmResult(value, round((time.perf_counter() - t0) * 1000), self.litellm_model)
        raise AssertionError("inalcançável")

    async def _complete(self, messages: list[dict[str, str]], kwargs: dict[str, Any]) -> str:
        import litellm
        import litellm.exceptions as llm_errors

        delay = 1.0
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await litellm.acompletion(
                    model=self.litellm_model, messages=messages, **kwargs
                )
                return str(resp.choices[0].message.content or "")
            except asyncio.CancelledError:
                raise
            except (
                llm_errors.AuthenticationError,
                llm_errors.NotFoundError,
                llm_errors.BadRequestError,
            ) as exc:
                log.warning("LLM %s recusou: %s", self.litellm_model, _short(exc))
                raise self.friendly(exc) from exc
            except (
                llm_errors.RateLimitError,
                llm_errors.APIConnectionError,
                llm_errors.Timeout,
                llm_errors.ServiceUnavailableError,
                llm_errors.InternalServerError,
            ) as exc:
                error = self.friendly(exc)
                # Cota esgotada não volta sozinha: não adianta insistir.
                if attempt == MAX_RETRIES or error.kind == "quota":
                    log.warning("LLM %s falhou: %s", self.litellm_model, _short(exc))
                    raise error from exc
                log.warning("LLM %s falhou (%s); tentando de novo", self.litellm_model, _short(exc))
                await asyncio.sleep(delay)
                delay *= 2
            except Exception as exc:
                log.warning("LLM %s falhou: %s", self.litellm_model, _short(exc))
                raise self.friendly(exc) from exc
        raise AssertionError("inalcançável")

    def friendly(self, exc: BaseException) -> LlmError:
        """Traduz o erro do provedor numa mensagem que diz o que aconteceu e o que fazer."""
        import litellm.exceptions as e

        label, model = self.provider.label, self.role.model
        text = str(exc).lower()
        base = self.role.base_url or self.provider.default_base_url or ""
        if isinstance(exc, e.AuthenticationError):
            return LlmConfigError(
                f"{label}: chave de API inválida ou revogada. "
                "Atualize em Configurações → Modelos de IA.",
                "auth",
            )
        if isinstance(exc, e.RateLimitError):
            if any(w in text for w in ("quota", "credit", "billing", "balance", "exceeded your")):
                return LlmError(
                    f"{label}: créditos ou cota esgotados. Recarregue a conta ou troque "
                    "para um modelo local (Ollama) nas configurações.",
                    "quota",
                )
            return LlmError(
                f"{label}: limite de requisições atingido. Aguarde um pouco ou reduza as "
                "checagens simultâneas.",
                "rate_limit",
            )
        if isinstance(exc, e.NotFoundError) or (self.is_local and "not found" in text):
            if self.is_local:
                return LlmConfigError(
                    f"O modelo {model} não está instalado no Ollama. "
                    f"Rode `ollama pull {model}` ou escolha outro modelo.",
                    "not_found",
                )
            return LlmConfigError(
                f"{label}: o modelo {model} não existe ou sua conta não tem acesso a ele.",
                "not_found",
            )
        if isinstance(exc, e.Timeout):
            hint = " O modelo pode ser grande demais para a memória livre." if self.is_local else ""
            return LlmError(
                f"{label} demorou demais para responder ({self._timeout:.0f} s).{hint}",
                "timeout",
            )
        if isinstance(exc, e.APIConnectionError):
            if self.is_local:
                return LlmError(
                    f"O Ollama não responde em {base or 'localhost:11434'}. "
                    "Abra o app Ollama (ou rode `ollama serve`).",
                    "offline",
                )
            return LlmError(
                f"Sem conexão com {label}. Verifique a internet.",
                "offline",
            )
        if isinstance(exc, e.ServiceUnavailableError | e.InternalServerError):
            return LlmError(
                f"{label} está instável ou fora do ar agora (erro do servidor).", "server"
            )
        if isinstance(exc, e.BadRequestError) and any(
            w in text for w in ("context length", "context window", "maximum context", "too long")
        ):
            return LlmConfigError(
                f"O texto ficou grande demais para o {model}. Use um modelo com mais contexto.",
                "too_long",
            )
        cls = LlmConfigError if isinstance(exc, e.BadRequestError) else LlmError
        return cls(f"{label}: {_short(exc)}", "other")


def _short(exc: BaseException) -> str:
    text = str(exc).replace("litellm.", "").strip()
    return text[:300] if text else type(exc).__name__
