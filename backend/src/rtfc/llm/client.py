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

# Alfabetos que não deveriam aparecer em respostas pt/en/es (grego, cirílico, árabe, indianos,
# CJK…). Modelos às vezes "vazam" uma palavra de outro idioma no meio do texto.
_FOREIGN_SCRIPT = re.compile(
    r"[\u0370-\u03ff\u0400-\u052f\u0590-\u08ff\u0900-\u0dff\u0e00-\u0fff"
    r"\u1100-\u11ff\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]"
)
MAX_RETRIES = 2


class LlmError(RuntimeError):
    pass


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
    def litellm_model(self) -> str:
        return f"{self.provider.litellm_prefix}{self.role.model}"

    def _call_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        base_url = self.role.base_url or self.provider.default_base_url
        if base_url:
            kwargs["api_base"] = base_url
        key = self._secrets.get(self.provider.id)
        if self.provider.needs_key and not key:
            raise LlmConfigError(f"chave de API do {self.provider.label} não configurada")
        if key:
            kwargs["api_key"] = key
        if self.provider.id == "ollama":
            # Raciocínio (Qwen3, DeepSeek-R1) deixa lento demais para rodar a cada frase.
            kwargs["think"] = False
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
            return LlmResult(fake_reply(messages, schema), 50, "fake/fake")  # type: ignore[arg-type]

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
                        f"resposta fora do formato após {attempt + 1} tentativas"
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
                raise LlmConfigError(_short(exc)) from exc
            except (
                llm_errors.RateLimitError,
                llm_errors.APIConnectionError,
                llm_errors.Timeout,
                llm_errors.ServiceUnavailableError,
                llm_errors.InternalServerError,
            ) as exc:
                if attempt == MAX_RETRIES:
                    raise LlmError(_short(exc)) from exc
                log.warning("LLM %s falhou (%s); tentando de novo", self.litellm_model, _short(exc))
                await asyncio.sleep(delay)
                delay *= 2
            except Exception as exc:
                raise LlmError(_short(exc)) from exc
        raise AssertionError("inalcançável")


def _short(exc: BaseException) -> str:
    text = str(exc).replace("litellm.", "").strip()
    return text[:300] if text else type(exc).__name__
