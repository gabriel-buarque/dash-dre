from email.message import EmailMessage
from logging.handlers import RotatingFileHandler
from pathlib import Path
import logging
import smtplib
import threading
import time
import traceback

import streamlit as st

from caminhos import ARQUIVO_LOG_ERROS, ARQUIVO_LOG_PIPELINE, garantir_pastas

INTERVALO_MINIMO_ALERTA = 15 * 60  # 15 minutos por título de incidente
TIMEOUT_SMTP = 15                  # segundos
TAMANHO_MAX_LOG = 5 * 1024 * 1024  # 5 MB por arquivo antes de rotacionar
QTD_BACKUPS_LOG = 3

_ultimos_alertas: dict[str, float] = {}
_trava_alerta = threading.Lock()
_LOGGER_NOME = "dre_pipeline"


def configurar_logs() -> logging.Logger:
    """
    Configura dois arquivos de log com rotação automática:
      1. logs/pipeline_dre.log (INFO+): auditoria de cargas ETL, latência e eventos.
      2. logs/app_errors.log   (ERROR+): falhas críticas, quebras de schema e clone.
    """
    logger = logging.getLogger(_LOGGER_NOME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        garantir_pastas()
        formato = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        caminhos_ativos = {
            Path(getattr(h, "baseFilename", ""))
            for h in logger.handlers
            if isinstance(h, RotatingFileHandler)
        }

        if ARQUIVO_LOG_PIPELINE not in caminhos_ativos:
            h_info = RotatingFileHandler(
                ARQUIVO_LOG_PIPELINE,
                maxBytes=TAMANHO_MAX_LOG,
                backupCount=QTD_BACKUPS_LOG,
                encoding="utf-8",
            )
            h_info.setLevel(logging.INFO)
            h_info.setFormatter(formato)
            logger.addHandler(h_info)

        if ARQUIVO_LOG_ERROS not in caminhos_ativos:
            h_err = RotatingFileHandler(
                ARQUIVO_LOG_ERROS,
                maxBytes=TAMANHO_MAX_LOG,
                backupCount=QTD_BACKUPS_LOG,
                encoding="utf-8",
            )
            h_err.setLevel(logging.ERROR)
            h_err.setFormatter(formato)
            logger.addHandler(h_err)

    except Exception:
        # Se o ambiente bloquear escrita em disco, segue sem derrubar o painel
        pass

    return logger


def registrar_log(mensagem: str, nivel: str = "info", origem: str = "PIPELINE") -> None:
    """Registra evento operacional padronizado no pipeline_dre.log."""
    logger = configurar_logs()
    texto = f"[{origem.upper()}] {mensagem}"
    nivel_limpo = nivel.lower().strip()

    if nivel_limpo == "warning":
        logger.warning(texto)
    elif nivel_limpo == "error":
        logger.error(texto)
    elif nivel_limpo == "critical":
        logger.critical(texto)
    else:
        logger.info(texto)


def em_producao() -> bool:
    try:
        return st.secrets.get("ambiente", {}).get("modo", "desenvolvimento") == "producao"
    except Exception:
        return False


def _obter_config_smtp() -> dict:
    try:
        return dict(st.secrets.get("alertas", {}))
    except Exception:
        return {}


def _pode_enviar_email(titulo: str) -> bool:
    agora = time.time()
    with _trava_alerta:
        ultimo = _ultimos_alertas.get(titulo, 0.0)
        if agora - ultimo < INTERVALO_MINIMO_ALERTA:
            return False
        _ultimos_alertas[titulo] = agora
        return True


def notificar_admin(titulo: str, erro: Exception, origem: str = "SISTEMA") -> None:
    """
    Grava o traceback completo em app_errors.log e pipeline_dre.log.
    Em produção (secrets.toml), envia alerta por e-mail com trava anti-spam.
    """
    logger = configurar_logs()
    detalhe = "".join(traceback.format_exception(type(erro), erro, erro.__traceback__))
    logger.error(f"[{origem.upper()}] {titulo}\n{detalhe}")

    if not em_producao() or not _pode_enviar_email(titulo):
        return

    cfg = _obter_config_smtp()
    chaves_minimas = ("smtp_host", "smtp_user", "smtp_password", "destinatario")
    if not all(cfg.get(k) for k in chaves_minimas):
        logger.error("[ALERTAS] E-mail não enviado: chaves incompletas em st.secrets['alertas'].")
        return

    try:
        msg = EmailMessage()
        msg["Subject"] = f"🚨 [{origem.upper()}] {titulo}"
        msg["From"] = cfg.get("remetente", cfg["smtp_user"])
        msg["To"] = cfg["destinatario"]
        msg.set_content(
            f"Incidente registrado no Painel Balanço Regional (DRE por UF).\n"
            f"Origem: {origem}\n\nDetalhes técnicos:\n{detalhe}"
        )
        with smtplib.SMTP_SSL(
            cfg["smtp_host"], int(cfg.get("smtp_port", 465)), timeout=TIMEOUT_SMTP
        ) as smtp:
            smtp.login(cfg["smtp_user"], cfg["smtp_password"])
            smtp.send_message(msg)
        registrar_log(f"Alerta SMTP enviado para {cfg['destinatario']}: {titulo}", origem="ALERTAS")
    except Exception as falha_smtp:
        logger.error(f"[ALERTAS] Falha ao enviar e-mail SMTP: {falha_smtp}")


def ler_ultimas_linhas_log(caminho_log: Path = ARQUIVO_LOG_PIPELINE, limite: int = 25) -> str:
    """Retorna as últimas N linhas do arquivo de log para inspeção na interface."""
    if not caminho_log.exists():
        return "Nenhum evento registrado ainda."
    try:
        linhas = caminho_log.read_text(encoding="utf-8", errors="replace").splitlines()
        trecho = linhas[-limite:] if len(linhas) > limite else linhas
        return "\n".join(trecho) if trecho else "Arquivo de log vazio."
    except Exception as e:
        return f"Não foi possível ler o log: {e}"
