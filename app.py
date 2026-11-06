import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

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

    # Datos de ejemplo (solo la primera vez)
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

# ==================== INTERFAZ ====================
st.set_page_config(page_title="Carnicería", page_icon="🥩", layout="wide")
init()

st.title("🥩 Sistema de Gestión - Carnicería")

menu = st.sidebar.radio("Menú", ["Inicio", "Productos", "Vender", "Comprar", "Pedidos"])

conn = get_db()

# ---------- INICIO ----------
if menu == "Inicio":
    st.header("Panel Principal")

    total = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    bajo = conn.execute("SELECT COUNT(*) FROM productos WHERE stock <= minimo").fetchone()[0]

    col1, col2 = st.columns(2)
    col1.metric("Total de productos", total)
    col2.metric("⚠️ Productos con stock bajo", bajo)

    st.subheader("Productos con stock bajo")
    df = pd.read_sql_query(
        "SELECT nombre, categoria, stock, minimo FROM productos WHERE stock <= minimo ORDER BY stock",
        conn
    )
    if df.empty:
        st.success("No hay productos con stock bajo")
    else:
        st.dataframe(df, use_container_width=True)

# ---------- PRODUCTOS ----------
elif menu == "Productos":
    st.header("📦 Productos")

    df = pd.read_sql_query("SELECT * FROM productos ORDER BY categoria, nombre", conn)
    st.dataframe(df, use_container_width=True)

    with st.expander("➕ Agregar nuevo producto"):
        with st.form("form_nuevo"):
            nombre = st.text_input("Nombre del producto")
            categoria = st.selectbox("Categoría", ["Vacuno", "Cerdo", "Pollo", "Otros"])
            precio = st.number_input("Precio de venta ($/kg)", min_value=0, step=100)
            stock = st.number_input("Stock actual (kg)", min_value=0.0, step=0.5)
            minimo = st.number_input("Stock mínimo (kg)", min_value=0.0, value=5.0, step=0.5)

            if st.form_submit_button("Guardar producto"):
                if nombre.strip():
                    conn.execute(
                        "INSERT INTO productos (nombre, categoria, precio, stock, minimo) VALUES (?,?,?,?,?)",
                        (nombre.strip(), categoria, precio, stock, minimo)
                    )
                    conn.commit()
                    st.success("Producto guardado correctamente")
                    st.rerun()
                else:
                    st.error("El nombre es obligatorio")

# ---------- VENDER ----------
elif menu == "Vender":
    st.header("💰 Registrar Venta")

    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    opciones = {
        f"{p['nombre']} | Stock: {p['stock']:.1f} kg | ${p['precio']:,.0f}/kg": p
        for p in productos
    }

    seleccion = st.selectbox("Selecciona el producto", list(opciones.keys()))
    cantidad = st.number_input("Cantidad (kg)", min_value=0.1, step=0.1, value=1.0)

    if st.button("Registrar Venta", type="primary"):
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
            st.success(f"Venta registrada: {cantidad:.1f} kg de {p['nombre']} por ${total:,.0f}")
            st.rerun()

# ---------- COMPRAR ----------
elif menu == "Comprar":
    st.header("📥 Registrar Compra / Entrada de Stock")

    productos = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    opciones = {p["nombre"]: p["id"] for p in productos}

    producto = st.selectbox("Producto", list(opciones.keys()))
    cantidad = st.number_input("Cantidad comprada (kg)", min_value=0.1, step=0.5)
    precio = st.number_input("Precio de compra ($/kg)", min_value=0, step=100)

    if st.button("Registrar Compra", type="primary"):
        pid = opciones[producto]
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

        conn.execute("UPDATE productos SET stock = stock + ? WHERE id = ?", (cantidad, pid))
        conn.execute(
            "INSERT INTO compras (producto_id, cantidad, precio, fecha) VALUES (?,?,?,?)",
            (pid, cantidad, precio, fecha)
        )
        conn.commit()
        st.success(f"Compra registrada: +{cantidad:.1f} kg de {producto}")
        st.rerun()

# ---------- PEDIDOS ----------
elif menu == "Pedidos":
    st.header("📋 Pedidos Sugeridos")

    st.write("Productos que están en o bajo el stock mínimo:")

    df = pd.read_sql_query("""
        SELECT 
            nombre,
            categoria,
            stock,
            minimo,
            ROUND((minimo * 2 - stock), 1) as sugerido_kg
        FROM productos 
        WHERE stock <= minimo
        ORDER BY stock ASC
    """, conn)

    if df.empty:
        st.success("✅ No hay productos que necesiten reposición")
    else:
        st.dataframe(df, use_container_width=True)
        st.write(f"**Total de productos a pedir:** {len(df)}")

conn.close()
