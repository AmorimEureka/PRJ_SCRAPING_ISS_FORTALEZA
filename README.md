# NFS-e Fortaleza com Astro, Airflow e dlt

Automação por requisições HTTP para acessar o portal ISS Fortaleza, emitir NFS-e a partir de solicitações aprovadas no PostgreSQL, consultar notas emitidas, baixar XML/PDF e carregar os campos fiscais no PostgreSQL usando `dlt`.

O projeto não usa automação visual de navegador. Login, seleção de inscrição, pesquisa/cadastro de cliente, preenchimento, validação, emissão e downloads são feitos diretamente pelos endpoints JSF/Seam do portal, preservando cookies e `javax.faces.ViewState`.

## Arquitetura

As funcionalidades são executadas em DAGs independentes:

| DAG | Finalidade | Disparo |
| --- | --- | --- |
| `emissao_nfse` | Consulta o lote no PostgreSQL, emite somente itens aprovados e pendentes, baixa o PDF e atualiza a auditoria | Exclusivamente manual/API REST, sem agendamento |
| `extracao_nfse` | Consulta NFS-e emitidas no portal, baixa XML e carrega `nfse_xml` com `dlt` | Diariamente às 03:00 ou manualmente |

```mermaid
flowchart LR
    API[api_prontocardio] -->|POST dagRuns: lote_id + IDs| AIRFLOW[Airflow/Astro]
    AIRFLOW --> EMISSAO[DAG emissao_nfse]
    AIRFLOW --> EXTRACAO[DAG extracao_nfse]
    EMISSAO -->|Lê e atualiza lote/workflow| PG[(PostgreSQL)]
    EMISSAO -->|HTTP JSF/Seam| ISS[ISS Fortaleza]
    EXTRACAO -->|HTTP JSF/Seam| ISS
    EXTRACAO -->|dlt merge| NFSE[(nfse_xml)]
```

Os IDs enviados à DAG de emissão delimitam o lote solicitado, mas não autorizam a emissão. O PostgreSQL é a fonte de verdade: a DAG exige simultaneamente emissão `PENDENTE`, validação `VALIDADA` e workflow `EMISSAO_SOLICITADA`.

## Como o Sistema Escolhe e Emite as Notas

```mermaid
flowchart TD
    INICIO["Usuário seleciona<br/>as solicitações aprovadas"] --> GRUPO["Sistema reúne as notas<br/>que serão emitidas"]
    GRUPO --> AUTOMACAO["A emissão automática é iniciada"]

    subgraph SELECAO["1. Conferência das solicitações"]
        AUTOMACAO --> BUSCA["Busca somente as notas selecionadas"]
        BUSCA --> PRONTA{"A nota está pronta<br/>para emissão?"}
        REGRAS["A solicitação foi aprovada<br/>Foi marcada para emissão<br/>Ainda não foi emitida"] -.-> PRONTA
        PRONTA -- "Não" --> FORA["Não envia a nota<br/>e informa a pendência"]
        PRONTA -- "Sim" --> ANDAMENTO["Marca a nota como em andamento<br/>para evitar emissão duplicada"]
        ANDAMENTO --> DADOS{"Os dados estão completos?<br/>CPF, paciente, serviço,<br/>local, atendimento e valor"}
        DADOS -- "Não" --> ERRO
    end

    subgraph PREFEITURA["2. Emissão no site da Prefeitura"]
        DADOS -- "Sim" --> ACESSO["Acessa o site da Prefeitura"]
        ACESSO --> EMPRESA["Seleciona a empresa emissora correta"]
        EMPRESA --> EMITIR["Abre a opção Emitir NFS-e"]
        EMITIR --> CLIENTE["Pesquisa o cliente pelo CPF"]
        CLIENTE --> TOMADOR{"O cliente já está<br/>cadastrado?"}
        TOMADOR -- "Não" --> CADASTRO["Cadastra nome, CPF,<br/>endereço, cidade e e-mail"]
        TOMADOR -- "Sim" --> SERVICO
        CADASTRO --> SERVICO["Preenche o serviço realizado<br/>com o tipo de exame"]
        SERVICO --> VALOR["Informa o valor aprovado"]
        VALOR --> VALIDAR["Confere os dados antes de emitir"]
        VALIDAR --> CAMPOS{"A Prefeitura<br/>aceitou os dados?"}
        CAMPOS -- "Não" --> ERRO["Interrompe a emissão<br/>e guarda o motivo do erro"]
        CAMPOS -- "Sim" --> CONFIRMAR["Confirma a emissão"]
        CONFIRMAR --> EMITIDA{"A nota foi<br/>emitida com sucesso?"}
        EMITIDA -- "Não" --> ERRO
        EMITIDA -- "Sim" --> PDF["Obtém o número e baixa o PDF<br/>organizado por local, atendimento e paciente"]
    end

    subgraph RESULTADO["3. Resultado apresentado na aplicação"]
        PDF --> SUCESSO["Nota concluída<br/>Número e PDF disponíveis"]
        ERRO --> FALHA["Nota requer atenção<br/>Motivo disponível para correção"]
        SUCESSO --> LOTE{"Todas as notas selecionadas<br/>foram emitidas?"}
        FALHA --> LOTE
        FORA --> LOTE
        LOTE -- "Sim" --> LOTE_OK["Processo concluído<br/>Todas as notas estão disponíveis"]
        LOTE -- "Não" --> LOTE_ERRO["Processo requer atenção<br/>A aplicação mostra quais notas<br/>precisam ser corrigidas"]
    end

    classDef origem fill:#172033,stroke:#d9e2f2,color:#ffffff,stroke-width:1.5px;
    classDef processo fill:#1d2738,stroke:#cbd5e1,color:#ffffff,stroke-width:1.5px;
    classDef decisao fill:#4a3418,stroke:#f4c56a,color:#ffffff,stroke-width:1.5px;
    classDef sucesso fill:#123b2a,stroke:#70d6a0,color:#ffffff,stroke-width:1.5px;
    classDef falha fill:#471f25,stroke:#f08a96,color:#ffffff,stroke-width:1.5px;
    classDef regra fill:#2a2d33,stroke:#9ca3af,color:#ffffff,stroke-dasharray: 4 3;

    class INICIO,GRUPO,AUTOMACAO origem;
    class BUSCA,ANDAMENTO,ACESSO,EMPRESA,EMITIR,CLIENTE,CADASTRO,SERVICO,VALOR,VALIDAR,CONFIRMAR,PDF processo;
    class PRONTA,DADOS,TOMADOR,CAMPOS,EMITIDA,LOTE decisao;
    class SUCESSO,LOTE_OK sucesso;
    class ERRO,FALHA,FORA,LOTE_ERRO falha;
    class REGRAS regra;
```

