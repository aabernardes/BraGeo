import io
import json
import os
import logging
import re
import textwrap
from google.cloud import vision
from google.cloud import storage

# Configuração dinâmica das credenciais do Google Cloud
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(os.getcwd(), "scannerdepdfs.json")

# Configuração de logging para rastreamento de informações e erros
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def pdf_para_texto(caminho_pdf, caminho_saida=None):
    """
    Processa um arquivo PDF usando a API do Google Cloud Vision para OCR
    e salva o texto extraído em um arquivo.
    
    Args:
        caminho_pdf (str): Caminho do arquivo PDF de entrada.
        caminho_saida (str, optional): Caminho onde o texto extraído será salvo.
                                       Se None, o caminho será gerado dinamicamente
                                       baseado no nome do PDF, ficando em
                                       'documments/processed_ocr_files'.
    
    Returns:
        str: O texto extraído do PDF.
    """
    # Se não for informado um caminho de saída, gera-o dinamicamente
    if caminho_saida is None:
        nome_base = os.path.basename(caminho_pdf)
        nome_sem_extensao = os.path.splitext(nome_base)[0]
        # Define o diretório de saída para o OCR dentro da pasta 'documments/processed_ocr_files'
        caminho_saida = os.path.join("documments", "processed_ocr_files", f"{nome_sem_extensao}.txt")
        # Cria o diretório, se necessário
        os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)

    # Inicializa os clientes da API do Vision e do Storage
    client = vision.ImageAnnotatorClient()
    storage_client = storage.Client()

    # Nome do bucket do Google Cloud Storage (GCS) e nome do arquivo no GCS
    bucket_name = "scannerpdf"
    nome_arquivo_gcs = os.path.basename(caminho_pdf)

    try:
        # Configura o bucket e o blob no GCS
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(nome_arquivo_gcs)

        # Limpa resultados de OCR antigos no bucket (prefixo: "ocr_results/")
        blobs_antigos = list(bucket.list_blobs(prefix="ocr_results/"))
        for blob_antigo in blobs_antigos:
            blob_antigo.delete()
        logging.info("🗑️ Resultados antigos no GCS limpos com sucesso.")

        # Faz upload do arquivo PDF para o bucket no GCS
        logging.info("📤 Fazendo upload do PDF para o Google Cloud Storage...")
        blob.upload_from_filename(caminho_pdf)

        # Configuração para o processamento OCR
        uri_origem_gcs = f"gs://{bucket_name}/{nome_arquivo_gcs}"
        uri_destino_gcs = f"gs://{bucket_name}/ocr_results/"
        tipo_mime = "application/pdf"
        recurso = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

        entrada_gcs = vision.GcsSource(uri=uri_origem_gcs)
        configuracao_entrada = vision.InputConfig(gcs_source=entrada_gcs, mime_type=tipo_mime)

        destino_gcs = vision.GcsDestination(uri=uri_destino_gcs)
        configuracao_saida = vision.OutputConfig(gcs_destination=destino_gcs, batch_size=5)

        # Configuração do pedido assíncrono de OCR
        pedido_assincrono = vision.AsyncAnnotateFileRequest(
            features=[recurso],
            input_config=configuracao_entrada,
            output_config=configuracao_saida,
        )

        # Envia o pedido para o Google Vision API
        logging.info("📨 Enviando PDF para processamento OCR...")
        operacao = client.async_batch_annotate_files(requests=[pedido_assincrono])
        operacao.result(timeout=600)  # Tempo limite de 10 minutos

        # Baixa os resultados de OCR do GCS
        logging.info("📥 Baixando resultados do OCR do Google Cloud Storage...")
        blobs_resultados = list(bucket.list_blobs(prefix="ocr_results/"))
        texto_completo = ""

        for blob_resultado in blobs_resultados:
            if blob_resultado.name.endswith('.json'):
                # Lê os dados JSON de cada arquivo de resultado
                dados_resultado = blob_resultado.download_as_bytes()
                resposta = json.loads(dados_resultado)

                # Concatena o texto extraído de todas as páginas
                for resposta_pagina in resposta.get('responses', []):
                    if 'fullTextAnnotation' in resposta_pagina:
                        texto_completo += resposta_pagina['fullTextAnnotation']['text'] + "\n"

        # Salva o texto extraído em um arquivo local
        with open(caminho_saida, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto_completo)
        logging.info(f"✅ OCR concluído! Texto salvo em '{caminho_saida}'")

        # Limpa os arquivos temporários do GCS
        logging.info("🗑️ Limpando arquivos temporários do GCS...")
        blob.delete()

        # Retorna o texto extraído (pode ser uma string vazia se nada foi extraído)
        return texto_completo

    except Exception as e:
        logging.error(f"❌ Erro durante o processamento OCR: {e}")
        raise

