import time
import json
import logging
import tiktoken
import re
import textwrap
from typing import List, Dict, Any
import openai
import os

# --- OpenRouter / Gemini configuration ---
openai.api_base = "https://openrouter.ai/api/v1"
openai.api_key = "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"  # Replace with your actual API key

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Global definitions
MODELO_GEMINI = "google/gemini-2.0-pro-exp-02-05:free"
MAX_INPUT_TOKENS = 12000

# ======================================================================
# Utility Functions: Text splitting, JSON cleaning, etc.
# ======================================================================

def dividir_texto(texto: str, MAX_TOKENS_ENTRADA: int = 12000, sobreposicao: int = 350) -> List[str]:
    """
    Splits the text into chunks if it exceeds the token limit.
    If the text is short, returns a list with the whole text.
    """
    codificador = tiktoken.encoding_for_model("gpt-4")
    tokens = codificador.encode(texto)
    
    if len(tokens) <= MAX_INPUT_TOKENS:
        return [texto]
    
    partes = []
    inicio = 0
    while inicio < len(tokens):
        fim = min(inicio + MAX_INPUT_TOKENS, len(tokens))
        # Avoid breaking words mid-stream
        while fim > inicio and codificador.decode([tokens[fim - 1]]) not in {".", "\n", " "}:
            fim -= 1
        partes.append(codificador.decode(tokens[inicio:fim]))
        inicio = fim - sobreposicao if fim < len(tokens) else fim
    return partes

def limpar_json(bloco: str) -> str:
    """
    Cleans and formats a JSON text by:
      - Removing markdown code fences (``` or ```json) at the beginning and end.
      - Removing any stray backticks.
      - Extracting only the content between the first '{' and the last '}'.
      - Eliminating trailing commas from objects or arrays.
      - Stripping extra whitespace.
      
    Finally, it tries to parse and re-dump the JSON to ensure a normalized format.
    If extra data is present (i.e. multiple objects), it wraps the text in an array and tries again.
    """
    # Initial cleanup: trim whitespace and remove code fences
    bloco = bloco.strip()
    bloco = re.sub(r"^```(?:json)?\s*", "", bloco, flags=re.MULTILINE)
    bloco = re.sub(r"\s*```$", "", bloco, flags=re.MULTILINE)
    bloco = bloco.replace("```", "")
    
    # Extract content between the first { and the last }
    start = bloco.find('{')
    end = bloco.rfind('}')
    if start != -1 and end != -1 and start < end:
        bloco = bloco[start:end+1]
    
    # Remove trailing commas (e.g., before } or ])
    bloco = re.sub(r",\s*([}\]])", r"\1", bloco)
    bloco = bloco.strip()
    
    # Try parsing the JSON
    try:
        parsed = json.loads(bloco)
        return json.dumps(parsed, ensure_ascii=False, indent=4)
    except json.JSONDecodeError as e:
        # If there's extra data (multiple objects), try wrapping in an array.
        if "Extra data" in str(e):
            try:
                bloco_array = "[" + bloco + "]"
                parsed = json.loads(bloco_array)
                return json.dumps(parsed, ensure_ascii=False, indent=4)
            except Exception as e2:
                logging.error(f"Erro ao converter JSON após envolver em array: {e2}\nConteúdo (primeiros 300 caracteres): {bloco[:300]}...")
                return bloco
        else:
            logging.error(f"Erro ao converter JSON: {e}\nConteúdo (primeiros 300 caracteres): {bloco[:300]}...")
            return bloco


def extrair_objetos_json(texto: str) -> List[str]:
    """
    Extracts JSON objects from text by counting braces.
    It uses the improved limpar_json to clean each found JSON block.
    """
    objetos = []
    contador_chaves = 0
    indice_inicio = None
    dentro_string = False
    char_anterior = None

    for i, char in enumerate(texto):
        # Skip escaped characters
        if char_anterior == '\\':
            char_anterior = char
            continue

        # Toggle string state if encountering unescaped quotes
        if char == '"' and char_anterior != '\\':
            dentro_string = not dentro_string

        if not dentro_string:
            if char == '{':
                if contador_chaves == 0:
                    indice_inicio = i
                contador_chaves += 1
            elif char == '}':
                contador_chaves -= 1
                if contador_chaves == 0 and indice_inicio is not None:
                    obj_str = texto[indice_inicio:i+1]
                    obj_str_limpo = limpar_json(obj_str)
                    objetos.append(obj_str_limpo)
                    indice_inicio = None

        char_anterior = char

    logging.info(f"Extraídos {len(objetos)} objetos JSON.")
    return objetos

def converter_respostas_para_lista(resultados: List[str]) -> List[Dict[str, Any]]:
    """
    Converts model responses into a list of dictionaries.
    Joins all responses into a single text, extracts JSON objects,
    and attempts to parse them.
    """
    texto_completo = "\n".join(resultados).strip()
    objetos_json = extrair_objetos_json(texto_completo)
    lista_final = []
    for obj in objetos_json:
        try:
            lista_final.append(json.loads(obj))
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao converter JSON: {e}\nBloco: {obj[:200]}")
            try:
                obj_relimpo = limpar_json(obj)
                lista_final.append(json.loads(obj_relimpo))
            except json.JSONDecodeError as e2:
                logging.error(f"Erro na segunda tentativa de converter JSON: {e2}")
    return lista_final

