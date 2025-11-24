import os
import sys
import json
import time
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import argparse


# ================== CONFIGURAÇÕES ==================

# Endpoint de LOGIN (sem os params na URL)
LOGIN_URL = (
    "https://servicos.cittati.com.br/"
    "WSIntegracaoCittati/Autenticacao/AutenticarUsuario"
)

# Endpoint de DADOS (sem os params na URL)
DADOS_URL = (
    "https://servicos.cittati.com.br/"
    "WSIntegracaoCittati/Operacional/ConsultarViagensDeteccoes"
)

# Usuário/senha – ideal é usar variável de ambiente
USUARIO = os.getenv("CITTATI_USUARIO", "sintram.ws")
SENHA = os.getenv("CITTATI_SENHA", "4Eg_xyWa")

TIMEOUT = 180
MAX_TENTATIVAS = 3
BACKUP_DIR = "backups_cittati"


# ================== FUNÇÕES AUXILIARES ==================


def criar_sessao_com_retry():
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


def parse_data(texto):
    """Aceita: YYYYMMDD, DD/MM/YYYY, YYYY-MM-DD."""
    for fmt in ("%Y%m%d", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            continue
    raise ValueError(f"Data inválida: {texto}")


def gerar_intervalo_datas(data_inicio, data_fim):
    """Gera lista de datas de data_inicio até data_fim (inclusive)."""
    datas = []
    atual = data_inicio
    while atual <= data_fim:
        datas.append(atual)
        atual += timedelta(days=1)
    return datas


def obter_identificacao_login(session):
    params = {"usuario": USUARIO, "senha": SENHA}
    print(f"Fazendo login em {LOGIN_URL} ...")
    resp = session.post(LOGIN_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()

    dados = resp.json()
    token = dados["identificacaoLogin"]
    empresas = dados.get("empresas", [])

    print(f"Login OK. Token obtido. {len(empresas)} empresas encontradas.")
    return token, empresas


def buscar_dados_empresa(session, token, empresa, data_consulta, linha=None):
    """
    Consulta os dados da empresa para a data indicada.
    linha = None → todas as linhas.
    """
    data_str = data_consulta.strftime("%Y%m%d")  # ex: 20251123

    params = {
        "empresa": empresa,
        "data": data_str,
        "identificacaoLogin": token,  # token como query param
        "token": token,                # token extra como query param
    }

    if linha:
        params["linha"] = linha

    headers = {
        "Accept": "application/json",
        "identificacaoLogin": token,  # token como header
        "token": token,               # token extra como header
    }

    print(f"  -> Buscando empresa={empresa} data={data_str} linha={linha or 'TODAS'} ...")

    resp = session.get(DADOS_URL, params=params, headers=headers, timeout=TIMEOUT)

    # DEBUG opcional: descomente se quiser ver a URL e headers
    # print("     URL chamada:", resp.request.url)
    # print("     Headers enviados:", dict(resp.request.headers))

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

    if isinstance(dados, dict) and dados.get("codigoErro") == "02":
        print("     >>> A API respondeu 'Token inválido':", dados)

    return dados


def salvar_backup(estrutura_json, data_consulta, sufixo=""):
    """Salva o dicionário em arquivo .txt no formato JSON."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    data_str = data_consulta.strftime("%Y%m%d")
    if sufixo:
        caminho = os.path.join(BACKUP_DIR, f"backup_cittati_{data_str}_{sufixo}.txt")
    else:
        caminho = os.path.join(BACKUP_DIR, f"backup_cittati_{data_str}.txt")

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(estrutura_json, f, ensure_ascii=False, indent=2)

    print(f"\nBackup salvo em: {caminho}")


# ================== PARSE DE ARGUMENTOS ==================


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backup Cittati - viagens/deteccoes por data, empresa e linha."
    )

    group_data = parser.add_mutually_exclusive_group(required=True)
    group_data.add_argument(
        "--data",
        help="Data única (YYYYMMDD)",
    )
    group_data.add_argument(
        "--inicio-fim",
        nargs=2,
        metavar=("DATA_INICIO", "DATA_FIM"),
        help="Intervalo de datas (ex: 20251120 20251123)",
    )

    parser.add_argument(
        "--empresa",
        default="todas",
        help='E-mail da empresa. Use "todas" para todas as empresas do login.',
    )
    parser.add_argument(
        "--linha",
        default="todas",
        help='Código da linha (ex: 301C). Use "todas" para todas as linhas.',
    )

    return parser.parse_args()


# ================== MAIN ==================


def main():
    args = parse_args()

    # Datas
    if args.data:
        data_unica = parse_data(args.data)
        lista_datas = [data_unica]
    else:
        data_inicio = parse_data(args.inicio_fim[0])
        data_fim = parse_data(args.inicio_fim[1])
        if data_fim < data_inicio:
            raise SystemExit("DATA_FIM não pode ser menor que DATA_INICIO.")
        lista_datas = gerar_intervalo_datas(data_inicio, data_fim)

    linha = None if args.linha.lower() in ("todas", "all", "") else args.linha
    empresa_param = args.empresa

    print("Datas a processar:")
    for d in lista_datas:
        print(" -", d.strftime("%Y-%m-%d"))

    session = criar_sessao_com_retry()
    token, empresas_login = obter_identificacao_login(session)

    # Empresas que serão usadas
    if empresa_param.lower() in ("todas", "all", ""):
        empresas_selecionadas = empresas_login
        sufixo_emp = "todas_empresas"
    else:
        empresas_selecionadas = [empresa_param]
        sufixo_emp = empresa_param.replace("@", "_").replace(".", "_")

    sufixo_linha = "todas_linhas" if linha is None else f"linha_{linha}"
    sufixo_arquivo = f"{sufixo_emp}_{sufixo_linha}"

    # Loop por data
    for data_consulta in lista_datas:
        data_iso = data_consulta.strftime("%Y-%m-%d")
        print(f"\n======================")
        print(f"Processando data: {data_iso}")
        print(f"Empresas: {empresas_selecionadas}")
        print(f"Linha: {linha or 'TODAS'}")
        print(f"======================\n")

        resultado = {
            "data": data_iso,
            "linha": linha or "todas",
            "empresas": {},
        }

        for empresa in empresas_selecionadas:
            for tentativa in range(1, MAX_TENTATIVAS + 1):
                try:
                    dados = buscar_dados_empresa(
                        session, token, empresa, data_consulta, linha=linha
                    )
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

        salvar_backup(resultado, data_consulta, sufixo=sufixo_arquivo)


if __name__ == "__main__":
    main()
