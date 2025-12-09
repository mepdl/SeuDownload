import os
from pathlib import Path
from io import BytesIO

import streamlit as st
from yt_dlp import YoutubeDL

# =========================
# CONFIGURAÇÕES BÁSICAS
# =========================

BASE_DOWNLOAD_DIR = Path("downloads")
BASE_DOWNLOAD_DIR.mkdir(exist_ok=True)


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
        # 1) tenta 1080p
        # 2) se não tiver, pega a melhor qualidade disponível
        common_opts.update(
            {
                "format": "bestvideo[height=1080]+bestaudio/bestvideo+bestaudio/best",
            }
        )
    elif download_type == "audio":
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

    return common_opts


def download_single(url: str, download_type: str, output_dir: Path):
    """
    Download de um único vídeo/áudio.
    Retorna título, caminho e bytes do arquivo.
    """
    ydl_opts = get_ydl_opts(download_type, output_dir, is_playlist=False)

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        filepath = None
        if isinstance(info, dict) and "requested_downloads" in info:
            try:
                filepath = info["requested_downloads"][0]["filepath"]
            except Exception:
                pass

        if filepath is None:
            filepath = ydl.prepare_filename(info)
            if download_type == "audio":
                base, _ = os.path.splitext(filepath)
                filepath = base + ".mp3"

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

    results = []
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # Se não for playlist, trata como vídeo único
        if not info.get("_type") == "playlist":
            single = download_single(url, download_type, output_dir)
            results.append(single)
            return results

        entries = info.get("entries", []) or []
        for entry in entries:
            if entry is None:
                continue

            title = entry.get("title", "Sem título")
            filepath = None

            if "requested_downloads" in entry:
                try:
                    filepath = entry["requested_downloads"][0]["filepath"]
                except Exception:
                    pass

            if filepath is None:
                try:
                    filepath = ydl.prepare_filename(entry)
                    if download_type == "audio":
                        base, _ = os.path.splitext(filepath)
                        filepath = base + ".mp3"
                except Exception:
                    filepath = None

            if filepath and os.path.exists(filepath):
                filename = os.path.basename(filepath)
                with open(filepath, "rb") as f:
                    data = f.read()

                results.append(
                    {
                        "title": title,
                        "filename": filename,
                        "bytes": data,
                    }
                )

    return results


# =========================
# CONFIG STREAMLIT
# =========================

st.set_page_config(
    page_title="YouTube Downloader",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 YouTube Downloader com Streamlit")
st.write(
    "Baixe **vídeos**, **áudios (MP3)** ou **playlists** do YouTube.\n\n"
    "👉 Use apenas com conteúdo que você tem permissão para baixar."
)

st.divider()

# Estado para guardar resultado do download (para etapa 2)
if "downloads_prontos" not in st.session_state:
    st.session_state["downloads_prontos"] = None

url = st.text_input("Cole aqui a URL do vídeo ou playlist do YouTube:")

col1, col2 = st.columns(2)
with col1:
    tipo_download = st.radio(
        "Tipo de download:",
        options=["Vídeo (MP4)", "Áudio (MP3)", "Playlist"],
        help="Escolha se quer baixar um vídeo, apenas o áudio ou uma playlist inteira.",
    )

with col2:
    output_subdir = st.text_input(
        "Pasta (no servidor) para organizar os arquivos:",
        value="default",
        help="Apenas para organização no computador/servidor que roda o app.",
    )

# Se for playlist, escolher se será vídeo ou áudio
formato_playlist = None
if tipo_download == "Playlist":
    formato_playlist = st.radio(
        "Formato da playlist:",
        options=["Vídeo (MP4)", "Áudio (MP3)"],
        help="Defina se a playlist será baixada como vídeo ou áudio (MP3).",
    )

output_dir = BASE_DOWNLOAD_DIR / output_subdir
output_dir.mkdir(parents=True, exist_ok=True)

st.info(
    "⚠️ **Importante para celular:**\n"
    "- Primeiro clique em **Iniciar download** para preparar o arquivo.\n"
    "- Depois clique em **Baixar para o dispositivo**.\n"
    "- O navegador do seu celular vai perguntar onde salvar ou vai salvar na pasta de downloads."
)

st.divider()

# =========================
# ETAPA 1 – PREPARAR O DOWNLOAD
# =========================

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

                elif tipo_download == "Áudio (MP3)":
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
                                "Nenhum item foi baixado. Verifique a URL da playlist."
                            )
                        else:
                            st.session_state["downloads_prontos"] = {
                                "tipo": "playlist",
                                "itens": resultados,
                            }
                            st.success(
                                f"Playlist preparada! {len(resultados)} item(s) pronto(s) para baixar."
                            )

            except Exception as e:
                st.error(
                    "Ocorreu um erro durante o download. "
                    "Verifique se a URL é válida e tente novamente."
                )
                st.exception(e)

st.divider()

# =========================
# ETAPA 2 – BAIXAR PARA O DISPOSITIVO
# =========================

downloads = st.session_state.get("downloads_prontos")
if downloads:
    st.markdown("### 📲 Etapa 2 – Salvar no seu dispositivo")

    st.info(
        "No celular, ao tocar nos botões abaixo, o **navegador** irá perguntar onde salvar "
        "ou salvar direto na pasta de downloads.\n\n"
        "Se nada acontecer, verifique se o navegador permite downloads de arquivos."
    )

    for item in downloads["itens"]:
        title = item["title"]
        filename = item["filename"]
        data = item["bytes"]

        st.download_button(
            label=f"📥 Baixar: {title}",
            data=data,
            file_name=filename,
            mime=None,  # deixa o navegador detectar
            key=filename,
        )
else:
    st.markdown(
        "_Nenhum arquivo preparado ainda. Cole a URL, configure o tipo e clique em **Iniciar download**._"
    )