As notas selecionadas formam apenas a lista inicial. Antes de acessar a
Prefeitura, o sistema confirma que cada solicitação foi aprovada, está pronta
e ainda não foi emitida. Ao iniciar o processamento, a nota fica reservada
para impedir uma emissão duplicada.

## Como Emitir uma NFS-e

<div align="center">
  <p>
    Selecione as solicitações aprovadas e acompanhe todo o processo pela
    aplicação. Não é necessário acessar manualmente o portal da Prefeitura.
  </p>
  <table width="82%">
    <tr>
      <td align="center" bgcolor="#E8F1FF">
        <br>
        <strong>📋 Solicitações aprovadas</strong><br><br>
        A tela apresenta as solicitações que já foram conferidas e estão
        disponíveis para emissão.
        <br><br>
      </td>
    </tr>
    <tr>
      <td align="center"><strong>↓</strong></td>
    </tr>
    <tr>
      <td align="center" bgcolor="#F1ECFF">
        <br>
        <strong>☑️ Selecione as notas</strong><br><br>
        Marque uma ou mais solicitações que deseja emitir.
        <br><br>
      </td>
    </tr>
    <tr>
      <td align="center"><strong>↓</strong></td>
    </tr>
    <tr>
      <td align="center" bgcolor="#EAF7FF">
        <br>
        <strong>🚀 Solicite a emissão</strong><br><br>
        selecionadas para processamento.
        <br><br>
      </td>
    </tr>
    <tr>
      <td align="center"><strong>↓</strong></td>
    </tr>
    <tr>
      <td align="center" bgcolor="#FFF5D6">
        <br>
        <strong>⏳ Emissão em andamento</strong><br><br>
        Os dados do cliente, do serviço e do valor são conferidos
        automaticamente. Aguarde a conclusão sem reenviar a solicitação.
        <br><br>
      </td>
    </tr>
  </table>

  <table width="92%">
    <tr>
      <td align="center" width="46%"><strong>↙</strong></td>
      <td align="center" width="8%"></td>
      <td align="center" width="46%"><strong>↘</strong></td>
    </tr>
    <tr>
      <td align="center" bgcolor="#E6F7EC">
        <br>
        <strong>✅ Nota emitida</strong><br><br>
        O número da NFS-e e o PDF ficam disponíveis para consulta e download.
        <br><br>
        <strong>Resultado: concluído</strong>
        <br><br>
      </td>
      <td align="center"></td>
      <td align="center" bgcolor="#FDECEC">
        <br>
        <strong>⚠️ Emissão não concluída</strong><br><br>
        A aplicação informa o motivo para que os dados sejam corrigidos antes
        de uma nova tentativa.
        <br><br>
        <strong>Resultado: requer atenção</strong>
        <br><br>
      </td>
    </tr>
  </table>
</div>

<details>
  <summary><strong>Detalhes técnicos: contrato do disparo</strong></summary>
  <br>
  <p>A API cria os registros operacionais antes de acionar o Airflow. Em
  seguida, realiza um <code>POST</code> em
  <code>/api/v1/dags/emissao_nfse/dagRuns</code> com o seguinte corpo:</p>

  <pre><code>{
  "dag_run_id": "api_prontocardio_nfse_lote_42",
  "conf": {
    "origem": "API_PRONTOCARDIO",
    "lote_id": 42,
    "solicitacao_ids": [101, 102, 103]
  }
}</code></pre>
</details>

