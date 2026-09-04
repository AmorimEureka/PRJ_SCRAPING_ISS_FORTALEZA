with contextos_protocolos_contados as (
    select
        upper(btrim(numero_protocolo)) as numero_protocolo_normalizado,
        coalesce(
            competencia_producao,
            to_char(data_realizacao, 'MM/YYYY')
        ) as competencia_producao,
        min(numero_processo) as numero_processo,
        min(cd_remessa) as cd_remessa,
        count(
            distinct (upper(btrim(numero_processo)), cd_remessa)
        ) as quantidade_contextos
    from {{ ref('glosas_ipm_vinculadas') }}
    where nullif(btrim(numero_protocolo), '') is not null
      and numero_processo is not null
      and cd_remessa is not null
    group by 1, 2
), contextos_protocolos as (
    select *
    from contextos_protocolos_contados
    where quantidade_contextos = 1
), associados_remessa as (
    select
        d.*,
        coalesce(r.cd_remessa, contexto.cd_remessa) as cd_remessa,
        contexto.numero_processo as numero_processo_protocolo
    from {{ ref('stg_demonstrativo_processos_ipm') }} d
    left join {{ ref('int_ipm_processos_remessas') }} r
      on r.numero_processo = d.numero_processo
     and r.competencia_producao = d.competencia_producao
     and r.valor_protocolo
         = round(d.valor_protocolo_cogestao::numeric, 2)
     and r.numero_protocolo = upper(btrim(d.numero_protocolo))
    left join contextos_protocolos contexto
      on contexto.numero_protocolo_normalizado
         = upper(btrim(d.numero_protocolo))
     and contexto.competencia_producao
         = to_char(d.data_realizacao, 'MM/YYYY')
), primeira_regra_insegura as (
    select id_registro, criterio,
           row_number() over (partition by id_registro order by prioridade) as ordem
    from (
        select id_registro, prioridade, criterio
        from {{ ref('int_ipm_candidatos_sete_regras') }}
        group by id_registro, prioridade, criterio
        having count(
            distinct (numero_processo_resolvido, cd_remessa, conta)
        ) > 1
    ) regras
), pendentes as (
    select
        d.*,
        i.criterio,
        case
            when coalesce(
                d.numero_processo,
                d.numero_processo_protocolo
            ) is null then 'sem_processo'
            when d.status_associacao = 'AMBIGUO'
                 and d.numero_processo_protocolo is null
                then 'processo_ambiguo'
            when d.cd_remessa is null then 'remessa_nao_encontrada_ou_ambigua'
            when i.criterio is not null then 'ambiguo'
            else 'nao_encontrado'
        end as motivo
    from associados_remessa d
    left join {{ ref('int_ipm_glosas_resolvidas') }} ok using (id_registro)
    left join primeira_regra_insegura i
      on i.id_registro = d.id_registro and i.ordem = 1
    where ok.id_registro is null
)
select
    id_registro,
    coalesce(numero_processo, numero_processo_protocolo)
        as numero_processo,
    cd_remessa,
    motivo,
    valor_glosa,
    criterio as criterio_correspondencia,
    '[]'::jsonb as remessas_candidatas,
    numero_protocolo,
    data_realizacao,
    numero_guia_senha,
    codigo_servico,
    codigo_beneficiario,
    codigo_glosa,
    valor_processado,
    timezone('America/Sao_Paulo', now()) as data_primeira_ocorrencia,
    timezone('America/Sao_Paulo', now()) as data_ultima_tentativa
from pendentes
