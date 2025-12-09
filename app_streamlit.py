import os
from pathlib import Path
import shutil

import streamlit as st
from yt_dlp import YoutubeDL

# =========================
# CONFIGURAÇÕES BÁSICAS
# =========================

BASE_DOWNLOAD_DIR = Path("downloads")
BASE_DOWNLOAD_DIR.mkdir(exist_ok=True)

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def get_ydl_opts(download_type: str, output_dir: Path, is_playlist: bool):
    """
    Define opções do yt-dlp:
    - download_type: 'video' ou 'audio'
    - is_playlist: True se for playlist (não forçar noplaylist)
    """
    common_opts = {
        "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        "ignoreerrors": True,
        "noprogress": True,
        "continuedl": True,
        "retries": 5,
        "consoletitle": False,
    }

    if not is_playlist:
        common_opts["noplaylist"] = True

    if download_type == "video":
        if HAS_FFMPEG:
            # Com ffmpeg: tenta 1080p com merge, senão melhor qualidade disponível
            fmt = "bestvideo[height=1080]+bestaudio/bestvideo+bestaudio/best"
        else:
            # Sem ffmpeg: evita merge (pegando formatos progressivos)
            # Provavelmente vai até 720p, mas funciona no Streamlit Cloud sem ffmpeg.
            fmt = (
                "best[height=1080][ext=mp4]/"
                "best[ext=mp4]/"
                "best"
            )
        common_opts.update({"format": fmt})

    elif download_type == "audio":
        if HAS_FFMPEG:
            # Baixa e converte para MP3
            common_opts.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    ],
                }
            )
        else:
            # Sem ffmpeg: baixa no formato original (m4a/webm)
            common_opts.update({"format": "bestaudio/best"})

    return common_opts


def _resolver_caminho(info: dict, ydl: YoutubeDL, download_type: str, output_dir: Path):
    """
    Tenta encontrar o caminho real do arquivo baixado, de forma robusta.
    """
    candidatos = []

    # 1) requested_downloads (quando disponível)
    if isinstance(info, dict) and "requested_downloads" in info:
        for rd in info["requested_downloads"]:
            fp = rd.get("filepath")
            if fp:
                candidatos.append(fp)

    # 2) _filename (yt-dlp costuma preencher)
    if isinstance(info, dict):
        fp = info.get("_filename")
        if fp:
            candidatos.append(fp)

    # 3) prepare_filename (formato baseado no outtmpl)
    try:
        fp = ydl.prepare_filename(info)
        if download_type == "audio" and HAS_FFMPEG:
            # quando converte para mp3, a extensão final é .mp3
            base, _ = os.path.splitext(fp)
            fp_mp3 = base + ".mp3"
            candidatos.append(fp_mp3)
        else:
            candidatos.append(fp)
    except Exception:
        pass

    # 4) procurar por ID do vídeo na pasta de saída
    video_id = info.get("id")
    if video_id:
        for p in output_dir.glob(f"*{video_id}*"):
            candidatos.append(str(p))

    # Devolve o primeiro caminho que realmente existe
    vistos = set()
    for fp in candidatos:
        if not fp or fp in vistos:
            continue
        vistos.add(fp)
        if os.path.exists(fp):
            return fp

    return None


def download_single(url: str, download_type: str, output_dir: Path):
    """
    Download de um único vídeo/áudio.
    Retorna título, nome do arquivo e bytes.
    """
    ydl_opts = get_ydl_opts(download_type, output_dir, is_playlist=False)

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = _resolver_caminho(info, ydl, download_type, output_dir)

    if not filepath or not os.path.exists(filepath):
        raise FileNotFoundError(
            "O yt-dlp não conseguiu salvar o arquivo final no servidor. "
            "Em deploy (ex.: Streamlit Cloud), isso geralmente significa falta do FFmpeg "
            "ou permissão de escrita na pasta."
        )

    title = info.get("title", "Arquivo")
    filename = os.path.basename(filepath)

    with open(filepath, "rb") as f:
        data = f.read()

    return {
        "title": title,
        "filename": filename,
        "bytes": data,
    }


def download_playlist(url: str, download_type: str, output_dir: Path):
    """
    Download de playlist.
    Retorna lista de itens: {title, filename, bytes}
    """
    ydl_opts = get_ydl_opts(download_type, output_dir, is_playlist=True)
    resultados = []

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # Não é playlist? trata como único
        if not info.get("_type") == "playlist":
            resultados.append(download_single(url, download_type, output_dir))
            return resultados

        entries = info.get("entries", []) or []
        for entry in entries:
            if entry is None:
                continue

            filepath = _resolver_caminho(entry, ydl, download_type, output_dir)
            if not filepath or not os.path.exists(filepath):
                # pula o item problemático mas continua a playlist
                continue

            title = entry.get("title", "Sem título")
            filename = os.path.basename(filepath)
            with open(filepath, "rb") as f:
                data = f.read()

            resultados.append(
                {
                    "title": title,
                    "filename": filename,
                    "bytes": data,
                }
            )

    return resultados