<details>
  <summary><strong>Estados de uma solicitação</strong></summary>
  <br>
  <table>
    <thead>
      <tr>
        <th>Momento</th>
        <th>Workflow</th>
        <th>Emissão</th>
        <th>Lote</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Após validação</td>
        <td><code>VALIDADA</code></td>
        <td>—</td>
        <td>—</td>
      </tr>
      <tr>
        <td>Após seleção para emissão</td>
        <td><code>EMISSAO_SOLICITADA</code></td>
        <td><code>PENDENTE</code></td>
        <td><code>PENDENTE</code></td>
      </tr>
      <tr>
        <td>Durante a execução da DAG</td>
        <td><code>EMISSAO_SOLICITADA</code></td>
        <td><code>PROCESSANDO</code></td>
        <td><code>PROCESSANDO</code></td>
      </tr>
      <tr>
        <td>Emissão concluída</td>
        <td><code>EMITIDA</code></td>
        <td><code>EMITIDA</code></td>
        <td><code>EMITIDA</code></td>
      </tr>
      <tr>
        <td>Falha durante a emissão</td>
        <td><code>ERRO_EMISSAO</code></td>
        <td><code>ERRO</code></td>
        <td><code>ERRO</code></td>
      </tr>
    </tbody>
  </table>
</details>

## O Que Ela Faz

1. Cria sessao HTTP com `dlt.sources.helpers.requests.Session`.
2. Acessa portal ISS Fortaleza, segue o link OAuth e autentica no IdP/Keycloak com CPF e senha do `.env`.
3. Lista e percorre todas as inscricoes disponiveis quando o usuario logado possui mais de uma empresa.
4. Acessa menu `NFS-e > Consultar NFS-e` por request HTTP.
5. Seleciona `Serviços Prestados` e o filtro `Período Emissão/Tomador` via postbacks JSF.
6. Consulta o periodo em janelas seguras: quando `--inicio/--fim` recebem datas, divide automaticamente em meses e em blocos de ate 31 dias.
7. Localiza as linhas da NFS-e em `consultarnfseForm:dataTable`.
8. Aciona o exportador XML de cada linha (`consultarnfseForm:dataTable:*:j_id374`) por request/postback JSF.
9. Avanca nas paginas do resultado e repete a exportacao por linhas.
10. Baixa os XMLs em `downloads/`; quando houver mais de um arquivo, gera um ZIP local.
11. Entrega o XML/ZIP ao `dlt.sources.filesystem.filesystem`.
12. Usa um `@dlt.transformer` para parsear o XML e normalizar os campos.
13. Carrega a tabela `nfse_xml` no Postgres usando `dlt`.
14. Le a planilha `NOTAS FISCAIS.xlsx`, pesquisa o tomador por CPF e cadastra uma Pessoa Fisica quando necessario.
15. Configura CNAE, NBS, tributacao, descricao e valor, valida a NFS-e e so confirma a emissao quando o portal habilita o botao final.
16. Baixa o PDF emitido com o nome `NUMERO - LOCAL, TIPO ATENDIMENTO e PACIENTE.pdf`.
17. Registra o hash da linha em `downloads/emissoes_nfse.jsonl` para impedir reemissao acidental.

## Estrutura Do Projeto

```text
.
├── .astro/
├── dags/
│   ├── emissao_nfse.py
│   └── extracao_nfse.py
├── include/
├── plugins/
├── Dockerfile
├── docker-compose.override.yml
├── airflow_settings.yaml
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
└── src/
    └── nfs_fortaleza/
        ├── batch.py
        ├── __init__.py
        ├── cli.py
        ├── config.py
        ├── extraction.py
        ├── issuance.py
        ├── load.py
        ├── nfse_xml.py
        ├── periods.py
        ├── portal.py
        └── spreadsheet.py
```

## Arquivos

`README.md`: documentacao do projeto, comandos de uso, regras de negocio e fluxos.

`dags/emissao_nfse.py`: DAG sem agenda que recebe `lote_id` e `solicitacao_ids` pelo `dag_run.conf`.

`dags/extracao_nfse.py`: DAG separada para exportação dos XMLs e carga da tabela `nfse_xml`.

`src/nfs_fortaleza/batch.py`: contrato do payload, leitura segura dos itens aprovados/pendentes, reivindicação atômica e persistência dos resultados.

`src/nfs_fortaleza/extraction.py`: interpreta os filtros da DAG de extração e executa download/carga.

`Dockerfile`, `.astro/`, `airflow_settings.yaml` e `docker-compose.override.yml`: ambiente Astro baseado em `quay.io/astronomer/astro-runtime:13.0.0`.

`pyproject.toml`: metadados do pacote Python, dependencias principais e script `nfs-fortaleza`.

`requirements.txt`: lista de dependencias para instalacao direta no `.venv`.

`.env`: variaveis de ambiente com URL do portal, credenciais e conexao Postgres. Este arquivo nao deve ser versionado.

Variaveis opcionais de inscricao para usuarios representantes com mais de uma empresa:

- `INSCRICAO_CNPJ`: escolhe a inscricao pelo CNPJ.
- `INSCRICAO_MUNICIPAL`: escolhe pela inscricao municipal.
- `INSCRICAO_NOME`: escolhe por parte da razao social.

O fluxo principal percorre todas as inscricoes listadas pelo portal. Essas variaveis ficam disponiveis para cenarios em que seja necessario priorizar uma inscricao especifica em rotinas auxiliares.

