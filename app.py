from flask import Flask, render_template, request, redirect, url_for
from markupsafe import Markup
import requests as rq
import requests
import pandas as pd
import re
import plotly.graph_objects as go
import plotly.express as px
import os

app = Flask(__name__)

# URLs dos webhooks
WEBHOOK_VARIAVEIS = "https://n8n.v4lisboatech.com.br/webhook/painel-olympo/variaveis"
WEBHOOK_AGENTE = "https://n8n.v4lisboatech.com.br/webhook/painel-olympo/agente"

# Ordem correta dos meses
ORDEM_MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril",
    "Maio", "Junho", "Julho", "Agosto",
    "Setembro", "Outubro", "Novembro", "Dezembro"
]

# -----------------------------
# BUSCA OS DADOS
# -----------------------------
def fetch_data():
    resp = requests.get(WEBHOOK_VARIAVEIS, timeout=20)
    data = resp.json()
    df_var = pd.DataFrame(data.get("variavel", []))
    df_fixo = pd.DataFrame(data.get("fixo", []))
    return df_var, df_fixo


# -----------------------------
# TRATAMENTO DE NÚMEROS
# -----------------------------
def parse_number(x):
    if pd.isna(x):
        return 0.0

    x = str(x).strip()

    # remove caracteres que não sejam números, , . ou -
    x = re.sub(r"[^\d,.-]", "", x)

    # formato brasileiro
    if x.count(",") == 1 and x.rfind(",") > x.rfind("."):
        x = x.replace(".", "").replace(",", ".")
    else:
        x = x.replace(",", "")

    try:
        return float(x)
    except:
        return 0.0


# -----------------------------
# PREPARA DATAFRAME
# -----------------------------
def prepare_dataframes(df_var, df_fixo):

    # tratamento dos valores
    if "Valor Variável" in df_var.columns:
        df_var["Valor Variável"] = df_var["Valor Variável"].apply(parse_number)
    else:
        df_var["Valor Variável"] = 0.0

    if "Valor Fixo" in df_fixo.columns:
        df_fixo["Valor Fixo"] = df_fixo["Valor Fixo"].apply(parse_number)
    else:
        df_fixo["Valor Fixo"] = 0.0

    # agrupar variável por mês
    df_var_grouped = df_var.groupby(
        ["Cliente", "Mês"],
        as_index=False
    ).agg({
        "Valor Variável": "sum",
        "Registro": "count"
    })

    # merge com fixo
    df_merged = df_var_grouped.merge(df_fixo, on="Cliente", how="left")

    # ticket médio
    df_merged["Ticket Médio"] = df_merged.apply(
        lambda r: (r["Valor Variável"] / r["Registro"]) if r["Registro"] else 0.0,
        axis=1
    )

    # ordenar meses
    df_merged["Mês"] = pd.Categorical(df_merged["Mês"], categories=ORDEM_MESES, ordered=True)
    df_merged = df_merged.sort_values("Mês")

    # renomear registros → qtd eventos
    df_merged.rename(columns={"Registro": "Qtd Eventos"}, inplace=True)

    return df_merged


# -----------------------------
# GRÁFICO 1
# -----------------------------

