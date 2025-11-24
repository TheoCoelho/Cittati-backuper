import os
import sys
import json
import time
import re
import zipfile
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ================== CONFIGURAÇÕES ==================

# Endpoint de LOGIN (sem os params na URL)
LOGIN_URL = (
    "https://servicos.cittati.com.br/"
    "WSIntegracaoCittati/AutenticarUsuario"
)

# Endpoint de DADOS (sem os params na URL)
DADOS_URL = (
    "https://servicos.cittati.com.br/"
    "WSIntegracaoCittati/Operacional/ConsultarViagensDeteccoes"
)

# Usuário/senha – ideal é usar variável de ambiente, mas deixei default
USUARIO = os.getenv("CITTATI_USUARIO", "sintram.ws")
SENHA = os.getenv("CITTATI_SENHA", "4Eg_xyWa")

# Tempo máximo de espera por requisição
TIMEOUT = 180
MAX_TENTATIVAS = 3

# Pasta de saída dos backups
BACKUP_DIR = "backups_cittati"

# Mantido só por compatibilidade, mas não está sendo usado
TOKEN_HEADER_NAME = None

# Config compactação
MIN_DIAS_SEQUENCIA = 10
PADRAO_DATA = re.compile(r"backup_cittati_(\d{8})")


# ================== FUNÇÕES AUXILIARES HTTP ==================