def melhorar_ocr(texto_ocr: str) -> str:
    """
    Melhora os resultados do OCR, corrigindo erros, removendo ruídos e normalizando detalhes importantes.
    Em seguida, utiliza um prompt refinado com GPT para aprimorar o texto ainda mais.
    
    Args:
        texto_ocr (str): Texto extraído do OCR.
        
    Returns:
        str: Texto aprimorado.
    """
    logging.info("🔧 Iniciando melhoria do texto OCR (via regex).")
    
    # 1. Remoção de cabeçalhos, rodapés e outros ruídos genéricos.
    texto = re.sub(r"Operador Nacional.*?Imóveis", "", texto_ocr, flags=re.IGNORECASE | re.DOTALL)
    texto = re.sub(r"Solicitado POR:.*?\n", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"NÃO VALE COMO CERTIDÃO.*\n", "", texto, flags=re.IGNORECASE)
    
    # 2. Corrige quebras de palavras e normaliza quebras de linha
    texto = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", texto)  # Junta palavras hifenizadas
    texto = re.sub(r"\n\s*\n", "\n", texto)                 # Remove linhas em branco extras
    texto = re.sub(r"[^\S\n]+", " ", texto)                  # Normaliza espaços (exceto novas linhas)
    
    # 3. Normaliza datas para o formato DD/MM/AAAA
    texto = re.sub(r"\b(\d{1,2})[^\w](\d{1,2})[^\w](\d{2,4})\b", r"\1/\2/\3", texto)
    
    # 4. Formata CPF para o padrão xxx.xxx.xxx-xx
    texto = re.sub(r"(\d{3})[.\s-]?(\d{3})[.\s-]?(\d{3})[^\d]?(\d{2})", r"\1.\2.\3-\4", texto)
    
    # 5. Destaca palavras-chave importantes e normaliza termos recorrentes
    padroes = {
        r"\bmatr[ií]cula\b": "MATRÍCULA",
        r"\bim[oó]vel\b": "IMÓVEL",
        r"\bs[ií]tio\b": "SÍTIO",
        r"\bfazenda\b": "FAZENDA"
    }
    for pattern, repl in padroes.items():
        texto = re.sub(pattern, repl, texto, flags=re.IGNORECASE)
    
    # 6. Normaliza coordenadas geográficas e medidas
    texto = re.sub(r"rumo\s*([NSEWO]{1,2})\s*([\d°'\" ]+)", r"Rumo: \1 \2", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\b([\d,]+)\s*(metros|alqueires|hectares|ha)\b", r"\1 \2", texto, flags=re.IGNORECASE)
    
    # 7. Normaliza porcentagens para ter a frase completa
    texto = re.sub(r"(\d{1,3})\s*%(\s*(do\s*im[oó]vel|))", r"\1% do IMÓVEL", texto, flags=re.IGNORECASE)
    
    # 8. Normaliza valores financeiros, garantindo o padrão R$ 0.00
    def format_valor(match):
        valor = match.group(1).replace('.', '').replace(',', '.')
        return f"R$ {valor}"
    texto = re.sub(r"R\$[\s]*([\d.,]+)", format_valor, texto)
    
    # 9. Normaliza termos de ações, garantindo a capitalização correta
    texto = re.sub(r"\b(vendeu|doaram|doado|reservaram|usufruto|hipotecaram|cederam)\b", 
                   lambda match: match.group(1).capitalize(), texto, flags=re.IGNORECASE)
    
    texto = texto.strip()
    
    logging.info("✅ Melhoria do texto OCR (via regex) concluída.")
    
    # --- GPT-based enhancement (sempre executado) ---
    logging.info("🔍 Iniciando aprimoramento adicional com GPT...")
    from modules.gpt_handler import processar_parte  # Import local para evitar dependência circular
    prompt_refinado = textwrap.dedent("""
        Por favor, revise e melhore o seguinte texto extraído de um documento.
        Garanta clareza, correção gramatical, formatação consistente e remova quaisquer erros típicos de OCR.
        Retorne o documento de forma clara e organizada, reescreva todo o texto.
        Retorne apenas o texto formatado.
        Nomes Proprios, de AGENTES e BENEFICIARIOS em ações de troca de proprietarios, devem estar em CAPSLOCK assim como as AÇÕES.
        adicione formatação para quebra de linhas para evitar delas muito longas.
            
        Texto:
        {texto}
        
        Retorne apenas o texto aprimorado, sem comentários adicionais.
    """)
    texto_aprimorado = processar_parte(texto, prompt_refinado)
    logging.info("✅ Aprimoramento adicional com GPT concluído.")
    
    return texto_aprimorado