def build_fig1(df_filtrado, mostrar_ticket=False):
    # Criar cópia e garantir tipos corretos
    df_plot = df_filtrado.copy()
    df_plot["Mês"] = df_plot["Mês"].astype(str)  # Converter mês para string
    df_plot["Valor Variável"] = pd.to_numeric(df_plot["Valor Variável"], errors='coerce')  # Forçar numérico
    
    fig = go.Figure()

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',  # Fundo do papel transparente
        plot_bgcolor='rgba(0,0,0,0)',  
    )

    for cliente, grupo in df_plot.groupby("Cliente"):
        # Criar listas explícitas para x e y
        meses = grupo["Mês"].tolist()
        valores = grupo["Valor Variável"].tolist()
        
        fig.add_trace(go.Scatter(
            x=meses,
            y=valores,
            mode="lines+markers",
            name=f"{cliente} - Valor Variável",
            line=dict(width=3),
            marker=dict(size=7),
            hovertemplate="<b>%{x}</b><br>Cliente: "+cliente+"<br>Valor Variável: R$ %{y:,.2f}<extra></extra>"
        ))

    if mostrar_ticket:
        for cliente, grupo in df_plot.groupby("Cliente"):
            meses = grupo["Mês"].tolist()
            tickets = grupo["Ticket Médio"].tolist()
            
            fig.add_trace(go.Scatter(
                x=meses,
                y=tickets,
                mode="lines+markers",
                name=f"{cliente} - Ticket Médio",
                line=dict(width=2, dash="dot"),
                marker=dict(size=6, symbol="diamond"),
                yaxis="y2",
                hovertemplate="<b>%{x}</b><br>Cliente: "+cliente+"<br>Ticket Médio: R$ %{y:,.2f}<extra></extra>"
            ))

    layout_args = dict(
        title="Valor Variável por Mês e Cliente",
        template="plotly_dark",
        legend_title_text="Cliente / Métrica",
        margin=dict(t=60, l=40, r=40, b=40),
        xaxis=dict(title="Mês"),
        yaxis=dict(title="Valor Variável (R$)")
    )

    if mostrar_ticket:
        layout_args["yaxis2"] = dict(
            title="Ticket Médio (R$)",
            overlaying="y",
            side="right",
            showgrid=False
        )

    fig.update_layout(**layout_args)
    return fig


# -----------------------------
# GRÁFICO 2
# -----------------------------

def build_fig2(df_filtrado):
    df_comp = df_filtrado.groupby("Cliente", as_index=False)[["Valor Variável", "Valor Fixo"]].sum()
    
    # Garantir que os valores sejam numéricos e converter para listas
    df_comp["Valor Variável"] = pd.to_numeric(df_comp["Valor Variável"], errors='coerce')
    df_comp["Valor Fixo"] = pd.to_numeric(df_comp["Valor Fixo"], errors='coerce')
    
    # Criar listas explícitas
    clientes = df_comp["Cliente"].tolist()
    valores_variaveis = df_comp["Valor Variável"].tolist()
    valores_fixos = df_comp["Valor Fixo"].tolist()

    fig = go.Figure()
    
    # Adicionar barras manualmente
    fig.add_trace(go.Bar(
        name="Valor Variável",
        x=clientes,
        y=valores_variaveis,
        marker_color="#e5c100"
    ))
    
    fig.add_trace(go.Bar(
        name="Valor Fixo",
        x=clientes,
        y=valores_fixos,
        marker_color="#00aaff"
    ))

    fig.update_layout(
        barmode='group',
        title="Comparativo: Valor Variável x Valor Fixo por Cliente",
        uniformtext_minsize=8,
        uniformtext_mode='hide',
        yaxis_title="Valor (R$)",
        xaxis_title="Cliente",
        template="plotly_dark",
        legend_title_text="Tipo de Valor",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )




    return fig

