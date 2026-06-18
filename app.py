import streamlit as st
import pandas as pd
import os
import altair as alt
from datetime import datetime, time
import gspread
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# ==========================================
# CONFIGURAÇÃO DA PÁGINA E CSS
# ==========================================
st.set_page_config(page_title="Almoxarifado WEG", page_icon="⚙️", layout="wide")

def aplicar_estilo_weg():
    st.markdown("""
        <style>
        [data-testid="stSidebar"] {background-color: #005099; color: white;}
        [data-testid="stSidebar"] * {color: white !important;}
        .stButton > button {background-color: #005099; color: white; border-radius: 4px; border: none; padding: 10px 24px; font-weight: bold;}
        .stButton > button:hover {background-color: #003d75; color: white; border: 1px solid white;}
        #MainMenu {visibility: hidden;} footer {visibility: hidden;}
        .weg-banner {background-image: linear-gradient(to right, #003d75 , #005099); padding: 30px; border-radius: 5px; color: white; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}
        .weg-banner h1 {color: white; margin: 0; font-size: 28px; text-transform: uppercase;}
        .weg-banner p {margin: 5px 0 0 0; font-size: 16px; opacity: 0.9;}
        </style>
    """, unsafe_allow_html=True)

aplicar_estilo_weg()

def cabecalho_weg():
    st.markdown(f"""
        <div class="weg-banner">
            <h1>Depto Administrativo e Suprimentos - Seção Almoxarifado</h1>
            <p>Gestão de Modelos e Inventário | Usuário: {st.session_state.get('usuario', 'Acesso Restrito')}</p>
        </div>
    """, unsafe_allow_html=True)

# ==========================================
# CONEXÃO COM GOOGLE SHEETS E GMAIL
# ==========================================
def conectar_planilha():
    try:
        credenciais_dict = json.loads(st.secrets["gcp_service_account"])
        gc = gspread.service_account_from_dict(credenciais_dict)
        return gc.open_by_url(st.secrets["url_planilha"])
    except Exception as e:
        st.error(f"Erro ao conectar com o Google Sheets. Verifique os Segredos. ({e})")
        return None

def enviar_email_gmail(destinatarios, assunto, corpo_html, arquivo_pdf=None, nome_pdf="Anexo_NF.pdf"):
    try:
        remetente = st.secrets["email_robo"]
        senha = st.secrets["senha_robo"]
        msg = MIMEMultipart()
        msg['From'] = remetente
        msg['To'] = destinatarios
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo_html, 'html'))
        
        if arquivo_pdf is not None:
            part = MIMEApplication(arquivo_pdf, Name=nome_pdf)
            part['Content-Disposition'] = f'attachment; filename="{nome_pdf}"'
            msg.attach(part)
            
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remetente, senha)
        server.sendmail(remetente, destinatarios.split(';'), msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.warning(f"⚠️ Erro ao enviar E-mail via Gmail: {e}")
        return False

# ==========================================
# CONTROLE DE SESSÃO
# ==========================================
if 'logado' not in st.session_state:
    st.session_state.update({
        'logado': False, 'usuario': "", 'nivel': "", 'nivel_id': "",
        'menu_lateral_nav': "🏠 Dashboard", 'peca_selecionada': "", 'ultima_busca': "",
        'inv_ativo': False, 'inv_local': "", 'inv_esperados': [], 'inv_auditados_ok': [],
        'inv_auditados_movidos': [], 'inv_nao_encontrados': [], 'inv_extras': [], 'inv_key_counter': 0
    })

@st.cache_data(ttl=30)
def carregar_base():
    sh = conectar_planilha()
    if not sh: return pd.DataFrame()
    try:
        ws = sh.worksheet("Base")
        df = pd.DataFrame(ws.get_all_records()).astype(str)
        df.columns = df.columns.str.strip()
        df.replace(["", "None", "nan", "NaN"], "-", inplace=True)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=30)
def carregar_emails_config():
    try:
        sh = conectar_planilha()
        ws_cfg = sh.worksheet("Config")
        val = ws_cfg.acell('A2').value
        return str(val).strip() if val else ""
    except: return ""

def ir_para_tela(nome_tela, codigo_peca):
    st.session_state['menu_lateral_nav'] = nome_tela
    st.session_state['peca_selecionada'] = codigo_peca

# ==========================================
# TELA DE LOGIN
# ==========================================
def tela_login():
    cabecalho_weg()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Autenticação de Usuário")
        st.markdown("---")
        usuario_input = st.text_input("Login (Rede)").strip().upper()
        senha_input = st.text_input("Senha Numérica", type="password")
        
        if st.button("Acessar Sistema", type="primary", use_container_width=True):
            sh = conectar_planilha()
            if not sh: return
            try:
                ws_u = sh.worksheet("Usuarios")
                df_usuarios = pd.DataFrame(ws_u.get_all_records()).astype(str)
                df_usuarios['USUARIO'] = df_usuarios['USUARIO'].str.strip().str.upper()
                df_usuarios['SENHA'] = df_usuarios['SENHA'].str.strip()
                
                filtro = (df_usuarios['USUARIO'] == usuario_input) & (df_usuarios['SENHA'] == senha_input)
                if filtro.any():
                    dados_usuario = df_usuarios[filtro].iloc[0]
                    nivel_num = str(dados_usuario['NIVEL_ACESSO']).strip()
                    mapa_niveis = {"0": "Administrador (ADM)", "1": "Almoxarifado (Executar)", "2": "Compras (Solicitar)"}
                    st.session_state['logado'] = True
                    st.session_state['usuario'] = dados_usuario['USUARIO']
                    st.session_state['nivel'] = mapa_niveis.get(nivel_num, "Desconhecido")
                    st.session_state['nivel_id'] = nivel_num
                    st.rerun() 
                else: st.error("❌ Usuário ou senha incorretos!")
            except Exception as e: st.error(f"⚠️ Erro ao verificar usuários: {e}")

# ==========================================
# FUNÇÕES DAS TELAS
# ==========================================
def tela_geral():
    cabecalho_weg()
    df = carregar_base()
    if df.empty: return st.warning("⚠️ A aba 'Base' está vazia ou não foi encontrada.")

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    df_ativos = df[df['LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)'].astype(str).str.upper() != "DESCARTADO"]
    total_modelos = len(df_ativos)
    
    try:
        col_local, col_tipo = 'LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)', 'TURBINA OU REDUTOR?'
        loc_limpo, tip_limpo = df_ativos[col_local].astype(str).str.upper(), df_ativos[col_tipo].astype(str).str.upper()
        
        col1.metric("📦 Peças Ativas", f"{total_modelos}")
        col2.metric("📍 Galpão", len(df_ativos[loc_limpo.str.contains("GALP", na=False)]))
        col3.metric("🔥 Fundição", len(df_ativos[loc_limpo.str.contains("FUNDI", na=False)]))
        col4.metric("🪚 Modelação", len(df_ativos[loc_limpo.str.contains("MODEL", na=False)]))
        col5.metric("🌪️ Turbinas", len(df_ativos[tip_limpo.str.contains("TURB", na=False)]))
        col6.metric("⚙️ Redutores", len(df_ativos[tip_limpo.str.contains("REDUT", na=False)]))

        st.markdown("---")
        gc1, gc2 = st.columns(2)
        with gc1:
            st.markdown("**Distribuição por Local Armazenado**")
            df_loc = df_ativos[(df_ativos[col_local] != "-")][col_local].value_counts().reset_index()
            df_loc.columns = ['Local', 'Quantidade']
            if not df_loc.empty: st.altair_chart(alt.Chart(df_loc).mark_bar(color='#005099').encode(x='Quantidade:Q', y=alt.Y('Local:N', sort='-x')).properties(height=300), use_container_width=True)

        with gc2:
            st.markdown("**Distribuição por Equipamento**")
            df_tip = df_ativos[(df_ativos[col_tipo] != "-")][col_tipo].value_counts().reset_index()
            df_tip.columns = ['Tipo', 'Quantidade']
            if not df_tip.empty: st.altair_chart(alt.Chart(df_tip).mark_bar(color='#009EE3').encode(x=alt.X('Tipo:N', axis=alt.Axis(labelAngle=0)), y='Quantidade:Q').properties(height=300), use_container_width=True)
    except: pass

    st.markdown("---")
    st.markdown("#### Base de Dados Completa")
    st.dataframe(df, use_container_width=True, height=400)
    if st.button("🔄 Atualizar Dados Agora"): st.cache_data.clear(); st.rerun()

