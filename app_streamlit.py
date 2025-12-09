import os
from pathlib import Path

import streamlit as st
from yt_dlp import YoutubeDL

# =========================
# CONFIGURAÇÕES BÁSICAS
# =========================

# Pasta padrão onde os arquivos serão salvos
BASE_DOWNLOAD_DIR = Path("downloads")
BASE_DOWNLOAD_DIR.mkdir(exist_ok=True)


def get_ydl_opts(download_type: str, output_dir: Path, is_playlist: bool):
    """
    Retorna as opções do yt-dlp de acordo com o tipo de download:
    - download_type: 'video' ou 'audio'
    - is_playlist: True se for playlist (não forçar noplaylist)
    """
    common_opts = {
        "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        "ignoreerrors": True,  # continua mesmo se algum vídeo falhar
        "noprogress": True,
        "continuedl": True,
        "retries": 5,
        "consoletitle": False,
    }

    # Se for playlist, não forçamos noplaylist
    if not is_playlist:
        common_opts["noplaylist"] = True

    if download_type == "video":
        # Regra pedida:
        # 1) Tentar sempre baixar em 1080p
        # 2) Se não tiver 1080p, baixa na maior qualidade disponível
        common_opts.update(
            {
                "format": "bestvideo[height=1080]+bestaudio/bestvideo+bestaudio/best",
            }
        )
    elif download_type == "audio":
        # Melhor áudio possível e converte para MP3
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
    Faz download de um único vídeo (vídeo ou áudio) e retorna
    um dicionário com informações do arquivo salvo.
    """
    ydl_opts = get_ydl_opts(download_type, output_dir, is_playlist=False)

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # Em versões recentes, requested_downloads contém o caminho final
        filepath = None
        if isinstance(info, dict) and "requested_downloads" in info:
            try:
                filepath = info["requested_downloads"][0]["filepath"]
            except Exception:
                pass

        # Fallback usando prepare_filename
        if filepath is None:
            filepath = ydl.prepare_filename(info)
            if download_type == "audio":
                # Quando há pós-processamento, a extensão final é MP3
                base, _ = os.path.splitext(filepath)
                filepath = base + ".mp3"

    return {
        "title": info.get("title", "Arquivo"),
        "filepath": filepath,
    }


def download_playlist(url: str, download_type: str, output_dir: Path):
    """
    Faz download de uma playlist inteira (vídeo ou áudio).
    Retorna uma lista de dicionários com título e caminho de cada item.
    """
    ydl_opts = get_ydl_opts(download_type, output_dir, is_playlist=True)

    results = []
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # Se não for playlist, tratamos como um único vídeo
        if not info.get("_type") == "playlist":
            single = {
                "title": info.get("title", "Arquivo"),
            }
            filepath = None
            if "requested_downloads" in info:
                try:
                    filepath = info["requested_downloads"][0]["filepath"]
                except Exception:
                    pass

            if filepath is None:
                filepath = ydl.prepare_filename(info)
                if download_type == "audio":
                    base, _ = os.path.splitext(filepath)
                    filepath = base + ".mp3"

            single["filepath"] = filepath
            results.append(single)
            return results

        # Playlist de fato
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

            results.append(
                {
                    "title": title,
                    "filepath": filepath,
                }
            )

    return results


# =========================
# INTERFACE STREAMLIT
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

url = st.text_input("Cole aqui a URL do vídeo ou playlist do YouTube:")

col1, col2 = st.columns(2)
with col1:
    download_type = st.radio(
        "Tipo de download:",
        options=["Vídeo (MP4)", "Áudio (MP3)", "Playlist"],
        help="Escolha se quer baixar um vídeo, apenas o áudio ou uma playlist inteira.",
    )

with col2:
    output_subdir = st.text_input(
        "Pasta (dentro de 'downloads') para salvar os arquivos:",
        value="default",
        help="Os arquivos serão salvos na pasta 'downloads/NOME_DA_PASTA'.",
    )

# Se for playlist, escolha do formato (vídeo ou áudio) aparece
playlist_format = None
if download_type == "Playlist":
    playlist_format = st.radio(
        "Formato da playlist:",
        options=["Vídeo (MP4)", "Áudio (MP3)"],
        help="Defina se a playlist será baixada como vídeo ou apenas áudio (MP3).",
    )

output_dir = BASE_DOWNLOAD_DIR / output_subdir
output_dir.mkdir(parents=True, exist_ok=True)

st.info(f"Arquivos serão salvos em: `{output_dir.resolve()}`")

if st.button("⬇️ Iniciar download", type="primary", disabled=not url.strip()):
    if not url.strip():
        st.warning("Informe uma URL válida do YouTube.")
    else:
        with st.spinner("Baixando... aguarde."):
            try:
                if download_type == "Vídeo (MP4)":
                    result = download_single(url.strip(), "video", output_dir)

                    if result["filepath"] and os.path.exists(result["filepath"]):
                        filename = os.path.basename(result["filepath"])
                        with open(result["filepath"], "rb") as f:
                            data = f.read()

                        st.success(f"Vídeo baixado com sucesso: **{result['title']}**")

                        st.download_button(
                            label="📥 Baixar arquivo",
                            data=data,
                            file_name=filename,
                        )
                    else:
                        st.error(
                            "Não foi possível localizar o arquivo baixado. "
                            "Verifique a pasta de downloads."
                        )

                elif download_type == "Áudio (MP3)":
                    result = download_single(url.strip(), "audio", output_dir)

                    if result["filepath"] and os.path.exists(result["filepath"]):
                        filename = os.path.basename(result["filepath"])
                        with open(result["filepath"], "rb") as f:
                            data = f.read()

                        st.success(
                            f"Áudio (MP3) baixado com sucesso: **{result['title']}**"
                        )

                        st.download_button(
                            label="📥 Baixar arquivo",
                            data=data,
                            file_name=filename,
                        )
                    else:
                        st.error(
                            "Não foi possível localizar o arquivo baixado. "
                            "Verifique a pasta de downloads."
                        )

                elif download_type == "Playlist":
                    if not playlist_format:
                        st.error(
                            "Selecione o formato da playlist (Vídeo ou Áudio) antes de iniciar o download."
                        )
                    else:
                        internal_type = (
                            "video"
                            if playlist_format == "Vídeo (MP4)"
                            else "audio"
                        )
                        results = download_playlist(url.strip(), internal_type, output_dir)

                        if not results:
                            st.error("Nenhum item foi baixado. Verifique a URL.")
                        else:
                            st.success(
                                f"Playlist baixada! Itens salvos em `{output_dir.resolve()}`"
                            )

                            st.write("### Arquivos baixados:")
                            for item in results:
                                title = item.get("title", "Sem título")
                                filepath = item.get("filepath")

                                if filepath and os.path.exists(filepath):
                                    filename = os.path.basename(filepath)
                                    with open(filepath, "rb") as f:
                                        data = f.read()

                                    st.download_button(
                                        label=f"📥 {title}",
                                        data=data,
                                        file_name=filename,
                                        key=filepath,
                                    )
                                else:
                                    st.warning(
                                        f"Não foi possível localizar o arquivo para: **{title}**"
                                    )

            except Exception as e:
                st.error(
                    "Ocorreu um erro durante o download. "
                    "Verifique se a URL é válida e tente novamente."
                )
                st.exception(e)
