Aqui está um **README.md profissional, claro e completo**, perfeito para colocar na raiz do projeto.

---

# 📦 Cittati Backup System

**Automação de backups diários, consultas customizadas e compactação automática em lotes de 10 dias.**

Este projeto foi desenvolvido para automatizar a coleta de viagens e detecções do sistema **Cittati**, gerar backups diários, executar consultas customizadas por data/empresa/linha e compactar automaticamente conjuntos de 10 dias consecutivos de arquivos de backup.

---

## 📁 Estrutura do Projeto

```
📂 /
│
├── Diario.py               → Executa o backup diário (todas as empresas)
├── backup_cittati.py       → Backup manual por data, intervalo, empresa e linha
├── Compactador.py          → Compacta sequências de 10 dias e remove arquivos originais
│
└── backups_cittati/        → Pasta onde ficam os backups e os arquivos .zip
```

---

# 🚀 Funcionalidades

## ✅ **1. Backup diário automático**

O script **Diario.py** faz:

* Login no sistema Cittati
* Busca dados de **todas as empresas** para a data informada (ou dia anterior, se nenhum parâmetro for passado)
* Salva o arquivo no formato:

  ```
  backup_cittati_YYYYMMDD.txt
  ```
* Em seguida **chama automaticamente o Compactador** para verificar se é possível zipar 10 dias consecutivos.

---

## ✅ **2. Backup manual com filtros**

O script `backup_cittati.py` permite consultas personalizadas:

* 🔸 Uma data específica
* 🔸 Intervalo de datas
* 🔸 Uma empresa ou todas
* 🔸 Uma linha ou todas

Exemplos:

### Apenas um dia, todas as empresas:

```bash
python backup_cittati.py --data 20251123 --empresa todas --linha todas
```

### Intervalo de datas:

```bash
python backup_cittati.py --inicio-fim 20251120 20251123 --empresa todas --linha todas
```

### Uma empresa e uma linha:

```bash
python backup_cittati.py --data 20251123 --empresa gerencia.mgr@ciacoordenadas.com.br --linha 301C
```

---

## ✅ **3. Compactação automática em lotes de 10 dias**

O script **Compactador.py**:

* Identifica arquivos no formato:

  ```
  backup_cittati_YYYYMMDD*.txt
  ```
* Detecta **sequências de 10 dias consecutivos**
* Gera arquivos .zip com nome:

  ```
  backups_cittati_lote_YYYYMMDD_YYYYMMDD.zip
  ```
* E **remove automaticamente os arquivos .txt** que participaram do lote

Exemplo de saída:

```
backups_cittati_lote_20251101_20251110.zip
```

Após a criação do zip, os arquivos individuais daqueles 10 dias são excluídos.

---

# ⚙️ Configuração

## 1. Requisitos

* Python 3.8+
* Bibliotecas:

  ```bash
  pip install requests urllib3
  ```

## 2. Estrutura necessária

Certifique-se de que exista a pasta:

```
backups_cittati/
```

Os scripts criarão automaticamente se ela não existir.

---

# ▶️ Uso Diário

### Rodar o backup diário:

```bash
python Diario.py
```

O script:

1. Executa backup do dia
2. Salva `backup_cittati_YYYYMMDD.txt`
3. Executa `compacta_backups_em_lotes()`
4. Se houver 10 dias consecutivos → cria ZIP e apaga os TXT

---

# 📌 Nome esperado dos arquivos de backup

O Compactador reconhece arquivos neste formato:

```
backup_cittati_YYYYMMDD.txt
backup_cittati_YYYYMMDD_algum_sufixo.txt
```

Exemplos válidos:

```
backup_cittati_20251123.txt
backup_cittati_20251124_todas_empresas.txt
backup_cittati_20251125_linha_301C.txt
```

Se não seguir esse formato, o arquivo será ignorado pelo compactador.

---

# 🧠 Lógica de compactação

* O sistema acumula arquivos `.txt` diariamente.
* Quando existir **uma sequência de 10 dias seguidos**, por exemplo:

  ```
  2025-11-01
  2025-11-02
  ...
  2025-11-10
  ```
* O compactador cria:

  ```
  backups_cittati_lote_20251101_20251110.zip
  ```
* Todos os TXT desses 10 dias são **apagados imediatamente** após o ZIP ser criado.

---

# 🛠 Ajustes e Melhorias Futuras Possíveis

* Envio automático dos arquivos .zip para S3/Google Drive
* Notificações por e-mail/WhatsApp após sucesso ou falha
* Relatórios automáticos dos backups diários
* Execução agendada pelo Windows Task Scheduler

---

# 📞 Suporte

Se precisar de:

* Ajustes de lógica
* Agendamento do backup
* Logs mais detalhados
* Painel web
* Dashboard para visualizar os arquivos

Só avisar — posso criar tudo isso pra você.