`.gitignore`: ignora `.env`, `.venv`, downloads, artefatos de debug e caches Python.

`downloads/`: pasta local onde ficam os XMLs baixados do portal.

`src/nfs_fortaleza/cli.py`: interface de linha de comando. Expoe os comandos `run`, `download`, `load-file` e `emitir-planilha`.

`src/nfs_fortaleza/config.py`: carrega e normaliza configuracoes do `.env`, incluindo URL do portal e URL Postgres compativel com `dlt`.

`src/nfs_fortaleza/periods.py`: representa e interpreta competencias mensais, como `06/2026`, `2026-06` ou `Junho, 2026`; tambem interpreta datas completas, calcula a data final permitida e quebra intervalos longos em janelas aceitas pelo portal.

`src/nfs_fortaleza/portal.py`: usa `dlt.sources.helpers.requests.Session` para autenticar no portal/IdP, manter cookies, executar os postbacks JSF, abrir a consulta NFS-e, selecionar servicos prestados, filtrar por periodo, percorrer as paginas e baixar o XML via `consultarnfseForm:dataTable:*:j_id374`.

`src/nfs_fortaleza/spreadsheet.py`: le e valida as linhas do XLSX, normaliza CPF/valor e gera o nome final do PDF e o hash anti-duplicidade.

`src/nfs_fortaleza/issuance.py`: implementa por requests o fluxo `NFS-e > Emitir NFS-e`, incluindo pesquisa/cadastro do tomador, configuracao fiscal, validacao, confirmacao, recuperacao do numero e download do PDF.

`src/nfs_fortaleza/nfse_xml.py`: define o recurso XML dentro do `dlt`. Usa `dlt.sources.filesystem.filesystem` e um `@dlt.transformer` para ler XML/ZIP, parsear campos da NFS-e, preservar o XML bruto e gerar `row_hash`.

`src/nfs_fortaleza/load.py`: monta o pipeline `dlt`, aponta o destino Postgres e executa `pipeline.run(...)` com o recurso criado em `nfse_xml.py`.

## Executar com Astro e Docker

### Pré-requisitos

- Docker Engine com acesso ao daemon;
- Astro CLI;
- PostgreSQL acessível pelos containers;
- credenciais válidas do portal ISS Fortaleza.

Prepare as variáveis:

```bash
cp .env.example .env
```

Edite `.env` e informe as credenciais reais. `DATABASE_URL` e `AIRFLOW_CONN_POSTGRES_PRONTOCARDIO` devem apontar para o mesmo PostgreSQL usado por `api_prontocardio`. De dentro de um container, não use `localhost` para alcançar um banco executado em outro container ou host.

Se uma senha contiver `$`, coloque todo o valor entre aspas simples para impedir que o Docker Compose tente interpolar parte da credencial:

```dotenv
SENHA='senha-com-$-literal'
```

O PostgreSQL interno de metadados do Airflow usa a porta `5433` e o webserver usa `8082`, ambos configurados em `.astro/config.yaml`. Assim, o Astro não disputa as portas `5432` do banco de `api_prontocardio` e `8080` de outras aplicações. A porta de metadados não altera `DATABASE_URL` nem `AIRFLOW_CONN_POSTGRES_PRONTOCARDIO`.

Construa e valide as DAGs:

```bash
astro dev parse
```

Inicie o ambiente:

```bash
astro dev start
```

O Airflow local fica disponível em `http://localhost:8082`. Para encerrar:

```bash
astro dev stop
```

Os PDFs, XMLs e HTMLs de diagnóstico persistem no volume `data/`, montado em `/usr/local/airflow/data` nos serviços do Airflow.

Se uma tentativa anterior tiver deixado containers parciais, execute `astro dev stop` e depois `astro dev start` novamente. Use `astro dev kill` somente quando também quiser remover os containers e metadados locais do Airflow.

### Configuração da conexão PostgreSQL

A conexão usada pelas DAGs tem o ID `postgres_prontocardio`. No ambiente
local, ela é criada por `airflow_settings.yaml` com os mesmos dados de
`DATABASE_URL`. Como esse arquivo contém a senha em texto simples, ele está
ignorado pelo Git e pelo contexto de build Docker.

Depois de iniciar ou reiniciar o Astro, importe a conexão e o pool:

```bash
astro dev object import
```

As variáveis relacionadas devem permanecer coerentes:

```dotenv
DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/banco
NFSE_POSTGRES_CONN_ID=postgres_prontocardio
POSTGRES_SCHEMA=api_prontocardio
```

Como alternativa ao YAML local, `AIRFLOW_CONN_POSTGRES_PRONTOCARDIO` pode
receber uma URI PostgreSQL no `.env`; conexões definidas por variável de
ambiente têm precedência sobre a conexão importada para o banco de metadados
do Airflow.

Em um deployment Astro, cadastre a mesma conexão pelo painel/secret backend e forneça as demais variáveis como secrets do deployment.

O pool `nfse_portal`, com um slot, é criado por `airflow_settings.yaml`. Ele serializa os acessos das duas DAGs ao portal.

## Integração com `api_prontocardio`

O projeto `/home/rafaelamorim/repo/api_prontocardio` já contém o endpoint `POST /app_glosas/requisicoes/emissoes-nfse` e o cliente REST em `app_prontocardio/services/airflow_nfse.py`. A integração deve seguir este fluxo:

