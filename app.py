import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO

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

def generar_qr(texto):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# ==================== APP ====================
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
    [
        "🏠 Inicio",
        "📦 Productos",
        "💰 Vender",
        "📥 Comprar",
        "📋 Pedidos y Predicción",
        "📊 Análisis Completo",
        "📱 Generar QR"
    ],
    label_visibility="collapsed"
)

conn = get_db()

# ---------- INICIO ----------
if menu == "🏠 Inicio":
    st.header("Panel Principal")

    total = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    bajo = conn.execute("SELECT COUNT(*) FROM productos WHERE stock <= minimo").fetchone()[0]
    ventas_hoy = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM ventas WHERE date(fecha) = date('now')"
    ).fetchone()[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total productos", total)
    col2.metric("⚠️ Stock bajo", bajo)
    col3.metric("Ventas de hoy", f"${ventas_hoy:,.0f}")

    st.subheader("Productos con stock bajo")
    df = pd.read_sql_query(
        "SELECT nombre, categoria, stock, minimo FROM productos WHERE stock <= minimo ORDER BY stock",
        conn
    )
    if df.empty:
        st.success("✅ No hay productos con stock bajo")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

# ---------- PRODUCTOS ----------
elif menu == "📦 Productos":
    st.header("📦 Productos por Categoría")

    for cat in ["Vacuno", "Cerdo", "Pollo", "Otros"]:
        df_cat = pd.read_sql_query(
            "SELECT id, nombre, precio, stock, minimo FROM productos WHERE categoria = ? ORDER BY nombre",
            conn, params=(cat,)
        )
        if not df_cat.empty:
            st.subheader(f"🔹 {cat}")
            st.dataframe(df_cat, use_container_width=True, hide_index=True)

    st.markdown("---")

    with st.expander("➕ AGREGAR PRODUCTO"):
        with st.form("nuevo"):
            nombre = st.text_input("Nombre")
            categoria = st.selectbox("Categoría", ["Vacuno", "Cerdo", "Pollo", "Otros"])
            precio = st.number_input("Precio $/kg", min_value=0, step=100)
            stock = st.number_input("Stock actual (kg)", min_value=0.0, step=0.5)
            minimo = st.number_input("Stock mínimo", min_value=0.0, value=5.0, step=0.5)
            if st.form_submit_button("💾 GUARDAR"):
                if nombre.strip():
                    conn.execute(
                        "INSERT INTO productos (nombre, categoria, precio, stock, minimo) VALUES (?,?,?,?,?)",
                        (nombre.strip(), categoria, precio, stock, minimo)
                    )
                    conn.commit()
                    st.success("Producto guardado")
                    st.rerun()

    st.markdown("---")
    st.subheader("🗑️ Eliminar Producto")
    productos = conn.execute("SELECT id, nombre, categoria FROM productos ORDER BY categoria, nombre").fetchall()
    if productos:
        opciones = {f"{p['categoria']} - {p['nombre']}": p['id'] for p in productos}
        sel = st.selectbox("Producto a eliminar", list(opciones.keys()))
        if st.button("🗑️ ELIMINAR", type="primary"):
            conn.execute("DELETE FROM productos WHERE id = ?", (opciones[sel],))
            conn.commit()
            st.success("Eliminado")
            st.rerun()

# ---------- VENDER ----------
elif menu == "💰 Vender":
    st.header("💰 Registrar Venta (varios productos)")

    if "carrito" not in st.session_state:
        st.session_state.carrito = []

    productos = conn.execute("SELECT * FROM productos ORDER BY categoria, nombre").fetchall()

    if not productos:
        st.warning("No hay productos cargados")
    else:
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Agregar productos al carrito")

            opciones = {
                f"{p['categoria']} | {p['nombre']} | Stock: {p['stock']:.1f} kg | ${p['precio']:,.0f}": p
                for p in productos
            }

            seleccion = st.selectbox("Producto", list(opciones.keys()), key="venta_prod")
            cantidad = st.number_input("Cantidad (kg)", min_value=0.1, step=0.1, value=1.0, key="venta_cant")

            if st.button("➕ AGREGAR AL CARRITO", use_container_width=True):
                p = opciones[seleccion]

                if cantidad > p["stock"]:
                    st.error(f"Stock insuficiente. Solo hay {p['stock']:.1f} kg")
                else:
                    encontrado = False
                    for item in st.session_state.carrito:
                        if item["id"] == p["id"]:
                            item["cantidad"] += cantidad
                            item["subtotal"] = item["cantidad"] * item["precio"]
                            encontrado = True
                            break

                    if not encontrado:
                        st.session_state.carrito.append({
                            "id": p["id"],
                            "nombre": p["nombre"],
                            "categoria": p["categoria"],
                            "precio": p["precio"],
                            "cantidad": cantidad,
                            "subtotal": cantidad * p["precio"]
                        })
                    st.success(f"Agregado: {cantidad:.1f} kg de {p['nombre']}")
                    st.rerun()

        with col2:
            st.subheader("🛒 Carrito de Venta")

            if not st.session_state.carrito:
                st.info("El carrito está vacío")
            else:
                total_venta = 0
                for i, item in enumerate(st.session_state.carrito):
                    st.markdown(f"**{item['nombre']}**")
                    st.write(f"{item['cantidad']:.2f} kg × ${item['precio']:,.0f} = **${item['subtotal']:,.0f}**")
                    
                    if st.button("❌ Quitar", key=f"quitar_venta_{i}"):
                        st.session_state.carrito.pop(i)
                        st.rerun()
                    st.markdown("---")
                    total_venta += item["subtotal"]

                st.markdown(f"### TOTAL: ${total_venta:,.0f}")

                if st.button("✅ FINALIZAR VENTA", use_container_width=True, type="primary"):
                    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                    for item in st.session_state.carrito:
                        conn.execute(
                            "UPDATE productos SET stock = stock - ? WHERE id = ?",
                            (item["cantidad"], item["id"])
                        )
                        conn.execute(
                            "INSERT INTO ventas (producto_id, cantidad, total, fecha) VALUES (?,?,?,?)",
                            (item["id"], item["cantidad"], item["subtotal"], fecha)
                        )
                    conn.commit()
                    st.session_state.carrito = []
                    st.success(f"✅ Venta registrada por ${total_venta:,.0f}")
                    st.rerun()

                if st.button("🗑️ Vaciar carrito", use_container_width=True):
                    st.session_state.carrito = []
                    st.rerun()

# ---------- COMPRAR ----------
elif menu == "📥 Comprar":
    st.header("📥 Registrar Compra de Mercadería (varios productos)")

    if "carrito_compra" not in st.session_state:
        st.session_state.carrito_compra = []

    productos = conn.execute("SELECT * FROM productos ORDER BY categoria, nombre").fetchall()

    if not productos:
        st.warning("No hay productos registrados")
    else:
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Agregar productos a la compra")

            opciones = {
                f"{p['categoria']} | {p['nombre']} | Stock actual: {p['stock']:.1f} kg": p
                for p in productos
            }

            seleccion = st.selectbox("1. Selecciona el producto", list(opciones.keys()), key="compra_prod")
            cantidad = st.number_input("2. Cantidad que entra (kg)", min_value=0.1, step=0.5, value=5.0, key="compra_cant")
            precio = st.number_input("3. Precio de compra ($/kg)", min_value=0, step=100, value=0, key="compra_precio")

            if st.button("➕ AGREGAR AL CARRITO DE COMPRA", use_container_width=True):
                p = opciones[seleccion]

                encontrado = False
                for item in st.session_state.carrito_compra:
                    if item["id"] == p["id"]:
                        item["cantidad"] += cantidad
                        item["precio"] = precio
                        item["subtotal"] = item["cantidad"] * precio
                        encontrado = True
                        break

                if not encontrado:
                    st.session_state.carrito_compra.append({
                        "id": p["id"],
                        "nombre": p["nombre"],
                        "categoria": p["categoria"],
                        "cantidad": cantidad,
                        "precio": precio,
                        "subtotal": cantidad * precio
                    })

                st.success(f"Agregado: {cantidad:.1f} kg de {p['nombre']}")
                st.rerun()

        with col2:
            st.subheader("🛒 Carrito de Compra")

            if not st.session_state.carrito_compra:
                st.info("El carrito está vacío")
            else:
                total_compra = 0

                for i, item in enumerate(st.session_state.carrito_compra):
                    st.markdown(f"**{item['nombre']}**")
                    st.write(f"{item['cantidad']:.2f} kg × ${item['precio']:,.0f} = **${item['subtotal']:,.0f}**")

                    if st.button("❌ Quitar", key=f"quitar_compra_{i}"):
                        st.session_state.carrito_compra.pop(i)
                        st.rerun()

                    st.markdown("---")
                    total_compra += item["subtotal"]

                st.markdown(f"### TOTAL COMPRA: ${total_compra:,.0f}")

                if st.button("✅ FINALIZAR COMPRA", use_container_width=True, type="primary"):
                    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

                    for item in st.session_state.carrito_compra:
                        conn.execute(
                            "UPDATE productos SET stock = stock + ? WHERE id = ?",
                            (item["cantidad"], item["id"])
                        )
                        conn.execute(
                            "INSERT INTO compras (producto_id, cantidad, precio, fecha) VALUES (?,?,?,?)",
                            (item["id"], item["cantidad"], item["precio"], fecha)
                        )

                    conn.commit()
                    st.session_state.carrito_compra = []
                    st.success(f"✅ Compra registrada por ${total_compra:,.0f}")
                    st.rerun()

                if st.button("🗑️ Vaciar carrito", use_container_width=True):
                    st.session_state.carrito_compra = []
                    st.rerun()

# ---------- PEDIDOS Y PREDICCIÓN ----------
elif menu == "📋 Pedidos y Predicción":
    st.header("📋 Pedidos Sugeridos + Predicción (3 meses)")

    df_ventas = pd.read_sql_query("""
        SELECT p.id, p.nombre, p.categoria, p.stock, p.minimo,
               COALESCE(SUM(v.cantidad), 0) as vendido_90d
        FROM productos p
        LEFT JOIN ventas v ON p.id = v.producto_id 
            AND v.fecha >= date('now', '-90 days')
        GROUP BY p.id
        ORDER BY p.categoria, p.nombre
    """, conn)

    if df_ventas.empty:
        st.info("No hay suficientes datos de ventas aún")
    else:
        df_ventas["promedio_diario"] = df_ventas["vendido_90d"] / 90
        df_ventas["proyeccion_30d"] = (df_ventas["promedio_diario"] * 30).round(1)
        df_ventas["sugerido_compra"] = (
            df_ventas["proyeccion_30d"] + df_ventas["minimo"] - df_ventas["stock"]
        ).clip(lower=0).round(1)

        st.subheader("Pronóstico y sugerencia de compra (próximos 30 días)")
        st.dataframe(
            df_ventas[["categoria", "nombre", "stock", "vendido_90d", "proyeccion_30d", "sugerido_compra"]]
            .rename(columns={
                "categoria": "Categoría",
                "nombre": "Producto",
                "stock": "Stock actual",
                "vendido_90d": "Vendido últimos 90 días",
                "proyeccion_30d": "Proyección 30 días",
                "sugerido_compra": "Sugerido comprar (kg)"
            }),
            use_container_width=True,
            hide_index=True
        )

        total_sugerido = df_ventas["sugerido_compra"].sum()
        st.metric("Total kilos sugeridos a comprar", f"{total_sugerido:.1f} kg")

        necesita = df_ventas[df_ventas["sugerido_compra"] > 0]
        if not necesita.empty:
            st.subheader("⚠️ Productos que sí conviene comprar")
            st.dataframe(
                necesita[["categoria", "nombre", "stock", "sugerido_compra"]]
                .rename(columns={
                    "categoria": "Categoría",
                    "nombre": "Producto",
                    "stock": "Stock actual",
                    "sugerido_compra": "Comprar (kg)"
                }),
                use_container_width=True,
                hide_index=True
            )

# ---------- ANÁLISIS COMPLETO ----------
elif menu == "📊 Análisis Completo":
    st.header("📊 Análisis de Ventas y Compras")

    total_ventas = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas").fetchone()[0]
    total_kilos_v = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM ventas").fetchone()[0]
    total_compras = conn.execute("SELECT COALESCE(SUM(cantidad*precio),0) FROM compras").fetchone()[0]
    total_kilos_c = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM compras").fetchone()[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Total Ventas", f"${total_ventas:,.0f}")
    c2.metric("⚖️ Kilos Vendidos", f"{total_kilos_v:.1f}")
    c3.metric("🛒 Total Compras", f"${total_compras:,.0f}")
    c4.metric("📦 Kilos Comprados", f"{total_kilos_c:.1f}")

    st.markdown("---")

    st.subheader("🏆 Productos más vendidos (kg)")
    df_top = pd.read_sql_query("""
        SELECT p.nombre, ROUND(SUM(v.cantidad),1) as kilos
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
        GROUP BY v.producto_id
        ORDER BY kilos DESC
        LIMIT 10
