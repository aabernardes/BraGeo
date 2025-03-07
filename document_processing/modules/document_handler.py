import os
import shutil
import logging
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -------------------------------------------------------------------------
# Define directories where caches will be stored.
# -------------------------------------------------------------------------
DIRETORIO_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRETORIO_DOCUMENTOS = os.path.join(DIRETORIO_BASE, "documments")
DIRETORIO_OCR_CACHE = os.path.join(DIRETORIO_DOCUMENTOS, "processed_ocr_files")
DIRETORIO_GPT_CACHE = os.path.join(DIRETORIO_DOCUMENTOS, "processed_gpt_files")

# Subfolders for GPT outputs:
DIRETORIO_GPT_COORDINATES = os.path.join(DIRETORIO_GPT_CACHE, "gpt_processed_coordinates")
DIRETORIO_GPT_ACTIONS = os.path.join(DIRETORIO_GPT_CACHE, "gpt_processed_actions")
DIRETORIO_GPT_OWNERS = os.path.join(DIRETORIO_GPT_CACHE, "gpt_processed_owners")
# The generic folder is no longer used for saving GPT results.
# DIRETORIO_GPT_GENERIC = os.path.join(DIRETORIO_GPT_CACHE, "gpt_processed_")

def garantir_diretorio_cache():
    """
    Ensures that the 'documments' folder and its subdirectories (OCR, GPT, and GPT subdivisions)
    exist.
    """
    os.makedirs(DIRETORIO_DOCUMENTOS, exist_ok=True)
    os.makedirs(DIRETORIO_OCR_CACHE, exist_ok=True)
    os.makedirs(DIRETORIO_GPT_CACHE, exist_ok=True)
    os.makedirs(DIRETORIO_GPT_COORDINATES, exist_ok=True)
    os.makedirs(DIRETORIO_GPT_ACTIONS, exist_ok=True)
    os.makedirs(DIRETORIO_GPT_OWNERS, exist_ok=True)

def obter_nome_arquivo_cache(caminho_arquivo, tipo="ocr"):
    """
    Returns the cache file path based on the original file's name.
    
    :param caminho_arquivo: Path of the original file (e.g., a PDF).
    :param tipo: "ocr" for OCR.
    :return: For OCR, returns a .txt file in processed_ocr_files.
             (GPT files are saved directly in their dedicated subfolders.)
    """
    garantir_diretorio_cache()
    nome_base = os.path.basename(caminho_arquivo)
    nome_sem_extensao = os.path.splitext(nome_base)[0]
    if tipo == "ocr":
        return os.path.join(DIRETORIO_OCR_CACHE, f"{nome_sem_extensao}.txt")
    else:
        # We no longer use a generic path for GPT.
        return None

def salvar_resultado_ocr(caminho_arquivo, texto_ocr):
    """
    Saves the OCR result in a .txt file in the OCR cache directory.
    """
    caminho_cache = obter_nome_arquivo_cache(caminho_arquivo, tipo="ocr")
    with open(caminho_cache, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto_ocr)
    logging.info(f"✅ Resultado do OCR armazenado em cache: {caminho_cache}")

def carregar_ocr_cache(caminho_arquivo):
    """
    Loads the OCR result from a cached .txt file, if it exists.
    """
    caminho_cache = obter_nome_arquivo_cache(caminho_arquivo, tipo="ocr")
    if os.path.exists(caminho_cache):
        logging.info(f"📂 Resultado de OCR em cache encontrado para: {caminho_cache}")
        with open(caminho_cache, "r", encoding="utf-8") as arquivo:
            return arquivo.read()
    logging.info(f"❌ Nenhum resultado de OCR em cache encontrado para: {caminho_cache}")
    return None

