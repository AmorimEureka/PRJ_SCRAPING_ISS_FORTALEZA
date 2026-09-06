from pathlib import Path


MODELS = Path(__file__).parents[1] / 'dbt_glosas_ipm' / 'models'


def test_protocolo_sem_processo_recupera_contexto_por_remessa_unica():
    modelo = (
        MODELS / 'intermediate' / 'int_ipm_processos_remessas.sql'
    ).read_text()

    assert 'protocolos_sem_processo as (' in modelo
    assert "status_associacao = 'SEM_PROCESSO'" in modelo
    assert 'rel.cd_remessa = remessa.cd_remessa' in modelo
    assert 'where quantidade_candidatos = 1' in modelo
    assert 'select * from processos_recuperados' in modelo


def test_protocolo_orfao_prefere_relatorio_mais_recente_da_remessa():
    modelo = (
        MODELS / 'intermediate' / 'int_ipm_processos_remessas.sql'
    ).read_text()

    assert 'partition by cd_remessa' in modelo
    assert 'order by extraido_em desc nulls last' in modelo
    assert 'where ordem_remessa = 1' in modelo


def test_protocolo_orfao_herda_competencia_oficial_da_remessa_mv():
    modelo = (
        MODELS / 'intermediate' / 'int_ipm_processos_remessas.sql'
    ).read_text()

    assert 'remessa.competencia as competencia_producao' in modelo


def test_associacao_spu_usa_apenas_contexto_mais_recente_da_remessa():
    modelo = (
        MODELS / 'intermediate' / 'int_ipm_processos_remessas.sql'
    ).read_text()

    trecho = modelo.split('), candidatos_spu as (', 1)[1]
    trecho = trecho.split('), candidatos_spu_contados as (', 1)[0]
    assert "join relatorios_remessas rel" in trecho
    assert "ref('stg_processos_relatorios_ipm')" not in trecho


def test_contexto_recuperado_restringe_candidatos_a_remessa_correta():
    modelo = (
        MODELS / 'intermediate' / 'int_ipm_candidatos_sete_regras.sql'
    ).read_text()

    assert 'r.numero_processo as numero_processo_resolvido' in modelo
    assert 'coalesce(d.valor_protocolo_cogestao, d.valor_protocolo)' in modelo
    assert 'i.cd_remessa = d.cd_remessa_esperada' in modelo


def test_pendencia_usa_processo_recuperado_da_remessa():
    modelo = (
        MODELS / 'marts' / 'glossas_nao_vinculadas_ipm.sql'
    ).read_text()

    assert 'r.numero_processo as numero_processo_remessa' in modelo
    assert 'numero_processo_remessa,' in modelo
    assert 'coalesce(d.valor_protocolo_cogestao, d.valor_protocolo)' in modelo
