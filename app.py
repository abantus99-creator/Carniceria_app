import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# ==================== BASE DE DATOS ====================
def get_db():
    conn = sqlite3.connect("carniceria.db")
    conn.row_factory = sqlite3.Row
    return conn

def init():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            categoria TEXT,
            precio REAL,
            stock REAL,
            minimo REAL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            cantidad REAL,
            total REAL,
            fecha TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            cantidad REAL,
            precio REAL,
            fecha TEXT
        )
    """)

    # Datos de ejemplo
    if c.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        datos = [
            ("Lomo Vetado", "Vacuno", 12990, 15, 5),
            ("Asiento", "Vacuno", 8990, 20, 6),
            ("Posta Negra", "Vacuno", 7990, 18, 5),
            ("Posta Rosada", "Vacuno", 7490, 15, 5),
            ("Carne Molida", "Vacuno", 6990, 20, 6),
            ("Chuleta de Cerdo", "Cerdo", 5490, 15, 5),
            ("Costillar de Cerdo", "Cerdo", 4990, 18, 6),
            ("Lomo de Cerdo", "Cerdo", 6490, 10, 4),
            ("Longaniza", "Cerdo", 7990, 8, 3),
            ("Pollo Entero", "Pollo", 2990, 30, 10),
            ("Trutro Entero", "Pollo", 3490, 20, 6),
            ("Pechuga", "Pollo", 4990, 15, 5),
            ("Ala", "Pollo", 2490, 12, 4),
        ]
        c.executemany(
            "INSERT INTO productos (nombre, categoria, precio, stock, minimo) VALUES (?,?,?,?,?)",
            datos
        )

    conn.commit()
    conn.close()

# ==================== CONFIGURACIÓN ====================
st.set_page_config(page_title="Carnicería", page_icon="🥩", layout="wide")
init()

st.markdown("""
    <style>
    .stButton > button {
        height: 55px;
        font-size: 18px !important;
        font-weight: bold;
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🥩 Sistema de Gestión - Carnicería")

menu = st.sidebar.radio(
    "MENÚ PRINCIPAL",
    ["🏠 Inicio", "📦 Productos", "💰 Vender", "📥 Comprar", "📋 Pedidos", "📊 Análisis de Ventas"],
    label_visibility="collapsed"
)

conn = get_db()

# ---------- INICIO ----------
if menu == "🏠 Inicio":
    st.header("Panel Principal")

    total = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    bajo = conn.execute("SELECT COUNT(*) FROM productos WHERE stock <= minimo").fetchone()[0]

    col1, col2 = st.columns(2)
    col1.metric("Total de productos", total)
    col2.metric("⚠️ Stock bajo", bajo)

    st.subheader("Productos con stock bajo")
    df = pd.read_sql_query(
        "SELECT nombre, categoria, stock, minimo FROM productos WHERE stock <= minimo ORDER BY stock",
        conn
    )
    if df.empty:
        st.success("✅ No hay productos con stock bajo")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

# ---------- PRODUCTOS (ordenados por sección) ----------
elif menu == "📦 Productos":
    st.header("📦 Lista de Productos por Categoría")

    # Orden personalizado de categorías
    orden_categorias = ["Vacuno", "Cerdo", "Pollo", "Otros"]

    for cat in orden_categorias:
        df_cat = pd.read_sql_query(
            "SELECT id, nombre, precio, stock, minimo FROM productos WHERE categoria = ? ORDER BY nombre",
            conn,
            params=(cat,)
        )

        if not df_cat.empty:
            st.subheader(f"🔹 {cat}")
            st.dataframe(df_cat, use_container_width=True, hide_index=True)
            st.write("")  # espacio

    st.markdown("---")

    # --- AGREGAR PRODUCTO ---
    with st.expander("➕ AGREGAR NUEVO PRODUCTO"):
        with st.form("form_nuevo"):
            nombre = st.text_input("Nombre del producto")
            categoria = st.selectbox("Categoría", ["Vacuno", "Cerdo", "Pollo", "Otros"])
            precio = st.number_input("Precio de venta ($/kg)", min_value=0, step=100)
            stock = st.number_input("Stock actual (kg)", min_value=0.0, step=0.5)
            minimo = st.number_input("Stock mínimo (kg)", min_value=0.0, value=5.0, step=0.5)

            if st.form_submit_button("💾 GUARDAR PRODUCTO"):
                if nombre.strip():
                    conn.execute(
                        "INSERT INTO productos (nombre, categoria, precio, stock, minimo) VALUES (?,?,?,?,?)",
                        (nombre.strip(), categoria, precio, stock, minimo)
                    )
                    conn.commit()
                    st.success("✅ Producto guardado")
                    st.rerun()
                else:
                    st.error("Escribe el nombre del producto")

    st.markdown("---")

    # --- ELIMINAR PRODUCTO ---
    st.subheader("🗑️ Eliminar Producto")
    productos = conn.execute("SELECT id, nombre, categoria FROM productos ORDER BY categoria, nombre").fetchall()

    if productos:
        opciones = {f"{p['categoria']} - {p['nombre']}": p['id'] for p in productos}
        seleccionado = st.selectbox("Selecciona el producto a eliminar", list(opciones.keys()))

        if st.button("🗑️ ELIMINAR PRODUCTO", type="primary"):
            pid = opciones[seleccionado]
            conn.execute("DELETE FROM productos WHERE id = ?", (pid,))
            conn.commit()
            st.success("Producto eliminado")
            st.rerun()
    else:
        st.info("No hay productos para eliminar")

# ---------- VENDER ----------
elif menu == "💰 Vender":
    st.header("💰 Registrar Venta")

    productos = conn.execute("SELECT * FROM productos ORDER BY categoria, nombre").fetchall()

    if not productos:
        st.warning("No hay productos cargados")
    else:
        opciones = {
            f"{p['categoria']} | {p['nombre']} | Stock: {p['stock']:.1f} kg | ${p['precio']:,.0f}": p
            for p in productos
        }

        seleccion = st.selectbox("1. Elige el producto", list(opciones.keys()))
        cantidad = st.number_input("2. Cantidad (kg)", min_value=0.1, step=0.1, value=1.0)

        if st.button("✅ REGISTRAR VENTA", use_container_width=True):
            p = opciones[seleccion]
            if cantidad > p["stock"]:
                st.error(f"Stock insuficiente. Solo hay {p['stock']:.1f} kg")
            else:
                total = cantidad * p["precio"]
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                conn.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (cantidad, p["id"]))
                conn.execute(
                    "INSERT INTO ventas (producto_id, cantidad, total, fecha) VALUES (?,?,?,?)",
                    (p["id"], cantidad, total, fecha)
                )
                conn.commit()
                st.success(f"✅ Venta registrada: {cantidad:.1f} kg de {p['nombre']} por ${total:,.0f}")
                st.rerun()

