import streamlit as st
import pandas as pd
from databricks import sql as dbsql
from databricks.sdk import WorkspaceClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TABLE = "cufdwcatalog.db_analytic_dsi.campanhas"
PAGE_SIZE = 50

# Column definitions (DB name -> display label)
COLUMNS = [
    "Dia de envio",
    "Formato",
    "Produto",
    "Unidade",
    "Tema / Campanha Associada",
    "Conteúdo",
    "CTA (link)",
    "Resonsável equipa digital",
    "Resonsável equipa marca",
    "Responsável equipa intelligence",
]

LABELS = {
    "Dia de envio": "Dia de Envio",
    "Formato": "Formato",
    "Produto": "Produto",
    "Unidade": "Unidade",
    "Tema / Campanha Associada": "Tema / Campanha",
    "Conteúdo": "Conteúdo",
    "CTA (link)": "CTA (link)",
    "Resonsável equipa digital": "Resp. Equipa Digital",
    "Resonsável equipa marca": "Resp. Equipa Marca",
    "Responsável equipa intelligence": "Resp. Equipa Intelligence",
}


def bq(col: str) -> str:
    """Backtick-quote a column name for SQL."""
    return f"`{col}`"


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@st.cache_resource
def get_connection():
    w = WorkspaceClient()
    return dbsql.connect(
        server_hostname=w.config.host.replace("https://", ""),
        http_path="/sql/1.0/warehouses/" + _get_warehouse_id(w),
        credentials_provider=lambda: w.config.authenticate,
    )


def _get_warehouse_id(w: WorkspaceClient) -> str:
    warehouses = list(w.warehouses.list())
    for wh in warehouses:
        if wh.state and wh.state.value == "RUNNING":
            return wh.id
    if warehouses:
        return warehouses[0].id
    raise RuntimeError("Nenhum SQL Warehouse disponível.")


def run_query(query: str) -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(query)
        if cur.description:
            cols = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)
    return pd.DataFrame()


def run_update(query: str):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(query)


def esc(val: str | None) -> str:
    """Escape a string value for inline SQL."""
    if val is None or val == "":
        return "NULL"
    return "'" + val.replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_data(search: str = "", page: int = 0) -> pd.DataFrame:
    where = ""
    if search:
        clauses = " OR ".join(
            [f"UPPER(CAST({bq(c)} AS STRING)) LIKE UPPER('%{search}%')" for c in COLUMNS]
        )
        where = f"WHERE {clauses}"
    return run_query(
        f"SELECT *, monotonically_increasing_id() AS _row_id "
        f"FROM {TABLE} {where} "
        f"ORDER BY `Dia de envio` DESC "
        f"LIMIT {PAGE_SIZE} OFFSET {page * PAGE_SIZE}"
    )


def count_rows(search: str = "") -> int:
    where = ""
    if search:
        clauses = " OR ".join(
            [f"UPPER(CAST({bq(c)} AS STRING)) LIKE UPPER('%{search}%')" for c in COLUMNS]
        )
        where = f"WHERE {clauses}"
    df = run_query(f"SELECT COUNT(*) AS cnt FROM {TABLE} {where}")
    return int(df["cnt"].iloc[0]) if len(df) > 0 else 0


def build_where_clause(record: dict) -> str:
    """Build a WHERE clause that matches a specific row by all column values."""
    parts = []
    for c in COLUMNS:
        val = record.get(c)
        if val is None or (isinstance(val, str) and val.strip() == "") or (isinstance(val, float) and pd.isna(val)):
            parts.append(f"{bq(c)} IS NULL")
        else:
            parts.append(f"{bq(c)} = {esc(str(val))}")
    return " AND ".join(parts)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Gestão de Campanhas", page_icon="📣", layout="wide")
st.title("📣 Gestão de Campanhas de Marketing")
st.caption(f"Tabela: `{TABLE}`")

# ---------- Sidebar: Novo Registo ----------
with st.sidebar:
    st.header("➕ Nova Campanha")
    with st.form("add_form", clear_on_submit=True):
        new = {}
        new["Dia de envio"] = st.text_input(LABELS["Dia de envio"], placeholder="dd/mm/aaaa")
        new["Formato"] = st.text_input(LABELS["Formato"], placeholder="e.g. Email, SMS, Push")
        new["Produto"] = st.text_input(LABELS["Produto"])
        new["Unidade"] = st.text_input(LABELS["Unidade"])
        new["Tema / Campanha Associada"] = st.text_input(LABELS["Tema / Campanha Associada"])
        new["Conteúdo"] = st.text_area(LABELS["Conteúdo"], height=80)
        new["CTA (link)"] = st.text_input(LABELS["CTA (link)"], placeholder="https://...")
        new["Resonsável equipa digital"] = st.text_input(LABELS["Resonsável equipa digital"])
        new["Resonsável equipa marca"] = st.text_input(LABELS["Resonsável equipa marca"])
        new["Responsável equipa intelligence"] = st.text_input(LABELS["Responsável equipa intelligence"])

        if st.form_submit_button("Inserir Campanha", use_container_width=True):
            cols_sql = ", ".join([bq(c) for c in COLUMNS])
            vals_sql = ", ".join([esc(new[c]) for c in COLUMNS])
            try:
                run_update(f"INSERT INTO {TABLE} ({cols_sql}) VALUES ({vals_sql})")
                st.success("✅ Campanha inserida com sucesso!")
            except Exception as e:
                st.error(f"Erro ao inserir: {e}")