def tela_consulta():
    cabecalho_weg()
    df = carregar_base()
    if df.empty: return st.warning("⚠️ Base vazia.")

    busca = st.text_input("🔎 Localizar Modelo (Digite SAP, Antigo ou Descrição):", value=st.session_state['ultima_busca'])
    st.session_state['ultima_busca'] = busca
    st.markdown("---")
    
    if busca:
        termo = busca.upper().strip()
        cols = [c for c in ['CÓDIGO ANTIGO', 'CODIGO SAP', 'DESCRIÇÃO', 'CÓDIGO PAI', 'MODELO EQUIPAMENTO'] if c in df.columns]
        mask = pd.Series(False, index=df.index)
        for c in cols: mask |= df[c].astype(str).str.upper().str.contains(termo, na=False)
        df_f = df[mask]
        
        if df_f.empty: st.warning("Nenhum modelo encontrado.")
        else:
            st.success(f"✅ {len(df_f)} modelo(s) encontrado(s)!")
            st.dataframe(df_f[[c for c in ['CODIGO SAP', 'CÓDIGO ANTIGO', 'DESCRIÇÃO', 'LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)'] if c in df.columns]], use_container_width=True, hide_index=True)
            st.markdown("#### Ficha Técnica do Modelo")
            
            def fmt(idx): return f"SAP: {df_f.loc[idx].get('CODIGO SAP', '-')} | {df_f.loc[idx].get('DESCRIÇÃO', '-')}"
            item = st.selectbox("Selecione a peça detalhada:", df_f.index.tolist(), format_func=fmt)
            
            if item is not None:
                p = df_f.loc[item]
                with st.container(border=True):
                    st.subheader(f"🛠️ {p.get('DESCRIÇÃO', '-')}")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown("**Identificação**")
                        st.write(f"**Código SAP:** {p.get('CODIGO SAP', '-')}")
                        st.write(f"**Código Antigo:** {p.get('CÓDIGO ANTIGO', '-')}")
                    with c2:
                        st.markdown("**Localização Física**")
                        st.info(f"📍 **Local:** {p.get('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)', '-')}")
                        st.success(f"🗄️ **Posição:** {p.get('POSIÇÃO GALPÃO', '-')}")
                    with c3:
                        st.markdown("**Detalhes Técnicos**")
                        st.write(f"**Aplicação:** {p.get('TURBINA OU REDUTOR?', '-')} / {p.get('MODELO EQUIPAMENTO', '-')}")
                        st.write(f"**Última Movimentação:** {p.get('ÚLTIMA MOVIMENTAÇÃO', '-')}")
                    
                    obs = p.get('OBSERVAÇÃO', '-')
                    if str(obs).strip() != "-": st.warning(f"**Observação:** {obs}")

                    st.markdown("---")
                    bc1, bc2 = st.columns(2)
                    cod_mem = p.get('CODIGO SAP', '-')
                    if str(cod_mem).strip() in ["-", ""]: cod_mem = p.get('CÓDIGO ANTIGO', '')
                    if st.session_state['nivel_id'] in ["0", "1"]:
                        with bc1: st.button("✏️ Modificar Posição", use_container_width=True, on_click=ir_para_tela, args=("🔄 Movimentação Fís.", cod_mem))
                    with bc2: st.button("📥 Gerar Nova Solicitação", use_container_width=True, on_click=ir_para_tela, args=("📥 Emissão de Tickets", cod_mem))

def tela_modificar():
    cabecalho_weg()
    st.markdown("#### Registrar Movimentação Física no Galpão")
    df = carregar_base()
    if df.empty: return

    cod = st.text_input("Insira o Código (SAP ou Antigo) para registrar mudança:", value=st.session_state.get('peca_selecionada', '')).strip().upper()
    if cod:
        peca_enc = df[(df['CODIGO SAP'].astype(str).str.upper() == cod) | (df['CÓDIGO ANTIGO'].astype(str).str.upper() == cod)]
        if peca_enc.empty: st.error("❌ Peça não encontrada.")
        else:
            p = peca_enc.iloc[0]
            loc_atual, pos_atual = p.get('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)', '-'), p.get('POSIÇÃO GALPÃO', '-')
            st.success(f"✅ Peça selecionada: **{p.get('DESCRIÇÃO', '-')}**")
            
            with st.form("form_mov"):
                st.info(f"📍 **Endereço Atual:** {loc_atual} | Posição: {pos_atual}")
                st.markdown("---")
                
                opcoes = ["GALPÃO", "FUNDIÇÃO", "MODELAÇÃO", "DESCARTADO"]
                n_loc = st.selectbox("Novo Setor / Armazém:", opcoes, index=opcoes.index(loc_atual.upper()) if str(loc_atual).upper() in opcoes else 0)
                n_pos = st.text_input("Nova Posição Específica:", value="" if pos_atual == "-" else str(pos_atual))
                n_obs = st.text_input("Observação / Justificativa (* Obrigatório para Fundição/Modelação):" if n_loc in ["FUNDIÇÃO", "MODELAÇÃO"] else "Observação (Opcional):")
                
                if st.form_submit_button("💾 Confirmar Movimentação na Nuvem", type="primary"):
                    if not n_pos and n_loc != "DESCARTADO": st.warning("Preencha a Nova Posição.")
                    elif n_loc in ["FUNDIÇÃO", "MODELAÇÃO"] and not n_obs.strip(): st.warning(f"Observação é obrigatória para destino {n_loc}.")
                    else:
                        try:
                            sh = conectar_planilha()
                            ws_base = sh.worksheet("Base")
                            dados_completos = ws_base.get_all_values()
                            cabecalhos = dados_completos[0]
                            col_sap = cabecalhos.index('CODIGO SAP')
                            col_ant = cabecalhos.index('CÓDIGO ANTIGO')
                            
                            linha_alvo_sheets = None
                            for i, linha in enumerate(dados_completos[1:], start=2):
                                vs = str(linha[col_sap]).strip().upper() if len(linha) > col_sap else ""
                                va = str(linha[col_ant]).strip().upper() if len(linha) > col_ant else ""
                                if cod in [vs, va] and cod != "":
                                    linha_alvo_sheets = i
                                    break
                            
                            if linha_alvo_sheets:
                                dh = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                ws_base.update_cell(linha_alvo_sheets, cabecalhos.index('ÚLTIMO LOCAL QUE ESTEVE')+1, f"{loc_atual} ({pos_atual})")
                                ws_base.update_cell(linha_alvo_sheets, cabecalhos.index('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)')+1, n_loc.upper())
                                ws_base.update_cell(linha_alvo_sheets, cabecalhos.index('POSIÇÃO GALPÃO')+1, n_pos.upper())
                                ws_base.update_cell(linha_alvo_sheets, cabecalhos.index('OBSERVAÇÃO')+1, n_obs)
                                ws_base.update_cell(linha_alvo_sheets, cabecalhos.index('ÚLTIMA MOVIMENTAÇÃO')+1, dh)
                                
                                try:
                                    ws_hist = sh.worksheet("Historico")
                                    ws_hist.append_row([dh, st.session_state['usuario'], f"{p.get('CODIGO SAP','-')} / {p.get('CÓDIGO ANTIGO','-')}", "MOVIMENTAÇÃO", f"{loc_atual} ({pos_atual})", f"{n_loc.upper()} ({n_pos.upper()})", n_obs])
                                except: pass
                                
                                st.cache_data.clear(); st.session_state['peca_selecionada'] = ""; st.rerun()
                            else: st.error("Peça não encontrada fisicamente na Nuvem.")
                        except Exception as e: st.error(f"Erro ao salvar na nuvem: {e}")

def calcular_sla(prazo_str):
    if str(prazo_str).strip() in ['-', '', 'nan', 'N/A']: return "-"
    try:
        dt_str = str(prazo_str).replace(" às ", " ")
        prazo_dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M")
        agora = datetime.now()
        if agora > prazo_dt: return "🔴 ATRASADO"
        elif agora.date() == prazo_dt.date(): return "🟡 VENCE HOJE"
        else: return "🟢 NO PRAZO"
    except: return "⚪ INDEFINIDO"

