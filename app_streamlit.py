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

# detecta se o ffmpeg está disponível no ambiente
HAS_FFMPEG = shutil.which("ffmpeg") is not None


def get_ydl_opts(download_type: str, output_dir: Path, is_playlist: bool):
    """
    Opções do yt-dlp:
    - download_type: 'video' ou 'audio'
    - is_playlist: True se for playlist
    """
    # Saída SEMPRE no formato: downloads/<pasta>/<ID>.<ext>
    common_opts = {
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
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
            # Tenta 1080p com merge, depois melhor qualidade
            video_format = (
                "bestvideo[height=1080]+bestaudio/"
                "bestvideo+bestaudio/"
                "best"
            )
        else:
            # Sem ffmpeg: só formatos progressivos (geralmente até 720p)
            video_format = (
                "best[height=1080][ext=mp4]/"
                "best[ext=mp4]/"
                "best"
            )
        common_opts.update({"format": video_format})

    elif download_type == "audio":
        if HAS_FFMPEG:
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
            # Sem ffmpeg, baixa no formato original (m4a/webm)
            common_opts.update({"format": "bestaudio/best"})

    return common_opts


def _achar_arquivo_por_id(video_id: str, output_dir: Path, prefer_mp3: bool = False):
    """
    Procura um arquivo na pasta de saída com base no ID do vídeo.
    Se prefer_mp3=True, tenta primeiro <id>.mp3.
    """
    if not video_id:
        return None

    # se for áudio com conversão, o mais comum será <id>.mp3
    if prefer_mp3:
        mp3_path = output_dir / f"{video_id}.mp3"
        if mp3_path.exists():
            return str(mp3_path)

    # pega o primeiro arquivo que contenha exatamente o ID antes da extensão
    for p in output_dir.glob(f"{video_id}.*"):
        if p.is_file():
            return str(p)

    return None


def download_single(url: str, download_type: str, output_dir: Path):
    """
    Download de um único vídeo/áudio.
    Retorna: { title, filename, bytes }
    """
    ydl_opts = get_ydl_opts(download_type, output_dir, is_playlist=False)

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    video_id = info.get("id")
    title = info.get("title", "Arquivo")

    prefer_mp3 = download_type == "audio" and HAS_FFMPEG
    filepath = _achar_arquivo_por_id(video_id, output_dir, prefer_mp3=prefer_mp3)

    if not filepath or not os.path.exists(filepath):
        raise FileNotFoundError(
            "O yt-dlp não conseguiu salvar o arquivo final no servidor. "
            "Em deploy (ex.: Streamlit Cloud), isso geralmente é falta do FFmpeg "
            "ou problema de escrita na pasta de downloads."
        )

    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        data = f.read()

    return {"title": title, "filename": filename, "bytes": data}


def download_playlist(url: str, download_type: str, output_dir: Path):
    """
    Download de playlist.
    Retorna lista de itens: { title, filename, bytes }
    """
    ydl_opts = get_ydl_opts(download_type, output_dir, is_playlist=True)
    resultados = []

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Se não for playlist, trata como único
    if not info.get("_type") == "playlist":
        resultados.append(download_single(url, download_type, output_dir))
        return resultados

    entries = info.get("entries", []) or []
    for entry in entries:
        if not entry:
            continue

        video_id = entry.get("id")
        title = entry.get("title", "Sem título")

        prefer_mp3 = download_type == "audio" and HAS_FFMPEG
        filepath = _achar_arquivo_por_id(video_id, output_dir, prefer_mp3=prefer_mp3)

        if not filepath or not os.path.exists(filepath):
            # pula o item problemático
            continue

        filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            data = f.read()

        resultados.append({"title": title, "filename": filename, "bytes": data})

    return resultados


# =========================
# INTERFACE STREAMLIT
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
         "Em deploy (Streamlit Cloud), crie um arquivo `packages.txt` com o texto: `ffmpeg`."
)
st.caption(msg_ffmpeg)

st.write(
    "Baixe **vídeos**, **áudios** ou **playlists** do YouTube.\n\n"
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
    )

with col2:
    output_subdir = st.text_input(
        "Pasta (no servidor) para organizar os arquivos:",
        value="default",
    )

formato_playlist = None
if tipo_download == "Playlist":
    formato_playlist = st.radio(
        "Formato da playlist:",
        options=["Vídeo (MP4)", "Áudio"],
    )

output_dir = BASE_DOWNLOAD_DIR / output_subdir
output_dir.mkdir(parents=True, exist_ok=True)

st.info(
    "📱 **No celular:**\n"
    "1. Clique em **Iniciar download** para o servidor preparar o arquivo.\n"
    "2. Depois clique em **Baixar** para salvar no aparelho (o navegador escolhe a pasta)."
)

st.divider()

# ETAPA 1 – PREPARAR
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
                    st.success(f"Arquivo preparado: **{resultado['title']}**")

                elif tipo_download == "Áudio":
                    resultado = download_single(url.strip(), "audio", output_dir)
                    st.session_state["downloads_prontos"] = {
                        "tipo": "single",
                        "itens": [resultado],
                    }
                    st.success(f"Áudio preparado: **{resultado['title']}**")

                elif tipo_download == "Playlist":
                    if not formato_playlist:
                        st.error("Selecione o formato da playlist (Vídeo ou Áudio).")
                    else:
                        internal_type = (
                            "video" if formato_playlist == "Vídeo (MP4)" else "audio"
                        )
                        resultados = download_playlist(
                            url.strip(), internal_type, output_dir
                        )
                        if not resultados:
                            st.error(
                                "Nenhum item foi baixado. "
                                "Verifique a URL da playlist e se o FFmpeg está disponível."
                            )
                        else:
                            st.session_state["downloads_prontos"] = {
                                "tipo": "playlist",
                                "itens": resultados,
                            }
                            st.success(
                                f"Playlist preparada! {len(resultados)} item(s) pronto(s)."
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

# ETAPA 2 – BAIXAR PARA O DISPOSITIVO
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
