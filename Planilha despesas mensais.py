import json
import pandas as pd
import streamlit as st
from groq import Groq

st.set_page_config(page_title="Planilha Financeira", page_icon="💰", layout="wide")

MODELO_GROQ = "llama-3.3-70b-versatile"

NOMES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

MESES = [("2026-12", "Dezembro 2026")] + [
    (f"2027-{i+1:02d}", f"{NOMES[i]} 2027") for i in range(12)
]


def brl(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def dados_vazios(nome=""):
    return {"nome": nome,
            "meses": {k: {"salario": 0.0, "despesas": []} for k, _ in MESES}}


def normalizar(d):
    """Garante que o JSON carregado tenha todos os meses."""
    base = dados_vazios(d.get("nome", ""))
    for k, _ in MESES:
        m = d.get("meses", {}).get(k)
        if m:
            base["meses"][k] = {
                "salario": float(m.get("salario", 0) or 0),
                "despesas": [
                    {"Despesa": str(x.get("Despesa", "")),
                     "Valor": float(x.get("Valor", 0) or 0)}
                    for x in m.get("despesas", [])
                ],
            }
    return base


def calcular(dados):
    """Calcula saldo anterior, salário, despesas e sobra (que vira saldo do mês seguinte)."""
    linhas, anterior = [], 0.0
    for k, nome in MESES:
        m = dados["meses"][k]
        total_desp = sum(x["Valor"] for x in m["despesas"])
        sobra = anterior + m["salario"] - total_desp
        linhas.append({"Mês": nome, "Veio do mês anterior": anterior,
                       "Salário": m["salario"], "Despesas": total_desp,
                       "Sobra": sobra})
        anterior = sobra
    return pd.DataFrame(linhas)


# ---------- Login ----------
if "logado" not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    st.title("💰 Planilha Financeira")
    nome = st.text_input("Seu nome")
    chave = st.text_input("Chave Groq (gsk_...)", type="password")
    if st.button("Entrar", type="primary"):
        if not nome.strip() or not chave.strip():
            st.error("Informe seu nome e a chave Groq.")
        else:
            try:
                Groq(api_key=chave.strip()).models.list()  # valida a chave
                st.session_state.logado = True
                st.session_state.groq_key = chave.strip()
                st.session_state.dados = dados_vazios(nome.strip())
                st.rerun()
            except Exception:
                st.error("Chave Groq inválida.")
    st.stop()

dados = st.session_state.dados

# ---------- Barra lateral: salvar / carregar ----------
with st.sidebar:
    st.subheader(f"👤 {dados['nome']}")
    st.download_button(
        "💾 Salvar (JSON)",
        data=json.dumps(dados, ensure_ascii=False, indent=2),
        file_name=f"financeiro_{dados['nome']}.json",
        mime="application/json",
    )
    up = st.file_uploader("📂 Continuar de um JSON salvo", type="json")
    if up is not None:
        id_up = f"{up.name}-{up.size}"
        if st.session_state.get("ultimo_upload") != id_up:
            try:
                novo = normalizar(json.load(up))
                if not novo["nome"]:
                    novo["nome"] = dados["nome"]
                st.session_state.dados = novo
                st.session_state.ultimo_upload = id_up
                for k, _ in MESES:  # limpa estado dos editores
                    st.session_state.pop(f"ed_{k}", None)
                    st.session_state.pop(f"sal_{k}", None)
                st.rerun()
            except Exception:
                st.error("Arquivo JSON inválido.")
    if st.button("Sair"):
        st.session_state.clear()
        st.rerun()

# ---------- Tela principal ----------
st.title("💰 Planilha Financeira — Dez/2026 a Dez/2027")

resumo = calcular(dados)
idx = st.selectbox("Mês", range(len(MESES)), format_func=lambda i: MESES[i][1])
chave_mes, nome_mes = MESES[idx]
mes = dados["meses"][chave_mes]
anterior = resumo.loc[idx, "Veio do mês anterior"]

c1, c2 = st.columns(2)
with c1:
    mes["salario"] = st.number_input(
        f"Salário de {nome_mes}", min_value=0.0, step=100.0,
        value=float(mes["salario"]), format="%.2f", key=f"sal_{chave_mes}")
with c2:
    st.metric("Veio do mês anterior", brl(anterior))

st.markdown("**Despesas** (clique na última linha para adicionar; selecione e apague para remover)")
df = pd.DataFrame(mes["despesas"], columns=["Despesa", "Valor"])
df["Despesa"] = df["Despesa"].astype(str)
df["Valor"] = df["Valor"].astype(float)

editado = st.data_editor(
    df, num_rows="dynamic", use_container_width=True, key=f"ed_{chave_mes}",
    column_config={
        "Despesa": st.column_config.TextColumn("Despesa"),
        "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f",
                                               min_value=0.0, step=10.0),
    },
)
mes["despesas"] = [
    {"Despesa": str(r["Despesa"] if pd.notna(r["Despesa"]) else ""),
     "Valor": float(r["Valor"]) if pd.notna(r["Valor"]) else 0.0}
    for _, r in editado.iterrows()
    if (pd.notna(r["Despesa"]) and str(r["Despesa"]).strip()) or
       (pd.notna(r["Valor"]) and r["Valor"] != 0)
]

# recalcula com os valores atualizados
resumo = calcular(dados)
linha = resumo.loc[idx]
m1, m2, m3 = st.columns(3)
m1.metric("Total de despesas", brl(linha["Despesas"]))
m2.metric("Sobra do mês (vai para o próximo)", brl(linha["Sobra"]))
m3.metric("Disponível (anterior + salário)", brl(linha["Veio do mês anterior"] + linha["Salário"]))

# ---------- Planilha geral ----------
st.divider()
st.subheader("📊 Planilha geral")
tabela = resumo.copy()
st.dataframe(
    tabela.style.format({c: brl for c in tabela.columns if c != "Mês"})
    .map(lambda v: "color: red" if isinstance(v, float) and v < 0 else "", subset=["Sobra"]),
    use_container_width=True, hide_index=True,
)

# ---------- Análise com IA (Groq) ----------
st.divider()
st.subheader("🤖 Análise com IA")
if st.button("Analisar minhas finanças"):
    try:
        cliente = Groq(api_key=st.session_state.groq_key)
        resposta = cliente.chat.completions.create(
            model=MODELO_GROQ,
            messages=[
                {"role": "system",
                 "content": "Você é um consultor financeiro pessoal. Responda em português do Brasil, de forma curta e prática."},
                {"role": "user",
                 "content": "Analise minha planilha mensal (valores em R$) e dê 3 a 5 dicas:\n"
                            + resumo.to_string(index=False)
                            + "\n\nDespesas por mês:\n"
                            + json.dumps({MESES[i][1]: dados["meses"][k]["despesas"]
                                          for i, (k, _) in enumerate(MESES)},
                                         ensure_ascii=False)},
            ],
        )
        st.write(resposta.choices[0].message.content)
    except Exception as e:
        st.error(f"Erro ao consultar a Groq: {e}")