def tela_solicitacoes():
    cabecalho_weg()
    aba1, aba2 = st.tabs(["📝 Nova Solicitação (Workflow)", "🔄 Gerenciar Solicitações"])
    df = carregar_base()
    
    sh = conectar_planilha()
    try:
        ws_solic = sh.worksheet("Solicitacoes")
        df_solic = pd.DataFrame(ws_solic.get_all_records()).astype(str)
        df_solic.replace(["", "None", "nan", "NaN"], "-", inplace=True)
    except: df_solic = pd.DataFrame()

    with aba1:
        st.markdown("O prazo respeita a regra de 8 horas úteis.")
        cod = st.text_input("Código SAP ou Antigo do Material:", value=st.session_state.get('peca_selecionada', '')).strip().upper()
        if cod and not df.empty:
            peca_enc = df[(df['CODIGO SAP'].astype(str).str.upper() == cod) | (df['CÓDIGO ANTIGO'].astype(str).str.upper() == cod)]
            if peca_enc.empty: st.error("❌ Material não encontrado.")
            else:
                p = peca_enc.iloc[0]
                sap, ant, desc, loc_atual, pos_padrao = p.get('CODIGO SAP','-'), p.get('CÓDIGO ANTIGO','-'), p.get('DESCRIÇÃO','-'), p.get('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)','-'), p.get('POSIÇÃO GALPÃO','-')
                
                ticket_pendente = False
                id_bloqueio = ""
                if not df_solic.empty:
                    df_abertos = df_solic[~df_solic['STATUS'].astype(str).str.upper().isin(["ENVIADO/RECEBIDO", "CANCELADO"])]
                    for _, row in df_abertos.iterrows():
                        codigos_ticket = str(row.get('CODIGO_SAP', ''))
                        if (sap != '-' and sap in codigos_ticket) or (ant != '-' and ant in codigos_ticket):
                            ticket_pendente = True; id_bloqueio = str(row.get('ID_SOLICITACAO', '-')); break

                if ticket_pendente:
                    st.error(f"🛑 ATENÇÃO: Peça com solicitação em andamento (Protocolo {id_bloqueio}). Não é possível abrir um novo fluxo.")
                else:
                    st.success(f"✅ Material: **{desc}** | Armazenado em: **{loc_atual}** | Posição: **{pos_padrao}**")
                    with st.form("form_sol"):
                        c1, c2 = st.columns(2)
                        with c1:
                            if "GALP" in str(loc_atual).upper():
                                opcoes_mov = ["SAÍDA"]; st.info("💡 Material no Galpão. Fluxo: SAÍDA.")
                            else: opcoes_mov = ["RETORNO", "SAÍDA"]
                            tipo = st.selectbox("Tipo de Movimentação:", opcoes_mov)
                            dest = st.text_input("Fornecedor / Setor de Destino:")
                            dt_min = (pd.to_datetime(datetime.now().date()) + pd.offsets.BDay(1)).date()
                            s1, s2 = st.columns(2)
                            with s1: dt_prz = st.date_input("Data Limite:", value=dt_min, min_value=dt_min, format="DD/MM/YYYY")
                            with s2: hr_prz = st.time_input("Horário Limite:", value=time(8, 0))
                        with c2:
                            nf = st.text_input("Documento / Nota Fiscal (* Obrigatório):")
                            solic = st.text_input("Usuário Solicitante:", value=st.session_state['usuario'])
                            obs = st.text_input("Motivo / Observações:")
                            st.markdown("---")
                            arquivo_anexo = st.file_uploader("📎 Anexar NF (PDF opcional)", type=["pdf"])

                        if st.form_submit_button("📩 Emitir Solicitação", type="primary"):
                            if dt_prz.weekday() >= 5: st.warning("Escolha dia útil.")
                            elif not dest.strip() or not nf.strip(): st.warning("Destino e NF são obrigatórios.")
                            else:
                                try:
                                    dh_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    prz_str = f"{dt_prz.strftime('%d/%m/%Y')} às {hr_prz.strftime('%H:%M')}"
                                    
                                    cabs = ws_solic.row_values(1)
                                    required = ["DATA_HORA", "SOLICITANTE", "TIPO", "CODIGO_SAP", "NF", "STATUS", "OBSERVACAO", "DESTINO_NOME", "PRAZO", "EXECUTADO_POR", "EXECUTADO_EM", "ID_SOLICITACAO"]
                                    for r in required:
                                        if r not in cabs:
                                            cabs.append(r)
                                            ws_solic.update_cell(1, len(cabs), r)
                                    
                                    try:
                                        col_id = cabs.index("ID_SOLICITACAO") + 1
                                        ids = [int(i) for i in ws_solic.col_values(col_id)[1:] if i.isdigit()]
                                        n_id = f"{(max(ids) + 1) if ids else 1:05d}"
                                    except: n_id = "00001"

                                    nova_linha = ["" for _ in range(len(cabs))]
                                    nova_linha[cabs.index("DATA_HORA")] = dh_agora
                                    nova_linha[cabs.index("SOLICITANTE")] = solic
                                    nova_linha[cabs.index("TIPO")] = tipo
                                    nova_linha[cabs.index("CODIGO_SAP")] = f"{sap} / {ant}"
                                    nova_linha[cabs.index("NF")] = nf
                                    nova_linha[cabs.index("STATUS")] = "Solicitado"
                                    nova_linha[cabs.index("OBSERVACAO")] = obs
                                    nova_linha[cabs.index("DESTINO_NOME")] = dest
                                    nova_linha[cabs.index("PRAZO")] = prz_str
                                    nova_linha[cabs.index("EXECUTADO_POR")] = "-"
                                    nova_linha[cabs.index("EXECUTADO_EM")] = "-"
                                    nova_linha[cabs.index("ID_SOLICITACAO")] = n_id

                                    ws_solic.append_row(nova_linha)
                                    st.success(f"💾 Protocolo {n_id} gerado no Google Sheets!")
                                    
                                    # LÓGICA DE E-MAIL
                                    try:
                                        emails_admin = carregar_emails_config()
                                        lista_emails = [e.strip() for e in str(emails_admin).split(";") if e.strip()] if emails_admin else []
                                    except: lista_emails = []

                                    email_solicitante = f"{solic.strip().lower()}@weg.net"
                                    if email_solicitante not in lista_emails: lista_emails.append(email_solicitante)
                                    str_emails_destino = "; ".join(lista_emails)

                                    if tipo == "SAÍDA":
                                        assunto = f"Solicitação de Envio de Modelo para {dest} - NF: {nf}"
                                        corpo = f"""
                                        <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
                                            <p>Prezados,</p>
                                            <p>Solicitamos a retirada do modelo abaixo relacionado junto ao Galpão de Modelos para utilização no processo de fundição/modelação.</p>
                                            <p><b>Dados do Modelo e prazo de envio:</b></p>
                                            <ul>
                                                <li><b>Peça:</b> {desc}</li>
                                                <li><b>Código SAP:</b> {sap} | <b>Antigo:</b> {ant}</li>
                                                <li><b>Posição de Retirada:</b> {pos_padrao}</li>
                                                <li><b>Destino:</b> {dest}</li>
                                                <li><b>Prazo Máximo:</b> {prz_str}</li>
                                                <li><b>NF:</b> {nf}</li>
                                                <li><b>Solicitante:</b> {solic}</li>
                                            </ul>
                                            <p><b>Observações:</b> {obs}</p>
                                            <hr>
                                            <p style="font-size: 11px; color: #666;">[Protocolo Interno: {n_id}] Mensagem automática gerada pelo App Gestão de Modelos - WEN SZO.</p>
                                        </div>
                                        """
                                    else:
                                        assunto = f"Devolução de Modelo ao Galpão de Modelos - NF: {nf}"
                                        corpo = f"""
                                        <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
                                            <p>Prezados,</p>
                                            <p>Notificamos que o modelo <b>{sap if sap!='-' else ant} ({desc})</b> está sendo devolvido para WEG sendo necessário recebimento e acondicionamento no Galpão de Modelos.</p>
                                            <p><b>Previsão de chegada:</b> {prz_str}</p>
                                            <br>
                                            <p><b>Detalhes Complementares:</b></p>
                                            <ul>
                                                <li><b>Posição Padrão no Galpão:</b> {pos_padrao}</li>
                                                <li><b>Origem / Fornecedor:</b> {dest}</li>
                                                <li><b>NF:</b> {nf}</li>
                                                <li><b>Solicitante:</b> {solic}</li>
                                            </ul>
                                            <p><b>Observações:</b> {obs}</p>
                                            <hr>
                                            <p style="font-size: 11px; color: #666;">[Protocolo Interno: {n_id}] Mensagem automática gerada pelo App Gestão de Modelos - WEN SZO.</p>
                                        </div>
                                        """
                                    
                                    buffer_pdf = arquivo_anexo.read() if arquivo_anexo else None
                                    nome_pdf = f"NF_{nf}.pdf" if arquivo_anexo else None
                                    
                                    st.info("⏳ Enviando notificação oficial por E-mail...")
                                    if enviar_email_gmail(str_emails_destino, assunto, corpo, buffer_pdf, nome_pdf):
                                        st.success("✉️ E-mail oficial enviado com sucesso!")

                                    st.session_state['peca_selecionada'] = ""; st.cache_data.clear(); st.rerun()
                                except Exception as e: st.error(f"Erro na Nuvem: {e}")

    with aba2:
        st.markdown("Painel Operacional de Tickets Abertos.")
        if not df_solic.empty:
            for c in ['DESTINO_NOME', 'PRAZO', 'EXECUTADO_POR', 'EXECUTADO_EM', 'ID_SOLICITACAO']:
                if c not in df_solic.columns: df_solic[c] = '-'
            df_pend = df_solic[~df_solic['STATUS'].astype(str).str.upper().isin(["ENVIADO/RECEBIDO", "CANCELADO"])].copy()
            
            if df_pend.empty: st.success("🎉 Todos os fluxos concluídos!")
            else:
                df_pend['SLA'] = df_pend['PRAZO'].apply(calcular_sla)
                df_pend.insert(0, "Selecionar", False)
                
                st.dataframe(df_pend[["ID_SOLICITACAO", "SLA", "STATUS", "PRAZO", "TIPO", "DESTINO_NOME", "CODIGO_SAP", "SOLICITANTE"]], hide_index=True, use_container_width=True)
                st.markdown("---")
                
                col_almox, col_compras = st.columns(2)
                
                with col_almox:
                    if st.session_state['nivel_id'] in ["0", "1"]:
                        st.subheader("📦 Ações do Almoxarifado")
                        id_almox = st.selectbox("Selecione o Protocolo para Atualizar Status:", [""] + df_pend['ID_SOLICITACAO'].tolist())
                        nst = st.selectbox("Aplicar Novo Status:", ["Em preparação", "Preparado para carregar/descarregar", "Enviado/Recebido"])
                        notificar_solic = st.checkbox("✉️ Notificar Solicitante por e-mail", value=True)
                        
                        if st.button("🔄 Confirmar Status", type="primary") and id_almox != "":
                            try:
                                ws_solic = sh.worksheet("Solicitacoes")
                                cabs_solic = ws_solic.row_values(1)
                                col_id_idx = cabs_solic.index('ID_SOLICITACAO') + 1
                                todos_ids = ws_solic.col_values(col_id_idx)
                                
                                if id_almox in todos_ids:
                                    linha = todos_ids.index(id_almox) + 1
                                    h_ex = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    ws_solic.update_cell(linha, cabs_solic.index('STATUS') + 1, nst)
                                    ws_solic.update_cell(linha, cabs_solic.index('EXECUTADO_POR') + 1, st.session_state['usuario'])
                                    ws_solic.update_cell(linha, cabs_solic.index('EXECUTADO_EM') + 1, h_ex)
                                    
                                    # Baixa Física se for Enviado/Recebido
                                    if nst == "Enviado/Recebido":
                                        tk_sap = ws_solic.cell(linha, cabs_solic.index('CODIGO_SAP') + 1).value
                                        tk_tipo = str(ws_solic.cell(linha, cabs_solic.index('TIPO') + 1).value).upper()
                                        tk_dest = str(ws_solic.cell(linha, cabs_solic.index('DESTINO_NOME') + 1).value).upper()
                                        tk_nf = ws_solic.cell(linha, cabs_solic.index('NF') + 1).value
                                        
                                        cod_busca = tk_sap.split(" / ")[0].strip()
                                        if not cod_busca or cod_busca == "-": cod_busca = tk_sap.split(" / ")[1].strip()
                                        
                                        ws_base = sh.worksheet("Base")
                                        dados_base = ws_base.get_all_values()
                                        cabs_base = dados_base[0]
                                        
                                        linha_base = None
                                        for i, r_base in enumerate(dados_base[1:], start=2):
                                            if cod_busca in [str(r_base[cabs_base.index('CODIGO SAP')]).strip(), str(r_base[cabs_base.index('CÓDIGO ANTIGO')]).strip()]:
                                                linha_base = i; break
                                        
                                        if linha_base:
                                            loc_atual = dados_base[linha_base-1][cabs_base.index('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)')]
                                            pos_atual = dados_base[linha_base-1][cabs_base.index('POSIÇÃO GALPÃO')]
                                            novo_loc = "GALPÃO" if tk_tipo == "RETORNO" else tk_dest
                                            ws_base.update_cell(linha_base, cabs_base.index('ÚLTIMO LOCAL QUE ESTEVE')+1, f"{loc_atual} ({pos_atual})")
                                            ws_base.update_cell(linha_base, cabs_base.index('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)')+1, novo_loc)
                                            ws_base.update_cell(linha_base, cabs_base.index('ÚLTIMA MOVIMENTAÇÃO')+1, h_ex)
                                            
                                            try:
                                                ws_hist = sh.worksheet("Historico")
                                                ws_hist.append_row([h_ex, st.session_state['usuario'], tk_sap, f"WORKFLOW CONCLUÍDO ({tk_tipo})", f"{loc_atual} ({pos_atual})", novo_loc, f"NF: {tk_nf}"])
                                            except: pass

                                    # Notificar Solicitante
                                    if notificar_solic:
                                        solic_email = str(ws_solic.cell(linha, cabs_solic.index('SOLICITANTE') + 1).value).strip()
                                        if solic_email != "-":
                                            assunto = f"WEG | Protocolo {id_almox} Atualizado: {nst}"
                                            corpo = f"""
                                            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
                                                <p>Olá {solic_email},</p>
                                                <p>O seu Protocolo de Workflow foi atualizado pela equipe do Almoxarifado.</p>
                                                <p><b>Novo Status: <span style="color:#005099;">{nst}</span></b></p>
                                                <ul>
                                                    <li><b>Protocolo:</b> {id_almox}</li>
                                                    <li><b>Material:</b> {tk_sap if nst == 'Enviado/Recebido' else '-'}</li>
                                                    <li><b>Atualizado por:</b> {st.session_state['usuario']}</li>
                                                    <li><b>Data/Hora:</b> {h_ex}</li>
                                                </ul>
                                            </div>
                                            """
                                            enviar_email_gmail(f"{solic_email.lower()}@weg.net", assunto, corpo)

                                    st.success(f"✅ Protocolo {id_almox} atualizado!")
                                    st.cache_data.clear(); st.rerun() 
                            except Exception as e: st.error(f"Erro ao salvar: {e}")

                with col_compras:
                    st.subheader("👤 Ações do Solicitante")
                    meus_tickets = df_pend[(df_pend['SOLICITANTE'].str.upper() == st.session_state['usuario']) | (st.session_state['nivel_id'] == "0")]
                    
                    if meus_tickets.empty:
                        st.info("Você não tem protocolos abertos no momento.")
                    else:
                        id_edit = st.selectbox("Meus Protocolos Abertos:", [""] + meus_tickets['ID_SOLICITACAO'].tolist())
                        
                        if id_edit != "":
                            tk_selecionado = meus_tickets[meus_tickets['ID_SOLICITACAO'] == id_edit].iloc[0]
                            st.write(f"**Peça:** {tk_selecionado['CODIGO_SAP']} | **Destino:** {tk_selecionado['DESTINO_NOME']}")
                            
                            with st.expander("✏️ Editar Informações ou Cancelar"):
                                with st.form("form_edit_ticket"):
                                    n_nf = st.text_input("Nova NF:", value=tk_selecionado['NF'])
                                    n_dest = st.text_input("Novo Destino:", value=tk_selecionado['DESTINO_NOME'])
                                    n_obs = st.text_input("Nova Observação:", value=tk_selecionado['OBSERVACAO'])
                                    
                                    col_e1, col_e2 = st.columns(2)
                                    btn_salvar_edit = col_e1.form_submit_button("💾 Salvar Alterações", type="primary")
                                    btn_cancelar_tk = col_e2.form_submit_button("🗑️ Excluir (Cancelar) Protocolo")
                                    
                                    if btn_salvar_edit:
                                        try:
                                            ws_solic = sh.worksheet("Solicitacoes")
                                            cabs = ws_solic.row_values(1)
                                            todos_ids = ws_solic.col_values(cabs.index('ID_SOLICITACAO') + 1)
                                            linha = todos_ids.index(id_edit) + 1
                                            
                                            ws_solic.update_cell(linha, cabs.index('NF') + 1, n_nf)
                                            ws_solic.update_cell(linha, cabs.index('DESTINO_NOME') + 1, n_dest)
                                            ws_solic.update_cell(linha, cabs.index('OBSERVACAO') + 1, n_obs)
                                            st.success("✅ Informações atualizadas!")
                                            st.cache_data.clear(); st.rerun()
                                        except Exception as e: st.error(e)
                                        
                                    if btn_cancelar_tk:
                                        try:
                                            ws_solic = sh.worksheet("Solicitacoes")
                                            cabs = ws_solic.row_values(1)
                                            todos_ids = ws_solic.col_values(cabs.index('ID_SOLICITACAO') + 1)
                                            linha = todos_ids.index(id_edit) + 1
                                            
                                            ws_solic.update_cell(linha, cabs.index('STATUS') + 1, "CANCELADO")
                                            ws_solic.update_cell(linha, cabs.index('EXECUTADO_POR') + 1, st.session_state['usuario'])
                                            ws_solic.update_cell(linha, cabs.index('EXECUTADO_EM') + 1, datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
                                            ws_solic.update_cell(linha, cabs.index('OBSERVACAO') + 1, "Cancelado pelo Solicitante.")
                                            
                                            st.success("🚫 Protocolo cancelado e removido da fila!")
                                            st.cache_data.clear(); st.rerun()
                                        except Exception as e: st.error(e)

# ==========================================
# TELA 5: HISTÓRICO
# ==========================================
def tela_historico():
    cabecalho_weg()
    st.markdown("#### Portal de Auditoria Documental")
    aba1, aba2 = st.tabs(["🔄 Auditoria de Endereçamentos", "📥 Extrato de Protocolos (Workflow)"])
    
    sh = conectar_planilha()
    
    with aba1:
        try:
            df_hist = pd.DataFrame(sh.worksheet("Historico").get_all_records()).astype(str)
            df_hist.replace(["", "None", "nan", "NaN"], "-", inplace=True)
        except: df_hist = pd.DataFrame()

        if not df_hist.empty:
            busca_hist = st.text_input("🔎 Localizar na Trilha de Auditoria (SAP, Login ou Setor):")
            if busca_hist:
                termo = busca_hist.upper().strip()
                mask = pd.Series(False, index=df_hist.index)
                for col in df_hist.columns: mask |= df_hist[col].astype(str).str.upper().str.contains(termo, na=False)
                df_hist_filtrado = df_hist[mask]
                if df_hist_filtrado.empty: st.warning("Nenhum dado encontrado.")
                else: st.dataframe(df_hist_filtrado.iloc[::-1], use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_hist.iloc[::-1], use_container_width=True, hide_index=True)

    with aba2:
        try:
            df_solic = pd.DataFrame(sh.worksheet("Solicitacoes").get_all_records()).astype(str)
            df_solic.replace(["", "None", "nan", "NaN"], "-", inplace=True)
        except: df_solic = pd.DataFrame()

        if not df_solic.empty:
            busca_solic = st.text_input("🔎 Localizar Protocolo por ID, Documento ou Solicitante:")
            if busca_solic:
                termo2 = busca_solic.upper().strip()
                mask2 = pd.Series(False, index=df_solic.index)
                for col in df_solic.columns: mask2 |= df_solic[col].astype(str).str.upper().str.contains(termo2, na=False)
                df_solic_filtrado = df_solic[mask2]
                if df_solic_filtrado.empty: st.warning("Documento não encontrado.")
                else: st.dataframe(df_solic_filtrado.iloc[::-1], use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_solic.iloc[::-1], use_container_width=True, hide_index=True)

# ==========================================
# TELA 6: INVENTARIO WMS
# ==========================================
def tela_inventario():
    cabecalho_weg()
    st.markdown("#### Rotina de Contagem Cíclica (WMS)")
    if st.session_state['nivel_id'] == "2": return st.error("🔒 Perfil não autorizado para auditoria de WMS.")
    df = carregar_base()
    if df.empty: return st.warning("⚠️ Base indisponível.")

    aba_conf, aba_exec, aba_fecha, aba_hist = st.tabs(["⚙️ Gerar Plano", "📱 Validação em Campo", "✅ Fechamento", "📜 Doc.Inv. Processados"])

    with aba_conf:
        col1, col2 = st.columns(2)
        with col1: pos_alvo = st.text_input("Posição Alvo (Galpão):", placeholder="Ex: Pátio B")
        with col2: loc_alvo = st.selectbox("Área Abrangente:", ["TODOS", "GALPÃO", "FUNDIÇÃO", "MODELAÇÃO"])

        if st.button("🚀 Processar Plano de Contagem", type="primary"):
            if not pos_alvo.strip() and loc_alvo == "TODOS": st.warning("Defina um perímetro.")
            else:
                st.session_state['inv_key_counter'] += 1 
                for k in ['inv_auditados_ok', 'inv_auditados_movidos', 'inv_nao_encontrados', 'inv_extras']: st.session_state[k] = []
                filtro = pd.Series(True, index=df.index)
                if pos_alvo.strip(): filtro &= df['POSIÇÃO GALPÃO'].astype(str).str.upper().str.contains(pos_alvo.upper().strip(), na=False)
                if loc_alvo != "TODOS": filtro &= df['LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)'].astype(str).str.upper().str.contains(loc_alvo, na=False)
                
                df_esp = df[filtro]
                n_inv = pos_alvo.upper().strip() if pos_alvo.strip() else loc_alvo
                if df_esp.empty: st.warning(f"Sem itens mapeados.")
                else:
                    ls_saps = []
                    for _, r in df_esp.iterrows():
                        s, a = str(r.get('CODIGO SAP','-')).strip(), str(r.get('CÓDIGO ANTIGO','-')).strip()
                        if s != '-': ls_saps.append(s)
                        elif a != '-': ls_saps.append(a)
                    st.session_state['inv_ativo'], st.session_state['inv_local'], st.session_state['inv_esperados'] = True, n_inv, list(set(ls_saps))
                    st.success(f"✅ Plano validado. Vá para a aba de Campo.")

    with aba_exec:
        if not st.session_state['inv_ativo']: st.info("Gere o Plano primeiro.")
        else:
            esp, ok, mov, nao_enc, ext = st.session_state['inv_esperados'], st.session_state['inv_auditados_ok'], st.session_state['inv_auditados_movidos'], st.session_state['inv_nao_encontrados'], st.session_state['inv_extras']
            t_esp, t_aud = len(esp), len(ok) + len(mov) + len(nao_enc)
            
            st.markdown(f"#### Coleta de Dados: **{st.session_state['inv_local']}**")
            if t_esp > 0: st.progress(min(t_aud / t_esp, 1.0))
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Mapeados", t_esp); c2.metric("Conformes", len(ok)); c3.metric("Ajustados", len(mov) + len(ext)); c4.metric("Desvios", len(nao_enc))

            cod = st.text_input("Bipagem Sistêmica (Insira o Código):", key=f"input_inv_{st.session_state['inv_key_counter']}").strip().upper()
            if cod:
                if cod in ok or cod in mov or cod in nao_enc or cod in ext: st.warning("Código já consolidado.")
                else:
                    p_bip = df[(df['CODIGO SAP'].astype(str).str.upper() == cod) | (df['CÓDIGO ANTIGO'].astype(str).str.upper() == cod)]
                    if p_bip.empty: st.error("Registro não localizado.")
                    else:
                        p = p_bip.iloc[0]
                        st.info(f"**Vínculo no WMS:** {p.get('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)', '-')} | Slot: {p.get('POSIÇÃO GALPÃO', '-')}")
                        enc = st.radio("Confirma a integridade física do material neste exato local?", ["Sim, material em mãos", "Não, divergência identificada"], index=None, horizontal=True)
                        if enc == "Não, divergência identificada":
                            if st.button("Sinalizar Desvio", type="primary"):
                                st.session_state['inv_nao_encontrados'].append(cod); st.session_state['inv_key_counter'] += 1; st.rerun()
                        elif enc == "Sim, material em mãos":
                            p_corr = st.radio("O endereço físico confere com os dados do WMS acima?", ["Sim, endereçamento correto", "Não, é necessário transferir"], index=None, horizontal=True)
                            if p_corr == "Sim, endereçamento correto":
                                if st.button("Validar Leitura", type="primary"):
                                    if cod in esp: st.session_state['inv_auditados_ok'].append(cod)
                                    else: st.session_state['inv_extras'].append(cod) 
                                    st.session_state['inv_key_counter'] += 1; st.rerun()
                            elif p_corr == "Não, é necessário transferir":
                                n_loc = st.selectbox("Definir Novo Setor:", ["GALPÃO", "FUNDIÇÃO", "MODELAÇÃO", "DESCARTADO"])
                                n_pos = st.text_input("Definir Novo Slot (Prateleira/Pátio):")
                                if st.button("Processar Ajuste no Inventário", type="primary"):
                                    if not n_pos.strip(): st.warning("Slot obrigatório.")
                                    else:
                                        try:
                                            sh = conectar_planilha()
                                            ws_base = sh.worksheet("Base")
                                            dados_completos = ws_base.get_all_values()
                                            cabecalhos = dados_completos[0]
                                            
                                            if 'DATA_ULTIMA_CONTAGEM' not in cabecalhos:
                                                ws_base.update_cell(1, len(cabecalhos)+1, "DATA_ULTIMA_CONTAGEM")
                                                cabecalhos.append("DATA_ULTIMA_CONTAGEM")
                                                
                                            col_sap = cabecalhos.index('CODIGO SAP')
                                            col_ant = cabecalhos.index('CÓDIGO ANTIGO')
                                            
                                            linha_alvo = None
                                            for i, linha in enumerate(dados_completos[1:], start=2):
                                                vs = str(linha[col_sap]).strip().upper() if len(linha) > col_sap else ""
                                                va = str(linha[col_ant]).strip().upper() if len(linha) > col_ant else ""
                                                if cod in [vs, va] and cod != "":
                                                    linha_alvo = i; break
                                                    
                                            if linha_alvo:
                                                dh = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                                ws_base.update_cell(linha_alvo, cabecalhos.index('ÚLTIMO LOCAL QUE ESTEVE')+1, f"{p.get('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)', '-')} ({p.get('POSIÇÃO GALPÃO', '-')})")
                                                ws_base.update_cell(linha_alvo, cabecalhos.index('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)')+1, n_loc.upper())
                                                ws_base.update_cell(linha_alvo, cabecalhos.index('POSIÇÃO GALPÃO')+1, n_pos.upper())
                                                ws_base.update_cell(linha_alvo, cabecalhos.index('ÚLTIMA MOVIMENTAÇÃO')+1, dh)
                                                ws_base.update_cell(linha_alvo, cabecalhos.index('DATA_ULTIMA_CONTAGEM')+1, dh)
                                                
                                                try:
                                                    sh.worksheet("Historico").append_row([dh, st.session_state['usuario'], cod, "INVENTÁRIO (AJUSTE)", f"{p.get('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)', '-')} ({p.get('POSIÇÃO GALPÃO', '-')})", f"{n_loc.upper()} ({n_pos.upper()})", f"WMS por {st.session_state['usuario']}"])
                                                except: pass

                                                if cod in esp: st.session_state['inv_auditados_movidos'].append(cod)
                                                else: st.session_state['inv_extras'].append(cod)
                                                st.session_state['inv_key_counter'] += 1; st.rerun()
                                        except Exception as e: st.error(f"Erro: {e}")

            st.markdown("---")
            t_ex = esp + ext
            df_lst = df[df['CODIGO SAP'].isin(t_ex) | df['CÓDIGO ANTIGO'].isin(t_ex)].copy()
            if not df_lst.empty:
                df_ex = df_lst[[c for c in ['CODIGO SAP', 'CÓDIGO ANTIGO', 'DESCRIÇÃO', 'POSIÇÃO GALPÃO'] if c in df_lst.columns]].copy()
                def st_cont(rw):
                    s, a = str(rw.get('CODIGO SAP','-')).strip(), str(rw.get('CÓDIGO ANTIGO','-')).strip()
                    if s in ok or a in ok: return "✅ Conforme"
                    if s in mov or a in mov: return "🔄 Ajustado"
                    if s in ext or a in ext: return "⭐ Extra (Sobressalente)"
                    if s in nao_enc or a in nao_enc: return "🚨 Desvio Identificado"
                    return "⏳ Aguardando"
                df_ex['Status Operacional'] = df_ex.apply(st_cont, axis=1)
                df_ex.sort_values(by='Status Operacional', ascending=False, inplace=True)
                st.dataframe(df_ex, use_container_width=True, hide_index=True)

    with aba_fecha:
        if not st.session_state['inv_ativo']: st.info("Processo inativo.")
        else:
            esp, ok, mov, nao_enc, ext = st.session_state['inv_esperados'], st.session_state['inv_auditados_ok'], st.session_state['inv_auditados_movidos'], st.session_state['inv_nao_encontrados'], st.session_state['inv_extras']
            nao_aud = [s for s in esp if s not in ok and s not in mov and s not in nao_enc]
            st.warning(f"O plano acusa {len(nao_aud)} item(ns) pendente(s). Eles constarão como desvio no Doc.Inv.")
            
            if st.button("Homologar Ciclo no Google Sheets", type="primary"):
                try:
                    sh = conectar_planilha()
                    ws_base = sh.worksheet("Base")
                    dados_completos = ws_base.get_all_values()
                    cabecalhos = dados_completos[0]
                    
                    if 'DATA_ULTIMA_CONTAGEM' not in cabecalhos:
                        ws_base.update_cell(1, len(cabecalhos)+1, "DATA_ULTIMA_CONTAGEM")
                        cabecalhos.append("DATA_ULTIMA_CONTAGEM")

                    col_sap = cabecalhos.index('CODIGO SAP')
                    col_ant = cabecalhos.index('CÓDIGO ANTIGO')
                    col_ult = cabecalhos.index('DATA_ULTIMA_CONTAGEM') + 1

                    dh = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    
                    for i, linha in enumerate(dados_completos[1:], start=2):
                        vs = str(linha[col_sap]).strip().upper() if len(linha) > col_sap else ""
                        va = str(linha[col_ant]).strip().upper() if len(linha) > col_ant else ""
                        if vs in ok or va in ok:
                            ws_base.update_cell(i, col_ult, dh)
                            
                    try: ws_rel = sh.worksheet("Relatorio_Inventario")
                    except: 
                        ws_rel = sh.add_worksheet(title="Relatorio_Inventario", rows="1000", cols="10")
                        ws_rel.append_row(["DOC_INV", "DATA", "USUARIO", "LOCAL_CONTADO", "QTD_ESPERADA", "CORRETAS", "CORRIGIDAS", "FALTANTES"])
                    
                    cabs_rel = ws_rel.row_values(1)
                    if "DOC_INV" not in cabs_rel:
                        ws_rel.update_cell(1, len(cabs_rel)+1, "DOC_INV")
                        cabs_rel.append("DOC_INV")

                    try:
                        col_doc_idx = cabs_rel.index("DOC_INV") + 1
                        ids = [int(i) for i in ws_rel.col_values(col_doc_idx)[1:] if i.isdigit()]
                        n_doc = f"{(max(ids) + 1) if ids else 1:05d}"
                    except: n_doc = "00001"

                    nova_linha_rel = ["" for _ in range(len(cabs_rel))]
                    nova_linha_rel[cabs_rel.index("DOC_INV")] = n_doc
                    nova_linha_rel[cabs_rel.index("DATA")] = dh
                    nova_linha_rel[cabs_rel.index("USUARIO")] = st.session_state['usuario']
                    nova_linha_rel[cabs_rel.index("LOCAL_CONTADO")] = st.session_state['inv_local']
                    nova_linha_rel[cabs_rel.index("QTD_ESPERADA")] = len(esp)
                    nova_linha_rel[cabs_rel.index("CORRETAS")] = len(ok)
                    nova_linha_rel[cabs_rel.index("CORRIGIDAS")] = len(mov) + len(ext)
                    nova_linha_rel[cabs_rel.index("FALTANTES")] = len(nao_enc) + len(nao_aud)

                    ws_rel.append_row(nova_linha_rel)
                    
                    # ==============================================================
                    # MÁGICA DOS DETALHES DO INVENTÁRIO (ITEM A ITEM)
                    # ==============================================================
                    try: ws_itens = sh.worksheet("Inventario_Itens")
                    except:
                        ws_itens = sh.add_worksheet(title="Inventario_Itens", rows="1000", cols="10")
                        ws_itens.append_row(["DOC_INV", "DATA", "CODIGO", "DESCRICAO", "STATUS_CONTAGEM", "ENDERECO_FINAL", "AUDITOR"])
                    
                    linhas_detalhes = []
                    todos_envolvidos = list(set(esp + ext))
                    df_inv = df[df['CODIGO SAP'].isin(todos_envolvidos) | df['CÓDIGO ANTIGO'].isin(todos_envolvidos)]
                    
                    for _, r in df_inv.iterrows():
                        s = str(r.get('CODIGO SAP', '-')).strip()
                        a = str(r.get('CÓDIGO ANTIGO', '-')).strip()
                        cod_exibir = s if s != '-' else a
                        desc = str(r.get('DESCRIÇÃO', '-'))
                        loc = str(r.get('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)', '-'))
                        pos = str(r.get('POSIÇÃO GALPÃO', '-'))
                        end_final = f"{loc} ({pos})"
                        
                        if s in ok or a in ok: st_txt = "✅ Conforme"
                        elif s in mov or a in mov: st_txt = "🔄 Endereço Corrigido"
                        elif s in ext or a in ext: st_txt = "⭐ Extra (Achado)"
                        elif s in nao_enc or a in nao_enc or s in nao_aud or a in nao_aud: st_txt = "🚨 Faltante"
                        else: st_txt = "⚪ Indefinido"
                        
                        linhas_detalhes.append([n_doc, dh, cod_exibir, desc, st_txt, end_final, st.session_state['usuario']])
                        
                    if linhas_detalhes:
                        ws_itens.append_rows(linhas_detalhes)

                    st.cache_data.clear(); st.session_state['inv_ativo'] = False
                    st.success(f"✅ Doc.Inv. {n_doc} homologado com sucesso na nuvem com Detalhamento Item a Item!"); st.rerun()
                except Exception as e: st.error(f"Falha na homologação: {e}")

    with aba_hist:
        st.markdown("### 📜 Consultar Doc.Inv. (Relatório Gerencial)")
        try:
            sh = conectar_planilha()
            df_rel = pd.DataFrame(sh.worksheet("Relatorio_Inventario").get_all_records()).astype(str)
            df_rel.replace(["", "None", "nan", "NaN"], "-", inplace=True)
            
            # Tenta carregar a aba de itens para o detalhamento
            try:
                df_itens = pd.DataFrame(sh.worksheet("Inventario_Itens").get_all_records()).astype(str)
                df_itens.replace(["", "None", "nan", "NaN"], "-", inplace=True)
            except: df_itens = pd.DataFrame()
            
            if df_rel.empty: st.info("Sem registro de ciclos WMS.")
            else:
                c1, c2 = st.columns(2)
                with c1: f_dt = st.text_input("🔍 Localizar por Data ou Doc.Inv:")
                with c2: st.markdown("<br>", unsafe_allow_html=True); ap_desv = st.checkbox("Exibir unicamente protocolos com desvios")
                dfs = df_rel.copy()
                if f_dt: dfs = dfs[dfs.astype(str).apply(lambda x: x.str.upper().str.contains(f_dt.upper())).any(axis=1)]
                if ap_desv:
                    md = pd.Series(False, index=dfs.index)
                    if "CORRIGIDAS" in dfs.columns: md |= pd.to_numeric(dfs["CORRIGIDAS"], errors='coerce').fillna(0) > 0
                    if "FALTANTES" in dfs.columns: md |= pd.to_numeric(dfs["FALTANTES"], errors='coerce').fillna(0) > 0
                    dfs = dfs[md]
                
                # Mostra o resumo
                st.dataframe(dfs.iloc[::-1], use_container_width=True, hide_index=True)
                
                # Mostra o Detalhamento (Item a Item)
                if not df_itens.empty:
                    st.markdown("---")
                    st.markdown("### 🔍 Detalhamento do Inventário (Item a Item)")
                    doc_selecionado = st.selectbox("Selecione um Doc.Inv para ver o detalhamento completo:", [""] + dfs['DOC_INV'].tolist()[::-1])
                    if doc_selecionado != "":
                        df_itens_doc = df_itens[df_itens['DOC_INV'] == doc_selecionado]
                        if not df_itens_doc.empty:
                            # Ordena para os Faltantes e Corrigidos ficarem no topo da lista visualmente
                            df_itens_doc.sort_values(by='STATUS_CONTAGEM', ascending=False, inplace=True)
                            st.dataframe(df_itens_doc, use_container_width=True, hide_index=True)
                        else:
                            st.warning("Detalhes não encontrados para este documento.")
        except: st.warning("Estrutura do relatório WMS indisponível.")

def tela_administrador():
    cabecalho_weg()
    st.markdown("#### Painel de Gestão (Root)")
    if st.session_state['nivel_id'] != "0": return st.error("🔒 Restrito a credenciais corporativas Nível 0.")

    aba_novo, aba_desc, aba_user, aba_email = st.tabs(["➕ Homologar Peça Mestra", "🗑️ Descomissionar Peça", "👥 Matriz de Usuários", "✉️ Config. Alertas"])

    with aba_email:
        st.markdown("Defina os e-mails padronizados que receberão as notificações de **Nova Solicitação** (separados por ponto-e-vírgula).")
        atual_emails = carregar_emails_config()
        with st.form("form_config_email"):
            emails_input = st.text_input("E-mails de Notificação Padrão:", value=atual_emails, placeholder="exemplo1@weg.net; exemplo2@weg.net")
            if st.form_submit_button("💾 Salvar Configuração na Nuvem", type="primary"):
                try:
                    sh = conectar_planilha()
                    try: ws_cfg = sh.worksheet("Config")
                    except: 
                        ws_cfg = sh.add_worksheet("Config", 10, 2)
                        ws_cfg.update_cell(1, 1, "EMAILS_ALERTA")
                        
                    ws_cfg.update_cell(2, 1, emails_input.strip())
                    st.cache_data.clear()
                    st.success("✅ E-mails de alerta configurados com sucesso!")
                except Exception as e: st.error(f"Erro ao salvar: {e}")

    with aba_novo:
        with st.form("form_novo_modelo", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                n_sap = st.text_input("Código SAP:")
                n_antigo = st.text_input("Código Legado:")
                n_pai = st.text_input("Cód. Estrutural Pai:")
                n_desc = st.text_input("Nomenclatura (Obrigatório):")
                n_desenho = st.text_input("Ref. Desenho Técnico:")
            with col2:
                n_local = st.selectbox("Setor Alocado (Obrigatório):", ["GALPÃO", "FUNDIÇÃO", "MODELAÇÃO"])
                n_pos = st.text_input("Slot (Pátio/Prateleira):")
                n_tipo_mov = st.selectbox("Linha de Equipamento:", ["TURBINA", "REDUTOR", "AMBOS", "OUTRO"])
                n_equip = st.text_input("Denominação do Equipamento:")
            with col3:
                n_tipo = st.text_input("Categoria (Modelo/Composto):")
                n_valor = st.text_input("Valor Contábil:")
                n_caixa = st.text_input("Caixote/Acondicionamento:")
                n_obs = st.text_input("Anotação Complementar:")

            if st.form_submit_button("💾 Escrever no Banco de Dados Cloud", type="primary"):
                if not n_sap.strip() and not n_antigo.strip(): st.warning("Exigência mínima de rastreio falhou.")
                elif not n_desc.strip(): st.warning("Nomenclatura inválida.")
                else:
                    try:
                        sh = conectar_planilha()
                        ws_base = sh.worksheet("Base")
                        cabs = ws_base.row_values(1)
                        
                        data_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        nova_linha = ["" for _ in range(len(cabs))]
                        
                        def ins(nome_col, valor):
                            if nome_col in cabs: nova_linha[cabs.index(nome_col)] = valor
                            
                        ins('CÓDIGO ANTIGO', n_antigo.upper()); ins('CODIGO SAP', n_sap.upper()); ins('CÓDIGO PAI', n_pai.upper())
                        ins('DESENHO', n_desenho.upper()); ins('DESCRIÇÃO', n_desc.upper()); ins('TIPO (MODELO OU COMPOSTO)', n_tipo.upper())
                        ins('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)', n_local.upper()); ins('POSIÇÃO GALPÃO', n_pos.upper())
                        ins('VALOR', n_valor); ins('TURBINA OU REDUTOR?', n_tipo_mov.upper()); ins('MODELO EQUIPAMENTO', n_equip.upper())
                        ins('CAIXA', n_caixa); ins('ÚLTIMA MOVIMENTAÇÃO', data_agora); ins('OBSERVAÇÃO', n_obs)
                        
                        ws_base.append_row(nova_linha)
                        
                        try:
                            ws_hist = sh.worksheet("Historico")
                            ws_hist.append_row([data_agora, st.session_state['usuario'], f"{n_sap} / {n_antigo}", "CADASTRO NOVO", "", f"{n_local.upper()} ({n_pos.upper()})", ""])
                        except: pass
                        
                        st.cache_data.clear(); st.success("✅ Matriz de dados sincronizada na nuvem.")
                    except Exception as e: st.error(f"Erro: {e}")

    with aba_desc:
        df = carregar_base()
        if not df.empty:
            cod_desc = st.text_input("Código do Ativo a ser Descomissionado:").strip().upper()
            if cod_desc:
                f_desc = df[(df['CODIGO SAP'].astype(str).str.upper() == cod_desc) | (df['CÓDIGO ANTIGO'].astype(str).str.upper() == cod_desc)]
                if f_desc.empty: st.warning("Ativo inativo ou inexistente.")
                else:
                    pd_desc = f_desc.iloc[0]
                    st.error(f"⚠️ Atenção, fluxo irreversível na área operacional para: **{pd_desc.get('DESCRIÇÃO','-')}**")
                    with st.form("form_descarte"):
                        motivo = st.text_input("Laudo Técnico / Motivo:")
                        if st.form_submit_button("🗑️ Descomissionar na Nuvem", type="primary"):
                            if not motivo.strip(): st.warning("Laudo Técnico exigido.")
                            else:
                                try:
                                    sh = conectar_planilha()
                                    ws_base = sh.worksheet("Base")
                                    dados_completos = ws_base.get_all_values()
                                    cabecalhos = dados_completos[0]
                                    col_sap = cabecalhos.index('CODIGO SAP')
                                    col_ant = cabecalhos.index('CÓDIGO ANTIGO')
                                    
                                    linha_alvo = None
                                    for i, linha in enumerate(dados_completos[1:], start=2):
                                        vs = str(linha[col_sap]).strip().upper() if len(linha) > col_sap else ""
                                        va = str(linha[col_ant]).strip().upper() if len(linha) > col_ant else ""
                                        if cod_desc in [vs, va] and cod_desc != "": linha_alvo = i; break
                                    
                                    if linha_alvo:
                                        dh = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                        loc_atual = dados_completos[linha_alvo-1][cabecalhos.index('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)')]
                                        pos_atual = dados_completos[linha_alvo-1][cabecalhos.index('POSIÇÃO GALPÃO')]
                                        
                                        ws_base.update_cell(linha_alvo, cabecalhos.index('ÚLTIMO LOCAL QUE ESTEVE')+1, f"{loc_atual} ({pos_atual})")
                                        ws_base.update_cell(linha_alvo, cabecalhos.index('LOCAL ARMAZENADO (GALPÃO / FUNDIÇÃO / MODELAÇÃO)')+1, "DESCARTADO")
                                        ws_base.update_cell(linha_alvo, cabecalhos.index('OBSERVAÇÃO')+1, f"SUCATA: {motivo}")
                                        ws_base.update_cell(linha_alvo, cabecalhos.index('ÚLTIMA MOVIMENTAÇÃO')+1, dh)
                                        
                                        try:
                                            ws_hist = sh.worksheet("Historico")
                                            ws_hist.append_row([dh, st.session_state['usuario'], cod_desc, "DESCARTADO/SUCATEADO", "", "", motivo])
                                        except: pass
                                        
                                        st.cache_data.clear(); st.rerun()
                                except Exception as e: st.error(f"Erro: {e}")

    with aba_user:
        try:
            sh = conectar_planilha()
            ws_u = sh.worksheet("Usuarios")
            df_u = pd.DataFrame(ws_u.get_all_records()).astype(str)
            df_u.replace(["", "None", "nan", "NaN"], "-", inplace=True)
            
            c_u1, c_u2 = st.columns(2)
            with c_u1:
                st.dataframe(df_u[['USUARIO', 'NIVEL_ACESSO']], hide_index=True, use_container_width=True)
                with st.form("form_novo_user", clear_on_submit=True):
                    st.subheader("Emitir Credencial")
                    u_nome = st.text_input("Registro LDAP (Rede):").strip().upper()
                    st.caption("A matriz inicial será a chave corporativa **1234**.")
                    u_nivel = st.selectbox("Grupo de Políticas:", ["1 - Almoxarifado (Executar)", "2 - Compras (Solicitar)", "0 - Administrador (Total)"])
                    if st.form_submit_button("Protocolar Admissão Cloud"):
                        if not u_nome: st.warning("LDAP nulo.")
                        else:
                            try:
                                nv = u_nivel.split(" -")[0]
                                ws_u.append_row([u_nome, "1234", nv])
                                st.success("Credencial gravada na nuvem.")
                                st.rerun()
                            except Exception as e: st.error(f"Erro: {e}")
            with c_u2:
                user_edit = st.selectbox("Apontar Credencial:", df_u['USUARIO'].tolist())
                cb1, cb2 = st.columns(2)
                with cb1:
                    if st.button("🔑 Forçar Chave Padrão", use_container_width=True):
                        try:
                            usuarios_dados = ws_u.get_all_values()
                            for i, linha in enumerate(usuarios_dados[1:], start=2):
                                if str(linha[0]).strip().upper() == user_edit:
                                    ws_u.update_cell(i, 2, "1234")
                                    st.success(f"Log {user_edit} sobrescrito para 1234 na nuvem.")
                                    break
                        except Exception as e: st.error(f"Erro: {e}")
                with cb2:
                    if st.button("🚫 Revogar Acesso", use_container_width=True):
                        if user_edit == st.session_state['usuario']: st.error("Falha: Auto-revogação negada.")
                        else:
                            try:
                                usuarios_dados = ws_u.get_all_values()
                                for i, linha in enumerate(usuarios_dados[1:], start=2):
                                    if str(linha[0]).strip().upper() == user_edit:
                                        ws_u.delete_rows(i)
                                        st.success("Log revogado na raiz."); st.rerun()
                                        break
                            except Exception as e: st.error(f"Erro: {e}")
        except: st.error("Base de credenciais indisponível.")

# ==========================================
# FLUXO PRINCIPAL DO APLICATIVO E MENU
# ==========================================
if not st.session_state['logado']: tela_login()
else:
    st.sidebar.markdown('<style>section[data-testid="stSidebar"] div[data-testid="stText"] { display: none; }</style>', unsafe_allow_html=True)
    st.sidebar.markdown(f"**Matrícula:** {st.session_state['usuario']}")
    st.sidebar.caption(f"Acesso: {st.session_state['nivel']}")
    st.sidebar.markdown("---")
    
    opcoes_menu = ["🏠 Dashboard", "🔍 Localizar Material", "📥 Emissão de Tickets", "📜 Logs de Auditoria", "📋 Rotina WMS"]
    if st.session_state['nivel_id'] in ["0", "1"]: opcoes_menu.insert(2, "🔄 Movimentação Fís.") 
    if st.session_state['nivel_id'] == "0": opcoes_menu.append("⚙️ Painel Root")

    aba_atual = st.session_state.get('menu_lateral_nav')
    if aba_atual not in opcoes_menu: st.session_state['menu_lateral_nav'] = "🏠 Dashboard"

    menu_selecionado = st.sidebar.radio("Navegação Estrutural:", opcoes_menu, key="menu_lateral_nav")
    st.sidebar.markdown("---")
    
    with st.sidebar.expander("🔑 Minhas Credenciais"):
        n_senha = st.text_input("Nova Chave de Segurança:", type="password")
        c_senha = st.text_input("Validar Chave:", type="password")
        if st.button("Gravar Mudança", use_container_width=True):
            if not n_senha or not c_senha: st.warning("Entrada requerida.")
            elif n_senha != c_senha: st.error("Desvio na checagem.")
            else:
                try:
                    sh = conectar_planilha()
                    ws_u = sh.worksheet("Usuarios")
                    usuarios_dados = ws_u.get_all_values()
                    for i, linha in enumerate(usuarios_dados[1:], start=2):
                        if str(linha[0]).strip().upper() == st.session_state['usuario']:
                            ws_u.update_cell(i, 2, n_senha)
                            st.success("Sucesso corporativo na nuvem!")
                            break
                except Exception as e: st.error(f"Erro: {e}")

    if st.sidebar.button("🚪 Desconectar", use_container_width=True): st.session_state.clear(); st.rerun()

    if menu_selecionado == "🏠 Dashboard": tela_geral()
    elif menu_selecionado == "🔍 Localizar Material": tela_consulta()
    elif menu_selecionado == "🔄 Movimentação Fís.": tela_modificar()
    elif menu_selecionado == "📥 Emissão de Tickets": tela_solicitacoes()
    elif menu_selecionado == "📜 Logs de Auditoria": tela_historico()
    elif menu_selecionado == "📋 Rotina WMS": tela_inventario()
    elif menu_selecionado == "⚙️ Painel Root": tela_administrador()