# ---------- COMPRAR ----------
elif menu == "📥 Comprar":
    st.header("📥 Registrar Compra")

    productos = conn.execute("SELECT * FROM productos ORDER BY categoria, nombre").fetchall()

    if not productos:
        st.warning("No hay productos cargados")
    else:
        opciones = {f"{p['categoria']} - {p['nombre']}": p["id"] for p in productos}

        producto = st.selectbox("1. Producto", list(opciones.keys()))
        cantidad = st.number_input("2. Cantidad (kg)", min_value=0.1, step=0.5, value=5.0)
        precio = st.number_input("3. Precio de compra ($/kg)", min_value=0, step=100)

        if st.button("✅ REGISTRAR COMPRA", use_container_width=True):
            pid = opciones[producto]
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("UPDATE productos SET stock = stock + ? WHERE id = ?", (cantidad, pid))
            conn.execute(
                "INSERT INTO compras (producto_id, cantidad, precio, fecha) VALUES (?,?,?,?)",
                (pid, cantidad, precio, fecha)
            )
            conn.commit()
            st.success(f"✅ Compra registrada: +{cantidad:.1f} kg")
            st.rerun()

# ---------- PEDIDOS ----------
elif menu == "📋 Pedidos":
    st.header("📋 Pedidos Sugeridos")

    df = pd.read_sql_query("""
        SELECT 
            categoria as Categoría,
            nombre as Producto,
            stock as "Stock actual",
            minimo as "Stock mínimo",
            ROUND((minimo * 2 - stock), 1) as "Sugerido (kg)"
        FROM productos 
        WHERE stock <= minimo
        ORDER BY categoria, stock
    """, conn)

    if df.empty:
        st.success("✅ No hay productos que necesiten reposición")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.write(f"**Total de productos a pedir:** {len(df)}")

# ---------- ANÁLISIS DE VENTAS ----------
elif menu == "📊 Análisis de Ventas":
    st.header("📊 Análisis de Ventas")

    # Resumen general
    total_ventas = conn.execute("SELECT COALESCE(SUM(total), 0) FROM ventas").fetchone()[0]
    total_kilos = conn.execute("SELECT COALESCE(SUM(cantidad), 0) FROM ventas").fetchone()[0]
    num_ventas = conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Total vendido", f"${total_ventas:,.0f}")
    col2.metric("⚖️ Kilos vendidos", f"{total_kilos:.1f} kg")
    col3.metric("🧾 Número de ventas", num_ventas)

    st.markdown("---")

    # Productos más vendidos
    st.subheader("🏆 Productos más vendidos")
    df_top = pd.read_sql_query("""
        SELECT 
            p.nombre as Producto,
            p.categoria as Categoría,
            ROUND(SUM(v.cantidad), 1) as "Kilos vendidos",
            ROUND(SUM(v.total), 0) as "Total $"
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
        GROUP BY v.producto_id
        ORDER BY SUM(v.cantidad) DESC
        LIMIT 10
    """, conn)

    if df_top.empty:
        st.info("Todavía no hay ventas registradas")
    else:
        st.dataframe(df_top, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Ventas por categoría
    st.subheader("📦 Ventas por categoría")
    df_cat = pd.read_sql_query("""
        SELECT 
            p.categoria as Categoría,
            ROUND(SUM(v.cantidad), 1) as "Kilos",
            ROUND(SUM(v.total), 0) as "Total $"
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
        GROUP BY p.categoria
        ORDER BY SUM(v.total) DESC
    """, conn)

    if not df_cat.empty:
        st.dataframe(df_cat, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Últimas ventas
    st.subheader("🕒 Últimas ventas")
    df_ultimas = pd.read_sql_query("""
        SELECT 
            v.fecha as Fecha,
            p.nombre as Producto,
            p.categoria as Categoría,
            v.cantidad as Kg,
            v.total as Total
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
        ORDER BY v.fecha DESC
        LIMIT 15
    """, conn)

    if not df_ultimas.empty:
        st.dataframe(df_ultimas, use_container_width=True, hide_index=True)

conn.close()