# ---------- Tabs ----------
tab_list, tab_edit, tab_delete = st.tabs(["📋 Listagem", "✏️ Editar", "🗑️ Eliminar"])

# ---- TAB: Listagem ----
with tab_list:
    col_search, col_refresh = st.columns([4, 1])
    with col_search:
        search = st.text_input(
            "🔍 Pesquisar",
            placeholder="Pesquise por produto, tema, formato, responsável...",
            key="search",
        )
    with col_refresh:
        st.write("")
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    total = count_rows(search)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if "page" not in st.session_state:
        st.session_state.page = 0

    df = load_data(search, st.session_state.page)

    st.markdown(f"**{total}** registos — Página **{st.session_state.page + 1}** de **{total_pages}**")

    if not df.empty:
        display_df = df.drop(columns=["_row_id"], errors="ignore").copy()
        display_df.columns = [LABELS.get(c, c) for c in display_df.columns]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("⬅️ Anterior", disabled=st.session_state.page == 0, use_container_width=True):
            st.session_state.page -= 1
            st.rerun()
    with col_next:
        if st.button("Seguinte ➡️", disabled=st.session_state.page >= total_pages - 1, use_container_width=True):
            st.session_state.page += 1
            st.rerun()

# ---- TAB: Editar ----
with tab_edit:
    st.markdown("Pesquise a campanha para editar. Selecione o registo da lista abaixo.")
    edit_search = st.text_input("🔍 Pesquisar campanha", key="edit_search", placeholder="Produto, tema, formato...")

    if edit_search:
        results = load_data(edit_search, 0)
        if results.empty:
            st.warning("Nenhum registo encontrado.")
        else:
            display = results.drop(columns=["_row_id"], errors="ignore")
            display.columns = [LABELS.get(c, c) for c in display.columns]
            st.dataframe(display, use_container_width=True, hide_index=True)

            row_idx = st.number_input(
                "Selecione o nº da linha (0 = primeira)",
                min_value=0,
                max_value=len(results) - 1,
                value=0,
                step=1,
                key="edit_row_idx",
            )

            record = results.iloc[row_idx]
            where_clause = build_where_clause(record)

            with st.form("edit_form"):
                ed = {}
                for c in COLUMNS:
                    current_val = str(record.get(c, "") or "")
                    if c == "Conteúdo":
                        ed[c] = st.text_area(LABELS[c], value=current_val, height=80)
                    else:
                        ed[c] = st.text_input(LABELS[c], value=current_val)

                if st.form_submit_button("💾 Guardar Alterações", use_container_width=True):
                    set_parts = ", ".join([f"{bq(c)} = {esc(ed[c])}" for c in COLUMNS])
                    try:
                        run_update(f"UPDATE {TABLE} SET {set_parts} WHERE {where_clause} LIMIT 1")
                        st.success("✅ Campanha atualizada com sucesso!")
                    except Exception as e:
                        st.error(f"Erro ao atualizar: {e}")

# ---- TAB: Eliminar ----
with tab_delete:
    st.markdown("Pesquise a campanha para eliminar.")
    del_search = st.text_input("🔍 Pesquisar campanha", key="del_search", placeholder="Produto, tema, formato...")

    if del_search:
        results = load_data(del_search, 0)
        if results.empty:
            st.warning("Nenhum registo encontrado.")
        else:
            display = results.drop(columns=["_row_id"], errors="ignore")
            display.columns = [LABELS.get(c, c) for c in display.columns]
            st.dataframe(display, use_container_width=True, hide_index=True)

            row_idx = st.number_input(
                "Selecione o nº da linha (0 = primeira)",
                min_value=0,
                max_value=len(results) - 1,
                value=0,
                step=1,
                key="del_row_idx",
            )

            record = results.iloc[row_idx]
            where_clause = build_where_clause(record)

            st.markdown("**Registo selecionado:**")
            sel_display = pd.DataFrame([record[COLUMNS]])
            sel_display.columns = [LABELS.get(c, c) for c in sel_display.columns]
            st.dataframe(sel_display, use_container_width=True, hide_index=True)

            st.warning("⚠️ Esta ação é irreversível!")
            if st.button("🗑️ Confirmar Eliminação", type="primary"):
                try:
                    run_update(f"DELETE FROM {TABLE} WHERE {where_clause} LIMIT 1")
                    st.success("✅ Campanha eliminada com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao eliminar: {e}")
