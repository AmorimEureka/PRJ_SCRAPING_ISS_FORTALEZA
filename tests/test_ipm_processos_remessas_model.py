from pathlib import Path


MODELO = (
    Path(__file__).parents[1]
    / "dbt_glosas_ipm"
    / "models"
    / "intermediate"
    / "int_ipm_processos_remessas.sql"
).read_text()


def test_prioriza_remessa_confirmada_pelo_relatorio_spu():
    sql = " ".join(MODELO.lower().split())

    assert "ref('stg_processos_relatorios_ipm')" in sql
    assert "r.cd_remessa = rel.cd_remessa" in sql
    assert "r.valor_total::numeric, 2) = p.valor_protocolo" in sql
    assert "'automatica_spu'::text as origem_associacao" in sql
    assert "from candidatos_spu candidato_spu" in sql


def test_associacao_spu_nao_exige_mesma_competencia_do_true():
    trecho_spu = MODELO.split("), candidatos_spu as (", 1)[1].split(
        "), candidatos_spu_contados as (", 1
    )[0]

    assert "r.competencia = p.competencia_producao" not in trecho_spu
