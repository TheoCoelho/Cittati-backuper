# Compactador.py
import os
import re
import zipfile
from datetime import datetime, timedelta

BACKUP_DIR = "backups_cittati"
MIN_DIAS_SEQUENCIA = 10
PADRAO_DATA = re.compile(r"backup_cittati_(\d{8})")


def listar_arquivos_por_data():
    """
    Retorna:
      - arquivos_por_data: {date_str(YYYYMMDD): [lista de arquivos]}
      - datas_ordenadas: lista de datetime.date ordenadas
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
    Encontra blocos de 10 dias consecutivos (não sobrepostos).
    Retorna lista de tuplas: [(data_inicio, data_fim), ...]
    """
    blocos = []
    n = len(datas_ordenadas)
    i = 0

    while i < n:
        inicio_seq = i
        # avança até quebrar sequência de dias consecutivos
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
    Cria um zip para o intervalo [data_inicio, data_fim] (10 dias)
    e, após criar o zip com sucesso, APAGA os arquivos de backup
    que foram incluídos no zip.
    """
    ini_str = data_inicio.strftime("%Y%m%d")
    fim_str = data_fim.strftime("%Y%m%d")

    zip_name = f"backups_cittati_lote_{ini_str}_{fim_str}.zip"
    zip_path = os.path.join(BACKUP_DIR, zip_name)

    if os.path.exists(zip_path):
        print(f"Zip {zip_name} já existe. Pulando criação e exclusão...")
        return

    print(f"Criando {zip_name} ...")

    # Lista de arquivos que realmente entram no zip
    arquivos_zipados = []

    # 1) Cria o ZIP com todos os arquivos dos 10 dias
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        data_atual = data_inicio
        while data_atual <= data_fim:
            date_str = data_atual.strftime("%Y%m%d")
            for nome_arq in arquivos_por_data.get(date_str, []):
                caminho_arq = os.path.join(BACKUP_DIR, nome_arq)
                if os.path.isfile(caminho_arq):
                    zf.write(caminho_arq, arcname=nome_arq)
                    arquivos_zipados.append(caminho_arq)
            data_atual += timedelta(days=1)

    print(f"  -> {zip_name} criado com sucesso.")

    # 2) Apaga exatamente os arquivos que foram compactados
    print("  -> Removendo arquivos individuais que foram compactados...")
    removidos = 0
    erros = 0

    for caminho_arq in arquivos_zipados:
        if os.path.isfile(caminho_arq):
            try:
                os.remove(caminho_arq)
                removidos += 1
            except Exception as e:
                print(f"     Erro ao remover {os.path.basename(caminho_arq)}: {e}")
                erros += 1

    print(f"  -> Arquivos removidos: {removidos}. Erros ao remover: {erros}.")


def compacta_backups_em_lotes():
    """
    - identifica datas com backups
    - encontra blocos de 10 dias consecutivos
    - cria um .zip para cada bloco de 10 dias
    - apaga os arquivos individuais que foram compactados
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


if __name__ == "__main__":
    compacta_backups_em_lotes()