1. a API valida as solicitações e cria `lote_emissao_nfse` e `emissao_nfse`;
2. a API muda o workflow dos itens para `EMISSAO_SOLICITADA`;
3. a API chama `POST /api/v1/dags/emissao_nfse/dagRuns`;
4. a DAG consulta novamente o PostgreSQL e processa apenas registros aprovados e pendentes;
5. a DAG grava número da nota, status, evento, `dag_run_id`, horários e eventual erro;
6. a API consulta essas tabelas para apresentar o andamento ao usuário.

### Variáveis da API

Adicione ao `.env` de `api_prontocardio`:

```dotenv
AIRFLOW_NFSE_BASE_URL=http://host.docker.internal:8082
AIRFLOW_NFSE_DAG_ID=emissao_nfse
AIRFLOW_NFSE_DAG_RUNS_PATH=/api/v1/dags/{dag_id}/dagRuns
AIRFLOW_NFSE_TOKEN=
AIRFLOW_NFSE_USERNAME=admin
AIRFLOW_NFSE_PASSWORD=admin
AIRFLOW_NFSE_TIMEOUT_SECONDS=15
AIRFLOW_NFSE_VERIFY_SSL=false
```

Use usuário/senha apenas no ambiente local. Em produção, use HTTPS e um usuário de serviço com permissão mínima para ler a DAG e criar `dagRuns`; se houver gateway com Bearer token, preencha `AIRFLOW_NFSE_TOKEN`.

Quando a API também estiver em Docker, `localhost:8082` apontará para o próprio container da API. Use o DNS do serviço Airflow em uma rede Docker compartilhada ou o endereço publicado do host, como `host.docker.internal`.

### Endpoint da aplicação

Uma emissão individual:

```bash
curl -X POST "http://localhost:8000/app_glosas/requisicoes/emissoes-nfse" \
  -H "Authorization: Bearer TOKEN_DA_API" \
  -H "Content-Type: application/json" \
  -d '{"solicitacao_ids":[101]}'
```

Uma emissão em lote:

```bash
curl -X POST "http://localhost:8000/app_glosas/requisicoes/emissoes-nfse" \
  -H "Authorization: Bearer TOKEN_DA_API" \
  -H "Content-Type: application/json" \
  -d '{"solicitacao_ids":[101,102,103]}'
```

A API envia ao Airflow:

```json
{
  "dag_run_id": "api_prontocardio_nfse_lote_42",
  "conf": {
    "origem": "API_PRONTOCARDIO",
    "lote_id": 42,
    "solicitacao_ids": [101, 102, 103]
  }
}
```

### Contrato PostgreSQL da emissão

A DAG usa as tabelas criadas pelas migrações `20260723_028` e
`20260723_029` de `api_prontocardio`:

| Tabela | Responsabilidade |
| --- | --- |
| `solicitacao_nota` | Dados fiscais e cadastrais aprovados |
| `solicitacao_nota_workflow` | Aprovação e estado funcional |
| `lote_emissao_nfse` | `dag_run_id`, horário do disparo, estado e erro do lote |
| `emissao_nfse` | Estado, número, protocolo, erro e horários de cada item |
| `solicitacao_nota_evento` | Auditoria `NFSE_EMITIDA` ou `ERRO_EMISSAO` com o `dag_run_id` |

A seleção usada pela DAG equivale a:

```sql
SELECT e.id
FROM api_prontocardio.emissao_nfse e
JOIN api_prontocardio.solicitacao_nota s
  ON s.id = e.solicitacao_nota_id
JOIN api_prontocardio.solicitacao_nota_workflow w
  ON w.solicitacao_nota_id = s.id
WHERE e.lote_id = :lote_id
  AND e.solicitacao_nota_id = ANY(:solicitacao_ids)
  AND e.status = 'PENDENTE'
  AND w.validacao = 'VALIDADA'
  AND w.status = 'EMISSAO_SOLICITADA';
```

O valor aprovado é lido de `solicitacao_nota.valor_nota`, criado pela
migração `20260723_029`. Cidade e UF podem ser persistidas como `cidade`/`uf`;
na ausência, a DAG usa `NFSE_DEFAULT_CITY=FORTALEZA` e
`NFSE_DEFAULT_UF=CE`.

Registros sem CPF válido, valor positivo, paciente, local, tipo de atendimento ou procedimento não são enviados ao portal: a emissão é marcada como `ERRO`, preservando a mensagem para correção.

### Disparo direto da DAG de emissão

Para diagnóstico, o mesmo contrato pode ser enviado diretamente ao Airflow:

```bash
curl -u "admin:admin" \
  -X POST "http://localhost:8082/api/v1/dags/emissao_nfse/dagRuns" \
  -H "Content-Type: application/json" \
  -d '{
    "dag_run_id":"teste_nfse_lote_42",
    "conf":{"lote_id":42,"solicitacao_ids":[101,102]}
  }'
```

O disparo direto não cria lote nem aprova solicitações. Se os registros não existirem nos estados exigidos, nenhuma nota será emitida.

## DAG de extração para `nfse_xml`

