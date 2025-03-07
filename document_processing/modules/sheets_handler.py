import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_formatting import cellFormat, format_cell_range, Color, TextFormat

# Configuração do logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def autorizar_google_sheets():
    """
    Autoriza e conecta ao Google Sheets usando uma conta de serviço.
    
    Returns:
        gspread.Client: Cliente autenticado para interação com o Google Sheets.
    """
    escopo = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    credenciais = ServiceAccountCredentials.from_json_keyfile_name("scannerdepdfs.json", escopo)
    logging.info("🔑 Autorização do Google Sheets concluída.")
    return gspread.authorize(credenciais)


def salvar_no_google_sheets(dados, sheet_name=None, spreadsheet_id="1TS7GVQ_A1Vq_L7Qi7Fikve9G9uQfluoqYmJQJqfBhLc"):
    """
    Salva dados estruturados no Google Sheets.

    Args:
        dados (dict): Dados estruturados com informações de propriedade, proprietários e usufrutuários.
        sheet_name (str): Nome da planilha (opcional).
        spreadsheet_id (str): ID do Google Sheets.
    """
    if not isinstance(dados, dict):
        raise ValueError("Os dados fornecidos devem ser um dicionário.")

    # Autoriza o acesso ao Google Sheets
    cliente = autorizar_google_sheets()

    try:
        # Abre a planilha pelo ID
        planilha = cliente.open_by_key(spreadsheet_id).sheet1
        logging.info("📂 Planilha aberta com sucesso.")
    except gspread.exceptions.SpreadsheetNotFound:
        # Cria uma nova planilha se não encontrada
        planilha = cliente.create(sheet_name or "Nova Planilha").sheet1
        logging.info(f"📂 Nova planilha criada: {planilha.url}")

    # Recupera a última linha para começar a adicionar dados
    dados_existentes = planilha.get_all_values()
    ultima_linha = len(dados_existentes)
    linha_inicial = ultima_linha + 2  # Deixa uma linha em branco para separação

    # Cabeçalhos e subtítulos
    cabecalho = ["", "NOME", "DOCUMENTO (CPF/MATRÍCULA)", "NOME DO CÔNJUGE", "CPF DO CÔNJUGE", "PERCENTUAL", "OBS:"]
    subtitulo = [
        "IMÓVEL GEORREFERENCIADO:", 
        dados.get("Nome do Imóvel", "Propriedade Desconhecida"), 
        dados.get("Número da Matrícula", "Não informado"), 
        "", "", "", ""
    ]

    # Escreve os cabeçalhos na planilha
    planilha.update(f"A{linha_inicial}:G{linha_inicial + 1}", [cabecalho, subtitulo])
    logging.info("📝 Cabeçalhos e subtítulos adicionados.")

    # Aplica formatação aos cabeçalhos
    formatacao_cabecalho = cellFormat(
        backgroundColor=Color(0.8, 0.9, 1.0),  # Fundo azul claro
        textFormat=TextFormat(bold=True, fontSize=11),  # Texto em negrito
        horizontalAlignment="CENTER",  # Alinhamento centralizado
    )
    format_cell_range(planilha, f"B{linha_inicial}:G{linha_inicial}", formatacao_cabecalho)
    logging.info("🎨 Formatação dos cabeçalhos aplicada.")

    # Começa a inserir dados abaixo dos cabeçalhos
    indice_linha = linha_inicial + 2

    # Adiciona proprietários
    for proprietario in dados.get("Proprietários Atuais", []):
        # Trata o cônjuge, verificando se é um dicionário ou uma string
        conjuge = proprietario.get("Cônjuge", {})
        if isinstance(conjuge, str):
            conjuge = {"Nome": conjuge, "CPF": "Não informado"}

        planilha.update(
            f"A{indice_linha}:G{indice_linha}",
            [[
                f"PROPRIETÁRIO {indice_linha - linha_inicial - 1}",  # Número dinâmico do proprietário
                proprietario.get("Nome", "Não informado"),
                proprietario.get("CPF", "Não informado"),
                conjuge.get("Nome", "Não informado"),
                conjuge.get("CPF", "Não informado"),
                "",  # Percentual não especificado
                ""
            ]]
        )
        indice_linha += 1
        logging.info(f"✔️ Proprietário adicionado: {proprietario.get('Nome')}")

    # Adiciona usufrutuários, começando com o contador em 1
    indice_usufrutuario = 1
    for usufrutuario in dados.get("Usufrutuários", []):
        # Ignora entradas padrão com "Nome" igual a "Não informado"
        if usufrutuario.get("Nome") == "Não informado":
            continue

        conjuge = usufrutuario.get("Cônjuge", {})
        if isinstance(conjuge, str):
            conjuge = {"Nome": conjuge, "CPF": "Não informado"}

        # Adiciona usufrutuário válido à planilha
        planilha.update(
            f"A{indice_linha}:G{indice_linha}",
            [[
                f"USUFRUTUÁRIO {indice_usufrutuario}",
                usufrutuario.get("Nome", "Não informado"),
                usufrutuario.get("CPF", "Não informado"),
                conjuge.get("Nome", "Não informado"),
                conjuge.get("CPF", "Não informado"),
                "",
                "USUFRUTUÁRIO"
            ]]
        )
        indice_usufrutuario += 1
        indice_linha += 1
        logging.info(f"✔️ Usufrutuário adicionado: {usufrutuario.get('Nome')}")

    logging.info("✅ Dados salvos com sucesso no Google Sheets.")