# -----------------------------
# ROTA PRINCIPAL
# -----------------------------
@app.route("/", methods=["GET"])
def index():

    # busca dados
    try:
        df_var, df_fixo = fetch_data()
        df_agrupado = prepare_dataframes(df_var, df_fixo)
    except Exception as e:
        return render_template("index.html", error=f"Erro ao buscar dados: {e}")

    selected_clients = request.args.getlist("cliente")
    selected_months = request.args.getlist("mes")
    mostrar_ticket = request.args.get("ticket", "false").lower() == "true"

    all_clients = sorted(df_agrupado["Cliente"].unique().tolist())
    meses_disponiveis = [m for m in ORDEM_MESES if m in df_agrupado["Mês"].unique()]

    if not selected_clients:
        selected_clients = all_clients

    if not selected_months:
        selected_months = meses_disponiveis

    df_filtrado = df_agrupado[
        (df_agrupado["Cliente"].isin(selected_clients)) &
        (df_agrupado["Mês"].isin(selected_months))
    ]

    # -----------------------------
    # KPI CORRIGIDO
    # -----------------------------

    kpi_valor_variavel = df_filtrado["Valor Variável"].sum()

    # Valor Fixo → somar apenas uma vez por cliente
    kpi_valor_fixo = df_filtrado.groupby("Cliente")["Valor Fixo"].first().sum()

    # total correto de eventos
    kpi_eventos = int(df_filtrado["Qtd Eventos"].sum())

    # total de registros
    kpi_registros = len(df_filtrado)

    # Na função index(), antes de criar os gráficos
    print("=== DEBUG DATAFRAME FILTRADO ===")
    print(df_filtrado[["Cliente", "Mês", "Valor Variável"]].head())
    print(f"Soma total Valor Variável: {df_filtrado['Valor Variável'].sum()}")

    # montar gráficos
    fig1 = build_fig1(df_filtrado, mostrar_ticket=mostrar_ticket)
    fig2 = build_fig2(df_filtrado)

    fig1_html = fig1.to_html(include_plotlyjs=False, full_html=False)
    fig2_html = fig2.to_html(include_plotlyjs=False, full_html=False)

    return render_template(
        "index.html",
        fig1=Markup(fig1_html),
        fig2=Markup(fig2_html),
        plotly_cdn="https://cdn.plot.ly/plotly-latest.min.js",
        all_clients=all_clients,
        meses_disponiveis=meses_disponiveis,
        selected_clients=selected_clients,
        selected_months=selected_months,
        mostrar_ticket=mostrar_ticket,
        kpi_valor_variavel=kpi_valor_variavel,
        kpi_valor_fixo=kpi_valor_fixo,
        kpi_eventos=kpi_eventos,
        kpi_registros=kpi_registros
    )


# -----------------------------
# ROTAS DO AGENTE
# -----------------------------
@app.route("/agente", methods=["GET"])
def agente():
    periodo = request.args.get("periodo", "")
    clientes = request.args.get("cliente", "")

    url = f"{WEBHOOK_AGENTE}?periodo={periodo}&cliente={clientes}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        texto = resp.text
    except Exception as e:
        texto = f"❌ Erro ao consultar o agente: {e}"

    return render_template("potencial.html", texto=texto)

# ============ POTENCIAL ===========


# Adicione após as importações existentes
WEBHOOK_OPORTUNIDADES = "https://n8n.v4lisboatech.com.br/webhook/painel-olympo/oportunidades"

# Adicione esta função após prepare_dataframes
# def fetch_oportunidades():
#     resp = requests.get(WEBHOOK_OPORTUNIDADES, timeout=20)
#     data = resp.json()
#     df = pd.DataFrame(data)
    
#     # Renomear colunas
#     df = df.rename(columns={
#         "nome_do_cliente": "cliente",
#         "faturamento_monitorado_ou_previsivel": "tem_faturamento",
#         "cliente_tem_maturidade_para_variavel": "maturidade",
#         "aumento_de_performance_ultimos_3_meses": "crescimento",
#         "status_do_cliente": "status",
#         "step_atual_do_cliente": "step",
#         "oportunidade_de_monetizacao_mapeada": "oportunidades",
#         "alguma_objecao_de_preco_em_relacao_a_outros_produtos": "objeções",
#     })


#     return df