`extracao_nfse` é independente da emissão. Na execução agendada, consulta apenas o dia representado pelo início do intervalo de dados do Airflow. Também aceita os seguintes `dag_run.conf`:

Uma competência:

```json
{"competencia": "07/2026"}
```

Um intervalo:

```json
{"inicio": "01/07/2026", "fim": "23/07/2026"}
```

Uma nota específica:

```json
{"cnpj": "59932105000121", "numero_nfse": "8"}
```

Exemplo de disparo REST:

```bash
curl -u "admin:admin" \
  -X POST "http://localhost:8082/api/v1/dags/extracao_nfse/dagRuns" \
  -H "Content-Type: application/json" \
  -d '{
    "dag_run_id":"extracao_manual_202607",
    "conf":{"competencia":"07/2026"}
  }'
```

Os XMLs são processados com disposição `merge` e chave `row_hash`, evitando duplicação na tabela `POSTGRES_SCHEMA.nfse_xml`.

## Uso

### Emissão manual por planilha

Este comando permanece disponível para operação assistida ou diagnóstico. A integração em lote da aplicação deve usar `emissao_nfse` e o PostgreSQL.

Todo o fluxo é executado por requisições HTTP aos endpoints JSF/Seam do portal. O comando não abre navegador nem depende de clique, resolução de tela ou automação visual.

#### 1. Preparar o ambiente

O projeto requer Python 3.12 ou superior. Na raiz do repositório, crie o ambiente virtual e instale o pacote:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e .
```

Crie o arquivo `.env` na raiz do projeto:

```dotenv
PORTAL_PREFEITURA_FORTALEZA=https://iss.fortaleza.ce.gov.br/grpfor/home.seam
CPF_LOGIN=CPF_USADO_NO_LOGIN
SENHA=SENHA_DO_PORTAL
DATABASE_URL=postgresql://USUARIO:SENHA@HOST:PORTA/BANCO
POSTGRES_SCHEMA=NOME_DO_SCHEMA
```

As variáveis `DATABASE_URL` e `POSTGRES_SCHEMA` ainda são exigidas pela configuração compartilhada do projeto, embora a emissão não grave a nota no Postgres.

#### 2. Preparar a planilha

Por padrão, o comando lê `NOTAS FISCAIS.xlsx` na raiz do projeto. A primeira linha deve conter estes cabeçalhos:

| Coluna | Uso na emissão |
| --- | --- |
| `PACIENTE` | Nome do tomador e composição do nome do PDF |
| `CPF` | Pesquisa ou cadastro do tomador como Pessoa Física |
| `RUA` | Logradouro do novo cliente |
| `NUMERO CASA` | Número do endereço do novo cliente |
| `BAIRRO` | Bairro do novo cliente |
| `CIDADE` | Cidade do tomador |
| `UF` | Unidade federativa do tomador, com duas letras |
| `EMAIL` | E-mail do novo cliente |
| `TIPO DE EXAME` | Descrição do serviço |
| `VALOR` | Valor do serviço, que deve ser maior que zero |
| `LOCAL` | Composição do nome do PDF |
| `TIPO ATENDIMENTO` | Composição do nome do PDF |

Os cabeçalhos são normalizados, portanto diferenças entre maiúsculas/minúsculas e acentuação não impedem a leitura. As colunas `ATENDIMENTO` e `DATA` também são aceitas, mas não são obrigatórias para a emissão.

O valor passado em `--linha` é o número real da linha no XLSX, incluindo o cabeçalho. Assim, a primeira linha de dados é a linha `2`.

#### 3. Conferir uma linha sem emitir

Faça primeiro uma prévia da linha desejada:

```bash
.venv/bin/nfs-fortaleza emitir-planilha "NOTAS FISCAIS.xlsx" \
  --linha 2
```

Sem `--confirmar-emissao`, o comando apenas lê e valida a planilha e mostra paciente, CPF, exame e valor. Ele não autentica nem altera dados no portal.

Também é possível conferir as próximas linhas de um lote:

```bash
.venv/bin/nfs-fortaleza emitir-planilha "NOTAS FISCAIS.xlsx" \
  --todas \
  --limite 10
```

#### 4. Emitir uma NFS-e

Depois de conferir a prévia, execute:

```bash
.venv/bin/nfs-fortaleza emitir-planilha "NOTAS FISCAIS.xlsx" \
  --linha 2 \
  --cnpj 59932105000121 \
```

O CNPJ `59932105000121` já é o padrão, portanto `--cnpj` pode ser omitido quando essa for a inscrição emissora. A opção `--confirmar-emissao` autoriza uma operação fiscal real no portal.

O comando:

1. autentica e seleciona a inscrição pelo CNPJ usando os endpoints do portal;
2. pesquisa o tomador pelo CPF;
3. cadastra o tomador como Pessoa Física quando ele ainda não existe;
4. preenche serviço e valor com os dados da planilha;
5. valida os campos;
6. confirma a emissão somente quando o portal habilita a ação;
7. recupera o número da NFS-e e baixa o PDF.

#### 5. Emitir um lote

Para emitir todas as linhas que ainda não constam no histórico local:

```bash
.venv/bin/nfs-fortaleza emitir-planilha "NOTAS FISCAIS.xlsx" \
  --todas \
  --confirmar-emissao