# =========================
# CONFIG STREAMLIT
# =========================

st.set_page_config(
    page_title="YouTube Downloader",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 YouTube Downloader com Streamlit")

msg_ffmpeg = (
    "✅ FFmpeg detectado. Downloads em **1080p com merge** e **áudio em MP3** ativados."
    if HAS_FFMPEG
    else "⚠️ FFmpeg **não** detectado. "
         "Vídeos podem não chegar em 1080p e o áudio será baixado no formato original (m4a/webm). "
         "Em deploy (Streamlit Cloud), crie um arquivo `packages.txt` com a linha `ffmpeg`."
)
st.caption(msg_ffmpeg)

st.write(
    "Baixe **vídeos**, **áudios (MP3 ou formato original)** ou **playlists** do YouTube.\n\n"
    "👉 Use apenas com conteúdo que você tem permissão para baixar."
)

st.divider()

if "downloads_prontos" not in st.session_state:
    st.session_state["downloads_prontos"] = None

url = st.text_input("Cole aqui a URL do vídeo ou playlist do YouTube:")

col1, col2 = st.columns(2)
with col1:
    tipo_download = st.radio(
        "Tipo de download:",
        options=["Vídeo (MP4)", "Áudio", "Playlist"],
        help="Escolha se quer baixar um único vídeo, apenas o áudio ou uma playlist inteira.",
    )

with col2:
    output_subdir = st.text_input(
        "Pasta (no servidor) para organizar os arquivos:",
        value="default",
        help="Apenas para organização no computador/servidor que roda o app.",
    )

formato_playlist = None
if tipo_download == "Playlist":
    formato_playlist = st.radio(
        "Formato da playlist:",
        options=["Vídeo (MP4)", "Áudio"],
        help="Defina se a playlist será baixada como vídeo ou áudio.",
    )

output_dir = BASE_DOWNLOAD_DIR / output_subdir
output_dir.mkdir(parents=True, exist_ok=True)

st.info(
    "⚠️ **No celular:**\n"
    "1. Clique em **Iniciar download** para o servidor preparar o arquivo.\n"
    "2. Depois clique nos botões de **Baixar** para salvar no seu dispositivo (o navegador decide a pasta)."
)

st.divider()

# ETAPA 1 – Preparar download
if st.button("⬇️ Iniciar download", type="primary", disabled=not url.strip()):
    if not url.strip():
        st.warning("Informe uma URL válida do YouTube.")
    else:
        st.session_state["downloads_prontos"] = None

        with st.spinner("Baixando e preparando arquivo(s)..."):
            try:
                if tipo_download == "Vídeo (MP4)":
                    resultado = download_single(url.strip(), "video", output_dir)
                    st.session_state["downloads_prontos"] = {
                        "tipo": "single",
                        "itens": [resultado],
                    }
                    st.success(
                        f"Arquivo preparado com sucesso: **{resultado['title']}**"
                    )

                elif tipo_download == "Áudio":
                    resultado = download_single(url.strip(), "audio", output_dir)
                    st.session_state["downloads_prontos"] = {
                        "tipo": "single",
                        "itens": [resultado],
                    }
                    st.success(
                        f"Arquivo de áudio preparado com sucesso: **{resultado['title']}**"
                    )

                elif tipo_download == "Playlist":
                    if not formato_playlist:
                        st.error(
                            "Selecione o formato da playlist (Vídeo ou Áudio) antes."
                        )
                    else:
                        internal_type = (
                            "video" if formato_playlist == "Vídeo (MP4)" else "audio"
                        )
                        resultados = download_playlist(
                            url.strip(), internal_type, output_dir
                        )

                        if not resultados:
                            st.error(
                                "Nenhum item foi baixado. Verifique a URL da playlist "
                                "e se o servidor tem FFmpeg instalado."
                            )
                        else:
                            st.session_state["downloads_prontos"] = {
                                "tipo": "playlist",
                                "itens": resultados,
                            }
                            st.success(
                                f"Playlist preparada! {len(resultados)} item(s) pronto(s) para baixar."
                            )

            except FileNotFoundError as e:
                st.error(str(e))
            except Exception as e:
                st.error(
                    "Ocorreu um erro durante o download. "
                    "Verifique se a URL é válida e tente novamente."
                )
                st.exception(e)

st.divider()

# ETAPA 2 – Baixar para o dispositivo
downloads = st.session_state.get("downloads_prontos")
if downloads:
    st.markdown("### 📲 Etapa 2 – Salvar no seu dispositivo")

    for item in downloads["itens"]:
        st.download_button(
            label=f"📥 Baixar: {item['title']}",
            data=item["bytes"],
            file_name=item["filename"],
            mime=None,
            key=item["filename"],
        )
else:
    st.markdown(
        "_Nenhum arquivo preparado ainda. Cole a URL, configure o tipo e clique em **Iniciar download**._"
    )