def fetch_oportunidades():
    resp = requests.get(WEBHOOK_OPORTUNIDADES, timeout=20)
    data = resp.json()
    df = pd.DataFrame(data)
    
    # Renomear colunas
    df = df.rename(columns={
        "nome_do_cliente": "cliente",
        "faturamento_monitorado_ou_previsivel": "tem_faturamento",
        "cliente_tem_maturidade_para_variavel": "maturidade",
        "aumento_de_performance_ultimos_3_meses": "crescimento",
        "status_do_cliente": "status",
        "step_atual_do_cliente": "step",
        "oportunidade_de_monetizacao_mapeada": "oportunidades",
        "alguma_objecao_de_preco_em_relacao_a_outros_produtos": "objeções",
    })

    # -----------------------------
    # NORMALIZAÇÃO COMPLETA
    # -----------------------------

    # Corrige casos específicos
    df["status"] = df["status"].replace({
        "⚫Aviso Prévio": "⚫ Aviso Prévio",
        "⚫  Aviso Prévio": "⚫ Aviso Prévio",
    })

    # Remove espaços extras
    df["status"] = df["status"].astype(str).str.strip()
    df["step"] = df["step"].astype(str).str.strip()
    df["maturidade"] = df["maturidade"].astype(str).str.strip()
    df["crescimento"] = df["crescimento"].astype(str).str.strip()

    # Normalização unificada
    df["status_norm"] = df["status"].apply(normalize_status)

    return df

def normalize_status(s):
    if not isinstance(s, str):
        return "Aviso Prévio"
    s_lower = s.lower()
    if "safe" in s_lower or "🟢" in s_lower:
        return "Safe"
    if "care" in s_lower or "atenção" in s_lower or "🟡" in s_lower:
        return "Care"
    if "danger" in s_lower or "risco" in s_lower or "churn" in s_lower or "🔴" in s_lower:
        return "Danger"
    if "aviso" in s_lower or "⚫" in s_lower:
        return "Aviso Prévio"
    if "🟢" in s:
        return "Safe"
    if "🟡" in s:
        return "Care"
    if "🔴" in s:
        return "Danger"
    return s.strip()