def criar_sessao_com_retry():
    """Cria sessão requests com retry automático."""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def parse_data_argumento():
    """
    Lê a data da linha de comando.
    Aceita: YYYYMMDD, DD/MM/YYYY, YYYY-MM-DD.
    Se nada for passado, usa DIA ANTERIOR.
    """
    if len(sys.argv) >= 2:
        txt = sys.argv[1]
        for fmt in ("%Y%m%d", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(txt, fmt)
            except ValueError:
                continue
        raise SystemExit(
            "Formato de data inválido.\n"
            "Use: backup_cittati.py 20251117 ou 17/11/2025 ou 2025-11-17"
        )
    else:
        return datetime.now() - timedelta(days=1)


def obter_identificacao_login(session):
    """
    Faz o POST de login e retorna (identificacaoLogin, lista_empresas).
    Usa o mesmo esquema que você tem no Postman: params usuario/senha.
    """
    params = {"usuario": USUARIO, "senha": SENHA}
    print(f"Fazendo login em {LOGIN_URL} ...")
    resp = session.post(LOGIN_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()

    dados = resp.json()

    token = dados["identificacaoLogin"]
    empresas = dados.get("empresas", [])

    print(f"Login OK. Token obtido. {len(empresas)} empresas encontradas.")
    return token, empresas


def buscar_dados_empresa(session, token, empresa, data_consulta):
    """
    Consulta os dados da empresa para a data indicada.
    Retorna o JSON da resposta (ou None se vazio / 204).

    Aqui a gente manda o token de TODOS os jeitos prováveis:
      - query param identificacaoLogin
      - query param token
      - header identificacaoLogin
      - header token
    """
    data_str = data_consulta.strftime("%Y%m%d")  # ex: 20251117

    # NÃO colocar 'linha' se você quer TODAS as linhas
    params = {
        "empresa": empresa,
        "data": data_str,
        "identificacaoLogin": token,  # token como query param
        "token": token,                # token com outro nome como query param
    }

    headers = {
        "Accept": "application/json",
        "identificacaoLogin": token,  # token como header
        "token": token,               # token como header alternativo
    }

    print(f"  -> Buscando empresa={empresa} data={data_str} ...")

    resp = session.get(DADOS_URL, params=params, headers=headers, timeout=TIMEOUT)

    # DEBUG: mostra a URL e headers que realmente foram enviados
    print("     URL chamada:", resp.request.url)
    print("     Headers enviados:", dict(resp.request.headers))

    if resp.status_code == 204 or not resp.content:
        print("     (sem conteúdo / 204)")
        return None

    resp.raise_for_status()

    try:
        dados = resp.json()
    except ValueError:
        print("     Atenção: resposta não é JSON puro. Texto bruto (até 1000 chars):")
        print(resp.text[:1000])
        return {"raw": resp.text}

    # DEBUG: se vier erro de token, avisa
    if isinstance(dados, dict) and dados.get("codigoErro") == "02":
        print("     >>> A API respondeu 'Token inválido':", dados)

    return dados


def salvar_backup(estrutura_json, data_consulta):
    """Salva o dicionário em arquivo .txt no formato JSON."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    data_str = data_consulta.strftime("%Y%m%d")
    caminho = os.path.join(BACKUP_DIR, f"backup_cittati_{data_str}.txt")

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(estrutura_json, f, ensure_ascii=False, indent=2)

    print(f"\nBackup salvo em: {caminho}")


# ================== FUNÇÕES DE COMPACTAÇÃO ==================


def listar_arquivos_por_data():
    """
    Varre BACKUP_DIR e retorna:
      - dict: {date_str(YYYYMMDD): [lista de arquivos]}
      - lista ordenada de datas (datetime.date)
    """
    if not os.path.exists(BACKUP_DIR):
        print(f"Pasta '{BACKUP_DIR}' não existe.")
        return {}, []

    arquivos_por_data = {}
    datas_set = set()

    for nome in os.listdir(BACKUP_DIR):
        caminho = os.path.join(BACKUP_DIR, nome)
        if not os.path.isfile(caminho):
            continue

        m = PADRAO_DATA.search(nome)
        if not m:
            continue

        date_str = m.group(1)  # ex: 20251123
        try:
            data = datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            continue

        arquivos_por_data.setdefault(date_str, []).append(nome)
        datas_set.add(data)

    datas_ordenadas = sorted(datas_set)
    return arquivos_por_data, datas_ordenadas


def encontrar_blocos_10_dias(datas_ordenadas):
    """
    Recebe lista de dates (ordenada) e devolve lista de blocos:
      [ (data_inicio, data_fim), ... ] de 10 dias consecutivos (não sobrepostos).
    Ex: se há 13 dias seguidos, gera 1 bloco (10 dias) e deixa 3 para depois.
    """
    blocos = []
    n = len(datas_ordenadas)
    i = 0

    while i < n:
        inicio_seq = i
        # avança até quebrar sequência
        while (
            i + 1 < n
            and datas_ordenadas[i + 1] == datas_ordenadas[i] + timedelta(days=1)
        ):
            i += 1

        fim_seq = i
        tamanho_seq = fim_seq - inicio_seq + 1

        if tamanho_seq >= MIN_DIAS_SEQUENCIA:
            # quantos blocos de 10 cabem nessa sequência?
            num_blocos = tamanho_seq // MIN_DIAS_SEQUENCIA
            for b in range(num_blocos):
                idx_inicio = inicio_seq + b * MIN_DIAS_SEQUENCIA
                idx_fim = idx_inicio + MIN_DIAS_SEQUENCIA - 1
                data_ini = datas_ordenadas[idx_inicio]
                data_fim = datas_ordenadas[idx_fim]
                blocos.append((data_ini, data_fim))

        i = fim_seq + 1

    return blocos


def criar_zip_do_bloco(arquivos_por_data, data_inicio, data_fim):
    """
    Cria um zip para o intervalo [data_inicio, data_fim] (10 dias).
    Nome: backups_cittati_lote_YYYYMMDD_YYYYMMDD.zip
    Não recria se o arquivo já existir.
    """
    ini_str = data_inicio.strftime("%Y%m%d")
    fim_str = data_fim.strftime("%Y%m%d")

    zip_name = f"backups_cittati_lote_{ini_str}_{fim_str}.zip"
    zip_path = os.path.join(BACKUP_DIR, zip_name)

    if os.path.exists(zip_path):
        print(f"Zip {zip_name} já existe. Pulando...")
        return

    print(f"Criando {zip_name} ...")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        data_atual = data_inicio
        while data_atual <= data_fim:
            date_str = data_atual.strftime("%Y%m%d")
            for nome_arq in arquivos_por_data.get(date_str, []):
                caminho_arq = os.path.join(BACKUP_DIR, nome_arq)
                if os.path.isfile(caminho_arq):
                    zf.write(caminho_arq, arcname=nome_arq)
            data_atual += timedelta(days=1)

    print(f"  -> {zip_name} criado com sucesso.")


def compacta_backups_em_lotes():
    """
    - identifica datas com backups
    - encontra blocos de 10 dias consecutivos
    - cria um .zip para cada bloco de 10 dias
    """
    arquivos_por_data, datas_ordenadas = listar_arquivos_por_data()

    if not datas_ordenadas:
        print("Nenhum arquivo de backup encontrado para compactar.")
        return

    print("\nVerificando possibilidade de compactar em lotes de 10 dias...")
    blocos = encontrar_blocos_10_dias(datas_ordenadas)

    if not blocos:
        print("Ainda não há sequência de 10 dias consecutivos para compactar.")
        return

    print("Blocos de 10 dias que serão compactados:")
    for b in blocos:
        print(f" - {b[0].strftime('%Y-%m-%d')} até {b[1].strftime('%Y-%m-%d')}")

    for data_inicio, data_fim in blocos:
        criar_zip_do_bloco(arquivos_por_data, data_inicio, data_fim)

    print("Compactação em lotes concluída.\n")


# ================== MAIN ==================


def main():
    data_consulta = parse_data_argumento()
    data_iso = data_consulta.strftime("%Y-%m-%d")
    print(f"Data de referência: {data_iso}")

    session = criar_sessao_com_retry()

    # 1) LOGIN → token + lista de empresas
    token, empresas = obter_identificacao_login(session)

    # Estrutura final do backup
    resultado = {
        "data": data_iso,
        "empresas": {},  # chave = empresa (email), valor = dados da API
    }

    # 2) Para cada empresa, buscar os dados do dia
    for empresa in empresas:
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            try:
                dados = buscar_dados_empresa(session, token, empresa, data_consulta)
                if dados is not None:
                    resultado["empresas"][empresa] = dados
                else:
                    resultado["empresas"][empresa] = []
                break
            except (
                requests.Timeout,
                requests.ConnectionError,
                requests.RequestException,
            ) as e:
                print(
                    f"     Erro (tentativa {tentativa}/{MAX_TENTATIVAS}) "
                    f"para empresa {empresa}: {e}"
                )
                time.sleep(5 * tentativa)
        else:
            print(f"     Falha definitiva para empresa {empresa}")
            resultado["empresas"][empresa] = {"erro": "falha_apos_retentativas"}

    # 3) Salvar backup em TXT (JSON)
    salvar_backup(resultado, data_consulta)

    # 4) Verificar se já existem 10 dias consecutivos e compactar
    compacta_backups_em_lotes()


if __name__ == "__main__":
    main()