```

Use `--limite` para restringir a quantidade processada na execução:

```bash
.venv/bin/nfs-fortaleza emitir-planilha "NOTAS FISCAIS.xlsx" \
  --todas \
  --limite 10 \
  --confirmar-emissao
```

É obrigatório informar `--linha` ou `--todas`; as duas opções não podem ser usadas juntas. No lote, as linhas são processadas na ordem em que aparecem na planilha. Se uma delas falhar, a execução é interrompida e as emissões anteriores permanecem registradas.

#### 6. Arquivos gerados e proteção contra duplicidade

O PDF é salvo em `downloads/` com o padrão:

```text
NUMERO DA NFS-E - LOCAL, TIPO ATENDIMENTO e PACIENTE.pdf
```

Depois de obter um PDF válido, a aplicação grava o sucesso em `downloads/emissoes_nfse.jsonl`. Uma linha com o mesmo conteúdo e número no XLSX será ignorada nas execuções seguintes. Se o conteúdo de uma linha já emitida for alterado, seu hash também muda; por isso, não altere linhas emitidas para tentar repetir ou corrigir uma nota.

Para usar outro diretório de saída:

```bash
.venv/bin/nfs-fortaleza emitir-planilha "NOTAS FISCAIS.xlsx" \
  --linha 2 \
  --downloads-dir "/caminho/para/notas" \
  --confirmar-emissao
```

Em caso de erro de navegação, mudança de layout, sessão expirada ou resposta inesperada do portal, os HTMLs de diagnóstico são salvos em `.artifacts/`.

#### Parâmetros disponíveis

| Parâmetro | Descrição |
| --- | --- |
| `PLANILHA` | Caminho do XLSX; o padrão é `NOTAS FISCAIS.xlsx` |
| `--linha N` | Processa uma linha específica, incluindo o cabeçalho na contagem |
| `--todas` | Processa todas as linhas pendentes |
| `--limite N` | Limita o número de linhas quando usado com `--todas` |
| `--cnpj CNPJ` | Seleciona a inscrição emissora; padrão `59932105000121` |
| `--downloads-dir DIR` | Altera o diretório dos PDFs e do histórico local |
| `--confirmar-emissao` | Autoriza validar, confirmar e emitir no portal |

O fluxo usa CNAE `861010101`, NBS `123011900`, indicador `030104`, CST `200`, classificação tributária `200029` e alíquota `3,00`. A descrição vem de `TIPO DE EXAME` e o valor vem de `VALOR`.

Para validar a implementação localmente sem emitir notas:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

### Consulta e carga

Consultar e carregar uma NFS-e especifica, informando o CNPJ da inscricao e o numero da nota fiscal:

```bash
.venv/bin/nfs-fortaleza run --cnpj 12345678000190 --numero-nfse 12345
```

Nesse modo, a aplicacao seleciona apenas a inscricao correspondente ao CNPJ, consulta a aba `Número NFS-e` e identifica a competencia diretamente no XML antes da carga. Os argumentos `--cnpj` e `--numero-nfse` devem ser informados juntos e nao podem ser combinados com `--competencia`, `--inicio` ou `--fim`.

Fluxo completo para uma competencia:

```bash
.venv/bin/nfs-fortaleza run --competencia 06/2026
```

Baixar XML sem carregar no banco:

```bash
.venv/bin/nfs-fortaleza download --competencia 06/2026
```

Carregar um XML ou ZIP ja baixado:

```bash
.venv/bin/nfs-fortaleza load-file downloads/nota_5.xml --competencia 06/2026
```

Rodar um intervalo mensal:

```bash
.venv/bin/nfs-fortaleza run --inicio 01/2026 --fim 06/2026
```

Rodar um intervalo de datas maior que 31 dias:

```bash
.venv/bin/nfs-fortaleza run --inicio 01/06/2026 --fim 09/07/2026
```

Baixar XMLs de um intervalo de datas sem carregar no banco:

```bash
.venv/bin/nfs-fortaleza download --inicio 01/06/2026 --fim 09/07/2026
```

## Regra De Negocio

### Emissao

Para cada linha selecionada, a aplicacao:

- autentica e seleciona exclusivamente a inscricao do CNPJ informado por postback JSF;
- abre `NFS-e > Emitir NFS-e` pelo endpoint do menu, preservando a conversa Seam;
- pesquisa o CPF e seleciona o resultado do componente RichFaces;
- cadastra o tomador como Pessoa Fisica somente quando a pesquisa nao retorna cliente;
- pesquisa e seleciona o CNAE hospitalar, encadeando os eventos AJAX de NBS, indicador, CST e classificacao;
- preenche descricao e valor da planilha;
- executa as duas requisicoes do botao de validacao;
- interrompe sem emitir caso o portal retorne erro ou nao habilite `Confirmar Emissão de NFS-e`;
- aciona o endpoint final uma unica vez, confirma a mensagem de sucesso, extrai o numero e baixa o PDF;
- grava o sucesso no historico local somente depois de obter um PDF valido.

### Consulta

O arquivo gerado deve vir da tela `NFS-e > Consultar NFS-e`, usando o resultado de notas emitidas no periodo solicitado.

Para cada competencia ou janela de datas, a aplicacao:

- seleciona `Serviços Prestados`;
- usa a aba/filtro `Período Emissão/Tomador`;
- preenche `Data de emissão inicial` e `Data de emissão final` com a janela atual;
- limita a data final a data de hoje quando o periodo solicitado esta em andamento;
- submete a consulta por postback JSF;
- identifica cada NFS-e na tabela `Resultado da Consulta`;
- usa o link da linha com `title="Exportar XML"` e acao `consultarnfseForm:dataTable:*:j_id374`;
- faz o postback JSF com o `javax.faces.ViewState` atual;
- avanca no paginador da tabela e repete a exportacao ate a ultima pagina;
- baixa os XMLs e carrega os campos no Postgres.

O portal rejeita consulta com data final maior que hoje, exibindo `Data final da pesquisa não poderá ser superior a data de hoje.`. Por isso, para a competencia corrente, a aplicacao consulta de `01/MM/AAAA` ate a data atual.

O portal tambem limita consultas sem CPF/CNPJ do tomador a no maximo 31 dias, exibindo `Período escolhido para a consulta tem mais de um mês. Escolha um período com no máximo 31 dias ou informe o CPF/CNPJ do tomador.`. Para evitar esse erro, a CLI aceita `--inicio/--fim` como competencias ou datas completas. Quando recebe datas completas, divide automaticamente em janelas por mes e por limite de 31 dias antes de consultar o portal.

Se nenhuma NFS-e for encontrada no periodo, a CLI exibe `Ignorado` e segue para a proxima competencia do intervalo.

## Campos Da Tabela

A tabela principal no Postgres e `nfse_xml`. Entre os campos mapeados estao:

- status, situacao, cancelamento e mensagens de retorno;
- numero da NFS-e, codigo de verificacao, competencia e data/hora;
- RPS e lote de RPS;
- servico, CNAE, item da lista, tributacao, aliquota, discriminacao e municipio;
- prestador, tomador, CPF/CNPJ, inscricao municipal, endereco e contato;
- construcao civil, obra e ART;
- valores do servico, deducoes, retencoes, ISS, base de calculo, descontos e valor liquido;
- `xml_campos`, com flatten do XML;
- `xml_documento`, com o XML original do documento;
- `row_hash`, usado como chave primaria de merge.

A coluna `aliquota` e normalizada para formato decimal com quatro casas. O valor bruto do XML fica em `aliquota_xml`.

## Fluxo De Negocio

```mermaid
flowchart TD
    A[Solicitar competencia ou intervalo] --> B[Acessar ISS Fortaleza]
    B --> C[Criar dlt requests Session]
    C --> D[Autenticar no IdP com CPF e senha]
    D --> E[Abrir NFS-e > Consultar NFS-e]
    E --> F[Selecionar Serviços Prestados]
    F --> G[Filtrar por Periodo Emissao/Tomador]
    G --> H[Quebrar datas em janelas permitidas]
    H --> I[Consultar notas por janela]
    I --> J{Existem resultados?}
    J -- Nao --> K[Ignorar competencia sem notas]
    J -- Sim --> L[Acionar Exportar XML das linhas da pagina]
    L --> M{Ha proxima pagina?}
    M -- Sim --> L
    M -- Nao --> N[Baixar XML ou ZIP das NFS-e]
    N --> O[Parsear campos fiscais]
    O --> P[Carregar nfse_xml no Postgres]
