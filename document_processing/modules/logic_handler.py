import json
import logging
import unicodedata
import re
from datetime import datetime
from fractions import Fraction
from typing import List, Dict, Any, Set
import sys 

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ------------------------------------------------
# 1) Funções Auxiliares: JSON, Data, Nome, Percentual e Chave Única
# ------------------------------------------------

def analisar_json_dinamico(chunk: Any) -> Dict[str, Any]:
    if isinstance(chunk, dict):
        return chunk
    if isinstance(chunk, str):
        try:
            chunk_limpo = re.sub(r'^```(?:json)?|\n|```', '', chunk).strip()
            return json.loads(chunk_limpo)
        except json.JSONDecodeError as e:
            logging.error(f"Erro de decodificação JSON: {e}\nTrecho problemático: {chunk[:200]}...")
            return {}
        except Exception as e:
            logging.error(f"Erro inesperado ao analisar JSON: {str(e)}")
            return {}
    return {}

def parse_data(data_str: str) -> datetime:
    formatos = ["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d%m%Y", "%Y/%m/%d"]
    data_str = data_str.strip()
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    logging.warning(f"Formato de data desconhecido: {data_str}. Usando data padrão 1900-01-01.")
    return datetime(1900, 1, 1)

def normalizar_nome(nome: str) -> str:
    nome = nome.strip().upper()
    nome = unicodedata.normalize('NFKD', nome).encode('ASCII', 'ignore').decode('ASCII')
    return re.sub(r'[^A-Z0-9 ]', '', nome)

def parse_percentual(percentual: Any) -> float:
    """
    Converte representações percentuais para um valor numérico entre 0 e 100.
    Se o valor estiver ausente, ou for "não informado", "indeterminado" ou "parcial",
    retorna None.
    Se o valor numérico for ≤ 1, multiplica por 100; caso contrário, assume que já está em pontos percentuais.
    """
    if isinstance(percentual, float):
        return percentual
    if not percentual or str(percentual).strip().lower() in {"não informado", "nao informado", "", "indeterminado", "parcial"}:
        return None
    try:
        txt = str(percentual).strip()
        if '/' in txt:
            partes = txt.split('/')
            return float(Fraction(int(partes[0]), int(partes[1]))) * 100
        valor = float(re.sub(r'[^\d.,]', '', txt).replace(',', '.'))
        return valor * 100 if valor <= 1 else valor
    except (ValueError, ZeroDivisionError):
        logging.warning(f"Percentual inválido: {percentual}.")
        return None

def processar_conjuge(conjuge: Any) -> Dict[str, str]:
    if isinstance(conjuge, dict):
        nome = conjuge.get("Name") or conjuge.get("Nome") or "Não informado"
        cpf = conjuge.get("CPF") or "Não informado"
        return {"Nome": nome, "CPF": cpf}
    return {}

def chave_proprietario(item: Dict[str, Any]) -> str:
    cpf = item.get("CPF")
    if cpf and cpf.strip():
        return cpf.strip()
    return normalizar_nome(item.get("Name", ""))

def obter_tipo_acao(acao: Dict[str, Any]) -> str:
    return (acao.get("Action") or acao.get("Tipo da Ação") or "").strip()

