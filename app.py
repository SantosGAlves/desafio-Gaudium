from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import threading
import httpx
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime, timezone
import random
import string

load_dotenv()

app = Flask(__name__)
app.secret_key = 'gaudium_super_secreta_2026' 

url: str = os.environ.get("SUPABASE_URL") or ""
key: str = os.environ.get("SUPABASE_KEY") or ""
n8n_url: str = os.environ.get("N8N_WEBHOOK_URL") or ""
supabase: Client = create_client(url, key) if url and key else None

def disparar_n8n(evento, ticket_data):
    if not n8n_url: return
    def enviar():
        try:
            httpx.post(n8n_url, json={"evento": evento, "timestamp": datetime.now(timezone.utc).isoformat(), "ticket": ticket_data}, timeout=5.0)
        except Exception as e:
            print(f"Erro ao comunicar com n8n: {e}")
    threading.Thread(target=enviar).start()

@app.route('/')
def index():
    if 'usuario_id' not in session: return redirect(url_for('login_page'))
    return render_template('index.html', usuario_logado=session.get('usuario_nome'), usuario_dept=session.get('usuario_dept'), is_admin=session.get('is_admin'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def fazer_login():
    try:
        dados = request.json
        email_login = dados.get('email').lower().strip()
        auth_response = supabase.auth.sign_in_with_password({"email": email_login, "password": dados.get('senha')})
        
        perfil_response = supabase.table('usuarios').select('*').ilike('email', email_login).execute()
        
        nome = email_login.split('@')[0]
        dept = 'Geral'
        is_admin = False
        
        if len(perfil_response.data) > 0:
            nome = perfil_response.data[0]['nome']
            dept = perfil_response.data[0]['departamento']
            is_admin = perfil_response.data[0].get('is_admin', False)
            
        session['usuario_id'] = auth_response.user.id
        session['usuario_nome'] = nome
        session['usuario_dept'] = dept
        session['usuario_email'] = email_login 
        session['is_admin'] = is_admin # <-- NOVA LÓGICA DE ADMIN AQUI
        
        return jsonify({"status": "sucesso", "mensagem": "Bem-vindo!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": "E-mail ou senha incorretos."}), 401
    
@app.route('/api/recuperar-senha', methods=['POST'])
def recuperar_senha():
    try:
        dados = request.json
        email = dados.get('email')
        if not email: return jsonify({"status": "erro", "mensagem": "E-mail não fornecido."}), 400
        supabase.auth.reset_password_email(email)
        return jsonify({"status": "sucesso", "mensagem": "Se o e-mail existir na nossa base, receberá um link em instantes."})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
@app.route('/nova-senha')
def nova_senha_page():
    return render_template('nova-senha.html')

@app.route('/api/atualizar-senha', methods=['POST'])
def atualizar_senha():
    try:
        dados = request.json
        token = dados.get('access_token')
        nova_senha = dados.get('senha')
        if not token: return jsonify({"status": "erro", "mensagem": "Link inválido ou expirado."}), 400
        supabase.auth.set_session(token, "")
        supabase.auth.update_user({"password": nova_senha})
        supabase.auth.sign_out()
        return jsonify({"status": "sucesso"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def fazer_logout():
    session.clear() 
    return jsonify({"status": "sucesso"})

@app.route('/api/demandas', methods=['GET'])
def get_demandas():
    if 'usuario_id' not in session: return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 401
    try:
        response = supabase.table('demandas').select("*").order('created_at', desc=True).execute()
        dados = response.data
        
        usuario_dept = session.get('usuario_dept')
        nome_usuario = session.get('usuario_nome')
        is_admin = session.get('is_admin', False)

        if request.args.get('meus') == 'true':
            dados = [d for d in dados if d.get('solicitante') == nome_usuario]
        else:
            if not is_admin: # <-- ADMINS VEEM TUDO NO KANBAN
                dados = [d for d in dados if d.get('departamento') == usuario_dept]
            
        return jsonify({"status": "sucesso", "dados": dados})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/demandas', methods=['POST'])
def criar_demanda():
    if 'usuario_id' not in session: return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 401
    try:
        dados = request.json
        nova_demanda = {
            "setor_solicitante": session.get('usuario_dept'),
            "email_solicitante": session.get('usuario_email'),
            "titulo": dados.get('titulo'),
            "descricao": dados.get('descricao'),
            "prioridade": dados.get('prioridade'),
            "solicitante": session.get('usuario_nome'),
            "departamento": dados.get('departamento'),
            "prazo": dados.get('prazo'),
            "status": "entrada",
            "status_execucao": "pausado",
            "historico": ""
        }
        response = supabase.table('demandas').insert(nova_demanda).execute()
        disparar_n8n("novo_ticket", response.data[0])
        return jsonify({"status": "sucesso", "dados": response.data}), 201
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/demandas/<string:id>', methods=['PATCH'])
def atualizar_status(id):
    if 'usuario_id' not in session: return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 401
    try:
        dados = request.json
        atualizacao = {}
        ticket_atual = supabase.table('demandas').select('*').eq("id", id).execute().data[0]

        usuario_dept = session.get('usuario_dept', '').upper()
        dept_destino = (ticket_atual.get('departamento') or '').upper()
        is_admin = session.get('is_admin', False)
        
        is_apenas_historico = ('novo_historico' in dados and len(dados) == 1)
        
        # <-- SEGURANÇA BASEADA NO STATUS DE ADMIN
        if not is_admin and usuario_dept != dept_destino and not is_apenas_historico:
            return jsonify({"status": "erro", "mensagem": "Acesso Negado: Apenas a área de destino pode assumir ou alterar este chamado."}), 403

        def calcular_tempo_pendente():
            if ticket_atual.get('hora_inicio'):
                inicio = datetime.fromisoformat(ticket_atual['hora_inicio'].replace('Z', '+00:00'))
                return int((datetime.now(timezone.utc) - inicio).total_seconds() / 60)
            return 0

        evento_n8n = None
        if 'status' in dados:
            novo_status = dados.get('status')
            atualizacao['status'] = novo_status
            if novo_status == 'andamento':
                atualizacao['responsavel'] = session.get('usuario_nome')
                atualizacao['status_execucao'] = 'play'
                atualizacao['hora_inicio'] = datetime.now(timezone.utc).isoformat()
                if ticket_atual.get('status') != 'andamento': evento_n8n = "ticket_assumido"
            elif novo_status in ['pausado', 'concluido']:
                atualizacao['status_execucao'] = 'pausado'
                atualizacao['tempo_gasto'] = ticket_atual.get('tempo_gasto', 0) + calcular_tempo_pendente()
                atualizacao['hora_inicio'] = None
                if novo_status == 'concluido': evento_n8n = "ticket_concluido"
        
        elif 'status_execucao' in dados:
            execucao = dados.get('status_execucao')
            atualizacao['status_execucao'] = execucao
            if execucao == 'play':
                atualizacao['status'] = 'andamento'
                atualizacao['responsavel'] = session.get('usuario_nome')
                atualizacao['hora_inicio'] = datetime.now(timezone.utc).isoformat()
            elif execucao == 'pausado':
                atualizacao['status'] = 'pausado'
                atualizacao['tempo_gasto'] = ticket_atual.get('tempo_gasto', 0) + calcular_tempo_pendente()
                atualizacao['hora_inicio'] = None

        if 'novo_historico' in dados:
            hist_antigo = ticket_atual.get('historico', '') or ''
            atualizacao['historico'] = hist_antigo + f"• {session.get('usuario_nome')}: {dados.get('novo_historico')}\n"

        response = supabase.table('demandas').update(atualizacao).eq("id", id).execute()
        if evento_n8n: disparar_n8n(evento_n8n, response.data[0])
        return jsonify({"status": "sucesso", "dados": response.data})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/demandas/<string:id>', methods=['DELETE'])
def deletar_demanda(id):
    if not session.get('is_admin'): return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 403
    try:
        supabase.table('demandas').delete().eq("id", id).execute()
        return jsonify({"status": "sucesso"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/admin/usuarios', methods=['POST'])
def criar_usuario():
    if not session.get('is_admin'): return jsonify({"status": "erro", "mensagem": "Não autorizado"}), 403
    dados = request.json
    try:
        senha_temporaria = ''.join(random.choices(string.ascii_letters + string.digits, k=8)) + "@"
        auth_response = supabase.auth.admin.create_user({
            "email": dados.get('email'), "password": senha_temporaria, "email_confirm": True
        })
        perfil = {
            "nome": dados.get('nome'), "email": dados.get('email'),
            "departamento": dados.get('departamento'), "is_admin": dados.get('is_admin', False)
        }
        supabase.table('usuarios').insert(perfil).execute()
        return jsonify({"status": "sucesso", "senha_temp": senha_temporaria})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
@app.route('/api/admin/usuarios', methods=['GET'])
def get_usuarios():
    if not session.get('is_admin'): return jsonify({"status": "erro"}), 403
    response = supabase.table('usuarios').select('*').order('nome').execute()
    return jsonify({"status": "sucesso", "dados": response.data})

# ROTA NOVA: Ligar e Desligar o status de Admin de um usuário
@app.route('/api/admin/usuarios/<string:email>', methods=['PATCH'])
def toggle_admin_usuario(email):
    if not session.get('is_admin'): return jsonify({"status": "erro"}), 403
    try:
        novo_status = request.json.get('is_admin')
        supabase.table('usuarios').update({"is_admin": novo_status}).eq("email", email).execute()
        return jsonify({"status": "sucesso"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/admin/usuarios/<string:email>', methods=['DELETE'])
def deletar_usuario(email):
    if not session.get('is_admin'): return jsonify({"status": "erro"}), 403
    try:
        try:
            users = supabase.auth.admin.list_users()
            user = next((u for u in users.users if u.email == email), None)
            if user: supabase.auth.admin.delete_user(user.id)
        except Exception as auth_err:
            pass
        supabase.table('usuarios').delete().eq("email", email).execute()
        return jsonify({"status": "sucesso"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)