```

## Fluxo Da Aplicacao

```mermaid
flowchart TD
    A[CLI: nfs-fortaleza run] --> B["config.py carrega .env"]
    B --> C["periods.py normaliza periodo"]
    C --> D["portal.py cria dlt requests Session"]
    D --> E[GET login.seam e OAuth login]
    E --> F[POST formulario Keycloak com CPF/senha]
    F --> G[GET consultaNfsePorNumero.seam]
    G --> H[POST JSF seleciona Serviços Prestados]
    H --> I[POST JSF ativa Periodo Emissao/Tomador]
    I --> J[POST JSF consulta janela]
    J --> K{Resultado encontrado?}
    K -- Nao --> L[PeriodWithoutInvoicesError]
    L --> M[CLI imprime Ignorado e segue]
    K -- Sim --> N[POST JSF dos links j_id374 da pagina]
    N --> O{Paginador tem proxima pagina?}
    O -- Sim --> N
    O -- Nao --> P[XML ou ZIP em downloads/]
    P --> Q["load.py cria pipeline dlt"]
    Q --> R["nfse_xml.py cria filesystem resource"]
    R --> S["@dlt.transformer parseia XML"]
    S --> T[Normaliza campos e adiciona metadados]
    T --> U[dlt merge em nfse_xml]
    U --> V[Postgres Railway]
```

## Observacoes Do Portal

O portal e JSF/Seam. O botao geral `Exportar XML das Notas Selecionadas` pode retornar XML vazio se o estado de selecao nao estiver sincronizado no servidor. Por isso a automacao usa o link de exportacao XML da propria linha da NFS-e e submete o formulario com o `javax.faces.ViewState` atual via `dlt.sources.helpers.requests.Session`.

A automacao salva HTML em `.artifacts/` quando ocorre falha de navegacao, login, mudanca de layout ou bloqueio de sessao.
