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