# ======================================================================
# GPT Handler Functions: Sending text to Gemini via OpenRouter
# ======================================================================

def processar_parte(texto: str, modelo_prompt: str, tentativas: int = 5, atraso: int = 10) -> str:
    """
    Processes a text using Gemini via OpenRouter with the given prompt.
    """
    for tentativa in range(tentativas):
        try:
            prompt = modelo_prompt.format(texto=texto)
            logging.info(f"🔍 Enviando consulta para Gemini via OpenRouter (Tentativa {tentativa + 1}/{tentativas})...")
            completion = openai.ChatCompletion.create(
                extra_headers={
                    "HTTP-Referer": "<YOUR_SITE_URL>",  # Optional: Replace with your site URL
                    "X-Title": "<YOUR_SITE_NAME>"        # Optional: Replace with your site name
                },
                extra_body={},
                model=MODELO_GEMINI,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )
            logging.info("✅ Resposta recebida do Gemini via OpenRouter.")
            return completion.choices[0].message.content
        except Exception as e:
            logging.warning(f"⚠️ Erro ao chamar Gemini via OpenRouter: {e}. Nova tentativa em {atraso}s...")
            time.sleep(atraso)
    raise RuntimeError("Número máximo de tentativas excedido.")

def processar_texto_com_prompts(texto: str, caminho_saida_json: str = None, caminho_saida_txt: str = None) -> List[str]:
    """
    Processes the complete refined OCR text (from processed_ocr_files) for GPT JSON extraction.
    It sends three GPT prompts to extract:
      1. JSON de Localização do Imóvel.
      2. JSON de Histórico Completo das Ações.
      3. JSON dos Proprietários Atuais.
      
    - Returns a list containing the 3 JSON responses and the refined text.
    - Optionally, saves the JSON results to a file and the refined text to a .txt file.
    """
    # Since the OCR text is already refined, we assume it is ready to be used.
    partes = dividir_texto(texto)
    full_text = "\n".join(partes)
    texto_refinado = full_text  # Use the text directly without further GPT formatting.
    
    # ----- STEP 2: Use the refined text for the JSON prompts -----
    prompt_template1 = textwrap.dedent("""
    1. **JSON de Localização do Imóvel:**  
       - **Número da Matrícula:** número de registro da matrícula.
       - **Nome do Imóvel:** nome atual do imóvel.
       - **Localização do Imóvel:** deve incluir Cidade e Estado.
       - **Registros Legais Adicionais:** todos os registros ou anotações legais disponíveis.
       - **Descrição de Georreferenciamento:** 
         - **Área:** área total do imóvel.
         - **Localização:** descrição detalhada da localização.
         - **Limites:** uma lista de objetos, onde cada objeto descreve:
            - **Ponto Inicial**
            - **Direção**  
            - **Distância** (em metros ou KM) 
            - **Ponto Final**
            - **Observação:** quaisquer referências ou anotações adicionais.
        
                {{
                "Matricula_Number": "Número da Matrícula",
                "Property_Name": "Nome Atual do Imóvel",
                "Property_Location": {{
                    "Town": "Cidade",
                    "State": "Estado",
                    "Additional_Legal_Registrations": "Registros legais adicionais (se houver)"
                }},
                "Georreferencing_Description": {{
                    "Area": "XX hectares",
                    "Location": "Descrição da localização",
                    "Boundaries": [
                        {{
                            "Starting_Point": "Marco Inicial",
                            "Direction": "Rumo XX°",
                            "Distance": "XXX metros",
                            "End_Point": "Marco Final",
                            "Observation": "Referência ou observação adicional"
                        }}
                    ]
                    }}
                }}

        RETORNE APENAS O JSON EM SUA RESPOSTA, SEM NENHUM TEXTO OU EXPLICAÇÃO ADICIONAL

        Texto a ser analisado:
        {texto}
    """)
    
    prompt_template2 = textwrap.dedent("""
   2. **JSON de Histórico Completo das Ações:**  
       Extraia **TODAS** as ações quem fazem referencia a troca de proprietarios do imóvel descritas no texto. Para cada ação, inclua:
       - **Número da Matrícula:** conforme consta no documento.
       - **Nome do Imóvel:** conforme consta no documento.
       - **Data:** a data da ação, no formato DD/MM/AAAA.
       - **Tipo da Ação:** descreva exatamente o que aconteceu, podendo ser:
         - Venda, Compra, Doação, Instituição de Usufruto, Cancelamento de Usufruto, Óbito, Partilha, Alteração de Nome do Imóvel, Instituição de Servidão, ou qualquer outro tipo de transação ou alteração. Retorne as ações padronizadas.
       - **Agentes:** uma lista de objetos representando os agentes envolvidos, onde cada objeto deve conter:
         - **Nome:** o nome completo do agente.
         - **CPF:** o CPF ou identificação do agente.
         - **Porcentagem Transferida:** 
         - **Cônjuge:** se disponível, um objeto com:
             - **Nome do Cônjuge:** o nome completo.
             - **CPF do Cônjuge:** o CPF, se informado.
       - **Beneficiários:** uma lista de objetos representando os beneficiários envolvidos, onde cada objeto deve conter:
         - **Nome:** o nome completo do beneficiário.
         - **CPF:** o CPF ou identificação do beneficiário.
         - **Porcentagem Recebida:** 
         - **Cônjuge:** se disponível, um objeto com:
             - **Nome do Cônjuge:** o nome completo.
             - **CPF do Cônjuge:** o CPF.
       - **Informações Adicionais:** qualquer outro dado ou anotação complementar.
       - **Observações:** quaisquer observações textuais presentes.
       - **Contexto:** informações sobre alterações de estado, condições especiais, etc.
            
                {{
            "Matricula_Number": "Número da Matrícula",
            "Property_Name": "Nome Atual do Imóvel",
            "Actions": [
                {{
                    "Date": "AAAA/MM/DD",
                    "Action": "Tipo da Ação (Venda, Doação, Usufruto, etc.)",
                    "Agents": [
                        {{
                            "Name": "Nome do Agente",
                            "CPF": "CPF do Agente",
                            "Percentage_Transferred": "XX,XX%",
                            "Spouse": {{
                                "Name": "Nome do Cônjuge",
                                "CPF": "CPF do Cônjuge"
                            }}
                        }}
                    ],
                    "Beneficiaries": [
                        {{
                            "Name": "Nome do Beneficiário",
                            "CPF": "CPF do Beneficiário",
                            "Percentage_Received": "XX,XX%",
                            "Spouse": {{
                                "Name": "Nome do Cônjuge",
                                "CPF": "CPF do Cônjuge"
                            }}
                        }}
                    ],
                    "Additional_Info": "Detalhes extras da transação, se houver"
                }}
            ]
        }}

        RETORNE APENAS O JSON EM SUA RESPOSTA, SEM NENHUM TEXTO OU EXPLICAÇÃO ADICIONAL

        Texto a ser analisado:
        {texto}
    """)
    
    prompt_template3 = textwrap.dedent("""
    3. **JSON dos Proprietários Atuais:**  
       Com base em todo o histórico acima, retorne o estado final dos proprietários do imóvel, separando-os em:
       - **Proprietários Finais (Bare Ownership)**
       - **Usufrutuários (Usufruct)**
       
       Para cada registro, inclua:
         - **Número da Matrícula:** conforme consta no documento.
         - **Nome do Imóvel:** conforme consta no documento.
         - **Nome do Proprietário ou Usufrutuário:** conforme a última ação relevante.
         - **CPF:** o CPF ou identificação.
         - **Porcentagem:** exatamente como informado.
         - **Cônjuge:** se houver, um objeto com Nome e CPF.
         
         Exemplo de estrutura:
         
         {{
        "Matricula_Number": "Número da Matrícula",
        "Property_Name": "Nome Atual do Imóvel",
        "Final_Owners": [
            {{
                "Name": "Nome do Proprietário",
                "CPF": "CPF do Proprietário",
                "Percentage_Owned": "XX,XX%",
                "Spouse": {{
                    "Name": "Nome do Cônjuge",
                    "CPF": "CPF do Cônjuge"
                }},
                "Ownership_Type": "Bare Ownership"
            }}
        ],
        "Usufructuaries": [
            {{
                "Name": "Nome do Usufrutuário",
                "CPF": "CPF do Usufrutuário",
                "Percentage_Usufruct": "XX,XX%",
                "Spouse": {{
                    "Name": "Nome do Cônjuge",
                    "CPF": "CPF do Cônjuge"
                }},
                "Ownership_Type": "Usufruct"
            }}
        ]
    }}

        RETORNE APENAS O JSON EM SUA RESPOSTA, SEM NENHUM TEXTO OU EXPLICAÇÃO ADICIONAL

        Texto a ser analisado:
        {texto}
    """)
    
    prompt_templates = [prompt_template1, prompt_template2, prompt_template3]
    
    resultados_json = []
    for i, modelo_prompt in enumerate(prompt_templates):
        logging.info(f"🔍 Enviando consulta JSON {i + 1}/3 utilizando o texto refinado...")
        resposta = processar_parte(texto_refinado, modelo_prompt)
        # Clean each GPT response
        resposta_limpa = limpar_json(resposta)
        resultados_json.append(resposta_limpa)
        time.sleep(2)
    
    # ----- STEP 3: Optionally, save the results to files -----
    if caminho_saida_json:
        with open(caminho_saida_json, "w", encoding="utf-8") as arquivo:
            json.dump(resultados_json, arquivo, ensure_ascii=False, indent=4)
        logging.info(f"📁 Resultados JSON salvos em: {caminho_saida_json}")
    
    if caminho_saida_txt:
        with open(caminho_saida_txt, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto_refinado)
        logging.info(f"📁 Texto refinado salvo em: {caminho_saida_txt}")
    
    # Returns the 3 JSON responses and the refined text
    return resultados_json + [texto_refinado]
