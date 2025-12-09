import streamlit as st
from yt_dlp import YoutubeDL
from io import BytesIO
import shutil

# Detecta ffmpeg
HAS_FFMPEG = shutil.which("ffmpeg") is not None

# =============================
# Função central de download
# =============================

def baixar_para_memoria(url: str, tipo: str):
    """
    Baixa vídeo/áudio usando yt-dlp **direto para a memória**.
    Não usa pastas nem gravação no disco.
    """
    
    ydl_opts = {
        "format": (
            "bestvideo[height=1080]+bestaudio/bestvideo+bestaudio/best"
            if tipo == "video"
            else "bestaudio/best"
        ),
        "noplaylist": True,
        "ignoreerrors": False,
        "consoletitle": False,
        "retries": 5,
        "outtmpl": "-",        # <- NÃO SALVA EM DISCO
        "logtostderr": False,
        "quiet": True,
    }

    # Se for áudio, converte para MP3 quando ffmpeg estiver disponível
    if tipo == "audio" and HAS_FFMPEG:
        ydl_opts.update({
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        })

    # Buffer de memória onde o vídeo/áudio será gravado
    buffer = BytesIO()

    def hook(d):
        pass  # podemos colocar barra de progresso depois

    ydl_opts["progress_hooks"] = [hook]

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if not info:
            raise RuntimeError("Não foi possível obter informações do vídeo.")

        # yt-dlp sempre retorna os dados binários no campo 'requested_downloads'
        filedata = info.get("requested_downloads", [{}])[0].get("data")

        if not filedata:
            raise RuntimeError("Falha ao capturar o arquivo na memória.")

        buffer.write(filedata)
        buffer.seek(0)

        # Nome final do arquivo
        if tipo == "audio":
            ext = "mp3" if HAS_FFMPEG else info.get("ext", "m4a")
        else:
            ext = info.get("ext", "mp4")

        filename = f"{info.get('title','video')}.{ext}"

        return buffer, filename, info.get("title", "Vídeo")


# =============================
# Interface Streamlit
# =============================

st.set_page_config(page_title="YouTube Downloader", page_icon="🎬")

st.title("🎬 Downloader YouTube (versão sem pastas)")
st.write("Agora 100% compatível com Streamlit Cloud e celular 📱")

url = st.text_input("URL do vídeo:")

tipo = st.radio("Tipo de download:", ["Vídeo (MP4)", "Áudio (MP3)"])
tipo_interno = "video" if tipo == "Vídeo (MP4)" else "audio"

if st.button("⬇️ Iniciar download", disabled=not url.strip()):
    try:
        with st.spinner("Baixando e preparando arquivo..."):
            buffer, filename, title = baixar_para_memoria(url.strip(), tipo_interno)

        st.success("Arquivo pronto para baixar:")
        st.download_button(
            label=f"📥 Baixar: {title}",
            data=buffer,
            file_name=filename,
            mime="application/octet-stream",
        )

    except Exception as e:
        st.error(f"Erro ao baixar: {str(e)}")