def normalizar_e_ordenar_acoes(acoes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    acoes_unicas = []
    conjunto_visto: Set[tuple] = set()
    for acao in acoes:
        data_str = acao.get("Date") or acao.get("Data", "")
        tipo_acao = obter_tipo_acao(acao).lower()
        agentes = acao.get("Agents", [])
        beneficiarios = acao.get("Beneficiaries", [])
        chave = (
            tipo_acao,
            data_str,
            tuple(sorted(a.get("Name", "") for a in agentes)),
            tuple(sorted(b.get("Name", "") for b in beneficiarios))
        )
        if chave not in conjunto_visto:
            conjunto_visto.add(chave)
            data_dt = parse_data(data_str)
            acao["Date"] = data_dt.strftime("%d/%m/%Y")
            acoes_unicas.append(acao)
    return sorted(acoes_unicas, key=lambda x: (parse_data(x.get("Date") or x.get("Data", "")), obter_tipo_acao(x).lower()))

# ------------------------------------------------
# 2) Processamento dos Atos – Atualização do Registro
# ------------------------------------------------

def atualizar_proprietarios_parcial(proprietarios: Dict[str, Dict[str, Any]],
                                    agentes: List[Dict[str, Any]],
                                    beneficiarios: List[Dict[str, Any]]) -> None:
    """
    Inicializa os agentes se o registro estiver vazio, distribuindo igualmente 100%
    entre eles. Para cada agente, se o percentual de transferência for informado, subtrai
    esse valor da participação do agente; caso contrário, ignora a transferência.
    Depois, distribui o total transferido entre os beneficiários proporcionalmente aos percentuais
    informados (ou igualmente, se nenhum percentual for informado).
    """
    logging.info(f"🔄 Atualizar Proprietários Parcial - Agentes: {[a.get('Name') for a in agentes]}, Beneficiários: {[b.get('Name') for b in beneficiarios]}")
    logging.debug(f"Proprietários (antes da atualização parcial): {proprietarios}")

    # Inicializa os agentes se o registro estiver vazio
    if not proprietarios and agentes:
        total_agentes = len(agentes)
        for agente in agentes:
            chave = chave_proprietario(agente)
            proprietarios[chave] = {
                "Nome": agente.get("Name"),
                "CPF": agente.get("CPF", "Não informado"),
                "Percentual": 100.0 / total_agentes,
                "Cônjuge": processar_conjuge(agente.get("Spouse"))
            }
        logging.info(f"✨ Inicialização de proprietários: {proprietarios}")

    total_transferido = 0.0  # Mudança: Inicializar para 0.0 para acumular corretamente
    # Processa cada agente para subtrair o valor transferido
    for agente in agentes:
        chave = chave_proprietario(agente)
        frac = parse_percentual(agente.get("Percentage_Transferred", ""))
        if frac is None:
            logging.warning(f"Percentual não informado para o agente '{agente.get('Name')}'. Transferência ignorada.")
            continue
        if chave in proprietarios:
            current_share = proprietarios[chave]["Percentual"]
            transfer_amount = current_share * (frac / 100)
            proprietarios[chave]["Percentual"] = current_share - transfer_amount
            logging.info(f"{proprietarios[chave]['Nome']} vendeu {frac:.2f}% (de {current_share:.2f}%), transferiu {transfer_amount:.2f}%, agora tem {proprietarios[chave]['Percentual']:.2f}%")
            total_transferido += transfer_amount # Mudança: Acumular o valor transferido
            if proprietarios[chave]["Percentual"] < 0.0001:
                logging.info(f"Removendo proprietário esgotado: {proprietarios[chave]['Nome']}")
                del proprietarios[chave]
        else:
            logging.warning(f"O agente '{agente.get('Name')}' não está no registro de proprietários.")

    logging.info(f"Total transferido pelos agentes: {total_transferido:.2f}%")

    # Processa os beneficiários
    benef_info = []
    for b in beneficiarios:
        pct = parse_percentual(b.get("Percentage_Received", ""))
        benef_info.append((b, pct))

    logging.debug(f"Beneficiários info: {benef_info}")

    # Se nenhum beneficiário informar percentual, distribui igualmente
    if all(pct is None for (_, pct) in benef_info) and benef_info:
        n = len(benef_info)
        benef_info = [(b, 100.0 / n) for (b, _) in benef_info]
        logging.info(f"Nenhum percentual de beneficiário informado, distribuindo igualmente: {benef_info}")

    else:
        total_declared = sum(pct for (_, pct) in benef_info if pct is not None)

        # Verifica se a soma dos percentuais declarados excede 100%
        if total_declared > 100.0:
            logging.warning(f"Soma dos percentuais de beneficiários excede 100% ({total_declared:.2f}%). Normalizando para 100%.")
            benef_info = [(b, (pct if pct is not None else 0.0)) for (b, pct) in benef_info] # Define percentual não informado como 0 para normalizar
            total_declared = sum(pct for (_, pct) in benef_info if pct is not None)


        remaining_percentage = max(0.0, total_transferido - total_declared) # Mudança: Usar total_transferido aqui
        num_undefined_pct = sum(1 for (_, pct) in benef_info if pct is None)


        if num_undefined_pct > 0:
            addition_per_beneficiary = remaining_percentage / num_undefined_pct if num_undefined_pct > 0 else 0.0
            benef_info = [(b, (pct if pct is not None else addition_per_beneficiary)) for (b, pct) in benef_info]
            logging.info(f"Percentuais de beneficiários parcialmente informados, distribuindo restante ({remaining_percentage:.2f}%) igualmente: {benef_info}")
        elif total_declared < total_transferido:
             logging.warning(f"A soma dos percentuais de beneficiários ({total_declared:.2f}%) é menor que o total transferido ({total_transferido:.2f}%). Distribuindo o restante proporcionalmente.")
             benef_info = [(b, pct + (remaining_percentage * (pct / total_declared) if total_declared > 0 else 0.0) ) for (b, pct) in benef_info]


    logging.debug(f"Beneficiários info processado: {benef_info}")

    # Distribui o total transferido entre os beneficiários
    for b, pct in benef_info:
        addition = pct # Agora 'pct' já é a parcela correta a adicionar
        chave_b = chave_proprietario(b)
        if chave_b in proprietarios:
            proprietarios[chave_b]["Percentual"] += addition
            logging.info(f"{proprietarios[chave_b]['Nome']} recebeu {addition:.2f}%, agora tem {proprietarios[chave_b]['Percentual']:.2f}%")
        else:
            proprietarios[chave_b] = {
                "Nome": b.get("Name"),
                "CPF": b.get("CPF", "Não informado"),
                "Percentual": addition,
                "Cônjuge": processar_conjuge(b.get("Spouse"))
            }
            logging.info(f"Novo proprietário adicionado: {proprietarios[chave_b]['Nome']} com {addition:.2f}%")

    logging.debug(f"Proprietários (após atualização parcial): {proprietarios}")


def processar_venda(proprietarios: Dict[str, Dict[str, Any]], acao: Dict[str, Any]) -> None:
    logging.info("Processando Venda...")
    atualizar_proprietarios_parcial(proprietarios, acao.get("Agents", []), acao.get("Beneficiaries", []))

def processar_doacao(proprietarios: Dict[str, Dict[str, Any]], acao: Dict[str, Any]) -> None:
    logging.info("Processando Doação...")
    atualizar_proprietarios_parcial(proprietarios, acao.get("Agents", []), acao.get("Beneficiaries", []))

def processar_obito(proprietarios: Dict[str, Dict[str, Any]], acao: Dict[str, Any]) -> None:
    """
    Em uma ação de óbito, remove o proprietário falecido (listado em Agents)
    e distribui sua participação entre os herdeiros (Beneficiaries) proporcionalmente.
    """
    logging.info("Processando Óbito...")
    logging.debug(f"Proprietários (antes do óbito): {proprietarios}")
    for agente in acao.get("Agents", []):
        chave = chave_proprietario(agente)
        if chave in proprietarios:
            share = proprietarios[chave]["Percentual"]
            logging.info(f"Removendo proprietário falecido: {proprietarios[chave]['Nome']} (share={share:.2f}%)")
            del proprietarios[chave]
            total_frac = sum(parse_percentual(b.get("Percentage_Received", "")) or 100.0 for b in acao.get("Beneficiaries", []))
            for b in acao.get("Beneficiaries", []):
                frac = parse_percentual(b.get("Percentage_Received", "")) or 100.0
                addition = share * (frac / total_frac) if total_frac > 0 else share
                chave_b = chave_proprietario(b)
                if chave_b in proprietarios:
                    proprietarios[chave_b]["Percentual"] += addition
                    logging.info(f"Heredeiro(a) {proprietarios[chave_b]['Nome']} recebeu {addition:.2f}% por óbito, agora tem {proprietarios[chave_b]['Percentual']:.2f}%")

                else:
                    proprietarios[chave_b] = {
                        "Nome": b.get("Name"),
                        "CPF": b.get("CPF", "Não informado"),
                        "Percentual": addition,
                        "Cônjuge": processar_conjuge(b.get("Spouse"))
                    }
                    logging.info(f"Novo herdeiro(a) {proprietarios[chave_b]['Nome']} adicionado(a) com {addition:.2f}% por óbito.")
    logging.debug(f"Proprietários (após óbito): {proprietarios}")


def processar_partilha(proprietarios: Dict[str, Dict[str, Any]], acao: Dict[str, Any]) -> None:
    """
    Em uma ação de partilha, remove os agentes (que transferem sua participação)
    e distribui a parcela removida entre os beneficiários proporcionalmente.
    Se os beneficiários não informarem percentuais, a distribuição será feita de forma igualitária.
    """
    logging.info("Processando Partilha...")
    logging.debug(f"Proprietários (antes da partilha): {proprietarios}")

    agentes = acao.get("Agents", [])
    total_removido = 0.0
    for agente in agentes:
        chave = chave_proprietario(agente)
        if chave in proprietarios:
            share = proprietarios[chave]["Percentual"]
            logging.info(f"Removendo agente na partilha: {proprietarios[chave]['Nome']} (share={share:.2f}%)")
            total_removido += share
            del proprietarios[chave]
    logging.info(f"Total removido na partilha: {total_removido:.2f}%")


    beneficiarios = acao.get("Beneficiaries", [])
    benef_info = []
    for b in beneficiarios:
        pct = parse_percentual(b.get("Percentage_Received", ""))
        benef_info.append((b, pct))

    if all(pct is None for (_, pct) in benef_info) and benef_info:
        n = len(benef_info)
        benef_info = [(b, 100.0 / n) for (b, _) in benef_info]
        logging.info(f"Nenhum percentual de beneficiário informado na partilha, distribuindo igualmente: {benef_info}")

    else:
        total_declared = sum(pct for (_, pct) in benef_info if pct is not None)
        remaining_percentage = max(0.0, total_removido - total_declared)
        num_undefined_pct = sum(1 for (_, pct) in benef_info if pct is None)

        if num_undefined_pct > 0:
            addition_per_beneficiary = remaining_percentage / num_undefined_pct if num_undefined_pct > 0 else 0.0
            benef_info = [(b, (pct if pct is not None else addition_per_beneficiary)) for (b, pct) in benef_info]
            logging.info(f"Percentuais de beneficiários parcialmente informados na partilha, distribuindo restante ({remaining_percentage:.2f}%) igualmente: {benef_info}")
        elif total_declared < total_removido:
             logging.warning(f"Soma dos percentuais de beneficiários na partilha ({total_declared:.2f}%) é menor que o total removido ({total_removido:.2f}%). Distribuindo o restante proporcionalmente.")
             benef_info = [(b, pct + (remaining_percentage * (pct / total_declared) if total_declared > 0 else 0.0) ) for (b, pct) in benef_info]


    for b, pct in benef_info:
        addition = pct
        chave_b = chave_proprietario(b)
        if chave_b in proprietarios:
            proprietarios[chave_b]["Percentual"] += addition
            logging.info(f"{proprietarios[chave_b]['Nome']} recebeu {addition:.2f}% na partilha, agora tem {proprietarios[chave_b]['Percentual']:.2f}%")
        else:
            proprietarios[chave_b] = {
                "Nome": b.get("Name"),
                "CPF": b.get("CPF", "Não informado"),
                "Percentual": addition,
                "Cônjuge": processar_conjuge(b.get("Spouse"))
            }
            logging.info(f"Novo proprietário adicionado: {proprietarios[chave_b]['Nome']} com {addition:.2f}% na partilha")
    logging.debug(f"Proprietários (após partilha): {proprietarios}")


def processar_usufruto(usufrutuarios: Dict[str, Dict[str, Any]], acao: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Processa uma ação de usufruto adicionando os beneficiários ao registro de usufrutuários.
    Se o beneficiário já existir, acumula seu percentual.
    """
    logging.info("Processando Usufruto...")
    logging.debug(f"Usufrutuários (antes do usufruto): {usufrutuarios}")
    for b in acao.get("Beneficiaries", []):
        chave = chave_proprietario(b)
        perc = parse_percentual(b.get("Percentage_Received", "")) or 100.0
        if chave in usufrutuarios:
            usufrutuarios[chave]["Percentual"] += perc
            logging.info(f"Usufrutuário(a) {usufrutuarios[chave]['Nome']} teve percentual de usufruto aumentado em {perc:.2f}%, agora tem {usufrutuarios[chave]['Percentual']:.2f}%")
        else:
            usufrutuarios[chave] = {
                "Nome": b.get("Name"),
                "CPF": b.get("CPF", "Não informado"),
                "Percentual": perc,
                "Cônjuge": processar_conjuge(b.get("Spouse"))
            }
            logging.info(f"Novo usufrutuário(a) adicionado(a): {usufrutuarios[chave]['Nome']} com {perc:.2f}%")
    logging.debug(f"Usufrutuários (após usufruto): {usufrutuarios}")
    return usufrutuarios

def processar_alteracao_estado_civil(proprietarios: Dict[str, Dict[str, Any]], acao: Dict[str, Any]) -> None:
    """
    Processa uma ação de alteração do estado civil e nome, adicionando ou atualizando os dados do cônjuge,
    sem alterar o nome do proprietário.
    """
    logging.info("Processando Alteração do estado civil e nome (adicionando cônjuge)...")
    for agente in acao.get("Agents", []):
        chave = chave_proprietario(agente)
        novo_conjuge = processar_conjuge(agente.get("Spouse"))
        if chave in proprietarios:
            if not proprietarios[chave].get("Cônjuge"):
                proprietarios[chave]["Cônjuge"] = novo_conjuge
                logging.info(f"Cônjuge adicionado(a) para {proprietarios[chave]['Nome']}: {novo_conjuge.get('Nome')}")
        else:
            proprietarios[chave] = {
                "Nome": agente.get("Name"),
                "CPF": agente.get("CPF", "Não informado"),
                "Percentual": 0.0,
                "Cônjuge": novo_conjuge
            }
            logging.info(f"Proprietário(a) {proprietarios[chave]['Nome']} adicionado(a) com cônjuge: {novo_conjuge.get('Nome')}")


def validar_percentuais(lista_proprietarios: List[Dict[str, Any]], normalizar: bool = False) -> List[Dict[str, Any]]:
    """
    Formata os percentuais dos proprietários.

    Se 'normalizar' for True, reescala os percentuais para que a soma seja 100%.
    Caso contrário, retorna os percentuais originais formatados.
    """
    if normalizar:
        soma = sum(p["Percentual"] for p in lista_proprietarios)
        if abs(soma - 100) > 0.1:
            logging.warning(f"Soma dos percentuais final é {soma:.2f}% e não 100%.")
    else:
        soma = None  # Não usaremos a soma

    resultado = []
    for p in lista_proprietarios:
        novo = p.copy()
        if normalizar and soma and soma > 0:
            perc_rel = (p["Percentual"] / soma) * 100
            novo["Percentual"] = f"{perc_rel:.2f}%"
        else:
            novo["Percentual"] = f"{p['Percentual']:.2f}%"
        if not isinstance(novo.get("Cônjuge"), dict):
            novo["Cônjuge"] = {}
        resultado.append(novo)
    return resultado


# ------------------------------------------------
# 3) Processamento Final dos Atos
# ------------------------------------------------

def processar_acoes(dados: Any) -> Dict[str, Any]:
    """
    Processa as ações contidas em 'dados' (pode ser um dicionário com chave "Actions" ou uma lista)
    e retorna um dicionário final contendo:
      - "Número da Matrícula"
      - "Nome do Imóvel"
      - "Proprietários Atuais" (nua propriedade)
      - "Usufrutuários" (detentores do usufruto)
    """
    if isinstance(dados, dict):
        matricula = dados.get("Matricula_Number", "Não informado")
        nome_imovel = dados.get("Property_Name", "Não informado")
        lista_acoes = dados.get("Actions", [])
    elif isinstance(dados, list):
        matricula = "Não informado"
        nome_imovel = "Não informado"
        lista_acoes = dados
    else:
        matricula = "Não informado"
        nome_imovel = "Não informado"
        lista_acoes = []

    lista_acoes = normalizar_e_ordenar_acoes(lista_acoes)
    proprietarios: Dict[str, Dict[str, Any]] = {}
    usufrutuarios: Dict[str, Dict[str, Any]] = {}

    logging.info("📝 Iniciando processamento das ações...")
    logging.debug(f"Ações normalizadas e ordenadas: {lista_acoes}")
    logging.debug(f"Proprietários (inicial): {proprietarios}")
    logging.debug(f"Usufrutuários (inicial): {usufrutuarios}")


    for acao in lista_acoes:
        tipo = obter_tipo_acao(acao).lower()
        data = acao.get("Date") or acao.get("Data", "")
        logging.info(f"⚙️ Processando ação: '{tipo}' na data {data}")
        logging.debug(f"Ação detalhada: {acao}")

        if "alteração do estado civil e nome" in tipo:
            processar_alteracao_estado_civil(proprietarios, acao)
        elif any(x in tipo for x in ["alteração nome", "casamento"]):
            logging.info(f"Ignorando ação '{tipo}' na data {data}.")
            continue
        elif "venda" in tipo or "sale" in tipo or "venda nua propriedade" in tipo:
            processar_venda(proprietarios, acao)
        elif "doação" in tipo or "donation" in tipo:
            processar_doacao(proprietarios, acao)
            # Se houver indicação de usufruto na mesma ação, processa usufruto
            if "usufruto" in tipo or "reserva" in (acao.get("Additional_Info", "").lower()):
                usufrutuarios = processar_usufruto(usufrutuarios, acao)
        elif "óbito" in tipo or "falecimento" in tipo or "death" in tipo:
            processar_obito(proprietarios, acao)
        elif "partilha" in tipo or "share" in tipo:
            processar_partilha(proprietarios, acao)
        elif "usufruto" in tipo or "usufruct" in tipo:
            usufrutuarios = processar_usufruto(usufrutuarios, acao)
        elif "cancelamento de usufruto" in tipo:
            logging.info(f"Processando Cancelamento de Usufruto - Ação ainda não implementada. Ignorando ação '{tipo}' na data {data}.") #TODO: Implementar cancelamento de usufruto

        logging.debug(f"Ledger (Proprietários) após ação '{tipo}': {proprietarios}")
        logging.debug(f"Ledger (Usufrutuários) após ação '{tipo}': {usufrutuarios}")
        # Remove registros com percentual insignificante
        proprietarios = {k: v for k, v in proprietarios.items() if v["Percentual"] > 0.0001}

    final = {
        "Número da Matrícula": matricula,
        "Nome do Imóvel": nome_imovel,
        "Proprietários Atuais": validar_percentuais(list(proprietarios.values())),
        "Usufrutuários": validar_percentuais([u for k, u in usufrutuarios.items() if k not in proprietarios])
    }
    soma = sum(float(p["Percentual"].replace('%', '')) for p in final["Proprietários Atuais"])
    if abs(soma - 100) > 0.1:
        logging.warning(f"A soma dos percentuais finais é {soma:.2f}% e não 100%. Pode haver inconsistências.")
    logging.info("✅ Processamento das ações finalizado.")
    logging.debug(f"Resultado final: {final}")
    return final