# Nova rota para potencial
@app.route("/potencial-crescimento", methods=["GET"])
def potencial_crescimento():
    try:
        df = fetch_oportunidades()
    except Exception as e:
        return render_template("potencial_crescimento.html", error=f"Erro ao buscar dados: {e}")
    
    # Opções para filtros
    opcoes_status = [
        "🟢 Safe (resultado sólido, relacionamento positivo, potencial de longo prazo)",
        "🟡 Care (atenção necessária, alguns pontos de risco ou instabilidade)",
        "🔴 Danger (risco de churn ou baixo engajamento)",
        "⚫ Aviso Prévio"
    ]
    
    opcoes_step = ["V0", "V1", "V2", "V3", "V4"]
    
    opcoes_maturidade = [
        "Sim, total abertura",
        "Possivelmente, mas precisa ser educado sobre o modelo",
        "Não, prefere contratos fixos tradicionais"
    ]
    
    opcoes_crescimento = [
        "Sim, houve crescimento consistente",
        "Estável, mas com potencial de expansão",
        "Em queda ou sem histórico confiável"
    ]
    
    # Filtros selecionados
    selected_status = request.args.getlist("status")
    selected_step = request.args.getlist("step")
    selected_maturidade = request.args.getlist("maturidade")
    selected_crescimento = request.args.getlist("crescimento")
    
    # Defaults
    if not selected_status:
        selected_status = opcoes_status
    if not selected_step:
        selected_step = opcoes_step
    if not selected_maturidade:
        selected_maturidade = opcoes_maturidade
    if not selected_crescimento:
        selected_crescimento = opcoes_crescimento
    
    # Aplicar filtros
    df_filtrado = df[
        (df["status"].isin(selected_status)) &
        (df["step"].isin(selected_step)) &
        (df["maturidade"].isin(selected_maturidade)) &
        (df["crescimento"].isin(selected_crescimento))
    ]
    
    # Normalizar status
    df_filtrado["status_norm"] = df_filtrado["status"].apply(normalize_status)
    
    # Gráfico 1: Distribuição por Step
    cores_step = {
        "V0": "#FFFFFF",
        "V1": "#FFCFCF",
        "V2": "#FF8983",
        "V3": "#FF4545",
        "V4": "#FF0000"
    }
    
    step_counts = df_filtrado["step"].value_counts().reindex(opcoes_step, fill_value=0)
    
    fig_step = go.Figure()
    fig_step.add_trace(go.Bar(
        x=step_counts.index.tolist(),
        y=step_counts.values.tolist(),
        marker_color=[cores_step.get(s, "#888") for s in step_counts.index],
        text=step_counts.values.tolist(),
        textposition='auto',
    ))
    
    fig_step.update_layout(
        title="Clientes por Step",
        xaxis_title="Step",
        yaxis_title="Quantidade de Clientes",
        template="plotly_dark",
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        
        # Controle de tamanho
        autosize=True,
        height=400,
        margin=dict(l=60, r=40, t=60, b=60),
        
        # Grid personalizado
        xaxis=dict(
            gridcolor='rgba(255,255,255,0.1)',
            linecolor='rgba(0,212,255,0.3)'
        ),
        yaxis=dict(
            gridcolor='rgba(255,255,255,0.1)',
            linecolor='rgba(0,212,255,0.3)'
        ),
        
        # Fonte
        font=dict(color='#ffffff', size=12)
    )

    # Gráfico 2: Distribuição por Status
    cores_status = {
        "Safe": "#34C759",
        "Care": "#FFD60A",
        "Danger": "#FF3B30",
        "Aviso Prévio": "#4A4A4A"
    }
    
    ordem_status = ["Safe", "Care", "Danger", "Aviso Prévio"]
    status_counts = df_filtrado["status_norm"].value_counts().reindex(ordem_status, fill_value=0)
    
    fig_status = go.Figure()
    fig_status.add_trace(go.Bar(
        x=status_counts.index.tolist(),
        y=status_counts.values.tolist(),
        marker_color=[cores_status.get(s, "#888") for s in status_counts.index],
        text=status_counts.values.tolist(),
        textposition='auto',
    ))

    fig_status.update_layout(
        title="Clientes por Status",
        xaxis_title="Status",
        yaxis_title="Quantidade de Clientes",
        template="plotly_dark",
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        
        # Controle de tamanho
        autosize=True,
        height=400,
        margin=dict(l=60, r=40, t=60, b=60),
        
        # Grid personalizado
        xaxis=dict(
            gridcolor='rgba(255,255,255,0.1)',
            linecolor='rgba(0,212,255,0.3)'
        ),
        yaxis=dict(
            gridcolor='rgba(255,255,255,0.1)',
            linecolor='rgba(0,212,255,0.3)'
        ),
        
        # Fonte
        font=dict(color='#ffffff', size=12)
    )
    
    # Converter gráficos para HTML
    fig_step_html = fig_step.to_html(
        include_plotlyjs='cdn',
        config={'responsive': True, 'displayModeBar': False}
    )

    fig_status_html = fig_status.to_html(
        include_plotlyjs='cdn',
        config={'responsive': True, 'displayModeBar': False}
    )
    
    # Converter DataFrame para HTML table

    colunas_para_remover = ["createdAt", "updatedAt", "status_norm", "id"]

    df_filtrado = df_filtrado.drop(columns=colunas_para_remover, errors="ignore")

    df_table = df_filtrado.to_html(classes='data-table', index=False, escape=False)
    
    return render_template(
        "potencial_crescimento.html",
        fig_step=Markup(fig_step_html),
        fig_status=Markup(fig_status_html),
        df_table=Markup(df_table),
        plotly_cdn="https://cdn.plot.ly/plotly-latest.min.js",
        opcoes_status=opcoes_status,
        opcoes_step=opcoes_step,
        opcoes_maturidade=opcoes_maturidade,
        opcoes_crescimento=opcoes_crescimento,
        selected_status=selected_status,
        selected_step=selected_step,
        selected_maturidade=selected_maturidade,
        selected_crescimento=selected_crescimento,
        total_clientes=len(df_filtrado)
    )

