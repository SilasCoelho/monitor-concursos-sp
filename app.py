import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

st.set_page_config(page_title="Monitor Docente - Admin SP", page_icon="🎓", layout="wide")
st.title("🎓 Monitor de Processos Seletivos - Docentes de Administração (SP)")
st.caption("Dados atualizados automaticamente. Fonte: concursos.db")

@st.cache_data(ttl=300)
def load_data():
    try:
        conn = sqlite3.connect('concursos.db')
        df = pd.read_sql_query("SELECT * FROM concursos", conn)
        conn.close()
        # Converte datas
        df['data_limite'] = pd.to_datetime(df['data_limite_inscricao'], errors='coerce')
        df['dias_restantes'] = (df['data_limite'] - datetime.now()).dt.days
        return df.sort_values('dias_restantes')
    except Exception as e:
        st.error("Erro ao carregar: " + str(e))
        return pd.DataFrame()

df = load_data()

if df.empty:
    st.info("⏳ Nenhum edital capturado ainda. Execute pipeline.py primeiro.")
    st.stop()

# --- FILTROS COM KEYS ÚNICAS (Obrigatório para Streamlit) ---
st.sidebar.header("🔍 Filtros")

fontes = ["Todas"] + list(df['fonte'].dropna().unique())
fonte_sel = st.sidebar.selectbox("Fonte", fontes, key="sel_fonte_01")

areas = ["Todas"] + list(df['area_conhecimento'].dropna().unique())
area_sel = st.sidebar.selectbox("Área", areas, key="sel_area_02")

tipos = ["Todos"] + list(df['tipo_edital'].dropna().unique())
tipo_sel = st.sidebar.selectbox("Tipo", tipos, key="sel_tipo_03")

# Aplica filtros
df_view = df.copy()
if fonte_sel != "Todas":
    df_view = df_view[df_view['fonte'] == fonte_sel]
if area_sel != "Todas":
    df_view = df_view[df_view['area_conhecimento'] == area_sel]
if tipo_sel != "Todos":
    df_view = df_view[df_view['tipo_edital'] == tipo_sel]

# --- ALERTA 48 HORAS ---
urgentes = df_view[df_view['dias_restantes'] <= 2]
if not urgentes.empty:
    st.error("🚨 ATENÇÃO: Inscrições encerrando em até 48h!")
    for _, r in urgentes.iterrows():
        data_fmt = r['data_limite'].strftime('%d/%m/%Y') if pd.notna(r['data_limite']) else "A definir"
        st.warning(f"📌 **{r['fonte']}** - {r['area_conhecimento']} | Encerra: {data_fmt} | [Link]({r['url_edital']})")

# --- TABELA PRINCIPAL ---
st.subheader("📋 Lista de Editais")

# Formata data para exibição
df_show = df_view.copy()
df_show['data_limite_inscricao'] = df_show['data_limite'].dt.strftime('%d/%m/%Y')

cols = ['fonte', 'campus', 'area_conhecimento', 'tipo_edital', 'data_limite_inscricao', 'url_edital', 'dias_restantes']

# Função de destaque para urgência
def highlight_urgency(val):
    try:
        if float(val) <= 2:
            return 'background-color: #ffe6e6; font-weight: bold'
    except:
        pass
    return ''

st.dataframe(
    df_show[cols].style.map(highlight_urgency, subset=['dias_restantes']),
    use_container_width=True,
    height=400
)

st.markdown("---")
st.caption("💡 Clique no link da coluna `url_edital` para abrir o edital original.")