def carregar_gpt_cache(caminho_arquivo):
    """
    Loads the GPT results from the cache by reading the individual JSON files from their dedicated subfolders.
    Returns a list with three elements: [Coordinates JSON, Actions JSON, Owners JSON].
    """
    nome_base = os.path.basename(caminho_arquivo)
    nome_sem_extensao = os.path.splitext(nome_base)[0]
    
    caminho_coordinates = os.path.join(DIRETORIO_GPT_COORDINATES, f"{nome_sem_extensao}_coordinates.json")
    caminho_actions = os.path.join(DIRETORIO_GPT_ACTIONS, f"{nome_sem_extensao}_actions.json")
    caminho_owners = os.path.join(DIRETORIO_GPT_OWNERS, f"{nome_sem_extensao}_owners.json")
    
    if os.path.exists(caminho_coordinates) and os.path.exists(caminho_actions) and os.path.exists(caminho_owners):
        logging.info(f"📂 Resultados do GPT encontrados nos subdiretórios.")
        with open(caminho_coordinates, "r", encoding="utf-8") as f:
            coordinates = json.load(f)
        with open(caminho_actions, "r", encoding="utf-8") as f:
            actions = json.load(f)
        with open(caminho_owners, "r", encoding="utf-8") as f:
            owners = json.load(f)
        return [coordinates, actions, owners]
    logging.info(f"❌ Nenhum resultado do GPT em cache encontrado para: {caminho_arquivo}")
    return None

def limpar_cache():
    """
    Removes the cache directories (OCR and GPT) inside the 'documments' folder.
    """
    for diretorio in [DIRETORIO_OCR_CACHE, DIRETORIO_GPT_CACHE]:
        if os.path.exists(diretorio):
            shutil.rmtree(diretorio)
            logging.info(f"🗑️ Cache no diretório '{diretorio}' limpo com sucesso.")
        else:
            logging.info(f"🗑️ Nenhum diretório de cache encontrado para limpar: '{diretorio}'")

def salvar_resultados_gpt(caminho_arquivo, resultados_gpt):
    """
    Saves the individual GPT outputs into their dedicated subfolders:
      - resultados_gpt[0]: JSON de Georreferenciamento (saved in DIRETORIO_GPT_COORDINATES)
      - resultados_gpt[1]: JSON de Histórico de Ações (saved in DIRETORIO_GPT_ACTIONS)
      - resultados_gpt[2]: JSON dos Proprietários Atuais (saved in DIRETORIO_GPT_OWNERS)
      
    Note: The refined text is not saved to the generic folder.
    """
    garantir_diretorio_cache()
    nome_base = os.path.basename(caminho_arquivo)
    nome_sem_extensao = os.path.splitext(nome_base)[0]
    
    # Save JSON de Georreferenciamento
    if len(resultados_gpt) >= 1:
        caminho_saida = os.path.join(DIRETORIO_GPT_COORDINATES, f"{nome_sem_extensao}_coordinates.json")
        with open(caminho_saida, "w", encoding="utf-8") as f:
            f.write(resultados_gpt[0])
        logging.info(f"✅ GPT (Georreferenciamento) salvo em: {caminho_saida}")
    
    # Save JSON de Histórico de Ações
    if len(resultados_gpt) >= 2:
        caminho_saida = os.path.join(DIRETORIO_GPT_ACTIONS, f"{nome_sem_extensao}_actions.json")
        with open(caminho_saida, "w", encoding="utf-8") as f:
            f.write(resultados_gpt[1])
        logging.info(f"✅ GPT (Ações) salvo em: {caminho_saida}")
    
    # Save JSON dos Proprietários Atuais
    if len(resultados_gpt) >= 3:
        caminho_saida = os.path.join(DIRETORIO_GPT_OWNERS, f"{nome_sem_extensao}_owners.json")
        with open(caminho_saida, "w", encoding="utf-8") as f:
            f.write(resultados_gpt[2])
        logging.info(f"✅ GPT (Proprietários) salvo em: {caminho_saida}")

# End of document_handler module