# -----------------------------
# FORMULÁRIO
# -----------------------------
@app.route('/formulario', methods=['GET', 'POST'])
def formulario():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        comentario = request.form.get('comentario')
        
        # Aqui você trata os dados — salvar em banco, webhook, excel, etc.
        print("Nome:", nome)
        print("E-mail:", email)
        print("Comentário:", comentario)

        return render_template('form_success.html', nome=nome)

    return render_template('formulario.html')

# # Classificação antiga
# @app.route('/classificacao', methods=['GET', 'POST'])
# def classificacao():

#     criterios = {
#         "Faturamento": ["0 a 69mil", "70mil a 100mil", "101mil a 200mil", "201mil a 400mil", "401mil a 1mm", "1mm a 2mm", "2mm a 4mm", "5mm a 16mm", "17mm a 40mm", "Acima de 40mm"],  #9 #Peso 2
#         "Ticket Médio": ["Até R$2.000", "Entre R$2.000 e R$20.0000", "Acima de R$20.000"],#2  #Peso 2
#         "Step": ["V0", "V1", "V2", "V3", "V4"],#4  #Peso 3
#         "Empresa Familiar": ["Sim", "Não"], #1  #Peso 2
#         "Tempo de Mercado": ["Novo", "1-2 anos", "2-5 anos", "5+ anos"],#3  #Peso 1
#         "Ebitda": ["0% a 10%", "11% a 20%", "21% a 30%", "31% a 40%", "51% a 60%", "61% a 70%", "81% a 90%", "91% a 100%"], #Peso 3
#         "Aderência do Cliente ao Modelo Variável": ["Baixo", "Médio", "Alto"], #Peso 3
#         "Projeto tem CRM sendo utilizado a mais de 1 ano?": ["Não", "Sim"], #Peso 3
#         "Projeto tem inteligencia de dados de funil comercial?": ["Não", "Sim"], #Peso 3
#         "Health Score": ["Novo Cliente","Aviso Prévio","Danger", "Care","Safe"], #Peso 2
#     }

#     # Opções que zeram pontos
#     # Step: V1 Analisa, V0 Zera
#     # Ebitda: 0 a 10% zera

#     # Tela com pontos positivos e negativos explicando o feedback do cliente

# ## Analise de Crédito do Cliente
# # Analise de Credito Ruim > Paga Mal


#     if request.method == "POST":

#         # respostas = {campo: request.form.get(campo) for campo in criterios.keys()}
#         # respostas["Nome do Cliente"] = request.form.get("Nome do Cliente")

#         respostas = {
#             "Nome do Cliente": request.form.get("Nome do Cliente"),
#             **{campo: request.form.get(campo) for campo in criterios.keys()}
#         }

#         pontos = 0

#         # cálculo automático baseado no index
#         for criterio, opcoes in criterios.items():
#             resposta = request.form.get(criterio)
#             indice = opcoes.index(resposta)
#             pontos += indice

#         # classificação baseada na soma dos índices
#         if pontos >= 6:
#             resultado = "Apto"
#         elif pontos >= 3:
#             resultado = "Revisar"
#         else:
#             resultado = "Não Apto"

#         return render_template("resultado_classificacao.html",
#                                respostas=respostas,
#                                resultado=resultado,
#                                pontos=pontos)

#     return render_template("classificacao_form.html", criterios=criterios)

@app.route('/classificacao', methods=['GET', 'POST'])
def classificacao():

    criterios = {
        "Faturamento": ["0 a 69mil", "70mil a 100mil", "101mil a 200mil", "201mil a 400mil", "401mil a 1mm", "1mm a 2mm", "2mm a 4mm", "5mm a 16mm", "17mm a 40mm", "Acima de 40mm"],
        "Ticket Médio": ["Até R$2.000", "Entre R$2.000 e R$20.0000", "Acima de R$20.000"],
        "Step": ["V0", "V1", "V2", "V3", "V4"],
        "Empresa Familiar": ["Sim", "Não"],
        "Tempo de Mercado": ["Novo", "1-2 anos", "2-5 anos", "5+ anos"],
        "Ebitda": ["0% a 10%", "11% a 20%", "21% a 30%", "31% a 40%", "51% a 60%", "61% a 70%", "81% a 90%", "91% a 100%"],
        "Aderência do Cliente ao Modelo Variável": ["Baixo", "Médio", "Alto"],
        "Projeto tem CRM sendo utilizado a mais de 1 ano?": ["Não", "Sim"],
        "Projeto tem inteligencia de dados de funil comercial?": ["Não", "Sim"],
        "Health Score": ["Novo Cliente","Aviso Prévio","Danger", "Care","Safe"],
    }

    pesos = {
        "Faturamento": 2,
        "Ticket Médio": 2,
        "Step": 3,
        "Empresa Familiar": 2,
        "Tempo de Mercado": 1,
        "Ebitda": 3,
        "Aderência do Cliente ao Modelo Variável": 3,
        "Projeto tem CRM sendo utilizado a mais de 1 ano?": 3,
        "Projeto tem inteligencia de dados de funil comercial?": 3,
        "Health Score": 2,
    }

    regras_forcadas = {
        "Step": {
            "V0": "Não Apto",
            "V1": "Revisar"
        },
        "Ebitda": {
            "0% a 10%": "Não Apto",
            "11% a 20%": "Revisar"
        }
    }

    if request.method == "POST":

        respostas = {
            "Nome do Cliente": request.form.get("Nome do Cliente"),
            **{campo: request.form.get(campo) for campo in criterios.keys()}
        }

        analise_ia = rq.post(url = "https://n8n.v4lisboatech.com.br/webhook/analise/cliente-variavel", json = respostas)

        # 1 - VERIFICAR REGRAS ABSOLUTAS
        for criterio, regras in regras_forcadas.items():
            resposta = respostas.get(criterio)
            if resposta in regras:
                resultado = regras[resposta]
                respostas["resultado"] = resultado
                rq.post(url = "https://n8n.v4lisboatech.com.br/webhook/analise/registrar-forms", json = respostas)
                return render_template(
                    "resultado_classificacao.html",
                    respostas=respostas,
                    resultado=resultado,
                    pontos="Forçado por regra",
                    analise_ia=analise_ia.json()[0]  # deve ser um dict, não string
                )

        # 2 - CALCULAR PONTOS (ÍNDICE * PESO)
        # sistema de pontuação antigo
        # pontos = 0

        # for criterio, opcoes in criterios.items():
        #     resposta = respostas[criterio]
        #     indice = opcoes.index(resposta)

        #     peso = pesos.get(criterio, 1)

        #     pontos += indice * peso

        # # 3 - CLASSIFICAÇÃO POR PONTOS
        # if pontos >= 40:
        #     resultado = "Apto"
        # elif pontos >= 20:
        #     resultado = "Revisar"
        # else:
        #     resultado = "Não Apto"

        # Sistema de pontuação novo
        pontos = 0
        pontos_maximos = 0

        for criterio, opcoes in criterios.items():
            resposta = respostas[criterio]
            indice = opcoes.index(resposta)

            peso = pesos.get(criterio, 1)

            pontos += indice * peso
            pontos_maximos += (len(opcoes) - 1) * peso

        # 3 - NORMALIZAÇÃO AUTOMÁTICA
        pontuacao = (pontos / pontos_maximos) * 100

        # 4 - CLASSIFICAÇÃO AUTOMÁTICA
        if pontuacao >= 70:
            resultado = "Apto"
        elif pontuacao >= 40:
            resultado = "Revisar"
        else:
            resultado = "Não Apto"

        respostas["resultado"] = resultado
        rq.post(url = "https://n8n.v4lisboatech.com.br/webhook/analise/registrar-forms", json = respostas)

        return render_template("resultado_classificacao.html",
                                respostas=respostas,
                                resultado=resultado,
                                pontos=pontos,
                                analise_ia=analise_ia.json()[0]  # deve ser um dict, não string
                            )



    return render_template("classificacao_form.html", criterios=criterios)

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app.run("0.0.0.0", port=5001, debug=True)
